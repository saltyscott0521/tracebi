"""The web journey: a scaffolded project served by the real FastAPI app.

Discovery is driven the way the running server drives it (the live-discovery
rescan), then a reader walks the pages and API calls the UI makes: status,
the report list, a run, the built page and its share link, downloads, source,
lineage, the model browser and an Explore query. The process-wide registry is
swapped for an empty one for the journey and restored after.
"""

import json
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
    assert "sample_model/sample_dashboard" in found["added"], found
    return TestClient(app)


def test_a_reader_opens_runs_shares_and_downloads_a_report(served):
    c = served
    assert c.get("/api/health").status_code == 200
    status = c.get("/api/status").json()
    assert "version" in status

    names = [r["name"] for r in c.get("/api/reports").json()]
    assert "sample_model/sample_dashboard" in names

    run = c.post("/api/reports/sample_model/sample_dashboard/run")
    assert run.status_code == 200, run.text
    body = run.json()
    assert "<html" in body["html"].lower()
    assert body["manifest"]["figures"], "a run returns its receipt"

    built = c.get("/api/reports/sample_model/sample_dashboard/built")
    assert built.status_code == 200 and "<html" in built.json()["html"].lower()

    share = c.get("/r/sample_model/sample_dashboard")
    assert share.status_code == 200
    assert share.headers["content-type"].startswith("text/html")
    assert "tracebi-receipt" in share.text

    html = c.get("/api/reports/sample_model/sample_dashboard/download?format=html")
    assert html.status_code == 200 and "tracebi-receipt" in html.text
    xlsx = c.get("/api/reports/sample_model/sample_dashboard/download?format=xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"   # a zip = xlsx

    source = c.get("/api/reports/sample_model/sample_dashboard/source").json()
    assert source, "the report's source files are served"
    # Lineage is read from the last build's receipt: transform → tables →
    # model → queries → figures, each figure under the query it reads.
    lineage = c.get("/api/reports/sample_model/sample_dashboard/lineage")
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
    start = c.post("/api/reports/sample_model/sample_dashboard/runs")
    assert start.status_code == 202, start.text
    run_id = start.json()["run_id"]
    for _ in range(100):
        state = c.get(f"/api/reports/sample_model/sample_dashboard/runs/{run_id}").json()
        if state["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.05)
    assert state["status"] == "succeeded", state
    listed = c.get("/api/reports/sample_model/sample_dashboard/runs").json()
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

    # A table with an empty number still previews: the cell comes back null
    # (JSON has no NaN), not a 500 for the whole table.
    import pandas as pd

    from tracebi import DataModel, MemoryConnector
    from tracebi.registry import registry
    gappy = DataModel("gappy").add_connector(
        MemoryConnector("mem", tables={"t": pd.DataFrame({"x": [1.5, None]})}))
    gappy.add_table("t", connector="mem", source="t")
    registry.add_model(gappy)
    preview = c.get("/api/models/gappy/tables/t/preview")
    assert preview.status_code == 200, preview.text
    assert [r["x"] for r in preview.json()["data"]] == [1.5, None]


def test_the_warehouse_view_says_what_is_there_and_what_was_certified(served, scaffolded):
    """Sources → Warehouse: tables, row counts, profiles, and each table's sink
    contract read honestly — a table changed or added behind the certificate's
    back is stale / no_contract, never green — and the file is not held open."""
    import pandas as pd

    from tracebi.connectors.duckdb_connector import DuckDBConnector

    [conn] = served.get("/api/connectors").json()
    url = f"/api/connectors/{conn['name']}/warehouse"
    wh = served.get(url).json()
    assert wh["supported"] and wh["exists"]
    tables = {t["name"]: t for t in wh["tables"]}
    orders = tables["fact_orders"]
    assert orders["rows"] == 10
    assert orders["profile"]["order_id"]["distinct"] == 10
    assert orders["contract"]["status"] == "satisfied"
    assert orders["contract"]["checks"] > 0
    assert all(t["contract"]["status"] == "satisfied" for t in tables.values())

    # Behind the certificate's back: one table rewritten, one added. Writing
    # here also proves the request held nothing open.
    w = DuckDBConnector("w", database=str(scaffolded / "data" / "warehouse.duckdb"))
    df = w.load("fact_orders")
    w.write(df.iloc[:9], "fact_orders")
    w.write(pd.DataFrame({"x": [1]}), "scratch")
    w.disconnect()
    tables = {t["name"]: t for t in served.get(url).json()["tables"]}
    assert tables["fact_orders"]["rows"] == 9
    assert tables["fact_orders"]["contract"]["status"] == "stale"
    assert tables["scratch"]["contract"] == {"status": "no_contract"}

    # A transform runs right after the call, and re-certifies.
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    tables = {t["name"]: t for t in served.get(url).json()["tables"]}
    assert tables["fact_orders"]["contract"]["status"] == "satisfied"

    assert served.get("/api/connectors/nope/warehouse").status_code == 404


def test_a_warehouse_that_is_not_built_yet_says_so(served, scaffolded):
    [conn] = served.get("/api/connectors").json()
    (scaffolded / "data" / "warehouse.duckdb").unlink()
    wh = served.get(f"/api/connectors/{conn['name']}/warehouse").json()
    assert wh["supported"] and wh["exists"] is False and wh["tables"] == []


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
    shutil.copytree(scaffolded / "reports" / "sample_model" / "sample_dashboard", app_reports / "app_dashboard")
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
    url = "/api/reports/sample_model/sample_dashboard/workbench/pointing"

    # Off by default: a deployed server cannot be asked to write dev-state.
    monkeypatch.delenv("TRACEBI_DEV_MODE", raising=False)
    assert served.post(url, json=point).status_code == 403
    assert served.get("/api/status").json()["build_mode"] is False

    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    assert served.get("/api/status").json()["build_mode"] is True
    kept = served.post(url, json=point).json()["pointing"]
    assert kept["id"] == "kpi-revenue" and "junk" not in kept

    state = gateway_workbench_state("sample_model/sample_dashboard")
    assert state["pointing"]["binding"] == "totals"
    assert state["pointing"]["cell"] == "revenue"

    assert served.post(url, json={"kind": "nonsense"}).status_code == 422
    assert served.delete(url).json() == {"pointing": None}
    assert gateway_workbench_state("sample_model/sample_dashboard")["pointing"] is None


def test_the_workbench_in_the_app_shows_what_the_agent_did(served, monkeypatch, scaffolded):
    """Build mode's pane is a live view: the version moves when the agent edits the
    package or leaves a pin, the preview is the working state, and what the agent
    resolved comes back in the state."""
    from tracebi.mcp_server import gateway_resolve_pin, gateway_workbench_state
    from tracebi.workbench import add_pin, workbench_dir

    base = "/api/reports/sample_model/sample_dashboard/workbench"
    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")

    v1 = served.get(f"{base}/version").json()["version"]
    assert served.get(f"{base}/version").json()["version"] == v1          # stable when nothing changed

    # The live preview is the working state, rendered in memory (not a build).
    preview = served.get(f"{base}/preview")
    assert preview.status_code == 200 and "<html" in preview.text.lower()
    assert not list((scaffolded / "output").rglob("sample_dashboard*")), "a preview is not a build"

    # A note left here is a pin the agent reads over MCP, and it moves the version.
    note = served.post(f"{base}/note", json={"note": "split this by region"}).json()["pin"]
    assert note["kind"] == "message" and note["note"] == "split this by region"
    assert served.get(f"{base}/version").json()["version"] != v1
    assert [p["note"] for p in gateway_workbench_state("sample_model/sample_dashboard")["pins"]] \
        == ["split this by region"]
    assert gateway_resolve_pin("sample_model/sample_dashboard", note["id"], "done")["ok"]
    assert served.post(f"{base}/note", json={"note": "  "}).status_code == 422
    v1 = served.get(f"{base}/version").json()["version"]

    # A pin (left from the workbench or the CLI) moves the version; the agent
    # resolves it over MCP and the pane's state shows the answer.
    wb = workbench_dir(str(scaffolded), "sample_model/sample_dashboard")
    add_pin(wb, "val-total", note="make this a line chart")
    assert served.get(f"{base}/version").json()["version"] != v1
    assert gateway_resolve_pin("sample_model/sample_dashboard", "val-total", "made it a line")["ok"]
    state = served.get(f"{base}/state").json()
    assert state["pins"] == [] and state["resolved"][-1]["resolved_note"] == "made it a line"

    # Editing the package moves the version: that is how the pane knows to refresh.
    v2 = served.get(f"{base}/version").json()["version"]
    (scaffolded / "reports" / "sample_model" / "sample_dashboard" / "style.css").open("a").write("\n/* edit */\n")
    assert served.get(f"{base}/version").json()["version"] != v2


def test_a_transform_reruns_while_the_dev_app_is_open(served, monkeypatch, scaffolded):
    """The building loop: the app is open in dev mode beside an agent that
    re-runs the transform from the terminal (another process). The app must not
    hold the warehouse between requests, or the transform cannot write it."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    c = served
    fact = c.get("/api/models/sample_model").json()["facts"][0]["name"]
    asked = c.post("/api/models/sample_model/query", json={"fact": fact, "measures": ["revenue"]})
    assert asked.status_code == 200, asked.text            # the app has read the warehouse

    repo = Path(__file__).resolve().parents[2]
    rerun = subprocess.run(
        [sys.executable, "-m", "tracebi.cli", "run-transform", "sample_transform"],
        cwd=scaffolded, env={**os.environ, "PYTHONPATH": str(repo)},
        capture_output=True, text=True, timeout=120)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    # ...and the app still answers from the rewritten warehouse.
    assert c.post("/api/models/sample_model/query",
                  json={"fact": fact, "measures": ["revenue"]}).status_code == 200


def test_the_build_panel_reads_the_data_and_the_checks(served, monkeypatch, scaffolded):
    """What the classic workbench's Figures & data tab showed, from the app: each binding
    with its model, size, the figures that read it and a few rows, plus the three
    checks (unbound figures, unused bindings, numbers typed outside figures)."""
    import json

    from tracebi.workbench import discovery_dir, heartbeat, read_exhibits

    pkg = scaffolded / "reports" / "sample_model" / "sample_dashboard"
    url = "/api/reports/sample_model/sample_dashboard/workbench/state"
    spec = json.loads((pkg / "report.json").read_text())
    spec["data"]["spare"] = {"model": "sample_model",
                             "query": {"fact": "fact_orders", "measures": ["revenue"]}}
    (pkg / "report.json").write_text(json.dumps(spec))
    template = (pkg / "template.html").read_text()
    (pkg / "template.html").write_text(template.replace(
        "Prose numbers can be bound too; never type one in.", "We took 1250 orders."))
    # report.py runs to describe the report; its show() must not reach the project
    # feed, which a live dev server keeps open for scripts.
    (pkg / "report.py").write_text(
        "from tracebi.workbench import show\n"
        "def build(frames):\n    show('from report.py')\n    return {}\n")
    monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
    heartbeat(discovery_dir(str(scaffolded)))

    monkeypatch.delenv("TRACEBI_DEV_MODE", raising=False)
    assert served.get(url).status_code == 403
    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    state = served.get(url).json()
    assert read_exhibits(discovery_dir(str(scaffolded))) == [], "reading state is not an exhibit"

    data = {b["name"]: b for b in state["bindings"]}
    assert set(data) == {"kpis", "top_region", "by_region", "region_detail", "spare"}
    kpis = data["kpis"]
    assert kpis["model"] == "sample_model" and kpis["rows"] == 1
    assert kpis["columns"] == ["revenue", "orders", "units"] and "kpi-revenue" in kpis["used_by"]
    assert 0 < len(data["by_region"]["sample"]) <= 5, "a few rows, not the table"
    assert state["checks"] == {"unbound_figures": [], "unused_bindings": ["spare"],
                               "numbers_outside_figures": 1}

    # A binding that stops running leaves its figures with no data behind them.
    spec["data"]["kpis"]["query"]["measures"] = ["no_such_measure"]
    (pkg / "report.json").write_text(json.dumps(spec))
    state = served.get(url).json()
    assert "kpis" in [b["binding"] for b in state["broken"]]
    assert "kpi-revenue" in state["checks"]["unbound_figures"]
    assert {b["name"]: b for b in state["bindings"]}["kpis"]["error"]


def test_the_project_feed_carries_the_agents_exhibits_before_any_report(served, monkeypatch, scaffolded):
    """With no report open the agent's exhibits and the person's notes live in the
    project feed. A script's show() reaches it with no setup while the dev app is
    up, the person's note reaches the agent over MCP, and none of it answers
    outside dev mode."""
    import pandas as pd

    from tracebi.mcp_server import gateway_workbench_state
    from tracebi.workbench import show

    feed = "/api/workbench/project"
    monkeypatch.delenv("TRACEBI_DEV_MODE", raising=False)
    monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
    assert served.get(feed).status_code == 403
    assert served.post(f"{feed}/note", json={"note": "hello"}).status_code == 403

    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    with served:                      # the app's startup keeps the feed's heartbeat live
        assert served.get(feed).json()["exhibits"] == []
        show(pd.DataFrame({"region": ["East", "West"], "revenue": [10.5, 20.5]}),
             note="revenue by region", name="region_scan")
        shown = served.get(feed).json()["exhibits"]
        assert [(e["name"], e["shape"]) for e in shown] == [("region_scan", [2, 2])]
        assert shown[0]["display"][0]["revenue"] == "10.50", "rows are written as the report would"

        note = served.post(f"{feed}/note", json={"note": "split by fund"}).json()["pin"]
        assert [p["note"] for p in served.get(feed).json()["pins"]] == ["split by fund"]
        agent_sees = gateway_workbench_state()
        assert [p["id"] for p in agent_sees["pins"]] == [note["id"]]
        assert [e["name"] for e in agent_sees["exhibits"]] == ["region_scan"]
        assert served.post(f"{feed}/note", json={"note": "   "}).status_code == 422


def test_the_person_watches_the_agent_work_over_mcp(served, monkeypatch, scaffolded):
    """With the dev app open, what an agent does over the gateway lands in the
    project feed: the query it ran (as a table) and the build it made, or the
    one it was refused. With no app open it posts nothing."""
    import json

    from tracebi import mcp_server as gw

    feed = "/api/workbench/project"
    monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
    fact = gw.gateway_model_info("sample_model")["facts"][0]["name"]
    exhibits = scaffolded / ".tracebi" / "workbench" / "_discovery" / "exhibits.jsonl"

    # No app serving: the gateway still answers, and the feed stays empty.
    assert gw.gateway_query("sample_model", fact, ["revenue"])["ok"]
    assert not exhibits.exists() or not exhibits.read_text().strip()

    monkeypatch.setenv("TRACEBI_DEV_MODE", "1")
    with served:                      # the app's startup keeps the feed's heartbeat live
        asked = gw.gateway_query("sample_model", fact, ["revenue"],
                                 dimensions=["dim_region.region"])
        built = gw.gateway_build_report("sample_model/sample_dashboard")
        refused = gw.gateway_build_report("sample_model/no_such_report")
        assert asked["ok"] and built["ok"] and not refused["ok"]

        shown = served.get(feed).json()["exhibits"]       # newest first
        assert [e["name"] for e in shown] == [
            "agent · build_report", "agent · build_report", "agent · query_model"]
        query = shown[2]
        assert query["shape"] == [asked["row_count"], len(asked["columns"])]
        assert query["note"] == "Queried sample_model: revenue by dim_region.region"
        dim = asked["columns"][0]
        assert [r[dim] for r in query["rows"]] == [r[dim] for r in asked["rows"]]
        assert shown[1]["text"] == ("Built sample_model/sample_dashboard → "
                                    "output/sample_model/sample_dashboard.html")
        assert shown[0]["text"].startswith("Build of sample_model/no_such_report refused: ")
        assert "fingerprint" not in json.dumps(shown), "an exhibit carries no receipt"


def _mcp_call(client, method, params=None, session=None, token="s3cret", id=1):
    """One JSON-RPC request to the app's /mcp: (response, the result or None)."""
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id is not None:
        body["id"] = id
    headers = {"Accept": "application/json, text/event-stream",
               "Authorization": f"Bearer {token}"}
    if session:
        headers["mcp-session-id"] = session
    resp = client.post("/mcp", json=body, headers=headers)
    data = [json.loads(line[5:]) for line in resp.text.splitlines() if line.startswith("data:")]
    return resp, (data[-1].get("result") if data else None)


def _mcp_session(client, token="s3cret"):
    resp, _ = _mcp_call(client, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "journey", "version": "0"}}, token=token)
    session = resp.headers["mcp-session-id"]
    _mcp_call(client, "notifications/initialized", session=session, token=token, id=None)
    return session


