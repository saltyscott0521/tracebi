"""Generate the calc-plan parity fixtures: tests/fixtures/calc_parity/<case>.json.

Each fixture is one binding as the page sees it: the slice the build would
embed for its fact, the plan ``compile_plan`` makes for it, a selection, and
the rows DuckDB returns for the same query under that selection (through
``DataModel.execute`` on the full model), passed through the fingerprint
rounding rule. The page engine (tracebi-calc.js) must reproduce ``expected``
from ``slice`` + ``plan`` + ``selection`` alone; tests/test_calc_plan.py
checks that Python's own reading of the plan (``execute_plan``) does.

The reference cases use the reference project's model as declared
(examples/portfolio_project/models/portfolio_model.yaml) over a small,
fixed holdings book defined here, so the fixtures need no warehouse. The
two-fact cases use a tiny model of their own, since the reference model has
one fact.

    python scripts/gen_calc_parity.py [--out DIR]

The output is deterministic: running it again writes the same bytes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tracebi import DataModel, MemoryConnector  # noqa: E402
from tracebi.model.data_model import QuerySpec  # noqa: E402
from tracebi.model.dataset import canonical_rows  # noqa: E402
from tracebi.model.model_spec import load_model_spec  # noqa: E402
from tracebi.reports.calc_plan import (  # noqa: E402
    apply_selection,
    compile_plan,
    selection_query,
)

OUT = ROOT / "tests" / "fixtures" / "calc_parity"
PROJECT = ROOT / "examples" / "portfolio_project"

_SECTORS = ["Software", "Healthcare", "Energy", "Industrials", None]


def _holdings_book() -> dict[str, pd.DataFrame]:
    """Three funds, ten issuers (one with no sector), twenty-four positions.

    Money has cents so float sums differ in the last bits by summation order,
    which is what the rounding rule is for. Two issuers tie on total fair
    value (the window and order_by tie-breaks), and one position has no
    spread (count and percentiles skip nulls).
    """
    funds = pd.DataFrame({"fund_id": [1, 2, 3],
                          "fund": ["Fund I", "Fund II", "Fund III"]})
    issuers = pd.DataFrame({
        "issuer_id": list(range(1, 11)),
        "issuer": ["Acme", "Birch", "Cobalt", "Delta", "Ember",
                   "Falcon", "Garnet", "Harbor", "Iris", "Juniper"],
        "sector": [_SECTORS[i % 5] for i in range(10)],
    })
    rows = []
    for h in range(1, 25):
        issuer = (h * 7) % 10 + 1
        fund = h % 3 + 1
        par = 1_000_000.0 + 250_000.0 * ((h * 5) % 9)
        cost = round(par * (0.97 + 0.004 * (h % 6)), 2)
        fair = round(cost * (0.93 + 0.0123 * ((h * 3) % 11)) + 0.07 * h, 2)
        spread = None if h == 11 else float(300 + 25 * ((h * 13) % 17))
        rows.append((h, fund, issuer, par, cost, fair, spread))
    holdings = pd.DataFrame(rows, columns=["holding_id", "fund_id", "issuer_id",
                                           "par", "cost", "fair_value",
                                           "spread_bps"])
    # The tie: Ember's positions total exactly what Juniper's do. Both are
    # whole quarters, which binary floats hold exactly, so the totals tie in
    # any summation order and the tie-break, not the last bits, decides.
    ember = holdings["issuer_id"] == 5
    juniper = holdings["issuer_id"] == 10
    holdings.loc[ember | juniper, "fair_value"] = (
        holdings.loc[ember | juniper, "fair_value"] * 4).round() / 4
    first = holdings.index[ember][0]
    holdings.loc[first, "fair_value"] += (
        holdings.loc[juniper, "fair_value"].sum()
        - holdings.loc[ember, "fair_value"].sum())
    return {"fact_holdings": holdings, "dim_fund": funds, "dim_issuer": issuers}


def reference_model() -> DataModel:
    """The reference model's declarations over the fixed book."""
    model = load_model_spec(PROJECT / "models" / "portfolio_model.yaml", root=PROJECT)
    model.add_connector(MemoryConnector("warehouse", tables=_holdings_book()))
    model.connect()
    return model


