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
one fact. The time-intelligence cases (period_end, offset, growth, to_date)
and the stddev and raw-row ones use a snapshot model in the shape of the
reference project's SaaS model (examples/portfolio_project/models/
saas_model.yaml), with declared month, quarter and year grains. Expected
rows spell time grains as the slice does (``_grain_strings``).

    python scripts/gen_calc_parity.py [--out DIR]

The output is deterministic: running it again writes the same bytes.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional

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
from tracebi.reports.slice import _grain_strings  # noqa: E402

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


_ACCOUNTS = [("A", "Software"), ("B", "Energy"), ("C", "Software"),
             ("D", "Energy"), ("E", "Software")]


def time_model() -> DataModel:
    """A snapshot fact in the shape of the reference project's SaaS model:
    one row per account per month-end, a balance taken at the latest
    snapshot (period_end) and a deposit flow summed, over eighteen month-ends
    from October 2024 to March 2026, so months and quarters cross two year
    ends.

    D closes after December 2025 and E opens in December 2025, so
    accounts' latest snapshots differ, and E has a single month in 2025
    (a stddev of one value). One deposit is missing (sums skip it) and one is
    zero (a growth over it is null).
    """
    month_ends = [pd.Timestamp(2024, 10, 31) + pd.offsets.MonthEnd(i)
                  for i in range(18)]
    dates = pd.DataFrame({"date_id": list(range(1, 19)), "date": month_ends})
    accounts = pd.DataFrame({"account_id": list(range(1, 6)),
                             "account": [a for a, _ in _ACCOUNTS],
                             "sector": [s for _, s in _ACCOUNTS]})
    rows = []
    for a in range(1, 6):
        for i, day in enumerate(month_ends):
            if (a == 4 and day > pd.Timestamp(2025, 12, 31)) or (
                    a == 5 and day < pd.Timestamp(2025, 12, 31)):
                continue
            balance = round(10_000.0 * a + 1234.56 * ((i * a) % 7) + 0.37 * i, 2)
            deposit = round(500.0 + 137.25 * ((i + 2 * a) % 5) - 0.03 * a, 2)
            if a == 3 and i == 5:
                deposit = None
            if a == 2 and i == 3:
                deposit = 0.0
            rows.append((len(rows) + 1, a, i + 1, balance, deposit, 1))
    balances = pd.DataFrame(rows, columns=["balance_id", "account_id", "date_id",
                                           "balance", "deposits", "active"])
    m = DataModel("time_model")
    m.add_connector(MemoryConnector("time", tables={
        "balances": balances, "dates": dates, "accounts": accounts}))
    for t in ("balances", "dates", "accounts"):
        m.add_table(t, connector="time", source=t)
    m.add_dimension("dim_date", table_name="dates", key_col="date_id",
                    attributes=["date"])
    for grain in ("month", "quarter", "year"):
        m.add_time_grain("dim_date", grain, source="date", grain=grain)
    m.add_dimension("dim_account", table_name="accounts", key_col="account_id",
                    attributes=["account", "sector"])
    m.add_fact("fact_balances", table_name="balances",
               measures=["balance", "deposits", "active"],
               foreign_keys={"dim_date": "date_id", "dim_account": "account_id"})
    m.add_measure("ending_balance", period_end=("balance", "dim_date.date"))
    m.add_measure("accounts_open", period_end=("active", "dim_date.date"))
    m.add_measure("avg_balance", ratio=("ending_balance", "accounts_open"))
    m.add_measure("deposits", column="deposits", agg="sum")
    m.add_measure("deposit_sd", column="deposits", agg="stddev")
    m.add_measure("deposits_mom", offset=("deposits", "month", 1))
    m.add_measure("deposits_growth", growth=("deposits", "month", 1))
    m.add_measure("deposits_yoy", growth=("deposits", "year", 1))
    m.add_measure("deposits_ytd", to_date=("deposits", "year"))
    m.add_measure("deposits_qtd", to_date=("deposits", "quarter"))
    m.add_measure("balance_last_month", offset=("ending_balance", "month", 1))
    m.add_measure("balance_qoq", growth=("ending_balance", "quarter", 1))
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

