"""The pipeline journey: ``tracebi new-pipeline`` scaffolds an empty runner,
the analyst fills in a landing layer and a cleaning layer (as the scaffold's
docstring shows), then runs it from the CLI and from the web Pipelines page, and
reads the run history back. The last steps move the reference project's
warehouse to the object tier (``tracebi.yaml``) and run the same pipeline.
"""

import json
import os

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
    code, out = run_cli("new-pipeline", "--python", "Orders ETL")
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


WAREHOUSE_LAYERS = '''
from tracebi import DuckDBConnector, LandingLayer, ManipulationLayer

_wh = DuckDBConnector("orders_wh", database="data/orders_wh.duckdb")
landed = LandingLayer(connector=_wh, source="orders_raw", sink=_wh, sink_table="orders_landed")
cleaned = (ManipulationLayer(source=_wh, source_table="orders_landed", sink=_wh, sink_table="orders_clean")
           .filter("order_id IS NOT NULL")
           .cast({"qty": "int32"})
           .deduplicate(subset=["order_id"])
           .rename({"qty": "units"}))
scored = (ManipulationLayer(source=_wh, source_table="orders_clean", sink=_wh, sink_table="orders_scored")
          .transform(lambda df: df.assign(big=df["units"] >= 10), description="flag big orders"))
runner.register(landed, name="orders_landed")
runner.register(cleaned, name="orders_clean", depends_on="orders_landed")
runner.register(scored, name="orders_scored", depends_on="orders_clean")
'''


def test_a_warehouse_pipeline_runs_in_duckdb_and_names_its_python_step(scaffolded, monkeypatch):
    """Landing and Manipulation over one DuckDB warehouse run as SQL inside it:
    no frame is loaded, each step's lineage carries its SELECT, the first of
    each duplicate is the one kept, and the one Python step says so."""
    import runpy

    import duckdb

    from tracebi import DataSet, DuckDBConnector

    code, out = run_cli("new-pipeline", "--python", "Warehouse ETL")
    assert code == 0, out
    path = scaffolded / "pipelines" / "warehouse_etl.py"
    marker = "runner = PipelineRunner(db_url=_DB_URL)\n"
    path.write_text(path.read_text().replace(marker, marker + WAREHOUSE_LAYERS))
    (scaffolded / "data").mkdir(exist_ok=True)
    raw = duckdb.connect("data/orders_wh.duckdb")
    raw.execute("CREATE TABLE orders_raw AS SELECT * FROM read_csv('inputs/orders.csv')")
    raw.close()

    def no_frame(*args, **kwargs):
        raise AssertionError("a SQL layer loaded the rows into pandas")

    with monkeypatch.context() as m:
        m.setattr(DataSet, "to_pandas", no_frame)
        m.setattr(DuckDBConnector, "load", no_frame)
        code, out = run_cli("run-pipeline", "warehouse_etl", "--layer", "orders_clean", "--refresh")
        assert code == 0, out
        # Twelve rows land; the one with no order id is filtered and order 1009's copy dropped.
        assert "[orders_clean] ✓  12 in → 10 out" in out
        cleaned = runpy.run_path(str(path))["cleaned"].execute()

    load, *steps = [dict(n.metadata) for n in cleaned.lineage]
    assert load["rows_loaded"] == 12 and load["engine"] == "duckdb"
    assert [s["step"] for s in steps] == ["filter", "cast", "deduplicate", "rename"]
    assert all(s["engine"] == "duckdb" and s["sql"].startswith("SELECT ") for s in steps)
    dedupe = steps[2]
    assert dedupe["duplicates_dropped"] == 1
    assert dedupe["sql"] == ('SELECT * FROM "__tb_step_2" QUALIFY row_number() '
                             'OVER (PARTITION BY "order_id" ORDER BY __tb_row) = 1')
    with duckdb.connect("data/orders_wh.duckdb", read_only=True) as wh:
        rows = wh.execute("SELECT order_id, units FROM orders_clean").fetchall()
        units_type = wh.execute("SELECT data_type FROM information_schema.columns "
                                "WHERE table_name = 'orders_clean' AND column_name = 'units'").fetchone()
    # In the source's order, with the cast and the rename applied.
    assert rows[:2] == [(1001, 12), (1002, 8)] and len(rows) == 10 and units_type == ("INTEGER",)

    # A transform(func) step is Python: the layer runs, and its run record says it left SQL.
    code, out = run_cli("run-pipeline", "warehouse_etl")
    assert code == 0, out
    code, out = run_cli("run-pipeline", "warehouse_etl", "--status")
    lines = {line.split()[0]: line for line in out.splitlines() if line.strip()}
    assert "(python escape hatch)" in lines["orders_scored"]
    assert "escape hatch" not in lines["orders_clean"] and "escape hatch" not in lines["orders_landed"]


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
    assert sorted(p["pipeline"] for p in listed) == ["orders_etl", "sample_model"]   # init's own, and this one
    run = c.post("/api/pipelines/orders_etl/layers/orders_bronze/run")
    assert run.status_code == 200, run.text
    history = c.get("/api/pipelines/orders_etl/layers/orders_bronze/history").json()
    assert history["runs"] and history["runs"][0]["status"] == "success"


