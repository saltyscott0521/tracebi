"""The pipeline journey: ``tracebi new-pipeline`` scaffolds an empty runner,
the analyst fills in a landing layer and a cleaning layer (as the scaffold's
docstring shows), then runs it from the CLI and from the web Pipelines page, and
reads the run history back.
"""

import pytest

from tests.e2e.conftest import follow_run, run_cli, serve_app

LAYERS = '''
from tracebi import CSVConnector, SQLConnector
from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer

_raw = CSVConnector("raw", directory="inputs")
_db = SQLConnector("orders_db", url=_DB_URL)
runner.register(BronzeLayer(connector=_raw, source="orders.csv", sink=_db,
                            sink_table="orders_bronze"), name="orders_bronze")
runner.register(SilverLayer(source=_db, source_table="orders_bronze", sink=_db,
                            sink_table="orders_silver").deduplicate(subset=["order_id"]),
                name="orders_silver", depends_on="orders_bronze")
'''


@pytest.fixture
def pipeline(scaffolded):
    code, out = run_cli("new-pipeline", "Orders ETL")
    assert code == 0, out
    path = scaffolded / "pipelines" / "orders_etl.py"
    src = path.read_text()
    marker = "runner = PipelineRunner(db_url=_DB_URL)\n"
    assert marker in src, "the scaffold changed shape; update the edit"
    path.write_text(src.replace(marker, marker + LAYERS))
    return scaffolded


def test_a_pipeline_runs_upstream_first_and_records_its_runs(pipeline):
    code, out = run_cli("run-pipeline", "orders_etl")
    assert code == 0, out
    code, out = run_cli("run-pipeline", "orders_etl", "--status")
    assert code == 0, out
    assert "orders_bronze" in out and "orders_silver" in out
    assert out.count("success") >= 2, out

    from tracebi.pipeline_registry import get_runner
    runner = get_runner("orders_etl")
    [landed] = runner.run_history("orders_bronze", limit=1)
    [cleaned] = runner.run_history("orders_silver", limit=1)
    assert landed["status"] == cleaned["status"] == "success"
    # The sample input has twelve rows, one an exact duplicate of order 1009.
    assert (landed["rows_out"], cleaned["rows_out"]) == (12, 11)


def test_the_refresh_page_runs_a_layer_and_shows_its_history(pipeline, monkeypatch):
    from fastapi.testclient import TestClient

    from tracebi.registry import registry
    from tracebi.web import discovery
    from tracebi.web.api.main import app

    for attr in ("_connectors", "_models", "_report_factories",
                 "_scheduled_factories", "_pipelines"):
        monkeypatch.setattr(registry, attr, {})
    monkeypatch.setattr(discovery, "_live_pipelines", set())
    discovery.register_pipelines("pipelines")
    c = TestClient(app)

    listed = c.get("/api/pipelines").json()
    assert [p["pipeline"] for p in listed] == ["orders_etl"]
    run = c.post("/api/pipelines/orders_etl/layers/orders_bronze/run")
    assert run.status_code == 200, run.text
    history = c.get("/api/pipelines/orders_etl/layers/orders_bronze/history").json()
    assert history["runs"] and history["runs"][0]["status"] == "success"


def test_the_build_step_will_not_rebuild_reports_after_a_failed_transform(scaffolded):
    """`run-pipeline` keeps going after a failure to report them all; the
    model pipeline's build must not turn that into a green rebuild on stale data."""
    import shutil

    # The convention: the sample model's report lives in reports/sample_model/.
    (scaffolded / "reports" / "sample_model").mkdir()
    shutil.move(str(scaffolded / "reports" / "sample_dashboard"),
                str(scaffolded / "reports" / "sample_model" / "sample_dashboard"))
    (scaffolded / "pipelines" / "sample_model.py").write_text(
        "from tracebi import model_pipeline\n"
        "runner = model_pipeline('sample_model', transform='sample_transform')\n")

    code, out = run_cli("run-pipeline", "sample_model")
    assert code == 0, out
    assert (scaffolded / "output" / "sample_model" / "sample_dashboard.html").is_file()

    (scaffolded / "transforms" / "sample_transform.py").write_text("raise SystemExit('broken')\n")   # a script that exits, not raises
    code, out = run_cli("run-pipeline", "sample_model")
    assert code != 0
    assert "transform" in out and "not rebuilding reports" in out