def two_fact_model() -> DataModel:
    """Two facts sharing dim_fund and dim_date; only holdings reach dim_issuer.

    Months are string labels, as a slice carries a time grain, so a range
    selection over them compares labels on both sides.
    """
    funds = pd.DataFrame({"fund_id": [1, 2], "fund": ["Fund I", "Fund II"]})
    issuers = pd.DataFrame({"issuer_id": [1, 2, 3],
                            "sector": ["Software", "Energy", "Software"]})
    dates = pd.DataFrame({"date_id": [1, 2, 3, 4],
                          "month": ["2026-01", "2026-02", "2026-03", "2026-04"]})
    holdings = pd.DataFrame({
        "holding_id": list(range(1, 13)),
        "fund_id":    [1, 2] * 6,
        "issuer_id":  [1, 2, 3] * 4,
        "date_id":    [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4],
        "fair_value": [101.25, 202.5, 303.75, 99.1, 198.2, 297.3,
                       120.0, 240.01, 360.02, 80.5, 161.0, 241.5],
    })
    cashflows = pd.DataFrame({
        "flow_id": list(range(1, 9)),
        "fund_id": [1, 2, 1, 2, 1, 2, 1, 2],
        "date_id": [1, 1, 2, 2, 3, 3, 4, 4],
        "amount":  [10.5, -4.25, 12.0, 3.3, -7.75, 8.0, 6.1, -2.2],
    })
    m = DataModel("two_fact_model")
    m.add_connector(MemoryConnector("two_fact", tables={
        "holdings": holdings, "cashflows": cashflows, "funds": funds,
        "issuers": issuers, "dates": dates}))
    for t in ("holdings", "cashflows", "funds", "issuers", "dates"):
        m.add_table(t, connector="two_fact", source=t)
    m.add_dimension("dim_fund", table_name="funds", key_col="fund_id",
                    attributes=["fund"])
    m.add_dimension("dim_issuer", table_name="issuers", key_col="issuer_id",
                    attributes=["sector"])
    m.add_dimension("dim_date", table_name="dates", key_col="date_id",
                    attributes=["month"])
    m.add_fact("fact_holdings", table_name="holdings", measures=["fair_value"],
               foreign_keys={"dim_fund": "fund_id", "dim_issuer": "issuer_id",
                             "dim_date": "date_id"})
    m.add_fact("fact_cashflows", table_name="cashflows", measures=["amount"],
               foreign_keys={"dim_fund": "fund_id", "dim_date": "date_id"})
    m.add_measure("fair_value", column="fair_value", agg="sum")
    m.add_measure("net_flow", column="amount", agg="sum")
    m.add_measure("flows", column="flow_id", agg="count")
    m.connect()
    return m


# ── Slices ───────────────────────────────────────────────────

def base_slice(model: DataModel, fact: str, dims: list[str],
               columns: list[str]) -> pd.DataFrame:
    """One row per fact row: the fact columns plus the dimension attributes."""
    spec = QuerySpec(fact=fact, measures={c: "sum" for c in columns},
                     dimensions=tuple(dims), aggregate=False)
    return model.execute(spec).to_pandas()


