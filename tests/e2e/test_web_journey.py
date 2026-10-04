"""The web journey: a scaffolded project served by the real FastAPI app.

Discovery is driven the way the running server drives it (the live-discovery
rescan), then a reader walks the pages and API calls the UI makes: status,
the report list, a run, the built page and its share link, downloads, source,
lineage, the model browser and an Explore query. The process-wide registry is
swapped for an empty one for the journey and restored after.
"""

import time

import pytest

from tests.e2e.conftest import run_cli


@pytest.fixture
def served(scaffolded, monkeypatch):
    from fastapi.testclient import TestClient

    from tracebi.registry import registry
    from tracebi.web import discovery
    from tracebi.web.api.main import app

    for attr in ("_connectors", "_models", "_report_factories",
                 "_scheduled_factories", "_pipelines"):
        monkeypatch.setattr(registry, attr, {})
    monkeypatch.setattr(registry, "_default_model_name", None)
    for attr, empty in (("_discovered", {}), ("_live_reports", {}),
                        ("_failed_sources", {}), ("_live_models", set()),
                        ("_live_pipelines", set()), ("_outcomes", [])):
        monkeypatch.setattr(discovery, attr, empty)

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    found = discovery.rescan("reports", "models", "pipelines")
    assert "sample_dashboard" in found["added"], found
    return TestClient(app)