def test_the_refresh_page_follows_a_run_as_a_log(pipeline, monkeypatch):
    c = serve_app(monkeypatch)

    started = c.post("/api/pipelines/orders_etl/runs")
    assert started.status_code == 202, started.text
    run = started.json()
    assert run["status"] == "running" and run["layers"] == ["orders_bronze", "orders_silver"]

    text, done = follow_run(c, "orders_etl", run["run_id"])
    assert done["status"] == "succeeded", text
    # What the runner printed, in the order it ran, each line timed.
    assert text.index("[orders_bronze] Running") < text.index("[orders_bronze] ✓  12 in → 12 out")
    assert "[orders_silver] ✓  12 in → 11 out" in text
    assert text.rstrip().splitlines()[-1].endswith("Run succeeded in " + text.rstrip().rsplit(" in ", 1)[1])
    # Asking again from the end of the log finds nothing new, and says it is done.
    again = c.get(f"/api/pipelines/orders_etl/runs/{run['run_id']}/log", params={"after": done["next"]}).json()
    assert (again["text"], again["done"]) == ("", True)

    # The layers recorded their runs as they always do, and the run is in the store.
    [landed] = c.get("/api/pipelines/orders_etl/layers/orders_bronze/history").json()["runs"][:1]
    assert landed["status"] == "success"
    assert [r["run_id"] for r in c.get("/api/pipelines/orders_etl/runs").json()] == [run["run_id"]]
    assert [r["status"] for r in c.get("/api/runs", params={"kind": "pipeline_run"}).json()] == ["succeeded"]

    # One layer, from its node on the flow.
    one = c.post("/api/pipelines/orders_etl/runs", params={"layer": "orders_silver"}).json()
    assert one["layers"] == ["orders_silver"]
    text, done = follow_run(c, "orders_etl", one["run_id"])
    assert done["status"] == "succeeded" and "[orders_bronze]" not in text


def test_a_failed_run_says_where_and_why_and_a_second_click_joins_the_first(pipeline, monkeypatch):
    path = pipeline / "pipelines" / "orders_etl.py"
    path.write_text(path.read_text() + '''
def _boom():
    import os, time
    print("waiting at the gate")
    give_up = time.monotonic() + 20           # a failing test must not leave this spinning
    while not os.path.exists("gate.txt") and time.monotonic() < give_up:
        time.sleep(0.02)
    raise ValueError("the warehouse said no")

runner.register_step("boom", _boom, depends_on="orders_silver")
''')
    c = serve_app(monkeypatch)

    first = c.post("/api/pipelines/orders_etl/runs").json()
    second = c.post("/api/pipelines/orders_etl/runs").json()
    assert second["run_id"] == first["run_id"] and second["already_running"] is True

    (pipeline / "gate.txt").write_text("open")
    text, done = follow_run(c, "orders_etl", first["run_id"])
    assert done["status"] == "failed"
    assert "waiting at the gate" in text                    # a step's own print() is in the log
    assert "[boom] ✗  the warehouse said no" in text and text.rstrip().splitlines()[-1].split("  ", 1)[1].startswith("Run failed in")
    status = c.get(f"/api/pipelines/orders_etl/runs/{first['run_id']}").json()
    assert "the warehouse said no" in status["error"]["message"]
    # The failed run is over, so the next click starts a fresh one.
    again = c.post("/api/pipelines/orders_etl/runs", params={"layer": "orders_bronze"}).json()
    assert again["run_id"] != first["run_id"] and again["already_running"] is False
    follow_run(c, "orders_etl", again["run_id"])
    # Nothing here is another pipeline's run.
    assert c.get(f"/api/pipelines/orders_etl/runs/{first['run_id']}/log").status_code == 200
    assert c.get("/api/pipelines/orders_etl/runs/nope/log").status_code == 404
    assert c.post("/api/pipelines/nope/runs").status_code == 404
    assert c.post("/api/pipelines/orders_etl/runs", params={"layer": "nope"}).status_code == 404


def test_a_model_pipelines_log_includes_what_its_transform_printed(scaffolded, monkeypatch):
    import shutil

    (scaffolded / "reports" / "sample_model").mkdir()
    shutil.move(str(scaffolded / "reports" / "sample_dashboard"),
                str(scaffolded / "reports" / "sample_model" / "sample_dashboard"))
    (scaffolded / "pipelines" / "sample_model.py").write_text(
        "from tracebi import model_pipeline\n"
        "runner = model_pipeline('sample_model', transform='sample_transform')\n")
    c = serve_app(monkeypatch)

    run = c.post("/api/pipelines/sample_model/runs").json()
    text, done = follow_run(c, "sample_model", run["run_id"])
    assert done["status"] == "succeeded", text
    # The transform ran through `tracebi run-transform`, whose own output used to be thrown away.
    assert "Running transforms/sample_transform.py" in text
    assert text.index("[transform]") < text.index("[build]")


def test_the_app_refreshes_a_model_while_another_model_holds_the_same_warehouse_open(reference, monkeypatch):
    """portfolio_model and saas_model sink into one warehouse file. Listing the
    models in the app opens it read-only for both; a refresh of one must still
    be able to rewrite it."""
    for transform in ("holdings_transform", "saas_transform", "affordability_transform"):
        code, out = run_cli("run-transform", transform)
        assert code == 0, out
    c = serve_app(monkeypatch, models=True)
    assert c.get("/api/models").status_code == 200

    run = c.post("/api/pipelines/portfolio_model/runs").json()
    text, done = follow_run(c, "portfolio_model", run["run_id"])
    assert done["status"] == "succeeded", text
    assert "[transform] ✓" in text and "[build] ✓" in text