# The aggregated slice carries the grains its cases group by, plus the
# snapshot date a period_end needs; the base-grain one the raw columns.
_TIME_GRAIN = ["dim_account.sector", "dim_account.account", "dim_date.date",
               "dim_date.month", "dim_date.quarter"]
_TIME_PARTS = {"ending_balance:sum": ("balance", "sum"),
               "accounts_open:sum": ("active", "sum"),
               "deposits:sum": ("deposits", "sum")}
_TIME_BASE = ["dim_account.sector", "dim_account.account", "dim_date.date",
              "dim_date.month", "dim_date.year"]
_TIME_COLS = ["balance", "deposits"]

SOFTWARE = {"dim_account.sector": ["Software"]}
TWO_ACCOUNTS = {"dim_account.account": ["A", "D"]}
# Months 2025-01 to 2025-06, as the page selects them (labels), and as the
# full model can filter them (the dates the month grain is derived from).
FIRST_HALF = {"dim_date.month": {"gte": "2025-01", "lte": "2025-06"}}
FIRST_HALF_DATES = {"and": [{"dim_date.date": {"gte": "2025-01-01"}},
                            {"dim_date.date": {"lt": "2025-07-01"}}]}


def _t(measures, dims=(), **kw) -> dict:
    return {"fact": "fact_balances", "measures": measures,
            "dimensions": list(dims), **kw}


def time_cases() -> list[tuple]:
    """Cases over the aggregated slice (the grain a period_end page embeds)."""
    by_month, by_quarter = ["dim_date.month"], ["dim_date.quarter"]
    by_sector, by_account = ["dim_account.sector"], ["dim_account.account"]
    return [
        *_pair("period_end_total", "period_end with no groups: the latest "
               "month-end across every account, summed.",
               _t(["ending_balance", "accounts_open"]), SOFTWARE),
        *_pair("period_end_by_sector", "period_end by a dimension, and a ratio "
               "of two period_ends.",
               _t(["ending_balance", "accounts_open", "avg_balance"], by_sector),
               TWO_ACCOUNTS),
        *_pair("period_end_by_account", "Each account at its own latest "
               "snapshot: D closed in December 2025.",
               _t(["ending_balance"], by_account), SOFTWARE),
        *_pair("period_end_by_quarter", "period_end by a time grain: each "
               "quarter at its last month-end.",
               _t(["ending_balance", "accounts_open"], by_quarter), SOFTWARE),
        ("period_end_date_range", "A month range selection: the latest "
         "snapshot is the range's last month.",
         _t(["ending_balance", "accounts_open"]), FIRST_HALF, FIRST_HALF_DATES),
        ("period_end_by_sector_date_range", "period_end by sector under a month "
         "range.", _t(["ending_balance"], by_sector), FIRST_HALF, FIRST_HALF_DATES),
        ("period_end_empty", "A selection nothing matches: a query of "
         "period_ends alone has no row at all (DataModel's skeleton row).",
         _t(["ending_balance", "avg_balance"]),
         {"dim_account.sector": ["No such sector"]}),
        ("period_end_beside_a_sum_empty", "Nothing matches, beside a sum: the "
         "one row an aggregate always has, null sum and a period_end of 0.",
         _t(["deposits", "ending_balance"]),
         {"dim_account.sector": ["No such sector"]}),
        *_pair("offset_month", "offset one month back; the first month has no "
               "prior.", _t(["deposits", "deposits_mom"], by_month), SOFTWARE),
        *_pair("growth_year", "growth over a year back on monthly rows: only "
               "months with a month a year earlier have one.",
               _t(["deposits", "deposits_yoy"], by_month), SOFTWARE),
        *_pair("growth_by_account", "growth matched within each account: a "
               "prior of 0 or null gives null, a new account has no prior.",
               _t(["deposits", "deposits_growth"], by_account + by_month),
               TWO_ACCOUNTS),
        *_pair("offset_period_end", "An offset of a period_end: last month's "
               "ending balance.",
               _t(["ending_balance", "balance_last_month"], by_month),
               TWO_ACCOUNTS),
        *_pair("growth_quarter", "Quarter-over-quarter growth of a period_end "
               "on the quarter grain.",
               _t(["ending_balance", "balance_qoq"], by_quarter), SOFTWARE),
        *_pair("ytd", "Year to date over months, restarting each January.",
               _t(["deposits", "deposits_ytd"], by_month), SOFTWARE),
        ("qtd", "Quarter to date over months, under a month range.",
         _t(["deposits", "deposits_qtd"], by_month), FIRST_HALF, FIRST_HALF_DATES),
        *_pair("ytd_by_sector", "Year to date within each sector.",
               _t(["deposits_ytd"], by_sector + by_month), TWO_ACCOUNTS),
    ]