def test_the_build_step_will_not_rebuild_reports_after_a_failed_transform(scaffolded):
    """`run-pipeline` keeps going after a failure to report them all; the
    model pipeline's build must not turn that into a green rebuild on stale data."""
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


def test_a_run_from_the_command_line_is_in_the_same_list_as_one_from_the_app(pipeline, monkeypatch):
    """`tracebi run-pipeline` used to leave nothing the Transform tab could show:
    a cron job's run was invisible beside the ones started from a button."""
    code, out = run_cli("run-pipeline", "orders_etl")
    assert code == 0, out
    c = serve_app(monkeypatch)

    [ran] = c.get("/api/pipelines/orders_etl/runs").json()
    assert ran["status"] == "succeeded" and ran["layers"] == ["orders_bronze", "orders_silver"]
    assert ran["actor_role"] == "cli" and ran["finished_at"]
    text, done = follow_run(c, "orders_etl", ran["run_id"])
    assert done["status"] == "succeeded" and not done["expired"]
    assert "[orders_silver] ✓  12 in → 11 out" in text
    assert text.rstrip().splitlines()[-1].split("  ", 1)[1].startswith("Run succeeded in")
    assert "[orders_silver] ✓" in out                       # the terminal still gets what it always did

    # `--status` runs nothing, so it records nothing; one layer is a run of its own.
    assert run_cli("run-pipeline", "orders_etl", "--status")[0] == 0
    assert run_cli("run-pipeline", "orders_etl", "--layer", "orders_silver")[0] == 0
    # …and a run from the app lands in the same list, newest first.
    from_app = c.post("/api/pipelines/orders_etl/runs").json()
    follow_run(c, "orders_etl", from_app["run_id"])
    runs = c.get("/api/pipelines/orders_etl/runs").json()
    assert [r["layers"] for r in runs] == [["orders_bronze", "orders_silver"], ["orders_silver"],
                                           ["orders_bronze", "orders_silver"]]
    assert [r["run_id"] for r in runs][0] == from_app["run_id"] and runs[2]["run_id"] == ran["run_id"]


def test_a_failed_command_line_run_is_recorded_as_failed_and_still_runs_the_rest(pipeline, monkeypatch):
    path = pipeline / "pipelines" / "orders_etl.py"
    path.write_text(path.read_text() + '''
def _boom():
    raise ValueError("the warehouse said no")

runner.register_step("boom", _boom, depends_on="orders_silver")
''')
    code, out = run_cli("run-pipeline", "orders_etl")
    assert code == 1 and "[tracebi] boom FAILED: ValueError: the warehouse said no" in out
    c = serve_app(monkeypatch)

    [ran] = c.get("/api/pipelines/orders_etl/runs").json()
    assert ran["status"] == "failed" and "the warehouse said no" in ran["error"]["message"]
    text, done = follow_run(c, "orders_etl", ran["run_id"])
    assert "[orders_silver] ✓" in text and "[tracebi] boom FAILED" in text    # what ran before it, and the failure
    assert text.rstrip().splitlines()[-1].split("  ", 1)[1].startswith("Run failed in")


