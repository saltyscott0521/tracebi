"""SQL calculations (``tracebi.model.sql_calc``) against a real DuckDB file.

What a journey cannot pin precisely: which statements are refused and that the
read-only engine reaches no file, extension or write, and how a measure
expands to SQL (and which kinds are refused by name). The journey in
tests/e2e/test_sql_calc_journey.py covers the calculation through a report,
its receipt and ``tracebi verify``.
"""

import duckdb
import pytest

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.model.sql_calc import SqlQuery, check_read_only


@pytest.fixture
def warehouse(tmp_path):
    path = tmp_path / "wh.duckdb"
    con = duckdb.connect(str(path))
    con.execute(
        "CREATE TABLE fact_x AS SELECT * FROM (VALUES "
        "('a', DATE '2024-01-01', 1.0, 'purchase'), "
        "('a', DATE '2024-01-02', 2.0, 'sale'), "
        "('b', DATE '2024-01-01', 5.0, 'purchase')) t(grp, d, v, kind)")
    con.execute("CREATE TABLE other AS SELECT 1 AS k")
    con.close()
    return path


@pytest.fixture
def model(warehouse):
    m = DataModel("Warehouse").add_connector(
        DuckDBConnector("wh", database=str(warehouse)))
    m.add_table("fact_x", connector="wh", source="fact_x")
    m.add_fact("fact_x", table_name="fact_x", measures=["v"])
    m.add_measure("total", column="v", agg="sum")
    m.add_measure("purchases", column="v", agg="sum",
                  filters={"kind": "purchase"})
    m.add_measure("rows", column="v", agg="count")
    m.add_measure("purchase_share", ratio=("purchases", "total"))
    return m


@pytest.mark.parametrize("sql", [
    "INSERT INTO fact_x VALUES ('c', DATE '2024-01-03', 9.0, 'sale')",
    "DELETE FROM fact_x",
    "DROP TABLE other",
    "CREATE TABLE leak AS SELECT * FROM fact_x",
    "ATTACH '/tmp/elsewhere.duckdb' AS elsewhere",
    "COPY fact_x TO '/tmp/fact_x.csv'",
    "PRAGMA database_list",
    "SET enable_external_access = true",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SELECT 1; DROP TABLE other",
    "SELECT 1; SELECT 2",
    "",
])
def test_anything_but_one_select_is_refused(sql):
    with pytest.raises(ValueError):
        check_read_only(sql)


def test_a_with_query_and_a_trailing_comment_are_still_one_select():
    check_read_only("WITH a AS (SELECT 1 AS x) SELECT x FROM a -- done\n;")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('/etc/hosts')",
    "SELECT * FROM read_text('/etc/hosts')",
    "SELECT * FROM glob('/*')",
    "SELECT * FROM '/etc/hosts'",
])
def test_a_select_that_reads_a_file_fails_in_the_read_only_engine(model, sql):
    # Passes the structural check (it is a SELECT); the engine refuses the file.
    with pytest.raises(duckdb.Error):
        model.execute(SqlQuery(sql=sql))


def test_the_warehouse_is_unchanged_after_a_refused_write(model, warehouse):
    with pytest.raises(ValueError):
        model.execute(SqlQuery(sql="DELETE FROM fact_x"))
    ds = model.execute(SqlQuery(sql="SELECT COUNT(*) AS n FROM fact_x"))
    assert int(ds.to_pandas()["n"][0]) == 3


def test_a_measure_expands_to_sql_and_a_filtered_one_keeps_its_filter(model):
    ds = model.execute(SqlQuery(
        sql="SELECT grp, {{ measure('purchases') }} AS purchases, "
            "{{ measure('rows') }} AS rows FROM fact_x GROUP BY grp"))
    df = ds.to_pandas()
    assert df.to_dict("records") == [
        {"grp": "a", "purchases": 1.0, "rows": 2},
        {"grp": "b", "purchases": 5.0, "rows": 1},
    ]
    resolved = [n for n in ds.lineage if n.operation == "transform"][-1].metadata
    assert "FILTER (WHERE \"kind\" = 'purchase')" in resolved["sql_resolved"]


def test_a_model_query_and_a_sql_calculation_run_side_by_side(model):
    # The model's own read-only connection stays open while the SQL engine
    # attaches the same file.
    assert int(model.query(fact="fact_x", measures=["rows"]).to_pandas()["rows"][0]) == 3
    ds = model.execute(SqlQuery(sql="SELECT SUM(v) AS s FROM fact_x"))
    assert float(ds.to_pandas()["s"][0]) == 8.0


def test_a_ratio_measure_is_refused_by_name(model):
    with pytest.raises(ValueError, match="purchase_share.*ratio"):
        model.execute(SqlQuery(sql="SELECT {{ measure('purchase_share') }} AS s FROM fact_x"))


def test_an_undeclared_measure_is_refused_by_name(model):
    with pytest.raises(ValueError, match="'nope'.*does not declare"):
        model.execute(SqlQuery(sql="SELECT {{ measure('nope') }} AS s FROM fact_x"))
