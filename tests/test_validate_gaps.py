"""
Validation-before-execution gaps (ROADMAP "Now" item 2).

"Validation before execution" is the keystone claim, and it used to hold
only for section structure, fact names, named measures, and dimension
names. The typo classes an agent actually produces — a bad filter column,
a bad aggregation name, a bad dimension attribute, a chart axis naming a
column the query never produces, ``dataset`` instead of ``data`` — passed
``validate()`` with ``ok: true`` and detonated at render.

Every test here asserts two things: the mistake is caught with a *pathed*
message, and it is caught **before any data loads** — the connector
records every ``load()`` call precisely so that claim is checkable.

References only the physical table can confirm (an ad-hoc dict-measure
column, a bare filter column beyond the declared ones) surface as pathed
*warnings* — erroring on those would refuse specs that execute fine, and
would break the documented from_report round-trip. Execution still fails
loudly on them, and the gateway's render channel now returns that failure
as structured ``{ok: false, errors: [...]}`` rather than a raw traceback.
"""

import pandas as pd

from tracebi import DataModel, MemoryConnector
from tracebi.spec import ReportSpec


class RecordingConnector(MemoryConnector):
    """A MemoryConnector that records every load — proof nothing executed."""

    def __init__(self, name, tables):
        super().__init__(name, tables)
        self.loads: list[str] = []

    def load(self, source, filter=None, columns=None):
        self.loads.append(source)
        return super().load(source, filter=filter, columns=columns)


def _model(connector_cls=RecordingConnector, name="VG Sales"):
    orders = pd.DataFrame({
        "order_id":    [1, 2, 3, 4],
        "customer_id": [1, 2, 1, 2],
        "revenue":     [100.0, 200.0, 300.0, 400.0],
        "cost":        [60.0, 150.0, 180.0, 320.0],
    })
    customers = pd.DataFrame({
        "customer_id": [1, 2], "region": ["West", "NE"],
    })
    connector = connector_cls(
        "vg_mem", {"orders": orders, "customers": customers}
    )
    m = DataModel(name).add_connector(connector)
    m.add_table("orders", connector="vg_mem", source="orders")
    m.add_table("customers", connector="vg_mem", source="customers")
    m.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders",
               measures=["revenue", "cost"],
               foreign_keys={"dim_customer": "customer_id"})
    m.add_measure("total_revenue", column="revenue", agg="sum")
    m.add_measure("gross_margin", expr="revenue - cost", agg="sum")
    m.add_measure("margin_pct", ratio=("gross_margin", "total_revenue"),
                  format="percent")
    m.connect()
    return m, connector


def _spec(section):
    return {"name": "VG", "sections": [section]}


def _table(query):
    return _spec({
        "type": "table", "title": "T",
        "data": {"model": "VG Sales", "query": query},
    })


def _validate(spec_dict, model):
    return ReportSpec.from_dict(spec_dict).validate({"VG Sales": model})


# ── Filter columns ─────────────────────────────────────────────────────────

def test_bare_filter_naming_a_dimension_attribute_is_a_pathed_warning():
    # A warning, not an error: the bare name may also be a physical column
    # on a denormalised fact table, and execution accepts that spelling with
    # different semantics than the dimension filter — rejecting it outright
    # was a false rejection (review finding on the validate-gaps branch).
    model, conn = _model()
    result = _validate(_table({
        "fact": "fact_orders", "measures": ["total_revenue"],
        "filters": {"region": "West"},
    }), model)
    assert result["ok"]
    warn = next(w for w in result["warnings"]
                if w.startswith("sections[0].data.query.filters.region:"))
    assert "dim_customer.region" in warn
    assert conn.loads == [], "validation must not load data"


def test_dotted_filter_with_undeclared_attribute_is_a_pathed_error():
    model, conn = _model()
    result = _validate(_table({
        "fact": "fact_orders", "measures": ["total_revenue"],
        "filters": {"dim_customer.regoin": "West"},
    }), model)
    assert not result["ok"]
    err = next(e for e in result["errors"]
               if "filters.dim_customer.regoin" in e)
    assert "Did you mean 'region'?" in err
    assert conn.loads == []


# ─────────────────────────────────────────────


def test_unknown_filter_operator_is_a_pathed_error():
    model, conn = _model()
    result = _validate(_table({
        "fact": "fact_orders", "measures": ["total_revenue"],
        "filters": {"revenue": {"gte!": 1000}},
    }), model)
    assert not result["ok"]
    err = next(e for e in result["errors"] if "gte!" in e)
    assert "filters.revenue" in err
    assert "gte" in err   # did-you-mean or supported list
    assert conn.loads == []
