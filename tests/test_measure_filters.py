"""Measures with their own filters (``add_measure(..., filters=...)``).

Unit-level only for what a journey cannot pin precisely: a filtered sum differs
from the unfiltered one, other measures are untouched, declaration errors name
the measure, and the stamped lineage carries the resolved filter. The journey
in tests/e2e/ covers the same measure through a report and ``tracebi verify``.
"""

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.model.data_model import QuerySpec


@pytest.fixture
def model():
    activity = pd.DataFrame({
        "activity_id": [1, 2, 3, 4, 5],
        "activity_type": ["purchase", "sale", "purchase", "purchase", "sale"],
        "amount": [100.0, 40.0, 300.0, 50.0, 60.0],
        "qty": [1, 2, 3, 12, 5],
    })
    m = DataModel("Activity").add_connector(
        MemoryConnector("mem", {"activity": activity}))
    m.add_table("activity", connector="mem", source="activity")
    m.add_fact("fact_activity", table_name="activity",
               measures=["amount", "qty"])
    m.add_measure("total", column="amount", agg="sum")
    m.add_measure("purchases", column="amount", agg="sum",
                  filters={"activity_type": "purchase"})
    m.add_measure("purchase_share", ratio=("purchases", "total"))
    m.connect()
    return m


def _values(ds, col):
    return ds.to_pandas()[col].tolist()


def test_filtered_sum_differs_from_unfiltered_and_other_measures_are_unaffected(model):
    ds = model.query(fact="fact_activity", measures=["total", "purchases"])
    assert _values(ds, "total") == [550.0]          # 100+40+300+50+60
    assert _values(ds, "purchases") == [450.0]      # the purchase rows only

    # A ratio of a filtered and an unfiltered measure: a true ratio of totals.
    share = model.query(fact="fact_activity", measures=["purchase_share"])
    assert _values(share, "purchase_share")[0] == pytest.approx(450.0 / 550.0)


def test_the_filter_is_stamped_in_the_lineage(model):
    ds = model.query(fact="fact_activity", measures=["purchases"])
    filters = [n for n in ds.lineage if n.operation == "filter"
               and (n.metadata or {}).get("measure") == "purchases"]
    assert [(n.metadata["target"], n.metadata["value"]) for n in filters] == [
        ("activity_type", "purchase")]
    transform = [n for n in ds.lineage if n.operation == "transform"][-1]
    assert transform.metadata["measure_filters"] == {
        "purchases": [{"target": "activity_type", "operator": "eq",
                       "value": "purchase"}]}


def test_an_or_group_is_accepted_like_a_query_filter(model):
    model.add_measure("big_or_purchase", column="amount", agg="sum",
                      filters={"or": [{"activity_type": "sale"},
                                      {"qty": {"gte": 10}}]})
    ds = model.query(fact="fact_activity", measures=["big_or_purchase"])
    # sales (40, 60) or qty >= 10 (the 50 row): 40 + 50 + 60
    assert _values(ds, "big_or_purchase") == [150.0]


def test_a_filter_on_an_unknown_column_is_refused_by_name(model):
    model.add_measure("bogus", column="amount", agg="sum",
                      filters={"no_such_column": "x"})
    with pytest.raises(ValueError, match="Measure 'bogus'.*no_such_column"):
        model.query(fact="fact_activity", measures=["bogus"])


def test_a_filtered_measure_needs_an_aggregate(model):
    with pytest.raises(ValueError, match="aggregate=False"):
        model.query(fact="fact_activity", measures=["purchases"], aggregate=False)


@pytest.mark.parametrize("kwargs, message", [
    ({"filters": {"dim_customer.region": "West"}}, "dimension attribute"),
    ({"filters": {}}, "non-empty"),
    ({"filters": {"activity_type": {"nope": 1}}}, "operator"),
])
def test_bad_filters_are_refused_at_declaration(model, kwargs, message):
    with pytest.raises(ValueError, match=message):
        model.add_measure("bad", column="amount", agg="sum", **kwargs)


def test_filters_on_a_derived_measure_are_refused(model):
    with pytest.raises(ValueError, match="simple and expression"):
        model.add_measure("bad_ratio", ratio=("purchases", "total"),
                          filters={"activity_type": "purchase"})


# ── Report-level measures (a query's own `calculated`, and measure_expr) ──

_CALC = {
    "buys": {"column": "amount", "agg": "sum",
             "filters": {"activity_type": "purchase"}},
    "sells": {"column": "amount", "agg": "sum",
              "filters": {"activity_type": "sale"}},
    "net_new": {"measure_expr": "buys - sells"},
}


def test_a_calculated_measure_exists_for_one_query_and_not_the_model(model):
    view = model.with_measures({"purchases_only": _CALC["buys"]})
    assert _values(view.query(fact="fact_activity",
                              measures=["purchases_only"]), "purchases_only") == [450.0]
    assert "purchases_only" not in model.measures()
    with pytest.raises(ValueError, match="not declared"):
        model.query(fact="fact_activity", measures=["purchases_only"])


def test_net_new_is_purchases_less_sales(model):
    spec = QuerySpec(fact="fact_activity", measures=["net_new", "buys", "sells"],
                     calculated=_CALC)
    out = model.execute(spec).to_pandas()
    assert out[["buys", "sells", "net_new"]].iloc[0].tolist() == [450.0, 100.0, 350.0]


def test_the_stamp_carries_the_definitions_and_replays_to_the_same_bytes(model):
    spec = QuerySpec(fact="fact_activity", measures=["net_new"], calculated=_CALC)
    ds = model.execute(spec)
    [transform] = [n for n in ds.lineage if n.operation == "transform"]
    stamped = transform.metadata["query_spec"]
    assert stamped["calculated"]["net_new"] == {"measure_expr": "buys - sells"}
    assert model.execute(QuerySpec.from_dict(stamped)).fingerprint() == ds.fingerprint()


def test_a_calculated_measure_cannot_shadow_a_governed_one(model):
    with pytest.raises(ValueError, match="already declared"):
        model.with_measures({"total": {"column": "amount", "agg": "sum"}})


def test_an_unknown_keyword_in_a_calculated_definition_is_refused(model):
    with pytest.raises(ValueError, match="Measure 'x'"):
        model.with_measures({"x": {"colum": "amount", "agg": "sum"}})


@pytest.mark.parametrize("expr", ["sum(total)", "purchases.x", "purchases > 0"])
def test_measure_expr_is_arithmetic_over_measures_only(model, expr):
    with pytest.raises(ValueError, match="measure_expr"):
        model.add_measure("bad", measure_expr=expr)


def test_check_query_spec_validates_calculated_measures(model):
    ok = QuerySpec(fact="fact_activity", measures=["net_new"], calculated=_CALC)
    errors, _warnings = model.check_query_spec(ok)
    assert errors == []     # the undeclared filter column is a warning, not an error
    bad = QuerySpec(fact="fact_activity", measures=["net_new"],
                    calculated={"net_new": {"measure_expr": "missing - sells",
                                            "agg": "sum"}})
    errors, _ = model.check_query_spec(bad)
    assert errors
