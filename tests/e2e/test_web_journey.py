"""The web journey: a scaffolded project served by the real FastAPI app.

Discovery is driven the way the running server drives it (the live-discovery
rescan), then a reader walks the pages and API calls the UI makes: status,
the report list, a run, the built page and its share link, downloads, source,
lineage, the model browser and an Explore query. The process-wide registry is
swapped for an empty one for the journey and restored after.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

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

    listed = {r["name"]: r for r in c.get("/api/reports").json()}
    assert "sample_model/sample_dashboard" in listed
    # A list shows report.json's name; the path stays the identifier.
    assert listed["sample_model/sample_dashboard"]["display_name"] == "Sample Dashboard"
    # A report lists the measures it asks for, from its bindings alone.
    # The report's own calculations (big/small/split) are listed beside the model's.
    assert listed["sample_model/sample_dashboard"]["measures"] == [
        "big_minus_small", "big_orders", "orders", "revenue", "small_orders", "units"]
    # ...and the transform a model's pipeline runs, by the name it is run under.
    pipelines = {p["pipeline"]: p for p in c.get("/api/pipelines").json()}
    assert pipelines["sample_model"]["transform"] == "sample_transform"

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
    # The YAML's label is what people read; name stays the identifier.
    assert listed["sample_model"]["label"] == detail["label"] == "Sample Orders"

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


def test_without_sign_in_a_connection_is_set_up_on_the_server(served, scaffolded):
    """No sign-in makes every caller admin (no lockout), but a connection
    written from the app points the server at a database: refused, naming the
    command, and nothing lands. Catches the write left open on the demo."""
    body = {"name": "bank", "type": "sql", "fields": {"url": "sqlite:///inputs/bank.sqlite"}}
    refused = served.post("/api/connections", json=body)
    assert refused.status_code == 403
    assert "tracebi connect" in refused.json()["detail"]["message"]
    assert not (scaffolded / "connections" / "bank.yaml").exists()
    assert served.post("/api/inputs?name=x.csv", content=b"a\n1\n").status_code == 403
    assert not (scaffolded / "inputs" / "x.csv").exists()
    # The form is still drawn for everyone: reading the types writes nothing.
    types = {t["type"] for t in served.get("/api/connections/types").json()}
    assert {"postgres", "mysql", "sql", "upload"} <= types


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
    assert listed["plain"]["transform"] is None     # a hand-built runner runs no named transform


def test_the_demo_keeps_its_runs_in_the_state_store_not_its_data(served, scaffolded, monkeypatch):
    """The demo app seeds and runs at import with no TRACEBI_DEMO_DB_URL. Its
    runner keeps run history (and, beside it, sessions and tokens) in the
    state store; demo_db holds only the demo's data."""
    import sys

    import sqlalchemy

    from tests.e2e.conftest import follow_run
    import tracebi.web as web_pkg

    monkeypatch.delenv("TRACEBI_DEMO_DB_URL", raising=False)
    monkeypatch.setenv("TRACEBI_DEMO_DB_DIR", str(scaffolded / "data"))
    # A fresh import, so the demo seeds here; whatever was imported before is
    # put back after, so no later test sees this journey's paths.
    saved = {k: m for k, m in sys.modules.items() if k.startswith("tracebi.web.demo_app")}
    had = getattr(web_pkg, "demo_app", None)
    for k in saved:
        del sys.modules[k]
    try:
        import tracebi.web.demo_app  # noqa: F401

        demo = sqlalchemy.inspect(sqlalchemy.create_engine(
            f"sqlite:///{scaffolded / 'data' / 'demo.db'}")).get_table_names()
        assert "orders_raw" in demo and "gold_revenue_by_region" in demo
        # The bank wealth_model reads is in the same database, not in memory.
        assert {"clients", "holdings", "activities"} <= set(demo), demo
        assert not [t for t in demo if t.startswith("tracebi_") or t == "alembic_version"], demo
        listed = served.get("/api/connectors/demo_db/tables").json()
        assert listed["hidden_framework_tables"] == 0

        run = served.post("/api/pipelines/sales/runs").json()
        text, done = follow_run(served, "sales", run["run_id"])
        assert done["status"] == "succeeded", text
        assert run["run_id"] in [r["run_id"] for r in served.get("/api/pipelines/sales/runs").json()]
    finally:
        for k in [k for k in sys.modules if k.startswith("tracebi.web.demo_app")]:
            del sys.modules[k]
        sys.modules.update(saved)
        if had is None:
            web_pkg.__dict__.pop("demo_app", None)
        else:
            web_pkg.demo_app = had


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
    app = (pkg / "app.jsx").read_text()
    (pkg / "app.jsx").write_text(app.replace(
        "Revenue, orders and units across every region.", "We took 1250 orders."))
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
    assert set(data) == {"split", "kpis", "top_region", "by_region", "region_detail", "spare"}
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

    # Ask offers "ask your agent" only when an agent can reach this app.
    assert served.get("/api/status").json()["gateway"] is False
    route = main.serve_gateway("s3cret")
    try:
        assert served.get("/api/status").json()["gateway"] is True
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


