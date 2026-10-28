"""A proposal's dry run is isolated (``tracebi.dryrun``): the security promises
the agent journey cannot pin one by one. It never writes the real warehouse,
a connection, a file or the certificate; it reads no table the allowlist
leaves out, no file outside ``inputs/`` (nor a database file there), no URL,
and attaches nothing else."""

import os
import sqlite3

import pytest

duckdb = pytest.importorskip("duckdb")

from tracebi import dryrun  # noqa: E402

_CHECK = "checks:\n  - rows: t\n"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    for d in ("data", "inputs", "connections", "transforms"):
        (root / d).mkdir(parents=True)
    with duckdb.connect(str(root / "data" / "warehouse.duckdb")) as wh:
        wh.execute("CREATE TABLE dim_r AS SELECT * FROM (VALUES (1, 'one'), (2, 'two')) v(r, label)")
    with sqlite3.connect(root / "inputs" / "shop.sqlite") as db:
        db.executescript("CREATE TABLE orders (id INTEGER, r INTEGER);"
                         "INSERT INTO orders VALUES (1, 1), (2, 2);"
                         "CREATE TABLE salaries (person TEXT, pay REAL);"
                         "INSERT INTO salaries VALUES ('zelda77', 1.0);")
    (root / "connections" / "shop.yaml").write_text(
        "name: shop\ntype: sql\nurl: sqlite:///inputs/shop.sqlite\nagents:\n  tables: [orders]\n")
    (root / "inputs" / "open.csv").write_text("a\n1\n")
    (root / "inputs" / "pay.csv").write_text("person,pay\nzelda77,1\n")
    (root / "connections" / "pay.yaml").write_text("name: pay\ntype: upload\nfile: inputs/pay.csv\n")
    (root / ".env").write_text("SECRET=hunter2\n")
    (tmp_path / "outside.csv").write_text("a\n1\n")
    monkeypatch.chdir(root)
    return root


def _state(root):
    """The real warehouse's file and catalog, and every file the dry run must leave alone."""
    path = root / "data" / "warehouse.duckdb"
    with duckdb.connect(str(path), read_only=True) as wh:
        tables = wh.execute("SELECT table_name, column_name FROM duckdb_columns() "
                            "ORDER BY ALL").fetchall()
        rows = wh.execute("SELECT * FROM dim_r ORDER BY r").fetchall()
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    with sqlite3.connect(root / "inputs" / "shop.sqlite") as db:
        shop = db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
    return path.stat().st_mtime_ns, tables, rows, files, shop


def _run(sql, contract=_CHECK):
    return dryrun.run(sql, contract, "t", dryrun.dryrun_dir("20261028T000000-abcdef"))


def test_a_dry_run_never_writes_the_warehouse_a_connection_or_a_file(workspace):
    before = _state(workspace)
    # A table of the warehouse's own name lands in the scratch copy, and is read there.
    shadow = _run("CREATE OR REPLACE TABLE dim_r AS SELECT 9 AS r, 'nine' AS label;\n"
                  "CREATE OR REPLACE TABLE t AS SELECT * FROM dim_r;")
    assert shadow["ok"] is True, shadow
    assert shadow["tables"][1]["sample"] == [{"r": 9, "label": "nine"}]
    sink = _run("-- source: shop.orders\n-- sink: shop\nCREATE OR REPLACE TABLE t AS "
                "SELECT * FROM shop.orders;")
    assert sink["ok"] is True and sink["not_executed"][0]["what"] == "-- sink: shop"
    copied = _run("CREATE TABLE t AS SELECT 1 AS a;\nCOPY t TO 'inputs/open.csv';\n"
                  "COPY t TO '{{ sink }}';")
    assert copied["ok"] is True and [n["what"] for n in copied["not_executed"]] == ["COPY", "COPY"]
    for sql in ("CREATE OR REPLACE TABLE __tracebi_warehouse.main.dim_r AS SELECT 1 AS r",
                "DROP TABLE dim_r", "INSERT INTO dim_r VALUES (3, 'three')",
                "UPDATE dim_r SET label = 'x'", "EXPORT DATABASE 'inputs/out'"):
        refused = _run(sql)
        assert refused["ok"] is False and refused["error"], sql
    assert _state(workspace) == before
    assert not (workspace / "data" / "warehouse.contracts.json").exists()
    assert not (workspace / ".tracebi" / "dryrun").exists()


@pytest.mark.parametrize("sql", [
    "-- source: shop.salaries\nCREATE TABLE t AS SELECT * FROM shop.salaries",
    "-- source: shop.orders\nCREATE TABLE t AS SELECT * FROM __tracebi_src_shop.main.salaries",
    "CREATE TABLE t AS SELECT * FROM sqlite_scan('inputs/shop.sqlite', 'salaries')",
    "CREATE TABLE t AS SELECT * FROM query('SELECT * FROM sqlite_scan(''inputs/shop.sqlite'', ''salaries'')')",
    "CREATE TABLE t AS SELECT * FROM query_table('__tracebi' || '_src_shop.main.salaries')",
    "ATTACH 'inputs/shop.sqlite' AS s (TYPE sqlite)",
    "ATTACH ':memory:' AS m",
    "CREATE TABLE t AS SELECT * FROM 'inputs/shop.sqlite'",
    "CREATE TABLE t AS SELECT * FROM read_csv('inputs/pay.csv')",
    "CREATE TABLE t AS SELECT * FROM read_text('.env')",
    "CREATE TABLE t AS SELECT * FROM read_text('{{ root }}/.env')",
    "CREATE TABLE t AS SELECT * FROM read_csv('inputs/../../outside.csv')",
    "CREATE TABLE t AS SELECT * FROM read_csv('/etc/passwd')",
    "CREATE TABLE t AS SELECT * FROM read_csv('https://example.com/x.csv')",
    "INSTALL httpfs", "LOAD httpfs",
    "SET enable_external_access = true",
])
def test_a_dry_run_reads_only_what_agents_may_read(workspace, sql):
    out = _run(sql)
    assert out["ok"] is False and out["error"], out
    assert out["tables"] == []
    assert "zelda77" not in str(out) and "hunter2" not in str(out)


def test_a_dry_run_reads_an_allowed_source_an_input_file_and_the_warehouse(workspace):
    out = _run("-- source: shop.orders\nCREATE TABLE t AS SELECT o.id, d.label, f.a "
               "FROM shop.orders o JOIN dim_r d USING (r) CROSS JOIN read_csv('inputs/open.csv') f")
    assert out["ok"] is True, out
    assert out["tables"][0]["rows"] == 2
    assert out["lineage"]["t"]["label"]["from"] == ["dim_r.label"]
    assert out["sources"]["shop.orders"]["rows"] == 2


def test_a_dry_run_is_bounded_by_the_statement_timeout(workspace):
    (workspace / "tracebi.yaml").write_text("engine:\n  query_timeout_s: 1\n")
    out = _run("CREATE TABLE t AS SELECT count(*) FROM range(100000000000) a")
    assert out["ok"] is False and "1 s limit" in out["error"]["message"]
    assert out["elapsed_ms"] < 15000
    assert os.listdir(workspace / "data") == ["warehouse.duckdb"]
