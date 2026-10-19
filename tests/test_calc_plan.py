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
    m.add_measure("revenue_sd", column="amount", agg="stddev")
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

    assert "to_date" in plan(measures=["revenue_ytd"])["fixed"]
    assert "stddev" in plan(measures=["revenue_sd"])["fixed"]
    assert "aggregate=False" in plan(measures={"amount": "sum"},
                                     aggregate=False)["fixed"]
    assert "'amount'" in plan(slice_columns=SLICE[:1], measures=["revenue"])["fixed"]
    assert "no slice" in plan(slice_columns={"other_fact": SLICE},
                              measures=["revenue"])["fixed"]
    assert "Pow" in plan(measures=["sq"], calculated={
        "sq": {"expr": "amount ** 2", "agg": "sum"}})["fixed"]
    sql = SqlQuery.from_dict({"sql": "SELECT 1 AS one"})
    assert "SQL" in compile_plan(m, sql, SLICE)["fixed"]
    fixed = plan(measures=["revenue_sd"])
    assert apply_selection(fixed, {"dim_store.region": ["East"]}) is fixed


def test_a_mean_compiles_to_parts_the_page_divides():
    plan = _plan(measures=["revenue_avg"])
    assert [(a["name"], a["func"]) for a in plan["aggregates"]] == [
        ("revenue_avg:sum", "sum"), ("revenue_avg:count", "count")]
    assert plan["means"] == [{"name": "revenue_avg", "sum": "revenue_avg:sum",
                              "count": "revenue_avg:count"}]
    assert plan["columns"] == ["dim_store.region", "revenue_avg"]