def test_a_command_line_run_that_is_interrupted_does_not_stay_running(pipeline, monkeypatch):
    """A run stuck at 'running' would keep the Transform tab's Run all disabled for good."""
    path = pipeline / "pipelines" / "orders_etl.py"
    path.write_text(path.read_text() + '''
def _interrupt():
    raise KeyboardInterrupt

runner.register_step("interrupt", _interrupt, depends_on="orders_silver")
''')
    with pytest.raises(KeyboardInterrupt):
        run_cli("run-pipeline", "orders_etl")
    [ran] = serve_app(monkeypatch).get("/api/pipelines/orders_etl/runs").json()
    assert ran["status"] == "failed" and "KeyboardInterrupt" in ran["error"]["exception_type"]


def test_a_refresh_from_the_command_line_does_not_need_the_run_record(pipeline, monkeypatch):
    """The record is a convenience: a state store that cannot be reached must not stop the data refreshing."""
    (pipeline / "blocked").write_text("a file where the store's folder should be")
    monkeypatch.setenv("TRACEBI_STATE_URL", f"sqlite:///{pipeline / 'blocked' / 'state.db'}")
    code, out = run_cli("run-pipeline", "orders_etl")
    assert code == 0, out
    assert "this run is not being recorded" in out and "[orders_silver] ✓" in out


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
    c = serve_app(monkeypatch)

    # A fresh project's Transform tab has a pipeline for its model.
    [pipeline] = c.get("/api/pipelines").json()
    assert (pipeline["pipeline"], pipeline["model"]) == ("sample_model", "sample_model")
    # What the model's Data page says about it: the transform it runs, and its description.
    assert (pipeline["transform"], pipeline["description"]) == (
        "sample_transform", "Rebuild the sample warehouse, then its reports.")
    run = c.post("/api/pipelines/sample_model/runs").json()
    text, done = follow_run(c, "sample_model", run["run_id"])
    assert done["status"] == "succeeded", text
    # The transform ran through `tracebi run-transform`, whose own output used to be thrown away.
    # init's sample is the Python form, and the run says so.
    assert "Running transforms/sample_transform.py (form: python" in text
    [step] = [la for la in c.get("/api/pipelines").json()[0]["layers"] if la["name"] == "transform"]
    assert step["last_detail"] == {"form": "python"}
    # Paths read as the project's own, not the machine's.
    assert "→ output/sample_model/sample_dashboard.html\n" in text
    assert text.index("[transform]") < text.index("[build]")
    # The run says which reports it rebuilt, for the page to link to.
    assert c.get(f"/api/pipelines/sample_model/runs/{run['run_id']}").json()["reports"] == [
        "sample_model/sample_dashboard"]

    # The Code tab shows what ran: the pipeline file, then the transform it starts with.
    code = c.get("/api/pipelines/sample_model/source").json()
    assert [(f["label"], f["path"]) for f in code["files"]] == [
        ("pipeline", "pipelines/sample_model.yaml"), ("transform", "transforms/sample_transform.py")]
    assert "transform: sample_transform" in code["files"][0]["content"] and "sink" in code["files"][1]["content"].lower()
    assert c.get("/api/pipelines/nope/source").status_code == 404