def test_a_declarative_model_answers_like_the_python_one(served, scaffolded):
    """models/<name>.json is discovered beside models/*.py and a query through
    it fingerprints exactly like the same query through the Python model."""
    from tracebi import model_registry
    from tracebi.web import discovery

    (scaffolded / "models" / "sample_json.json").write_text(json.dumps({
        "name": "sample_json",
        "connectors": [{"name": "warehouse", "type": "duckdb",
                        "database": "data/warehouse.duckdb"}],
        "tables": [
            {"name": "fact_orders", "connector": "warehouse", "source": "fact_orders"},
            {"name": "dim_region", "connector": "warehouse", "source": "dim_region"}],
        "dimensions": [{"name": "dim_region", "table": "dim_region",
                        "key": "region_id", "attributes": ["region"]}],
        "facts": [{"name": "fact_orders", "table": "fact_orders",
                   "measures": ["revenue", "qty"],
                   "foreign_keys": {"dim_region": "region_id"}}],
        "measures": [
            {"name": "revenue", "column": "revenue", "agg": "sum",
             "description": "Total revenue", "format": "currency0"},
            {"name": "units", "column": "qty", "agg": "sum"},
            {"name": "orders", "column": "order_id", "agg": "count"}],
    }))
    assert "sample_json" in discovery.register_models("models")
    assert "sample_json" in [m["name"] for m in served.get("/api/models").json()]

    query = dict(fact="fact_orders", measures=["revenue", "units"],
                 dimensions=["dim_region.region"])
    via_json = model_registry.get_model("sample_json").query(**query)
    via_python = model_registry.get_model("sample_model").query(**query)
    assert via_json.fingerprint() == via_python.fingerprint()

    # A bad file is a reported failure with its reason, and the others stay up.
    (scaffolded / "models" / "broken.json").write_text(json.dumps(
        {"name": "broken", "measures": [{"name": "m", "agg": "sum", "colum": "x"}]}))
    discovery.register_models("models")
    [entry] = [e for e in served.get("/api/discovery").json()["entries"]
               if e["file"] == "broken.json"]
    assert entry["status"] == "failed" and "measures[0]" in entry["reason"]

    # x.yaml and x.json together: a model is one file, so both are refused.
    (scaffolded / "models" / "sample_model.json").write_text("{}")
    discovery.register_models("models")
    [clash] = [e for e in served.get("/api/discovery").json()["entries"]
               if e["file"] == "sample_model.json"]
    assert clash["status"] == "failed" and "both exist" in clash["reason"]


PYTHON_SAMPLE_MODEL = """\
import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
connector = DuckDBConnector("warehouse", database=os.path.join(ROOT, "data", "warehouse.duckdb"))
model = (
    DataModel("sample_model")
    .add_connector(connector)
    .add_table("fact_orders", connector="warehouse", source="fact_orders")
    .add_table("dim_region", connector="warehouse", source="dim_region")
    .add_dimension("dim_region", table_name="dim_region", key_col="region_id", attributes=["region"])
    .add_fact("fact_orders", table_name="fact_orders", measures=["revenue", "qty"],
              foreign_keys={"dim_region": "region_id"})
    .add_measure("revenue", column="revenue", agg="sum", description="Total revenue", format="currency0")
    .add_measure("units", column="qty", agg="sum", description="Units sold")
    .add_measure("orders", column="order_id", agg="count", description="Order count")
)
"""