def test_a_reader_opens_runs_shares_and_downloads_a_report(served):
    c = served
    assert c.get("/api/health").status_code == 200
    status = c.get("/api/status").json()
    assert "version" in status

    names = [r["name"] for r in c.get("/api/reports").json()]
    assert "sample_dashboard" in names

    run = c.post("/api/reports/sample_dashboard/run")
    assert run.status_code == 200, run.text
    body = run.json()
    assert "<html" in body["html"].lower()
    assert body["manifest"]["figures"], "a run returns its receipt"

    built = c.get("/api/reports/sample_dashboard/built")
    assert built.status_code == 200 and "<html" in built.json()["html"].lower()

    share = c.get("/r/sample_dashboard")
    assert share.status_code == 200
    assert share.headers["content-type"].startswith("text/html")
    assert "tracebi-receipt" in share.text

    html = c.get("/api/reports/sample_dashboard/download?format=html")
    assert html.status_code == 200 and "tracebi-receipt" in html.text
    xlsx = c.get("/api/reports/sample_dashboard/download?format=xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"   # a zip = xlsx

    source = c.get("/api/reports/sample_dashboard/source").json()
    assert source, "the report's source files are served"
    # Lineage is read from the last build's receipt: transform → tables →
    # model → queries → figures, each figure under the query it reads.
    lineage = c.get("/api/reports/sample_dashboard/lineage")
    assert lineage.status_code == 200
    flow = lineage.json()["flow"]
    kinds = {n["kind"] for n in flow["nodes"]}
    assert {"transform", "table", "model", "binding", "figures"} <= kinds
    assert flow["summary"]["figures"] == len(body["manifest"]["figures"])
    table = next(n for n in flow["nodes"] if n["kind"] == "table")
    assert table["detail"]["storage"]["where"].endswith("warehouse.duckdb")
    assert any(e["source"].startswith("binding:") and e["target"].startswith("figures:")
               for e in flow["edges"])


def test_a_background_run_settles_with_a_result(served):
    c = served
    start = c.post("/api/reports/sample_dashboard/runs")
    assert start.status_code == 202, start.text
    run_id = start.json()["run_id"]
    for _ in range(100):
        state = c.get(f"/api/reports/sample_dashboard/runs/{run_id}").json()
        if state["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert state["status"] == "succeeded", state
    listed = c.get("/api/reports/sample_dashboard/runs").json()
    assert any(r["run_id"] == run_id for r in listed)


def test_an_analyst_browses_the_model_and_queries_it(served):
    c = served
    listed = {m["name"]: m for m in c.get("/api/models").json()}
    assert "sample_model" in listed
    # The list carries the star schema's shape, not just a relationship count.
    assert listed["sample_model"]["facts"] and listed["sample_model"]["dimensions"]
    assert "revenue" in listed["sample_model"]["measures"]
    detail = c.get("/api/models/sample_model").json()
    assert detail["facts"] and detail["dimensions"]

    # A model file is code; the model says where its data is kept, and the
    # connector list includes connectors that only live inside a model.
    [conn] = detail["connector_details"]
    assert conn["storage"]["kind"] == "file" and conn["storage"]["exists"] is True
    assert conn["storage"]["where"].endswith("warehouse.duckdb")
    [listed_conn] = c.get("/api/connectors").json()
    assert listed_conn["name"] == conn["name"] and listed_conn["used_by"] == ["sample_model"]

    fact = detail["facts"][0]["name"]
    q = c.post("/api/models/sample_model/query", json={
        "fact": fact, "measures": ["revenue"], "dimensions": ["dim_region.region"]})
    assert q.status_code == 200, q.text
    rows = q.json()["data"]
    assert q.json()["rows"] == len(rows) == 4  # the four sample regions
    assert round(sum(r["revenue"] for r in rows), 2) == 16888.05
    assert q.json()["lineage"], "an Explore query answers with its lineage"

    bad = c.post("/api/models/sample_model/query", json={
        "fact": fact, "measures": ["no_such_measure"]})
    assert bad.status_code >= 400
    assert "no_such_measure" in bad.text       # the error names what was wrong


def test_an_unknown_report_is_a_clean_404(served):
    assert served.get("/api/reports/nope/built").status_code == 404
    assert served.get("/r/nope").status_code == 404


def test_an_app_modules_own_reports_survive_live_rescans(served, scaffolded):
    """An app module discovers its own reports folder (the demo app does);
    the live rescan watches the project's reports/ and must not forget them
    as "deleted" a few seconds after startup."""
    import shutil

    from tracebi.registry import registry
    from tracebi.web import discovery

    app_reports = scaffolded / "app_reports"
    shutil.copytree(scaffolded / "reports" / "sample_dashboard", app_reports / "app_dashboard")
    discovery.auto_discover(str(app_reports))
    assert "app_dashboard" in [r["name"] for r in registry.list_reports()]

    discovery.rescan("reports", "models", "pipelines")
    assert "app_dashboard" in [r["name"] for r in registry.list_reports()]
    assert served.get("/api/reports/app_dashboard/source").status_code == 200


def test_a_pipeline_names_the_models_it_touches(served):
    """A pipeline can land data from one model and build another; a hand-built
    runner says so with .models, and the app files it under each."""
    from tracebi import PipelineRunner
    from tracebi.registry import registry

    runner = PipelineRunner(db_url="sqlite://")
    runner.model, runner.models = "built_model", ["source_model", "built_model"]
    registry.add_pipeline("hand_built", runner)
    plain = PipelineRunner(db_url="sqlite://")
    registry.add_pipeline("plain", plain)

    listed = {p["pipeline"]: p for p in served.get("/api/pipelines").json()}
    assert listed["hand_built"]["models"] == ["source_model", "built_model"]
    assert listed["hand_built"]["model"] == "built_model"
    assert listed["plain"]["models"] == [] and listed["plain"]["model"] is None


def test_what_the_builder_points_at_reaches_the_agent(served, monkeypatch):
    """Build mode: a click in the app is a pointing file the agent's MCP tool
    reads, so "make this a line chart" means a specific figure."""
    from tracebi.mcp_server import gateway_workbench_state

    point = {"kind": "figure", "figure_kind": "value", "id": "kpi-revenue",
             "binding": "totals", "cell": "revenue", "junk": "dropped"}
    url = "/api/reports/sample_dashboard/workbench/pointing"

    # Off by default: a deployed server cannot be asked to write dev-state.
    monkeypatch.delenv("TRACEBI_DEV_MODE", raising=False)
    assert served.post(url, json=point).status_code == 403
    assert served.get("/api/status").json()["build_mode"] is False

    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    assert served.get("/api/status").json()["build_mode"] is True
    kept = served.post(url, json=point).json()["pointing"]
    assert kept["id"] == "kpi-revenue" and "junk" not in kept

    state = gateway_workbench_state("sample_dashboard")
    assert state["pointing"]["binding"] == "totals"
    assert state["pointing"]["cell"] == "revenue"

    assert served.post(url, json={"kind": "nonsense"}).status_code == 422
    assert served.delete(url).json() == {"pointing": None}
    assert gateway_workbench_state("sample_dashboard")["pointing"] is None
