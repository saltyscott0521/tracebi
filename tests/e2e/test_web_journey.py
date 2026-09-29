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
    lineage = c.get("/api/reports/sample_dashboard/lineage")
    assert lineage.status_code == 200


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