def test_a_python_model_migrates_to_yaml_and_answers_identically(scaffolded):
    """`tracebi migrate model` writes the YAML beside the .py (which still
    wins); with the .py moved away the YAML model is discovered and a query
    through it fingerprints exactly like the same query through the Python."""
    from tracebi import model_registry

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    query = dict(fact="fact_orders", measures=["revenue", "units"],
                 dimensions=["dim_region.region"])
    # The scaffold's model is YAML now; stand a Python twin in its place.
    (scaffolded / "models" / "sample_model.yaml").rename(scaffolded / "sample_model.yaml.old")
    (scaffolded / "models" / "sample_model.py").write_text(PYTHON_SAMPLE_MODEL)
    before = model_registry.get_model("sample_model").query(**query).fingerprint()

    code, out = run_cli("migrate", "model", "models/sample_model.py", "--write")
    assert code == 0, out
    assert "still wins" in out
    yaml_file = scaffolded / "models" / "sample_model.yaml"
    assert yaml_file.is_file() and (scaffolded / "models" / "sample_model.py").is_file()

    # The Python file is the user's to remove; here, in the temp project only.
    (scaffolded / "models" / "sample_model.py").rename(scaffolded / "sample_model.py.old")
    fresh = model_registry.ModelRegistry()
    assert fresh.auto_discover("models") == ["sample_model"]
    assert fresh.get("sample_model").query(**query).fingerprint() == before
    fresh.release_all()


def test_the_reference_models_convert_or_refuse_with_a_reason(reference):
    """Every model of the reference project converts; one that cannot be
    expressed is refused with its reason and nothing is written."""
    from tracebi import model_registry
    for name in ("portfolio_model", "housing_model", "saas_model"):
        assert model_registry.get_model(name).name == name
    (reference / "models" / "renamed.py").write_text(
        "from tracebi import DataModel\nmodel = DataModel('Other')\n")
    code, out = run_cli("migrate", "model", "models/renamed.py", "--write")
    assert code == 1 and "is named 'Other'" in out
    assert not (reference / "models" / "renamed.yaml").exists()


def test_a_yaml_model_with_comments_time_grains_and_bins_answers(scaffolded):
    """A commented YAML model declares a month grain and value bins, and a
    query grouped by each answers; a repeated key is refused at discovery with
    its reason."""
    import pandas as pd

    from tracebi import model_registry
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.web import discovery

    warehouse = DuckDBConnector("w", database=str(scaffolded / "data" / "yaml_demo.duckdb"))
    warehouse.write(pd.DataFrame({
        "id": [1, 2, 3, 4],
        "day": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-03", "2024-02-28"]),
        "score": [550, 650, 750, 850]}), "dim_customer")
    warehouse.write(pd.DataFrame({"cust": [1, 2, 3, 4], "amount": [10.0, 20.0, 30.0, 40.0]}),
                    "fact_sales")
    warehouse.disconnect()

    body = """\
# Sales by month and score band.
name: banded
connectors:
  - {name: w, type: duckdb, database: data/yaml_demo.duckdb}
tables:
  - {name: dim_customer, connector: w, source: dim_customer}
  - {name: fact_sales, connector: w, source: fact_sales}
dimensions:
  - {name: dim_customer, table: dim_customer, key: id, attributes: [day, score]}
facts:
  - {name: fact_sales, table: fact_sales, measures: [amount],
     foreign_keys: {dim_customer: cust}}
time_grains:
  - {dimension: dim_customer, name: month, source: day, grain: month}
value_bins:
  - dimension: dim_customer
    name: band
    source: score
    edges: [600, 700, 800]      # four bands
measures:
  # a plain sum: nothing to weight
  - {name: revenue, column: amount, agg: sum}
"""
    (scaffolded / "models" / "banded.yaml").write_text(body)
    assert "banded" in discovery.register_models("models")
    model = model_registry.get_model("banded")
    by_band = model.query(fact="fact_sales", measures=["revenue"],
                          dimensions=["dim_customer.band"]).to_pandas()
    assert sorted(by_band["revenue"]) == [10.0, 20.0, 30.0, 40.0]
    by_month = model.query(fact="fact_sales", measures=["revenue"],
                           dimensions=["dim_customer.month"]).to_pandas()
    assert sorted(by_month["revenue"]) == [30.0, 70.0]

    (scaffolded / "models" / "dup.yaml").write_text("name: dup\nname: dup\n")
    discovery.register_models("models")
    [entry] = [e for e in discovery.discovery_report() if e["file"] == "dup.yaml"]
    assert entry["status"] == "failed" and "duplicate key" in entry["reason"]


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
    published = scaffolded / "reports" / path / "app.jsx"
    route = main.serve_gateway("s3cret")
    try:
        with served:
            session = _mcp_session(served)
            started = call(session, "start_draft", kind="reports", path=path, from_published=True)
            assert started["ok"], started
            assert started["url"] == f"/drafts/agent/reports/{path}"

            html = call(session, "read_draft", kind="reports", path=path)["files"]["app.jsx"]
            assert html == published.read_text(encoding="utf-8")
            changed = html + "\n// a note added in the draft\n"
            assert call(session, "write_draft_file", kind="reports", path=path,
                        file="app.jsx", content=changed)["ok"]
            assert call(session, "preview_draft", kind="reports", path=path)["ok"]
            refused = call(session, "write_draft_file", kind="reports", path=path,
                           file="report.py", content="print(1)")
            assert not refused["ok"] and "report.py" in refused["errors"][0]

            # A script is accepted: it runs only in the reader's sandboxed frame.
            script = 'tracebi.ready(function () { document.title = "scripted"; });\n'
            assert call(session, "write_draft_file", kind="reports", path=path,
                        file="script.js", content=script)["ok"]
            assert call(session, "read_draft", kind="reports", path=path)["files"]["script.js"] == script
            scripted = served.get(f"/api/drafts/agent/reports/{path}/preview")
            assert scripted.status_code == 200 and 'document.title = "scripted"' in scripted.text
            assert scripted.headers["content-security-policy"].startswith("sandbox allow-scripts")
            assert "allow-same-origin" not in scripted.headers["content-security-policy"]

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
            assert (published.parent / "script.js").read_text(encoding="utf-8") == script
            kept = scaffolded / ".tracebi" / "history" / "reports" / path / done["version"]
            assert (kept / "app.jsx").read_text(encoding="utf-8") == html

            rows = served.get("/api/runs", params={"kind": "publish"}).json()
            assert [(r["target"], r["actor"]) for r in rows] == [(f"reports/{path}", "mcp:agent")]
            assert rows[0]["detail"]["note"] == "adds a note"
    finally:
        main.app.router.routes.remove(route)
        main._mcp_server = None


