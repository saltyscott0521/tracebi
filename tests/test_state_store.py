"""One ``tracebi_runs`` table, upgraded in place from a database today's code wrote."""

import sqlite3

from sqlalchemy import inspect

from tracebi.audit import actor
from tracebi.pipeline.runner import PipelineRunner
from tracebi.state import schedule_records, upgrade

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