def test_a_sql_transform_runs_top_to_bottom_and_its_contract_beside_it_certifies_the_sink(scaffolded):
    """`new-transform` scaffolds SQL and a contract file; the analyst writes the
    statements (a relative read from inputs/, a sink table, scratch TEMP
    tables), declares checks in YAML, and `run-transform` runs both: a failed
    check refuses the certificate, a passing one records it as the Python
    `with contract(...)` block would."""
    import duckdb

    from tracebi.contracts import read_contracts

    code, out = run_cli("new-transform", "Orders Clean")
    assert code == 0, out
    sql = scaffolded / "transforms" / "orders_clean.sql"
    contract = scaffolded / "transforms" / "orders_clean.contract.yaml"
    assert "(file tier)" in out and sql.is_file() and contract.is_file()
    # The scaffold runs as written (every statement is a comment), declaring nothing.
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 0 and "form: sql" in out, out

    warehouse = str(scaffolded / "data" / "warehouse.duckdb")
    sql.write_text(
        "-- %% read relative to the project root\n"
        "CREATE OR REPLACE TEMP TABLE raw AS\n"
        "SELECT * FROM read_csv('inputs/orders.csv', header = true, all_varchar = true);\n"
        "-- %% sink: a table that is not TEMP lands in the warehouse\n"
        "CREATE OR REPLACE TABLE fact_orders AS\n"
        "SELECT CAST(order_id AS BIGINT) AS order_id,\n"
        "       TRY_CAST(regexp_replace(revenue, '[^0-9.]', '', 'g') AS DOUBLE) AS revenue,\n"
        "       '{{ root }}' AS loaded_from\n"
        "FROM raw QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY order_id) = 1;\n")
    contract.write_text(
        "name: orders\nnote: deduped on order_id\nchecks:\n"
        "  - unique: fact_orders\n    columns: [order_id]\n"
        "  - rows: fact_orders\n    at_least: 1000\n    note: a full month\n")
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 1 and "did not satisfy contract 'orders'" in out and "rows(fact_orders" in out, out
    assert "orders" not in ((read_contracts(warehouse) or {}).get("transforms") or {})

    contract.write_text(contract.read_text().replace("at_least: 1000", "at_least: 1"))
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 0, out
    rec = read_contracts(warehouse)["transforms"]["orders"]
    assert rec["note"] == "deduped on order_id" and set(rec["tables"]) == {"fact_orders"}
    assert [(c["check"], c["params"], c.get("note")) for c in rec["checks"]] == [
        ("unique", {"columns": ["order_id"]}, None), ("rows", {"at_least": 1}, "a full month")]
    con = duckdb.connect(warehouse, read_only=True)
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        [(loaded_from,)] = con.execute("SELECT DISTINCT loaded_from FROM fact_orders").fetchall()
    finally:
        con.close()
    assert "fact_orders" in tables and "raw" not in tables       # TEMP is scratch
    assert loaded_from == os.path.abspath(os.getcwd())            # {{ root }}: the project root

    # A check outside the closed vocabulary, and a placeholder that is not one, are named.
    contract.write_text("checks:\n  - looks_right: fact_orders\n")
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 1 and "checks[0] must name exactly one check" in out, out
    contract.unlink()
    sql.write_text(sql.read_text() + "SELECT '{{ warehouse }}';\n")
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 1 and "{{ warehouse }} is not a placeholder" in out, out

    # Two forms of one name are one transform too many.
    (scaffolded / "transforms" / "orders_clean.py").write_text("print('pandas')\n")
    code, out = run_cli("run-transform", "orders_clean")
    assert code == 1 and "orders_clean.sql and " in out and "orders_clean.py" in out, out


