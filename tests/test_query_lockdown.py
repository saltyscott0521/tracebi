"""The query connection reaches nothing outside the warehouse (decision 19).

Security, which a journey cannot pin precisely: a model query, an Explore/Ask
query through the web route and a SQL calculation that reach for a URL, a
file, ``ATTACH``, ``COPY``, ``INSTALL`` or ``LOAD`` are refused by DuckDB
itself, the refusal reaches the caller as the structured error, the settings
cannot be switched back on from SQL, and a query past the statement timeout
is stopped with an error naming the limit.
"""

import os

import duckdb
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.model.engine import QueryTimeout, query_connection, statement_timeout
from tracebi.model.sql_calc import SqlQuery
from tracebi.registry import Registry


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE fact_x AS SELECT * FROM (VALUES "
                "('a', 1.0), ('a', 2.0), ('b', 5.0)) t(grp, v)")
    con.close()
    (tmp_path / "secret.csv").write_text("k\n42\n")
    return path


def _model(warehouse, source):
    m = DataModel("lock").add_connector(DuckDBConnector("wh", database=str(warehouse)))
    m.add_table("fact_x", connector="wh", source=source)
    m.add_fact("fact_x", table_name="fact_x", measures=["v"])
    return m


def _reaches(tmp_path):
    """Sources that reach outside the attached warehouse, one per door."""
    return [
        "SELECT 1.0 AS v FROM read_csv('http://127.0.0.1:9/x.csv')",
        f"SELECT 1.0 AS v FROM read_csv('{tmp_path / 'secret.csv'}')",
        f"SELECT 1.0 AS v FROM '{tmp_path / 'secret.csv'}'",
        "SELECT 1.0 AS v FROM glob('/*')",
    ]


def test_a_model_query_that_reaches_outside_the_warehouse_is_refused(warehouse, tmp_path):
    for source in _reaches(tmp_path):
        m = _model(warehouse, source)
        with pytest.raises(duckdb.PermissionException, match="disabled by configuration"):
            m.query(fact="fact_x", measures={"v": "sum"})
    # The same model over the warehouse table answers: the lock is not a ban.
    ds = _model(warehouse, "fact_x").query(fact="fact_x", measures={"v": "sum"})
    assert ds.to_pandas()["v"].tolist() == [8.0]


def test_an_explore_query_surfaces_the_refusal_as_the_structured_error(
        warehouse, tmp_path, monkeypatch):
    from tracebi.web.api.routers import models as models_router

    reg = Registry()
    reg.add_model(_model(warehouse, _reaches(tmp_path)[0]))
    monkeypatch.setattr(models_router, "registry", reg)
    app = FastAPI()
    app.include_router(models_router.router, prefix="/api")
    r = TestClient(app).post("/api/models/lock/query",
                             json={"fact": "fact_x", "measures": {"v": "sum"}})
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert set(detail) == {"message", "exception_type", "traceback"}
    assert detail["exception_type"] == "PermissionException"
    assert "http://127.0.0.1:9/x.csv" in detail["message"]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('http://127.0.0.1:9/x.csv')",
    "SELECT * FROM read_parquet('https://example.com/x.parquet')",
])
def test_a_sql_calculation_that_reads_a_url_is_refused(warehouse, sql):
    with pytest.raises(duckdb.PermissionException, match="disabled by configuration"):
        _model(warehouse, "fact_x").execute(SqlQuery(sql=sql))


@pytest.mark.parametrize("sql", [
    "ATTACH '{tmp}/other.duckdb' AS other",
    "COPY (SELECT 1) TO '{tmp}/out.csv'",
    "INSTALL httpfs",
    "LOAD httpfs",
])
def test_the_engine_itself_refuses_attach_copy_install_and_load(warehouse, tmp_path, sql):
    # sql_calc's parser refuses these first; this is the second wall, DuckDB's.
    with query_connection({"wh": str(warehouse)}, default="wh") as con:
        with pytest.raises(duckdb.PermissionException):
            con.execute(sql.format(tmp=tmp_path))
    assert not (tmp_path / "other.duckdb").exists()
    assert not (tmp_path / "out.csv").exists()


@pytest.mark.parametrize("sql", [
    "SET enable_external_access = true",
    "RESET enable_external_access",
    "SET lock_configuration = false",
    "SET memory_limit = '64GB'",
])
def test_the_settings_cannot_be_flipped_from_sql(warehouse, sql):
    with query_connection({"wh": str(warehouse)}, default="wh") as con:
        with pytest.raises(duckdb.Error, match="configuration has been locked"):
            con.execute(sql)
        assert con.execute(
            "SELECT current_setting('enable_external_access')").fetchone()[0] is False


