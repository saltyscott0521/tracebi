"""One ``tracebi_runs`` table, upgraded in place from a database today's code wrote."""

import sqlite3

from sqlalchemy import inspect

from tracebi.audit import actor
from tracebi.pipeline.runner import PipelineRunner
from tracebi.state import list_runs, record_run, schedule_records, upgrade

# The table ``_init_db`` left behind before Alembic: actor columns already
# reconciled, none of the shared-store columns yet.
_TODAY = """CREATE TABLE tracebi_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layer_name TEXT NOT NULL,
    layer_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    rows_in INTEGER,
    rows_out INTEGER,
    upstream_run_id INTEGER,
    error_message TEXT,
    actor TEXT,
    actor_role TEXT
)"""


def test_upgrade_of_todays_sqlite_keeps_history(tmp_path):
    db = tmp_path / "today.db"
    con = sqlite3.connect(db)
    con.execute(_TODAY)
    con.execute(
        "INSERT INTO tracebi_runs"
        " (layer_name, layer_type, started_at, status, actor, actor_role)"
        " VALUES ('orders', 'bronze', '2024-01-01T00:00:00+00:00', 'success',"
        "         'ada', 'admin')"
    )
    con.commit()
    con.close()

    url = f"sqlite:///{db}"
    upgrade(url)
    upgrade(url)
    runner = PipelineRunner(db_url=url)
    cols = [c["name"] for c in inspect(runner._engine_()).get_columns("tracebi_runs")]
    assert cols.count("kind") == 1
    assert cols.count("actor") == 1
    row = runner.run_history("orders", limit=1)[0]
    assert row["layer_name"] == "orders"
    assert row["actor"] == "ada"
    assert row["actor_role"] == "admin"
    assert row["status"] == "success"
    assert row["kind"] is None


def test_a_layer_run_is_tagged_and_a_schedule_row_is_not_its_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'runs.db'}"
    record_run(
        kind="schedule", target="step", status="delivered", url=url,
        detail={"report": "step", "status": "delivered"},
    )
    runner = PipelineRunner(db_url=url)
    runner.register_step("step", lambda: 2)
    runner.run("step")
    history = runner.run_history("step")
    assert len(history) == 1
    assert history[0]["kind"] == "pipeline_layer"
    assert history[0]["target"] == "step"
    assert history[0]["finished"] == history[0]["completed_at"]
    assert history[0]["status"] == "success"
    listed = list_runs(kind="schedule", target="step", url=url)
    assert len(listed) == 1
    assert listed[0]["kind"] == "schedule"


def test_memory_runner_records_a_run():
    runner = PipelineRunner(db_url="sqlite:///:memory:")
    runner.register_step("step", lambda: 1)
    runner.run("step")
    assert runner.last_run("step")["rows_out"] == 1


def test_schedule_import_is_idempotent_and_scoped(tmp_path):
    url = f"sqlite:///{tmp_path / 'sched.db'}"
    out = tmp_path / "output"
    out.mkdir()
    (out / "schedule_runs.jsonl").write_text(
        '{"report":"weekly","status":"built","started_at":"t0",'
        '"finished_at":"t1","actor":null}\n'
        "not json\n"
        "{}\n",
        encoding="utf-8",
    )
    with actor("alice", role="admin"):
        first = schedule_records(out, url=url)
        again = schedule_records(out, url=url)
    assert first == again
    assert first == [{
        "report": "weekly",
        "status": "built",
        "started_at": "t0",
        "finished_at": "t1",
        "actor": None,
    }]
    other = tmp_path / "other"
    other.mkdir()
    assert schedule_records(other, url=url) == []
    assert schedule_records(tmp_path / "missing", url=url) == []
