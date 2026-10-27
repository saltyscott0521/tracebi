"""Column lineage through a SQL transform is DuckDB's parse, never a guess.

Query semantics a journey cannot pin: for each shape a transform uses (a CTE,
a TEMP table, a join over an attached source and a file read, a window
function, ``SELECT *``, a UNION) the exact columns each sink column is
computed from; and where the tree cannot be followed, ``from: null`` with the
reason, so a wrong base can never be recorded as a fact.
"""

import duckdb
import pytest

from tracebi.lineage_sql import column_lineage


@pytest.fixture
def con(tmp_path):
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "trades.csv").write_text(
        "trade_id,issuer,qty,price\n1,acme,10,2.5\n2,bolt,3,4.0\n1,acme,10,2.5\n")
    con = duckdb.connect()
    con.execute(f"SET file_search_path = '{tmp_path}'")
    con.execute("ATTACH ':memory:' AS crm")
    con.execute("CREATE TABLE crm.main.ratings AS "
                "SELECT * FROM (VALUES ('acme', 'AA', true), ('bolt', 'B', false)) t(issuer, rating, watch)")
    yield con
    con.close()


def test_each_sink_column_records_exactly_the_columns_it_is_computed_from(con, tmp_path):
    lineage = column_lineage([
        "CREATE TEMP TABLE raw AS SELECT * FROM read_csv('inputs/trades.csv')",
        # a CTE and a window function; the WHERE decides rows, not values
        "CREATE TEMP TABLE clean AS WITH d AS (SELECT DISTINCT * FROM raw) "
        "SELECT row_number() OVER (ORDER BY trade_id) AS line, issuer, qty * price AS notional "
        "FROM d WHERE qty > 0",
        # a join over an attached -- source: table
        "CREATE TABLE fact_trades AS SELECT c.line, c.notional, r.rating, "
        "CASE WHEN r.watch THEN 'yes' ELSE 'no' END AS watch "
        "FROM clean c LEFT JOIN crm.ratings r USING (issuer)",
        # SELECT * over a sink table, and a UNION that adds a constant row
        "CREATE TABLE fact_all AS SELECT * FROM fact_trades "
        "UNION ALL SELECT 0, 0.0, 'NR', 'no'",
        # a scalar subquery is a lookup: what it reads decides the value
        "CREATE VIEW v_rated AS SELECT f.line, "
        "(SELECT max(r.rating) FROM crm.ratings r WHERE r.issuer = c.issuer) AS best "
        "FROM fact_trades f JOIN clean c USING (line)",
    ], con, sources=("crm",), root=str(tmp_path))

    assert set(lineage) == {"fact_trades", "fact_all", "v_rated"}    # TEMP tables are not sinks
    assert lineage["fact_trades"] == {
        "line": {"from": ["inputs/trades.csv.trade_id"], "via": ["clean", "raw"]},
        "notional": {"from": ["inputs/trades.csv.price", "inputs/trades.csv.qty"],
                     "via": ["clean", "raw"]},
        "rating": {"from": ["crm.ratings.rating"]},
        "watch": {"from": ["crm.ratings.watch"]},
    }
    # Another sink table is a base: lineage chains through the warehouse.
    assert lineage["fact_all"] == {
        "line": {"from": ["fact_trades.line"]},
        "notional": {"from": ["fact_trades.notional"]},
        "rating": {"from": ["fact_trades.rating"]},
        "watch": {"from": ["fact_trades.watch"]},
    }
    assert lineage["v_rated"] == {
        "line": {"from": ["fact_trades.line"]},
        "best": {"from": ["crm.ratings.issuer", "crm.ratings.rating",
                          "inputs/trades.csv.issuer"], "via": ["clean", "raw"]},
    }


def test_a_column_computed_from_no_column_says_so():
    con = duckdb.connect()
    lineage = column_lineage([
        "CREATE TABLE dim_type AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) t(id, name)",
        "CREATE TABLE days AS SELECT range AS day, 7 AS week FROM range(3)",
    ], con)
    assert lineage["dim_type"] == {"id": {"from": []}, "name": {"from": []}}
    assert lineage["days"] == {"day": {"from": []}, "week": {"from": []}}


@pytest.mark.parametrize("statements, reason", [
    (["CREATE TEMP MACRO pick(n) AS TABLE SELECT * FROM range(n)",
      "CREATE TABLE t AS SELECT * FROM pick(3)"],
     "table function pick"),
    (["CREATE TABLE s AS SELECT 1 AS a_x, 2 AS a_y",
      "CREATE TABLE t AS SELECT COLUMNS('a_.*') FROM s"],
     "COLUMNS"),
    (["CREATE TABLE t AS WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r "
      "WHERE n < 3) SELECT n FROM r"],
     "recursive CTE"),
    (["CREATE TABLE s AS SELECT 1 AS a",
      "CREATE TABLE t AS SELECT a FROM s",
      "INSERT INTO t SELECT 2"],
     "INSERT"),
    (["CREATE TABLE s AS SELECT 1 AS a",
      "CREATE TEMP MACRO peek(x) AS (SELECT max(a) FROM s WHERE a > x)",
      "CREATE TABLE t AS SELECT peek(0) AS a"],
     "macro peek"),
])
def test_what_the_tree_cannot_follow_is_null_with_the_reason(statements, reason):
    con = duckdb.connect()
    lineage = column_lineage(statements, con)
    for column in lineage["t"].values():
        assert column["from"] is None and reason in column["reason"], column