_ASK_JS = Path(__file__).resolve().parents[2] / "web" / "ui" / "src" / "ask.js"


def _ask(fn: str, *args):
    """Call one of Ask's own functions (web/ui/src/ask.js) in node."""
    script = ("import(process.argv[1]).then(A => { const args = JSON.parse(process.argv[2]);"
              f" console.log(JSON.stringify(A.{fn}(...args))) }})")
    done = subprocess.run(["node", "-e", script, _ASK_JS.as_uri(), json.dumps(args)],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_a_question_asked_in_the_app_is_kept_as_a_draft_that_builds(served, scaffolded):
    """Ask, with the page's own code and calls: typed words resolve to the
    model's tokens, a filter value comes from the dimension's values, the
    question runs as a model query, and Keep this starts a draft holding the
    query (never its numbers) whose one-figure app.jsx previews, publishes and
    builds with that figure on its receipt."""
    c = served
    detail = c.get("/api/models/sample_model").json()
    fact = detail["facts"][0]["name"]
    listed = c.get("/api/models/sample_model/dimensions/dim_region.region/values").json()
    values = listed["values"]
    assert listed["total"] == len(values) == 4 and values == sorted(values)
    assert c.get("/api/models/sample_model/dimensions/dim_region.nope/values").status_code == 404

    empty = {"fact": fact, "measures": [], "dimensions": [], "filters": {}}
    q = _ask("resolve", detail, empty, {}, "revenue by region largest", None, None)["q"]
    assert (q["measures"], q["dimensions"]) == (["revenue"], ["dim_region.region"])
    assert q["order_by"] == [{"column": "revenue", "desc": True}]
    assert _ask("sentenceOf", detail, q) == "Revenue by region, largest first"
    body = _ask("requestOf", detail, q)
    answer = c.post("/api/models/sample_model/query", json=body).json()
    assert answer["rows"] == 4 and answer["data"][0]["revenue"] == max(
        r["revenue"] for r in answer["data"])

    # A value of the dimension narrows it; a second question in the same session.
    one = _ask("resolve", detail, q, {"dim_region.region": values}, f"for {values[0]}", None, None)["q"]
    assert one["filters"] == {"dim_region.region": values[0]}
    assert c.post("/api/models/sample_model/query",
                  json=_ask("requestOf", detail, one)).json()["rows"] == 1

    taken = [r["name"] for r in c.get("/api/reports").json()]
    path = _ask("keepPath", "sample_model", q, taken)
    assert path == "sample_model/revenue_by_region"
    files = _ask("keepFiles", {"model": "sample_model", "modelLabel": detail["label"],
                               "detail": detail, "q": q, "rows": answer["rows"]})
    kept = json.loads(files["report.json"])
    assert kept["data"] == {"answer": {"model": "sample_model", "query": body}}
    assert all(f"{r['revenue']:,.0f}" not in files["app.jsx"] for r in answer["data"])

    started = c.post("/api/drafts", json={"kind": "reports", "path": path, "from_published": False})
    assert started.status_code == 201 and started.json()["created"] is True, started.text
    base = f"/api/drafts/anonymous/reports/{path}"
    for name in ("report.json", "app.jsx"):
        assert c.put(f"{base}/files/{name}", json={"content": files[name]}).status_code == 200
    preview = c.get(f"{base}/preview")
    assert preview.status_code == 200, preview.text
    assert c.post(f"{base}/publish", json={"note": "kept from Ask"}).status_code == 200

    code, out = run_cli("report", "build", path)
    assert code == 0, out
    [manifest] = [m for m in (scaffolded / "output").rglob("*.manifest.json")
                  if "revenue_by_region" in m.name]
    receipt = json.loads(manifest.read_text(encoding="utf-8"))
    assert receipt["figures"] == [{"binding": "answer", "id": "fig-answer", "kind": "chart"}]
    [stamped] = receipt["embedded_data"]
    assert (stamped["name"], stamped["query_spec"]["measures"]) == ("answer", ["revenue"])


def test_a_person_starts_edits_previews_and_publishes_a_draft_in_the_app(served, scaffolded):
    """The agent's loop, with the app's own calls: "Edit as a draft" starts the
    signed-in person's copy of a published report (asking again opens the same
    one), a saved file moves the preview and not the library, and publishing
    puts it in the library. Python is refused with the laptop line."""
    c = served
    path = "sample_model/sample_dashboard"
    published = scaffolded / "reports" / path / "app.jsx"
    before = published.read_text(encoding="utf-8")

    started = c.post("/api/drafts", json={"kind": "reports", "path": path, "from_published": True})
    assert started.status_code == 201, started.text
    draft = started.json()
    assert (draft["owner"], draft["kind"], draft["path"]) == ("anonymous", "reports", path)
    assert draft["differs_from_published"] is False and draft["created"] is True
    base = f"/api/drafts/anonymous/reports/{path}"
    version = c.get(f"{base}/version").json()["version"]

    # Asking again is "open my draft": the same one, nothing started over.
    again = c.post("/api/drafts", json={"kind": "reports", "path": path, "from_published": True})
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["updated"] == draft["updated"]

    changed = before + "\n// edited in the app\n"
    saved = c.put(f"{base}/files/app.jsx", json={"content": changed})
    assert saved.status_code == 200, saved.text
    assert saved.json()["differs_from_published"] is True
    assert saved.json()["version"] == c.get(f"{base}/version").json()["version"] != version
    assert c.get(f"{base}/files").json()["files"]["app.jsx"] == changed
    preview = c.get(f"{base}/preview")
    assert preview.status_code == 200 and "edited in the app" in preview.text
    assert published.read_text(encoding="utf-8") == before

    # A file a draft may not hold is refused, and the draft is left as it was.
    refused = c.put(f"{base}/files/report.py", json={"content": "print(1)"})
    assert refused.status_code == 422 and "report.py" in refused.json()["detail"]["message"]

    done = c.post(f"{base}/publish", json={"note": "edited in the app"})
    assert done.status_code == 200, done.text
    assert published.read_text(encoding="utf-8") == changed
    files = c.get(f"/api/reports/{path}/source").json()["files"]
    assert any("edited in the app" in f["content"] for f in files)

    (scaffolded / "models" / "legacy.py").write_text("model = None\n", encoding="utf-8")
    python = c.post("/api/drafts", json={"kind": "models", "path": "legacy"})
    assert python.status_code == 422 and "laptop" in python.json()["detail"]["message"]
    assert [d["path"] for d in c.get("/api/drafts").json()["drafts"]] == [path]


def test_a_report_can_be_drafted_on_a_draft_model_but_publishes_only_after_it(scaffolded):
    """dev → prod ordering: a report draft previews against the agent's draft
    model, but publishing it is refused until that model is published, so
    production never reads a model that only exists in someone's drafts. A
    model draft that does not compile is refused at publish."""
    from tracebi import mcp_server as gw

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    regions = {
        "name": "regions",
        "connectors": [{"name": "warehouse", "type": "duckdb",
                        "database": "data/warehouse.duckdb"}],
        "tables": [
            {"name": "fact_orders", "connector": "warehouse", "source": "fact_orders"},
            {"name": "dim_region", "connector": "warehouse", "source": "dim_region"}],
        "dimensions": [{"name": "dim_region", "table": "dim_region",
                        "key": "region_id", "attributes": ["region"]}],
        "facts": [{"name": "fact_orders", "table": "fact_orders",
                   "measures": ["revenue", "qty"],
                   "foreign_keys": {"dim_region": "region_id"}}],
        "measures": [{"name": "revenue", "column": "revenue", "agg": "summ"},
                     {"name": "units", "column": "qty", "agg": "sum"},
                     {"name": "orders", "column": "order_id", "agg": "count"}],
    }
    assert gw.gateway_start_draft("models", "regions")["ok"]
    gw.gateway_write_draft_file("models", "regions", "regions.json", json.dumps(regions))
    refused = gw.gateway_publish_draft("models", "regions")
    assert not refused["ok"] and "summ" in json.dumps(refused["errors"])
    regions["measures"][0]["agg"] = "sum"
    gw.gateway_write_draft_file("models", "regions", "regions.json", json.dumps(regions))

    report = "sample_model/sample_dashboard"
    assert gw.gateway_start_draft("reports", report, from_published=True)["ok"]
    spec = gw.gateway_read_draft("reports", report)["files"]["report.json"]
    gw.gateway_write_draft_file("reports", report, "report.json",
                                spec.replace('"sample_model"', '"regions"'))
    assert gw.gateway_preview_draft("reports", report)["ok"], "previews on the draft model"
    early = gw.gateway_publish_draft("reports", report)
    assert not early["ok"] and "regions" in json.dumps(early["errors"])

    assert gw.gateway_publish_draft("models", "regions")["ok"]
    assert (scaffolded / "models" / "regions.json").is_file()
    published = gw.gateway_publish_draft("reports", report)
    assert published["ok"], published
    assert '"regions"' in (scaffolded / "reports" / report / "report.json").read_text()


def test_a_model_draft_written_as_yaml_publishes_as_yaml(scaffolded):
    """A model draft may be YAML: it publishes as models/<name>.yaml, and
    writing the JSON form instead replaces the draft's file and, on publish,
    the published one (the old one is kept in history)."""
    from tracebi import mcp_server as gw

    yaml_text = (
        "# the regions\n"
        "name: regions\n"
        "connectors:\n"
        "  - {name: warehouse, type: duckdb, database: data/warehouse.duckdb}\n"
        "tables:\n"
        "  - {name: dim_region, connector: warehouse, source: dim_region}\n")
    assert gw.gateway_start_draft("models", "regions")["ok"]
    assert gw.gateway_write_draft_file("models", "regions", "regions.yaml", yaml_text)["ok"]
    files = gw.gateway_read_draft("models", "regions")["files"]
    assert files == {"regions.yaml": yaml_text}
    assert gw.gateway_publish_draft("models", "regions")["ok"]
    assert (scaffolded / "models" / "regions.yaml").read_text() == yaml_text

    as_json = json.dumps({"name": "regions", "connectors": [
        {"name": "warehouse", "type": "duckdb", "database": "data/warehouse.duckdb"}]})
    gw.gateway_write_draft_file("models", "regions", "regions.json", as_json)
    assert list(gw.gateway_read_draft("models", "regions")["files"]) == ["regions.json"]
    assert gw.gateway_publish_draft("models", "regions")["ok"]
    assert (scaffolded / "models" / "regions.json").is_file()
    assert not (scaffolded / "models" / "regions.yaml").exists()
    kept = list((scaffolded / ".tracebi" / "history" / "models" / "regions").rglob("regions.yaml"))
    assert kept, "the replaced YAML is kept in history"


def test_publishing_a_model_draft_shows_which_reports_it_moves_or_breaks(served, scaffolded):
    """Before a model draft goes live, the app re-runs the published reports'
    recorded queries against it: a measure change lists the figures that move
    (old and new), a report never built is listed and never called unchanged,
    the publish is refused until the impact is accepted, and what was accepted
    is in the publish run. A break needs accepting too."""
    import shutil

    c = served
    path = "sample_model/sample_dashboard"
    code, out = run_cli("report", "build", path)
    assert code == 0, out
    shutil.copytree(scaffolded / "reports" / "sample_model" / "sample_dashboard",
                    scaffolded / "reports" / "sample_model" / "never_built")

    model_file = scaffolded / "models" / "sample_model.yaml"
    published = model_file.read_text(encoding="utf-8")
    base = "/api/drafts/anonymous/models/sample_model"
    assert c.post("/api/drafts", json={"kind": "models", "path": "sample_model"}).status_code == 201

    # Unedited, the draft is the published model: nothing moves, nothing blocks.
    same = c.get(f"{base}/impact").json()
    assert {r["report"]: r["status"] for r in same["reports"]} == {
        path: "unchanged", "sample_model/never_built": "not_built"}
    assert same["needs_acceptance"] is False

    # Revenue becomes an average: the figures that claim it move.
    moved_text = published.replace("column: revenue\n    agg: sum\n    description: Total revenue",
                                   "column: revenue\n    agg: avg\n    description: Total revenue")
    assert moved_text != published
    assert c.put(f"{base}/files/sample_model.yaml", json={"content": moved_text}).status_code == 200
    impact = c.get(f"{base}/impact").json()
    [report] = [r for r in impact["reports"] if r["report"] == path]
    assert report["status"] == "moves" and impact["needs_acceptance"] is True
    [kpi] = [f for m in report["moved"] for f in m["figures"] if f["id"] == "val-revenue-inline"]
    assert kpi["old"] > kpi["new"] > 0
    assert [r["status"] for r in impact["reports"] if r["report"].endswith("never_built")] == ["not_built"]

    refused = c.post(f"{base}/publish", json={"note": "avg"})
    assert refused.status_code == 409
    assert "accept_impact" in refused.json()["detail"]["message"]
    assert refused.json()["detail"]["impact"]["needs_acceptance"] is True
    assert model_file.read_text(encoding="utf-8") == published

    done = c.post(f"{base}/publish", json={"note": "avg", "accept_impact": True})
    assert done.status_code == 200, done.text
    assert model_file.read_text(encoding="utf-8") == moved_text
    [run] = c.get("/api/runs", params={"kind": "publish"}).json()
    accepted = run["detail"]["accepted_impact"]
    assert accepted["summary"]["moves"] == 1
    assert [r["report"] for r in accepted["reports"]] == [path]

    # A measure the report asks for goes away: a break, which also needs accepting.
    broke = moved_text.replace("  - name: orders\n    column: order_id\n    agg: count\n"
                               "    description: Order count\n", "")
    assert broke != moved_text
    assert c.put(f"{base}/files/sample_model.yaml", json={"content": broke}).status_code == 200
    [report] = [r for r in c.get(f"{base}/impact").json()["reports"] if r["report"] == path]
    assert report["status"] == "breaks" and report["broken"][0]["error"]
    refused = c.post(f"{base}/publish", json={})
    assert refused.status_code == 409 and "breaks" in refused.json()["detail"]["message"]
    assert model_file.read_text(encoding="utf-8") == moved_text

    # An agent over MCP sees the same check, and is refused the same way.
    from tracebi import mcp_server as gw
    assert gw.gateway_start_draft("models", "sample_model", True)["ok"]
    gw.gateway_write_draft_file("models", "sample_model", "sample_model.yaml", broke)
    seen = gw.gateway_model_impact("sample_model")["impact"]
    assert [r["status"] for r in seen["reports"] if r["report"] == path] == ["breaks"]
    no = gw.gateway_publish_draft("models", "sample_model")
    assert not no["ok"] and "accept_impact" in no["errors"][0] and no["impact"]["needs_acceptance"]
    assert gw.gateway_publish_draft("models", "sample_model", accept_impact=True)["ok"]
    assert model_file.read_text(encoding="utf-8") == broke


def test_only_a_models_owners_or_an_admin_publish_it_but_anyone_drafts_it(served, scaffolded, monkeypatch):
    """A model that names owners is published only by one of them or an admin
    (HTTP 403, MCP ok:false, owners named). Anyone else still drafts it and
    sees the impact. The owners are the PUBLISHED file's, so a draft that
    adds the analyst cannot let them publish it. No owners: an analyst publishes."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tracebi import mcp_server as gw
    from tracebi.web.api.auth import ProxyHeaderAuthMiddleware
    from tracebi.web.api.routers import drafts as drafts_router

    monkeypatch.setenv("TRACEBI_AUTH_ROLE_HEADER", "X-Role")
    app = FastAPI()
    app.include_router(drafts_router.router, prefix="/api")
    app.add_middleware(ProxyHeaderAuthMiddleware, header="X-User")
    c = TestClient(app)

    def as_(user, role="analyst"):
        return {"X-User": user, "X-Role": role}

    model_file = scaffolded / "models" / "sample_model.yaml"
    plain = model_file.read_text(encoding="utf-8")
    owned = "owners: [olive]\n" + plain
    model_file.write_text(owned, encoding="utf-8")

    def draft(user, text):
        base = f"/api/drafts/{user}/models/sample_model"
        assert c.post("/api/drafts", json={"kind": "models", "path": "sample_model"},
                      headers=as_(user)).status_code in (200, 201)
        assert c.put(f"{base}/files/sample_model.yaml", json={"content": text},
                     headers=as_(user)).status_code == 200
        return base

    # A non-owner drafts, sees the impact, and is refused with the owners named.
    bob = draft("bob", owned + "# bob's change\n")
    assert c.get(f"{bob}/impact", headers=as_("bob")).status_code == 200
    refused = c.post(f"{bob}/publish", json={}, headers=as_("bob"))
    assert refused.status_code == 403 and "olive" in refused.json()["detail"]["message"]
    assert model_file.read_text(encoding="utf-8") == owned

    # A draft that makes bob an owner cannot self-grant: the published file decides.
    sneaky = draft("bob", owned.replace("[olive]", "[olive, bob]"))
    assert c.post(f"{sneaky}/publish", json={}, headers=as_("bob")).status_code == 403
    assert "bob" not in model_file.read_text(encoding="utf-8")

    # An owner and an admin publish.
    olive = draft("olive", owned + "# olive\n")
    assert c.post(f"{olive}/publish", json={}, headers=as_("olive")).status_code == 200
    root = draft("root", owned + "# root\n")
    assert c.post(f"{root}/publish", json={}, headers=as_("root", "admin")).status_code == 200

    # Over MCP the same check refuses a non-owner and allows an owner.
    monkeypatch.setattr(gw, "_caller", lambda: ("bob", "analyst"))
    no = gw.gateway_publish_draft("models", "sample_model")
    assert not no["ok"] and "olive" in no["errors"][0]
    monkeypatch.setattr(gw, "_caller", lambda: ("olive", "analyst"))
    assert gw.gateway_publish_draft("models", "sample_model")["ok"]

    # No owners: an analyst publishes, as before.
    model_file.write_text(plain, encoding="utf-8")
    again = draft("bob", plain + "# bob again\n")
    assert c.post(f"{again}/publish", json={}, headers=as_("bob")).status_code == 200


def test_a_transform_has_a_page_with_its_code_reads_and_tables(reference, monkeypatch):
    """The reads behind /data/transforms/<name>: the listing names the
    transform, its form and the pipeline that runs it; /source gives the file
    and its contract, to be shown side by side; the warehouse says what the
    run read (and how) and what it wrote. A file no pipeline runs and no
    certificate names still answers. The journey drives the API in-process,
    so the page itself is not opened here."""
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
    code, out = run_cli("run-transform", "holdings_transform")
    assert code == 0, out
    discovery.rescan("reports", "models", "pipelines")
    c = TestClient(app)

    listed = {t["name"]: t for t in c.get("/api/transforms").json()}
    holdings = listed["holdings_transform"]
    assert holdings["form"] == "sql" and holdings["pipelines"] == ["portfolio_model"]
    assert "fact_holdings" in holdings["tables"] and holdings["written_at"]
    twin = listed["holdings_transform_pandas"]
    assert twin["pipelines"] == [] and twin["tables"] == [] and twin["written_at"] is None

    files = c.get("/api/transforms/holdings_transform/source").json()["files"]
    assert [f["path"].split("/")[-1] for f in files] == [
        "holdings_transform.sql", "holdings_transform.contract.yaml"]
    assert c.get("/api/transforms/holdings_transform_pandas/source").status_code == 200
    assert c.get("/api/transforms/no_such_transform/source").status_code == 404

    writer = next(wr for w in c.get("/api/warehouse").json()["warehouses"]
                  for wr in w["writers"] if wr["transform"] == "holdings_transform")
    assert sorted(writer["tables"]) == sorted(holdings["tables"])
    # With no CRM configured the committed snapshot stood in, read through
    # the connector: the page names both.
    crm = next(r for r in writer["read"] if r["ref"] == "crm.issuer_ratings")
    assert crm["snapshot"] == "inputs/issuer_ratings.csv" and crm["method"] == "pandas"