def test_the_project_limits_apply_and_a_slow_query_stops_at_the_timeout(
        warehouse, tmp_path, monkeypatch):
    from tracebi.web.api.routers import models as models_router

    monkeypatch.chdir(tmp_path)
    (tmp_path / "tracebi.yaml").write_text(
        "engine:\n  memory_limit: 256MiB\n  threads: 1\n  query_timeout_s: 0.2\n")
    with query_connection() as con:
        assert con.execute("SELECT current_setting('threads')").fetchone()[0] == 1
        assert con.execute(
            "SELECT current_setting('memory_limit')").fetchone()[0] == "256.0 MiB"

    # Small tables, a slow query: an allowed fan-out joins every fact row to
    # every dimension row (2.5 billion rows), far past 0.2 s on one thread.
    path = tmp_path / "slow.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE f AS SELECT 1 AS k, 1.0 AS v FROM range(50000)")
    con.execute("CREATE TABLE d AS SELECT 1 AS k, 'x' AS a FROM range(50000)")
    con.close()
    slow = DataModel("slow").add_connector(DuckDBConnector("wh", database=str(path)))
    slow.add_table("f", connector="wh", source="f")
    slow.add_table("d", connector="wh", source="d")
    slow.add_dimension("d", table_name="d", key_col="k", attributes=["a"])
    slow.add_fact("f", table_name="f", measures=["v"], foreign_keys={"d": "k"})
    query = {"fact": "f", "measures": {"v": "sum"}, "dimensions": ["d.a"],
             "allow_fanout": True}
    with pytest.raises(QueryTimeout, match="0.2 s limit"):
        with statement_timeout():
            slow.query(**query)

    reg = Registry()
    reg.add_model(slow)
    monkeypatch.setattr(models_router, "registry", reg)
    app = FastAPI()
    app.include_router(models_router.router, prefix="/api")
    r = TestClient(app).post("/api/models/slow/query", json=query)
    assert r.status_code == 504
    assert r.json()["detail"]["exception_type"] == "QueryTimeout"
    assert "engine.query_timeout_s" in r.json()["detail"]["message"]


# ── The object tier (tracebi.yaml warehouse: tier: object) ───────────────────

def _lake(tmp_path, monkeypatch):
    from tracebi.project_config import sink_target

    monkeypatch.chdir(tmp_path)
    (tmp_path / "tracebi.yaml").write_text("warehouse:\n  tier: object\n  location: lake\n")
    sink = sink_target(str(tmp_path))
    DuckDBConnector("w", database=sink).write(
        pd.DataFrame({"grp": ["a", "a", "b"], "v": [1.0, 2.0, 5.0]}), "fact_x")
    return sink


def test_the_object_tier_reads_its_parquet_and_writes_nothing(tmp_path, monkeypatch):
    # An allowed path is writable as well as readable to DuckDB, so on this
    # connection the engine refuses the statements that write by type.
    sink = _lake(tmp_path, monkeypatch)
    lake_file = tmp_path / "lake" / "fact_x.parquet"
    before = lake_file.read_bytes()
    with query_connection({"wh0": sink.warehouse}, default="wh0") as con:
        assert con.execute("SELECT sum(v) FROM fact_x").fetchone() == (8.0,)
        # USE_TMP_FILE false: DuckDB itself would let this one overwrite the file.
        for sql in (f"COPY (SELECT 1 AS v) TO '{lake_file}' (FORMAT PARQUET, USE_TMP_FILE false)",
                    f"ATTACH '{tmp_path / 'lake' / 'x.duckdb'}' AS x",
                    f"SELECT * FROM read_csv('{tmp_path / 'tracebi.yaml'}')"):
            with pytest.raises(duckdb.PermissionException):
                con.execute(sql)
    assert lake_file.read_bytes() == before
    assert sorted(p.name for p in (tmp_path / "lake").iterdir()) == ["fact_x.parquet"]


@pytest.mark.parametrize("block, says", [
    ("tier: object\n  location: s3://b/p\n  secret: hunter2\n", "warehouse.secret is a credential"),
    ("tier: object\n  location: s3://b/p\n  key_id: AKIA123\n", "warehouse.key_id is a credential"),
    ("tier: file\n  region: us-east-1\n", "applies to the object tier only"),
    ("tier: cloud\n", "warehouse.tier must be one of"),
    ("tier: object\n  location: s3://b/p\n  bucket: b\n", "unknown warehouse key"),
    ("tier: remote\n  location: md:db?motherduck_token=abc\n", "carries a credential"),
])
def test_the_warehouse_block_refuses_a_literal_credential_and_a_bad_shape(tmp_path, block, says):
    from tracebi.project_config import warehouse

    (tmp_path / "tracebi.yaml").write_text("warehouse:\n  " + block)
    with pytest.raises(ValueError, match=says) as err:
        warehouse(str(tmp_path))
    assert "tracebi.yaml" in str(err.value)
    assert "hunter2" not in str(err.value) and "AKIA123" not in str(err.value)


def test_the_object_tier_secret_is_built_from_the_environment_when_used(tmp_path, monkeypatch):
    from tracebi.project_config import warehouse

    (tmp_path / "tracebi.yaml").write_text(
        "warehouse:\n  tier: object\n  location: s3://bucket/project/\n"
        "  endpoint: ${TB_T_ENDPOINT}\n  key_id: ${TB_T_KEY}\n  secret: ${TB_T_SECRET}\n"
        "  url_style: path\n")
    (tmp_path / ".env").write_text("TB_T_SECRET=from-dotenv\n")
    monkeypatch.setenv("TB_T_KEY", "AKIDEXAMPLE")
    monkeypatch.delenv("TB_T_SECRET", raising=False)
    monkeypatch.delenv("TB_T_ENDPOINT", raising=False)
    wh = warehouse(str(tmp_path))            # reads no variable yet
    assert str(wh.sink) == "s3://bucket/project"
    with pytest.raises(ValueError, match="TB_T_ENDPOINT is not set"):
        wh.secret_sql()
    monkeypatch.setenv("TB_T_ENDPOINT", "http://127.0.0.1:9000")
    assert wh.secret_sql() == (
        "CREATE OR REPLACE TEMPORARY SECRET tracebi_warehouse (TYPE s3, "
        "KEY_ID 'AKIDEXAMPLE', SECRET 'from-dotenv', URL_STYLE 'path', "
        "ENDPOINT '127.0.0.1:9000', USE_SSL false, SCOPE 's3://bucket/project/')")
    assert "TB_T_SECRET" not in os.environ
