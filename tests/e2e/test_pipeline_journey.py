"""The pipeline journey: ``tracebi new-pipeline`` scaffolds an empty runner,
the analyst fills in a landing layer and a cleaning layer (as the scaffold's
docstring shows), then runs it from the CLI and from the web Refresh page, and
reads the run history back.
"""

import pytest

from tests.e2e.conftest import run_cli

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