def parts_slice(model: DataModel, fact: str, grain: list[str],
                parts: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """The fact pre-aggregated at *grain*: one ``<measure>:<part>`` column each."""
    spec = QuerySpec(fact=fact, measures=dict(parts), dimensions=tuple(grain),
                     allow_rate_agg=True)
    return model.execute(spec).to_pandas()


_HOLDING_DIMS = ["dim_fund.fund", "dim_issuer.issuer", "dim_issuer.sector"]
_HOLDING_COLS = ["holding_id", "fund_id", "issuer_id", "par", "cost",
                 "fair_value", "spread_bps"]
_PARTS = {
    "fair_value:sum": ("fair_value", "sum"),
    "positions:count": ("holding_id", "count"),
    "cost_basis:sum": ("cost", "sum"),
    "avg_spread:sum": ("spread_bps", "sum"),
    "avg_spread:count": ("spread_bps", "count"),
    "max_par:max": ("par", "max"),
}
_AVG_SPREAD = {"avg_spread": {"column": "spread_bps", "agg": "mean",
                              "allow_rate_agg": True}}

SECTOR_SEL = {"dim_issuer.sector": ["Software", "Healthcare"]}
FUND_SEL = {"dim_fund.fund": ["Fund I", "Fund III"]}


def _q(measures, dims=(), **kw) -> dict:
    return {"fact": "fact_holdings", "measures": measures,
            "dimensions": list(dims), **kw}


def _pair(name: str, about: str, query: dict, selection: dict) -> list:
    """A case without a selection and the same case with one."""
    return [(name, about, query, {}),
            (f"{name}_selected", about + " Under a selection.", query, selection)]


def reference_cases() -> list[tuple[str, str, dict, dict]]:
    by_sector, by_fund, by_issuer = (["dim_issuer.sector"], ["dim_fund.fund"],
                                     ["dim_issuer.issuer"])
    return [
        *_pair("total", "A value figure: two sums and a count, no groups.",
               _q(["fair_value", "cost_basis", "positions"]), SECTOR_SEL),
        ("total_empty", "A selection nothing matches: one row, null sum, zero "
         "count.", _q(["fair_value", "positions"]),
         {"dim_issuer.sector": ["No such sector"]}),
        *_pair("sum_by_sector", "sum by a group with a null member (sorts last).",
               _q(["fair_value"], by_sector), FUND_SEL),
        *_pair("count", "count of a column with a null (counts non-null only).",
               _q({"holding_id": "count", "spread_bps": "count"}, by_fund),
               SECTOR_SEL),
        *_pair("mean", "mean, compiled as sum and count parts the page divides.",
               _q(["avg_spread"], by_sector, calculated=_AVG_SPREAD), FUND_SEL),
        *_pair("min_max", "min and max.",
               _q({"par": "min", "fair_value": "max"}, by_fund), SECTOR_SEL),
        *_pair("nunique", "nunique: distinct non-null values.",
               _q({"issuer_id": "nunique"}, by_fund), SECTOR_SEL),
        *_pair("percentile", "p90 (declared), p50 and median: quantile_cont.",
               _q(["spread_p90", "spread_p50", "spread_median"], by_sector,
                  calculated={
                      "spread_p50": {"column": "spread_bps", "agg": "p50"},
                      "spread_median": {"column": "spread_bps", "agg": "median"}}),
               FUND_SEL),
        *_pair("derived", "Row expressions over fact columns, then summed.",
               _q(["unrealized", "spread_x_par"], by_fund), SECTOR_SEL),
        *_pair("ratio", "Ratios of totals (their parts are result columns too).",
               _q(["wtd_spread_bps", "mark"], by_sector), FUND_SEL),
        *_pair("share", "share of the result's total.",
               _q(["fv_share"], by_sector), FUND_SEL),
        *_pair("rank", "rank by fair value, a tie broken by the group column.",
               _q(["fv_rank"], by_issuer), FUND_SEL),
        *_pair("running", "running share, largest first.",
               _q(["fv_cum_share"], by_issuer), FUND_SEL),
        *_pair("partitioned_rank", "Top two issuers per sector: a rank within "
               "each sector and a having on it.",
               _q(["fair_value", "fv_rank_in_sector"],
                  ["dim_issuer.sector", "dim_issuer.issuer"],
                  having={"fv_rank_in_sector": {"lte": 2}}), FUND_SEL),
        *_pair("having", "having on an aggregate, after aggregation.",
               _q(["fair_value", "positions"], by_issuer,
                  having={"fair_value": {"gte": 2500000}}), FUND_SEL),
        ("order", "order_by a measure descending; the tie falls back to the "
         "group column.", _q(["fair_value"], by_issuer,
                             order_by=[{"column": "fair_value", "desc": True}]), {}),
        *_pair("order_limit", "Top three by fair value: order_by and limit.",
               _q(["fair_value"], by_issuer,
                  order_by=[{"column": "fair_value", "desc": True}], limit=3),
               SECTOR_SEL),
        ("filter_narrowed", "The binding filters two sectors; the selection "
         "names one of them and another: only the overlap remains.",
         _q(["fair_value"], by_sector,
            filters={"dim_issuer.sector": ["Software", "Healthcare"],
                     "par": {"gte": 1250000}}),
         {"dim_issuer.sector": ["Healthcare", "Energy"]}),
        *_pair("calculated", "Per-query calculated measures: a filtered "
               "measure and arithmetic over measures.",
               _q(["fair_value", "large_fv", "fv_less_cost"], by_sector,
                  calculated={
                      "large_fv": {"column": "fair_value", "agg": "sum",
                                   "filters": {"par": {"gte": 2000000}}},
                      "fv_less_cost": {"measure_expr": "fair_value - cost_basis"}}),
               FUND_SEL),
        ("range_selected", "A range selection on a numeric fact column.",
         _q(["fair_value", "positions"], by_sector),
         {"par": {"gte": 1500000, "lt": 2500000}}),
    ]


def parts_cases() -> list[tuple[str, str, dict, dict]]:
    query = _q(["fair_value", "positions", "mark", "fv_share", "fv_rank",
                "avg_spread", "max_par"], ["dim_issuer.sector"],
               calculated={**_AVG_SPREAD,
                           "max_par": {"column": "par", "agg": "max"}})
    kpi = _q(["fair_value", "positions", "avg_spread"], calculated=_AVG_SPREAD)
    about = ("A slice pre-aggregated at (sector, fund): sums and counts "
             "re-aggregate, the mean divides its parts.")
    return [
        *_pair("parts", about, query, FUND_SEL),
        ("parts_empty", about + " No rows match: the count part stays 0.",
         kpi, {"dim_fund.fund": ["No such fund"]}),
    ]


TWO_FACT_SEL = {"dim_fund.fund": ["Fund I"],
                "dim_issuer.sector": ["Software"],
                "dim_date.month": {"gte": "2026-02", "lte": "2026-03"}}


# ── Writing ──────────────────────────────────────────────────

def _type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    return "string"


def _cell(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value) if abs(value) < 2 ** 53 else value
    return value


def _slice_json(fact: str, frame: pd.DataFrame) -> dict:
    return {"fact": fact,
            "columns": [{"name": str(c), "type": _type(frame[c])}
                        for c in frame.columns],
            "rows": [[_cell(v) for v in row]
                     for row in frame.itertuples(index=False, name=None)]}


def fixture(model, name: str, about: str, query: dict, selection: dict,
            frame: pd.DataFrame) -> dict:
    spec = QuerySpec.from_dict(query)
    sl = _slice_json(spec.fact, frame)
    plan = compile_plan(model, spec, sl["columns"])
    if "fixed" in plan:
        raise SystemExit(f"{name}: the plan is fixed: {plan['fixed']}")
    applied = apply_selection(plan, selection)
    result = model.execute(selection_query(spec, applied)).to_pandas()
    cols, rows = canonical_rows(result, total_order=False)
    return {
        "case": name,
        "about": about,
        "model": model.name,
        "query": spec.to_dict(),
        "slice": sl,
        "plan": plan,
        "selection": selection,
        "expected": {"cols": cols, "rows": rows,
                     "unfiltered_by": applied["unfiltered_by"]},
    }


def build() -> dict[str, dict]:
    out: dict[str, dict] = {}
    ref = reference_model()
    base = base_slice(ref, "fact_holdings", _HOLDING_DIMS, _HOLDING_COLS)
    for case in reference_cases():
        out[case[0]] = fixture(ref, *case, base)
    parts = parts_slice(ref, "fact_holdings",
                        ["dim_issuer.sector", "dim_fund.fund"], _PARTS)
    for case in parts_cases():
        out[case[0]] = fixture(ref, *case, parts)

    two = two_fact_model()
    holdings = base_slice(two, "fact_holdings",
                          ["dim_fund.fund", "dim_issuer.sector", "dim_date.month"],
                          ["fair_value"])
    cashflows = base_slice(two, "fact_cashflows",
                           ["dim_fund.fund", "dim_date.month"],
                           ["flow_id", "amount"])
    out["two_fact_holdings"] = fixture(
        two, "two_fact_holdings", "One page, two facts: every selected field "
        "reaches holdings (fund, sector, a month range).",
        {"fact": "fact_holdings", "measures": ["fair_value"],
         "dimensions": ["dim_date.month"]}, TWO_FACT_SEL, holdings)
    out["two_fact_cashflows"] = fixture(
        two, "two_fact_cashflows", "The same page's cash flows: the sector "
        "does not reach this fact, so it is listed in unfiltered_by and the "
        "fund and months still apply.",
        {"fact": "fact_cashflows", "measures": ["net_flow", "flows"],
         "dimensions": ["dim_date.month"]}, TWO_FACT_SEL, cashflows)
    return out


def dumps(value, indent: int = 0) -> str:
    """JSON with short arrays and objects on one line, so a row reads as one."""
    flat = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(flat) + indent <= 96 or not isinstance(value, (dict, list)) or not value:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, list):
        items = [pad + dumps(v, indent + 2) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + " " * indent + "]"
    items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 2)}"
             for k, v in value.items()]
    return "{\n" + ",\n".join(items) + "\n" + " " * indent + "}"


def write(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, fx in build().items():
        path = out_dir / f"{name}.json"
        path.write_text(dumps(fx) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    for path in write(args.out):
        print(path.relative_to(args.out.parent) if args.out == OUT else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
