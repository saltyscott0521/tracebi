"""
The calc plan and its parity fixtures (query semantics).

A calc plan is what the page engine runs when a selection changes, so it must
mean exactly what the binding's query means. Three things pin that:

* every committed fixture's expected rows (DuckDB on the full model under the
  selection) equal ``execute_plan`` on the fixture's own slice: the plan,
  read by ``DataModel.execute`` over only what the page carries, gives the
  same numbers;
* the fixtures regenerate byte for byte, so a change in ``DataModel`` or in
  the compiler that moves a number shows up as a diff, not as a page engine
  quietly agreeing with a stale file;
* ``apply_selection`` composes by the one rule: reachable fields AND with the
  binding's filters, unreachable ones are named and change nothing.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.model.data_model import QuerySpec
from tracebi.model.dataset import canonical_rows
from tracebi.model.sql_calc import SqlQuery
from tracebi.reports.calc_plan import (
    apply_selection,
    compile_plan,
    execute_plan,
    grain_label,
    label_start,
    reset_label,
    shift_label,
    slice_frame,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "calc_parity"
CASES = sorted(FIXTURES.glob("*.json"))


def _generator():
    spec = importlib.util.spec_from_file_location(
        "gen_calc_parity", ROOT / "scripts" / "gen_calc_parity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_the_plan_over_the_slice_gives_the_expected_rows(path):
    fx = json.loads(path.read_text(encoding="utf-8"))
    frame = slice_frame(fx["slice"]["columns"], fx["slice"]["rows"])
    result = execute_plan(fx["plan"], frame, fx["selection"])
    cols, rows = canonical_rows(result, total_order=False)
    assert cols == fx["expected"]["cols"]
    assert rows == fx["expected"]["rows"]
    applied = apply_selection(fx["plan"], fx["selection"])
    assert applied["unfiltered_by"] == fx["expected"]["unfiltered_by"]


def test_the_fixtures_cover_what_the_plan_promises():
    names = {p.stem for p in CASES}
    for kind in ("total", "sum_by_sector", "count", "mean", "min_max", "nunique",
                 "percentile", "derived", "ratio", "share", "rank", "running",
                 "partitioned_rank", "having", "order_limit", "calculated", "parts"):
        assert {kind, f"{kind}_selected"} <= names, kind
    assert {"order", "filter_narrowed", "range_selected", "total_empty",
            "parts_empty", "two_fact_holdings", "two_fact_cashflows"} <= names
    for kind in ("period_end_total", "period_end_by_sector", "period_end_by_quarter",
                 "offset_month", "growth_year", "growth_by_account",
                 "offset_period_end", "growth_quarter", "ytd", "ytd_by_sector",
                 "stddev", "raw_rows"):
        assert {kind, f"{kind}_selected"} <= names, kind
    assert {"period_end_date_range", "period_end_empty", "period_end_base_grain",
            "period_end_beside_a_sum_empty", "qtd", "raw_rows_all"} <= names


def test_the_fixtures_regenerate_byte_identically(tmp_path):
    written = _generator().write(tmp_path)
    assert sorted(p.name for p in written) == sorted(p.name for p in CASES)
    for path in written:
        committed = FIXTURES / path.name
        assert path.read_bytes() == committed.read_bytes(), (
            f"{path.name} moved: run `python scripts/gen_calc_parity.py` and "
            f"read the diff before committing it")


# ── apply_selection: the one composition rule ───────────────────────────────

def _model() -> DataModel:
    sales = pd.DataFrame({"order_id": [1, 2, 3, 4], "store_id": [1, 2, 1, 2],
                          "amount": [10.0, 20.0, 30.0, 40.0]})
    stores = pd.DataFrame({"store_id": [1, 2], "region": ["East", "West"]})
    m = DataModel("cp_model")
    m.add_connector(MemoryConnector("cp_mem", tables={"sales": sales,
                                                      "stores": stores}))
    m.add_table("sales", connector="cp_mem", source="sales")
    m.add_table("stores", connector="cp_mem", source="stores")
    m.add_dimension("dim_store", table_name="stores", key_col="store_id",
                    attributes=["region"])
    m.add_fact("fact_sales", table_name="sales", measures=["amount"],
               foreign_keys={"dim_store": "store_id"})
    m.add_measure("revenue", column="amount", agg="sum")
    m.add_measure("revenue_avg", column="amount", agg="mean")
    m.add_measure("revenue_share", share="revenue")
    m.add_measure("revenue_ytd", to_date=("revenue", "year"))
    m.connect()
    return m


SLICE = [{"name": "dim_store.region", "type": "string"},
         {"name": "amount", "type": "number"}]


def _plan(**query):
    spec = QuerySpec.from_dict({"fact": "fact_sales", "measures": ["revenue"],
                                "dimensions": ["dim_store.region"], **query})
    return compile_plan(_model(), spec, SLICE)


def test_a_reachable_field_applies_and_an_unreachable_one_is_named():
    plan = _plan()
    out = apply_selection(plan, {"dim_store.region": ["East"],
                                 "dim_date.month": ["2026-01"]})
    assert out["selection"] == {"dim_store.region": ["East"]}
    assert out["unfiltered_by"] == ["dim_date.month"]
    assert out["filters"] == plan["filters"]
    only_unreachable = apply_selection(plan, {"dim_date.month": ["2026-01"]})
    assert only_unreachable["selection"] == {}
    assert {k: v for k, v in only_unreachable.items()
            if k not in ("selection", "unfiltered_by")} == plan


def test_a_selection_narrows_a_binding_filter_and_never_widens_it():
    plan = _plan(filters={"dim_store.region": ["East"]})
    frame = slice_frame(SLICE, [["East", 10.0], ["West", 20.0], ["East", 30.0]])
    widened = execute_plan(plan, frame, {"dim_store.region": ["West"]})
    assert widened.empty, "the binding said East; selecting West must not show West"
    narrowed = execute_plan(plan, frame, {"dim_store.region": ["East", "West"]})
    assert narrowed.to_dict("records") == [{"dim_store.region": "East",
                                            "revenue": 40.0}]


def test_a_range_selection_keeps_its_bounds_and_an_empty_list_selects_nothing():
    plan = _plan()
    out = apply_selection(plan, {"amount": {"lte": 30, "gt": 10},
                                 "dim_store.region": []})
    assert out["selection"] == {"amount": {"gt": 10, "lte": 30}}
    frame = slice_frame(SLICE, [["East", 10.0], ["West", 20.0], ["East", 30.0]])
    rows = execute_plan(plan, frame, {"amount": {"lte": 30, "gt": 10}})
    assert rows.to_dict("records") == [{"dim_store.region": "East", "revenue": 30.0},
                                       {"dim_store.region": "West", "revenue": 20.0}]
    with pytest.raises(ValueError, match="list of values or a range"):
        apply_selection(plan, {"amount": 10})
    with pytest.raises(ValueError, match="list of values or a range"):
        apply_selection(plan, {"amount": {"eq": 10}})


def test_what_the_page_cannot_recompute_is_fixed_with_a_reason():
    m = _model()

    def plan(slice_columns=SLICE, **query):
        return compile_plan(m, QuerySpec.from_dict(
            {"fact": "fact_sales", "dimensions": ["dim_store.region"], **query}),
            slice_columns)

    assert "time grain" in plan(measures=["revenue_ytd"])["fixed"]
    assert "aggregate=False" in plan(measures=["revenue_avg", "revenue_share"],
                                     aggregate=False)["fixed"]
    assert "'amount'" in plan(slice_columns=SLICE[:1], measures=["revenue"])["fixed"]
    assert "no slice" in plan(slice_columns={"other_fact": SLICE},
                              measures=["revenue"])["fixed"]
    assert "Pow" in plan(measures=["sq"], calculated={
        "sq": {"expr": "amount ** 2", "agg": "sum"}})["fixed"]
    sql = SqlQuery.from_dict({"sql": "SELECT 1 AS one"})
    assert "SQL" in compile_plan(m, sql, SLICE)["fixed"]
    fixed = plan(measures=["revenue_ytd"])
    assert apply_selection(fixed, {"dim_store.region": ["East"]}) is fixed


def test_a_mean_compiles_to_parts_the_page_divides():
    plan = _plan(measures=["revenue_avg"])
    assert [(a["name"], a["func"]) for a in plan["aggregates"]] == [
        ("revenue_avg:sum", "sum"), ("revenue_avg:count", "count")]
    assert plan["means"] == [{"name": "revenue_avg", "sum": "revenue_avg:sum",
                              "count": "revenue_avg:count"}]
    assert plan["columns"] == ["dim_store.region", "revenue_avg"]


# ── Label arithmetic: the page's time axis is DataModel's ───────────────────

_GRAINS = ("year", "quarter", "month", "week", "day")


def test_label_shifts_and_resets_agree_with_datamodel_on_every_day():
    """Every day of 2023 to 2026 (two year ends, a leap day, ISO years of 52
    and 53 weeks), at every grain: the label is the slice's spelling, it
    starts where DuckDB's date_trunc puts the period, a shift lands where
    DataModel's DateOffset lands (and only on a period start, else there is
    no prior), and a reset partitions as DataModel's to_period does."""
    from tracebi.model.data_model import _PERIOD_FREQ, _pop_offset
    from tracebi.reports.slice import _grain_strings

    days = pd.date_range("2023-01-01", "2026-12-31", freq="D")
    m = DataModel("labels")
    m.add_connector(MemoryConnector("labels", tables={"d": pd.DataFrame({"day": days})}))
    m.add_table("d", connector="labels", source="d")
    m.add_dimension("dim_d", table_name="d", key_col="day", attributes=["day"])
    for grain in _GRAINS:
        m.add_time_grain("dim_d", grain, source="day", grain=grain)
    spelled = _grain_strings(m, pd.DataFrame({f"dim_d.{g}": days for g in _GRAINS}))
    for grain in _GRAINS:
        labels = spelled[f"dim_d.{grain}"].tolist()
        assert labels == [grain_label(d.date(), grain) for d in days], grain
        starts = {}
        for day, label in zip(days, labels):
            start = pd.Timestamp(label_start(label, grain))
            if grain == "week":
                assert start == day - pd.Timedelta(days=day.weekday())
            elif grain != "day":
                assert start == day.to_period(_PERIOD_FREQ[grain]).start_time
            else:
                assert start == day
            starts[label] = start
        def starts_a_period(day):
            if grain == "week":
                return day.weekday() == 0
            return grain == "day" or day == day.to_period(_PERIOD_FREQ[grain]).start_time

        for label, start in starts.items():
            for unit in _GRAINS:
                for n in (1, 2, 3):
                    moved = start - _pop_offset(unit, n)
                    want = (grain_label(moved.date(), grain)
                            if starts_a_period(moved) else None)
                    assert shift_label(label, grain, unit, n) == want, (
                        label, grain, unit, n)
            for period in _PERIOD_FREQ:
                assert reset_label(label, grain, period) == grain_label(
                    start.to_period(_PERIOD_FREQ[period]).start_time.date(), period)


