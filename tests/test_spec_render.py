"""The spec render lane routes through the artifact path.

A JSON ReportSpec no longer renders via the legacy HTMLRenderer — every spec
entry point (CLI, MCP, web) compiles the spec to the artifact package and
renders it like a hand-authored one, so it gets the figure grammar, the
receipt drawer, badges, and a schema-2 manifest. The MCP path is covered in
test_mcp_gateway; this pins the web POST /api/spec/render surface, which had
no test before.

NB: the web app / registry are imported INSIDE the tests, never at module top.
Importing tracebi.web.api.main binds the routers to the registry at import
time, and TestPipelineRunEndpoint::test_run_all_layers rebinds that registry
for isolation — a module-level import here would bind it first and break it
(CLAUDE.md invariant 3).
"""

import pandas as pd

from tracebi import DataModel, MemoryConnector


def _model(name: str) -> DataModel:
    m = DataModel(name).add_connector(MemoryConnector("mem", {
        "orders": pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [1, 2, 1],
                                "revenue": [100.0, 200.0, 300.0]}),
        "customers": pd.DataFrame({"customer_id": [1, 2], "region": ["West", "NE"]}),
    }))
    m.add_table("orders", connector="mem", source="orders")
    m.add_table("customers", connector="mem", source="customers")
    m.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
               foreign_keys={"dim_customer": "customer_id"})
    m.add_measure("total_revenue", column="revenue", agg="sum")
    m.connect()
    return m


def _spec(model: str) -> dict:
    return {"name": "web-spec", "sections": [{
        "type": "table", "title": "By region",
        "data": {"model": model, "query": {
            "fact": "fact_orders", "measures": ["total_revenue"],
            "dimensions": ["dim_customer.region"]}},
    }]}


def test_web_spec_render_returns_the_artifact():
    from fastapi.testclient import TestClient

    from tracebi.web.api.main import app
    from tracebi.web.api.registry import registry

    registry.add_model(_model("web_spec_demo"))
    try:
        r = TestClient(app).post("/api/spec/render", json=_spec("web_spec_demo"))
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"html", "manifest"}          # shape preserved
        assert body["manifest"]["schema_version"] == 2     # the artifact manifest
        # The figure grammar + receipt drawer, not the legacy second runtime.
        assert "data-tb-figure" in body["html"]
        assert 'id="tracebi-receipt"' in body["html"]
        assert 'id="tracebi-charts"' not in body["html"]
    finally:
        registry._models.pop("web_spec_demo", None)


def test_web_spec_render_still_400s_an_invalid_spec():
    from fastapi.testclient import TestClient

    from tracebi.web.api.main import app
    from tracebi.web.api.registry import registry

    registry.add_model(_model("web_spec_bad"))
    try:
        bad = _spec("web_spec_bad")
        bad["sections"][0]["data"]["query"]["fact"] = "nope"   # unknown fact
        r = TestClient(app).post("/api/spec/render", json=bad)
        assert r.status_code == 400
    finally:
        registry._models.pop("web_spec_bad", None)