def test_the_app_serves_the_agent_gateway_behind_its_token(served):
    """With TRACEBI_MCP_TOKEN set, the app answers MCP at /mcp: a wrong token is
    refused, and with the right one an agent queries the same models the app
    serves."""
    pytest.importorskip("mcp")
    from tracebi.web.api import main

    route = main.serve_gateway("s3cret")
    try:
        with served:                  # the app's lifespan runs the MCP sessions
            assert _mcp_call(served, "initialize", token="wrong")[0].status_code == 401
            session = _mcp_session(served)
            _, info = _mcp_call(served, "tools/call", {
                "name": "describe_model", "arguments": {"model": "sample_model"}}, session=session)
            fact = info["structuredContent"]["facts"][0]["name"]
            _, asked = _mcp_call(served, "tools/call", {"name": "query_model", "arguments": {
                "model": "sample_model", "fact": fact, "measures": ["revenue"],
                "include_lineage": False}}, session=session)
            assert asked["structuredContent"]["ok"], asked
            assert asked["structuredContent"]["fingerprint"]
    finally:
        main.app.router.routes.remove(route)
        main._mcp_server = None


def test_an_agent_drafts_a_change_the_person_previews_and_publishes_it(served, scaffolded):
    """The remote-authoring loop over the real /mcp and the real app: start a
    draft from a published report, change it, preview it, publish it. The
    published file has the change, the old version is kept, and the Runs list
    says who published."""
    pytest.importorskip("mcp")
    from tracebi.web.api import main

    def call(session, name, **arguments):
        _, got = _mcp_call(served, "tools/call", {"name": name, "arguments": arguments},
                           session=session)
        return got["structuredContent"]

    path = "sample_model/sample_dashboard"
    published = scaffolded / "reports" / path / "template.html"
    route = main.serve_gateway("s3cret")
    try:
        with served:
            session = _mcp_session(served)
            started = call(session, "start_draft", kind="reports", path=path, from_published=True)
            assert started["ok"], started
            assert started["url"] == f"/drafts/agent/reports/{path}"

            html = call(session, "read_draft", kind="reports", path=path)["files"]["template.html"]
            assert html == published.read_text(encoding="utf-8")
            changed = html + "\n<p>a note added in the draft</p>\n"
            assert call(session, "write_draft_file", kind="reports", path=path,
                        file="template.html", content=changed)["ok"]
            assert call(session, "preview_draft", kind="reports", path=path)["ok"]
            refused = call(session, "write_draft_file", kind="reports", path=path,
                           file="report.py", content="print(1)")
            assert not refused["ok"] and "report.py" in refused["errors"][0]

            listed = served.get("/api/drafts").json()["drafts"]
            assert [(d["owner"], d["kind"], d["path"], d["differs_from_published"])
                    for d in listed] == [("agent", "reports", path, True)]
            page = served.get(f"/api/drafts/agent/reports/{path}/preview")
            assert page.status_code == 200
            assert "a note added in the draft" in page.text
            assert page.headers["cache-control"] == "no-store"
            assert "a note added in the draft" not in published.read_text(encoding="utf-8")

            done = call(session, "publish_draft", kind="reports", path=path, note="adds a note")
            assert done["ok"], done
            assert published.read_text(encoding="utf-8") == changed
            kept = scaffolded / ".tracebi" / "history" / "reports" / path / done["version"]
            assert (kept / "template.html").read_text(encoding="utf-8") == html

            rows = served.get("/api/runs", params={"kind": "publish"}).json()
            assert [(r["target"], r["actor"]) for r in rows] == [(f"reports/{path}", "mcp:agent")]
            assert rows[0]["detail"]["note"] == "adds a note"
    finally:
        main.app.router.routes.remove(route)
        main._mcp_server = None
