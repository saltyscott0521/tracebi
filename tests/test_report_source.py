"""A report page's Files tab: which form a report takes, and its files."""

import json

import pandas as pd
import pytest

from tracebi import DataModel
from tracebi.connectors import MemoryConnector


def _model(name: str) -> DataModel:
    m = DataModel(name).add_connector(MemoryConnector("mem", {
        "orders": pd.DataFrame({"order_id": [1, 2], "revenue": [100.0, 200.0]}),
    }))
    m.add_table("orders", connector="mem", source="orders")
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"])
    m.connect()
    return m


@pytest.fixture
def discovered(tmp_path, monkeypatch):
    """A reports/ folder with one spec and one package, discovered."""
    from fastapi.testclient import TestClient

    import tracebi.model_registry as model_registry
    from tracebi.registry import registry
    from tracebi.web.api.main import app
    from tracebi.web.discovery import auto_discover

    reports = tmp_path / "reports"
    reports.mkdir()
    binding = {"model": "src_demo", "query": {"fact": "fact_orders",
                                              "measures": {"revenue": "sum"}}}
    (reports / "src_spec.json").write_text(json.dumps({
        "name": "Spec", "theme": "../outside.css",
        "sections": [{"type": "table", "title": "T", "data": binding}],
    }))
    pkg = reports / "src_pkg"
    (pkg / "assets").mkdir(parents=True)
    (pkg / "report.json").write_text(json.dumps({"name": "Pkg", "data": {"t": binding}}))
    (pkg / "template.html").write_text(
        '<main><table data-tb-figure="table" data-tb-binding="t" id="t"></table></main>')
    (pkg / "style.css").write_text(".tb-card { color: red; }")
    (pkg / "assets" / "logo.svg").write_text("<svg/>")
    (tmp_path / "outside.css").write_text("secret")

    monkeypatch.chdir(tmp_path)
    model_registry.register(_model("src_demo"))
    try:
        auto_discover(str(reports))
        yield TestClient(app)
    finally:
        for n in ("src_spec", "src_pkg"):
            registry._report_factories.pop(n, None)
        model_registry._registry._models.pop("src_demo", None)


def test_spec_theme_cannot_point_outside_the_reports_folder(discovered):
    body = discovered.get("/api/reports/src_spec/source").json()
    assert all("secret" not in f["content"] for f in body["files"])