def test_label_edges():
    assert shift_label("2026-01", "month", "month", 1) == "2025-12"
    assert shift_label("2026-Q1", "quarter", "quarter", 1) == "2025-Q4"
    assert shift_label("2026-03", "month", "year", 1) == "2025-03"
    assert shift_label("2026-W01", "week", "week", 1) == "2025-W52"
    assert shift_label("2021-W01", "week", "week", 1) == "2020-W53"
    assert shift_label("2024-02-29", "day", "year", 1) == "2023-02-28"
    assert shift_label("2024-03-31", "day", "month", 1) == "2024-02-29"
    assert shift_label("2024-03-01", "day", "day", 1) == "2024-02-29"
    assert shift_label("2026-03", "month", "week", 1) is None
    assert shift_label("2026", "year", "quarter", 4) == "2025"
    assert reset_label("2025-W01", "week", "year") == "2024"
    assert reset_label("2026-W01", "week", "month") == "2025-12"
    assert reset_label("2026-05", "month", "quarter") == "2026-Q2"
    with pytest.raises(ValueError, match="not a month label"):
        label_start("2026-Q1", "month")


def test_time_intelligence_compiles_to_its_own_steps():
    m = _model()
    slice_cols = SLICE + [{"name": "revenue:sum", "type": "number"}]
    plan = compile_plan(m, QuerySpec.from_dict({
        "fact": "fact_sales", "measures": ["revenue"],
        "dimensions": ["dim_store.region"]}), slice_cols)
    assert not {"period_ends", "pops", "to_dates", "time_grain"} & set(plan), (
        "a plan without time intelligence keeps version 1's exact shape")
    raw = compile_plan(m, QuerySpec.from_dict({
        "fact": "fact_sales", "measures": {"amount": "sum"},
        "dimensions": ["dim_store.region"], "aggregate": False,
        "order_by": [{"column": "amount", "desc": True}], "limit": 2}), SLICE)
    assert raw["raw"] is True and raw["project"] == [
        {"name": "amount", "source": {"col": "amount"}}]
    assert raw["order_by"] == [{"column": "amount", "desc": True},
                               {"column": "dim_store.region", "desc": False}]
    frame = slice_frame(SLICE, [["East", 10.0], ["West", 40.0], ["East", 30.0]])
    assert execute_plan(raw, frame).to_dict("records") == [
        {"dim_store.region": "West", "amount": 40.0},
        {"dim_store.region": "East", "amount": 30.0}]