def test_a_run_lists_only_the_reports_it_actually_rebuilt(scaffolded, monkeypatch):
    folder = scaffolded / "reports" / "sample_model"               # init's layout: the model's reports
    (folder / "zz_broken").mkdir()                                  # built after the good one, and fails
    (folder / "zz_broken" / "report.json").write_text("{not json")
    c = serve_app(monkeypatch)

    def run(layer=None):
        started = c.post("/api/pipelines/sample_model/runs", params={"layer": layer} if layer else {}).json()
        follow_run(c, "sample_model", started["run_id"])
        return c.get(f"/api/pipelines/sample_model/runs/{started['run_id']}").json()

    stopped = run()
    assert stopped["status"] == "failed" and stopped["reports"] == ["sample_model/sample_dashboard"]
    # A run that never reached the build step rebuilt nothing.
    assert run("transform")["reports"] == []


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
    # Every report of the model, and none of another model's.
    from tracebi.pipeline.model_pipeline import reports_of
    rebuilt = c.get(f"/api/pipelines/portfolio_model/runs/{run['run_id']}").json()["reports"]
    assert len(rebuilt) > 1 and sorted(rebuilt) == reports_of("portfolio_model")

    # The reference transform is SQL: the run records the form, the Transform
    # tab's Code view shows the SQL and the contract beside it, and --status names it.
    assert "Running transforms/holdings_transform.sql (form: sql" in text
    [pipe] = [p for p in c.get("/api/pipelines").json() if p["pipeline"] == "portfolio_model"]
    assert {la["name"]: la["last_detail"] for la in pipe["layers"]}["transform"] == {"form": "sql"}
    code = c.get("/api/pipelines/portfolio_model/source").json()
    assert [(f["label"], f["path"], f["language"]) for f in code["files"]][1:] == [
        ("transform", "transforms/holdings_transform.sql", "sql"),
        ("contract", "transforms/holdings_transform.contract.yaml", "text")]
    status, out = run_cli("run-pipeline", "portfolio_model", "--status")
    assert status == 0 and "(form: sql)" in out, out


def test_a_model_and_its_connector_show_the_file_that_declares_them(reference, monkeypatch):
    from tracebi import DataModel
    from tracebi.registry import registry

    c = serve_app(monkeypatch, models=True)
    code = c.get("/api/models/portfolio_model/source").json()
    assert [f["path"] for f in code["files"]] == ["models/portfolio_model.yaml"]
    assert "measures:" in code["files"][0]["content"] and not code["files"][0]["truncated"]
    # A connector is declared in the model files that read it: every model here reads this warehouse.
    shared = c.get("/api/connectors/warehouse/source").json()
    assert sorted(f["path"] for f in shared["files"]) == [
        "models/housing_model.yaml", "models/portfolio_model.yaml", "models/saas_model.yaml",
        "models/wealth_model.yaml"]
    # A model registered in code has no file, and says so rather than showing nothing.
    registry.add_model(DataModel("in_code"))
    nothing = c.get("/api/models/in_code/source").json()
    assert nothing["files"] == [] and "Python code" in nothing["hint"]
    assert c.get("/api/models/nope/source").status_code == 404


def _object_tier_journey(proj, monkeypatch, warehouse_block, rewrite):
    """One tracebi.yaml block moves the reference project's warehouse to the
    object tier: the pipeline's transform sinks one Parquet file per table and
    the certificate beside them, the model reads them where they lie, a
    report built from them reproduces, and a file rewritten behind the
    transform's back reads stale. Returns the warehouse."""
    from tracebi.project_config import warehouse

    (proj / "tracebi.yaml").write_text(warehouse_block)
    wh = warehouse(str(proj))
    code, out = run_cli("run-pipeline", "portfolio_model", "--layer", "transform")
    assert code == 0, out
    assert not (proj / "data" / "warehouse.duckdb").exists()
    rec = json.loads(wh.read_text(wh.certificate))["transforms"]["holdings"]
    assert rec["engine_version"] and set(rec["objects"]) == set(rec["tables"])
    fact = rec["objects"]["fact_holdings"]
    assert fact["path"] == wh.table_path("fact_holdings") and fact["size"] > 0

    # The model reads the Parquet in place, through the locked query connection.
    name = "portfolio_model/portfolio_overview"
    code, out = run_cli("report", "build", name)
    assert code == 0, out
    manifest = proj / "output" / f"{name}.html.manifest.json"
    contracts = json.loads(manifest.read_text())["transform_contracts"]
    assert contracts and {v["status"] for v in contracts.values()} == {"satisfied"}
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 0 and "REPRODUCES" in out, out

    # The Warehouse tab reads the tier too.
    c = serve_app(monkeypatch, models=True)
    view = c.get("/api/connectors/warehouse/warehouse").json()
    assert view["supported"] and view["exists"]
    assert {t["name"]: t["contract"]["status"] for t in view["tables"]}["fact_holdings"] == "satisfied"

    rewrite(wh, "dim_fund")
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 1, out
    assert "dim_fund" in out and ("REWRITTEN" in out or "CHANGED" in out), out
    return wh