def time_base_cases() -> list[tuple]:
    """Cases over the base-grain slice (what stddev and raw rows embed)."""
    return [
        *_pair("stddev", "stddev, the sample standard deviation; E has one "
               "deposit in 2025, so null.",
               _t(["deposit_sd"], ["dim_account.account", "dim_date.year"]),
               SOFTWARE),
        ("period_end_base_grain", "period_end over a base-grain slice: the "
         "value column itself.", _t(["ending_balance"], ["dim_date.year"]),
         SOFTWARE),
        *_pair("raw_rows", "Raw rows (aggregate=False): ordered by balance, "
               "ties broken by every column, top five.",
               _t({"balance": "sum", "deposits": "sum"},
                  ["dim_account.account", "dim_date.month"], aggregate=False,
                  order_by=[{"column": "balance", "desc": True}], limit=5),
               SOFTWARE),
        ("raw_rows_all", "Raw rows with no order_by: every column ascending; a "
         "datetime column and a row expression with a null operand.",
         _t({"net": {"expr": "balance - deposits", "agg": "sum"}},
            ["dim_date.date", "dim_account.account"], aggregate=False,
            filters={"dim_account.account": ["C", "E"]}),
         FIRST_HALF, FIRST_HALF_DATES),
    ]


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
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
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
            frame: pd.DataFrame, oracle: Optional[dict] = None) -> dict:
    """One case. The expected rows are the full model's answer under the
    selection, with time grains spelled as the slice spells them. A
    selection on a time-grain label is one DataModel cannot run (a grain is
    groupable, not filterable), so such a case names *oracle*: the same rows
    as a filter on the date the grain is derived from."""
    spec = QuerySpec.from_dict(query)
    sl = _slice_json(spec.fact, frame)
    plan = compile_plan(model, spec, sl["columns"])
    if "fixed" in plan:
        raise SystemExit(f"{name}: the plan is fixed: {plan['fixed']}")
    applied = apply_selection(plan, selection)
    if oracle is None:
        server = selection_query(spec, applied)
    else:
        filters = [dict(spec.filters)] if spec.filters else []
        server = dataclasses.replace(spec, filters={"and": filters + [oracle]})
    result = _grain_strings(model, model.execute(server).to_pandas())
    cols, rows = canonical_rows(result, total_order=False)
    return {
        "case": name,
        "about": about,
        "model": model.name,
        "query": spec.to_dict(),
        "slice": sl,
        "plan": plan,
        "selection": selection,
        **({"oracle_filters": oracle} if oracle else {}),
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

    timed = time_model()
    parts = _grain_strings(timed, parts_slice(timed, "fact_balances", _TIME_GRAIN,
                                              _TIME_PARTS))
    for case in time_cases():
        out[case[0]] = fixture(timed, *case[:4], parts, *case[4:])
    base = _grain_strings(timed, base_slice(timed, "fact_balances", _TIME_BASE,
                                            _TIME_COLS))
    for case in time_base_cases():
        out[case[0]] = fixture(timed, *case[:4], base, *case[4:])
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