def test_the_object_tier_sinks_parquet_the_model_reads_in_place(reference, monkeypatch):
    """The object tier on a local directory: no S3 needed, the same code path
    (views over read_parquet, COPY … TO, the certificate inside the prefix)."""
    import time

    def rewrite_same_bytes(wh, table):
        # Identical bytes, written again: the file's size and modification
        # time are what a directory can offer, so the stamp alone reads stale.
        path = wh.table_path(table)
        data = open(path, "rb").read()
        time.sleep(0.01)
        with open(path, "wb") as fh:
            fh.write(data)

    wh = _object_tier_journey(reference, monkeypatch,
                              "warehouse:\n  tier: object\n  location: data/lake\n",
                              rewrite_same_bytes)
    assert sorted(p.name for p in (reference / "data" / "lake").iterdir()) == [
        "_contracts.json", "dim_date.parquet", "dim_flow_type.parquet", "dim_fund.parquet",
        "dim_issuer.parquet", "dim_rating.parquet", "fact_cashflows.parquet",
        "fact_holdings.parquet"]   # the CRM source it read lands nowhere
    from tracebi.contracts import check_fingerprints
    [row] = [r for r in check_fingerprints(wh.sink) if r["table"] == "dim_fund"]
    assert row["rewritten"] and row["current"] == row["recorded"] and not row["matches"]


def test_the_object_tier_on_an_s3_endpoint(reference, monkeypatch):
    """The same journey against a local S3-compatible endpoint (moto), through
    httpfs and a temporary secret; the certificate records each object's
    ETag. Skipped, saying why, where httpfs or moto is not installed."""
    import urllib.request

    import duckdb

    try:
        duckdb.connect().execute("LOAD httpfs")
    except duckdb.Error:
        pytest.skip("DuckDB's httpfs extension is not installed here; the "
                    "local-directory object tier journey covers the same code path")
    server_mod = pytest.importorskip(
        "moto.server", reason="moto[server] is not installed: no local S3 endpoint")
    server = server_mod.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    try:
        host, port = server.get_host_and_port()
        endpoint = f"http://{host}:{port}"
        urllib.request.urlopen(urllib.request.Request(f"{endpoint}/tbjourney", method="PUT"))
        monkeypatch.setenv("TB_S3_KEY", "testing")
        monkeypatch.setenv("TB_S3_SECRET", "testing")

        def rewrite_fewer_rows(wh, table):
            con = wh.connect(write=True)
            try:
                con.execute(f"CREATE TEMP TABLE t AS SELECT * FROM "
                            f"read_parquet('{wh.table_path(table)}') LIMIT 1")
                con.execute(f"COPY t TO '{wh.table_path(table)}' (FORMAT PARQUET)")
            finally:
                con.close()

        wh = _object_tier_journey(reference, monkeypatch, (
            "warehouse:\n  tier: object\n  location: s3://tbjourney/portfolio\n"
            f"  endpoint: {endpoint}\n  region: us-east-1\n  url_style: path\n"
            "  key_id: ${TB_S3_KEY}\n  secret: ${TB_S3_SECRET}\n"), rewrite_fewer_rows)
        rec = json.loads(wh.read_text(wh.certificate))["transforms"]["holdings"]
        assert rec["objects"]["fact_holdings"]["version_by"] == "etag"
    finally:
        server.stop()
