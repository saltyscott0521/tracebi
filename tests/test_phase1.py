"""
Tests for TraceBi Phase 1: Connectors, DataSet, DataModel
"""

import decimal
import importlib.util
import pytest
import pandas as pd

from tracebi import DataModel, MemoryConnector, DataSet, LineageNode
from tracebi import DuckDBConnector
from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel


# ─────────────────────────────────────────────

@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "id":     [1, 2, 3, 4, 5],
        "region": ["North", "South", "East", "West", "North"],
        "value":  [100.0, 200.0, 150.0, 50.0, 300.0],
        "status": ["active", "inactive", "active", "active", "inactive"],
    })


@pytest.fixture
def sample_ds(sample_df):
    node = LineageNode(
        operation="load",
        description="Test load",
        connector={"connector_name": "test", "connector_type": "MemoryConnector"},
        source="test_table",
    )
    return DataSet(df=sample_df, name="test", lineage=[node])


# ─────────────────────────────────────────────

class TestDataSet:


    def test_chained_lineage(self, sample_ds):
        result = (
            sample_ds
            .filter("value > 50")
            .transform(lambda df: df.assign(pct=df["value"] / df["value"].sum()),
                       description="pct of total")
            .sort("pct", ascending=False)
        )
        assert len(result.lineage) == 4  # load + filter + transform + sort

    def test_fingerprint_changes_on_data_change(self, sample_ds):
        fp1 = sample_ds.fingerprint()
        ds2 = sample_ds.filter("value > 100")
        fp2 = ds2.fingerprint()
        assert fp1 != fp2

    def test_fingerprint_stable(self, sample_ds):
        assert sample_ds.fingerprint() == sample_ds.fingerprint()

    def test_fingerprint_changes_on_rename(self, sample_ds):
        renamed = sample_ds.rename({"value": "amount"})
        assert sample_ds.fingerprint() != renamed.fingerprint()


# ─────────────────────────────────────────────

@pytest.fixture
def customers_ds():
    df = pd.DataFrame({
        "id":      [1, 2, 3],
        "name":    ["Alice", "Bob", "Carol"],
        "segment": ["SMB", "Enterprise", "SMB"],
    })
    node = LineageNode(operation="load", description="Test load", source="customers")
    return DataSet(df=df, name="customers", lineage=[node])


class TestJoin:


    def test_join_lineage_keeps_both_sides(self, sample_ds, customers_ds):
        joined = sample_ds.join(customers_ds, on="id")
        ops = [n.operation for n in joined.lineage]
        assert ops == ["load", "load", "join"]


class TestAggregate:

    def test_aggregate_values_correct(self, sample_ds):
        agg = sample_ds.aggregate(by="region", value="sum")
        df = agg.to_pandas().set_index("region")
        assert df.loc["North", "value"] == 400.0  # 100 + 300


class TestAssign:

    def test_assign_callable(self, sample_ds):
        ds = sample_ds.assign(doubled=lambda df: df["value"] * 2)
        assert "doubled" in ds.columns
        assert ds.lineage[-1].operation == "assign"
        assert ds.lineage[-1].metadata["columns_added"] == ["doubled"]


# ─────────────────────────────────────────────

@pytest.fixture
def messy_ds():
    df = pd.DataFrame({
        "order_id": [1, 1, 2, 3, 4],
        "region":   ["North", "North", None, "East", "West"],
        "qty":      [2.0, 2.0, None, 5.0, 1.0],
    })
    node = LineageNode(operation="load", description="Test load", source="messy")
    return DataSet(df=df, name="messy", lineage=[node])


class TestCleaningVerbs:


    def test_cleaning_verbs_do_not_mutate_original(self, messy_ds):
        messy_ds.dropna()
        messy_ds.fillna(0)
        messy_ds.deduplicate()
        messy_ds.limit(1)
        assert len(messy_ds) == 5
        assert messy_ds.to_pandas().isna().sum().sum() == 2

    def test_chained_cleaning_lineage(self, messy_ds):
        ds = (
            messy_ds
            .deduplicate(subset="order_id")
            .fillna({"qty": 0})
            .dropna(subset="region")
            .limit(3)
        )
        ops = [n.operation for n in ds.lineage]
        assert ops == ["load", "deduplicate", "fillna", "dropna", "limit"]


# ─────────────────────────────────────────────

class TestDataModel:


    def test_resolve(self, sample_df):
        left_df = pd.DataFrame({"id": [1, 2], "val": [10, 20]})
        right_df = pd.DataFrame({"id": [1, 2], "name": ["A", "B"]})
        c = MemoryConnector("m", {"left": left_df, "right": right_df})
        m = DataModel("M")
        m.add_connector(c)
        m.add_table("left",  connector="m", source="left")
        m.add_table("right", connector="m", source="right")
        m.add_relationship("lr", "left", "right", "id", how="left")
        ds = m.resolve("lr")
        assert "name" in ds.to_pandas().columns
        assert any(n.operation == "join" for n in ds.lineage)

    def test_resolve_chain(self):
        a = pd.DataFrame({"id": [1, 2], "b_id": [10, 20]})
        b = pd.DataFrame({"id": [10, 20], "c_id": [100, 200]})
        c = pd.DataFrame({"id": [100, 200], "label": ["X", "Y"]})
        conn = MemoryConnector("m", {"a": a, "b": b, "c": c})
        m = DataModel("Chain")
        m.add_connector(conn)
        m.add_table("a", connector="m", source="a")
        m.add_table("b", connector="m", source="b")
        m.add_table("c", connector="m", source="c")
        m.add_relationship("ab", "a", "b", left_key="b_id", right_key="id", how="left")
        m.add_relationship("bc", "b", "c", left_key="c_id", right_key="id", how="left")
        # resolve_chain joins a→b using "ab", then the result→c using "bc"
        # Note: after ab join, b's "id" is suffixed; we join on b's c_id
        ds = m.resolve_chain(["ab", "bc"])
        assert "label" in ds.to_pandas().columns
        join_steps = [n for n in ds.lineage if n.operation == "join"]
        assert len(join_steps) == 2


# ─────────────────────────────────────────────

class TestNotebookReprs:


    def test_dataset_repr_html_escapes(self):
        df = pd.DataFrame({"col": ["<script>alert(1)</script>"]})
        ds = DataSet(df=df, name="<evil>", lineage=[])
        html = ds._repr_html_()
        assert "<script>" not in html
        assert "<evil>" not in html


# ─────────────────────────────────────────────

class TestDuckDBReadOnlyCoexistence:
    """File-backed connectors hold a READ-ONLY handle so dev, build, and
    serve coexist against one warehouse; write() releases it, writes through
    a short-lived read-write connection, and goes lazy again."""

    pytestmark = pytest.mark.skipif(
        importlib.util.find_spec("duckdb") is None,
        reason="duckdb not installed",
    )

    @pytest.fixture
    def warehouse(self, tmp_path, sample_df):
        db = str(tmp_path / "warehouse.duckdb")
        DuckDBConnector("seed", database=db).write(sample_df, "sales")
        return db


    def test_one_instance_loads_from_many_threads(self, warehouse):
        """The web server runs requests on a thread pool, all sharing one
        connector. Unguarded, a second execute() on the shared connection
        consumed the first one's result and load() returned None — which
        surfaced as correct receipts reading "not reproduced"."""
        from concurrent.futures import ThreadPoolExecutor

        conn = DuckDBConnector("dd", database=warehouse)
        expected = len(conn.load("sales"))
        with ThreadPoolExecutor(8) as pool:
            lengths = list(pool.map(
                lambda i: len(conn.load("sales", filter=None if i % 2 else {})),
                range(200)))
        assert lengths == [expected] * 200


    def test_write_lock_conflict_names_the_fix(self, warehouse, sample_df, monkeypatch):
        import duckdb

        monkeypatch.setattr(DuckDBConnector, "WRITE_LOCK_WAIT", 0.3)
        holder = duckdb.connect(warehouse, read_only=True)
        try:
            conn = DuckDBConnector("dd", database=warehouse)
            with pytest.raises(RuntimeError, match="tracebi serve") as excinfo:
                conn.write(sample_df, "sales")
            assert excinfo.value.__cause__ is not None
        finally:
            holder.close()


# ─────────────────────────────────────────────

class TestDuckDBDecimalWrite:
    """Object columns of decimal.Decimal — the standard way to carry exact
    money — land as DECIMAL(38,12), so no digit is lost to a too-narrow
    inferred type or a float64 conversion."""

    pytestmark = pytest.mark.skipif(
        importlib.util.find_spec("duckdb") is None,
        reason="duckdb not installed",
    )

    WIDE = "12345678901234.567890123456"

    @pytest.fixture
    def money_df(self):
        return pd.DataFrame({
            "amount": [decimal.Decimal("19.99"), decimal.Decimal(self.WIDE), None],
            "weight": [0.5, 0.25, 0.25],
        })

    @staticmethod
    def _column_type(conn, table, column):
        return conn.connection.execute(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            [table, column],
        ).fetchone()[0]

    def test_decimal_column_lands_as_decimal_38_12(self, money_df):
        conn = DuckDBConnector("dd")
        conn.write(money_df, "money")
        assert self._column_type(conn, "money", "amount") == "DECIMAL(38,12)"

    def test_plain_float_column_still_lands_as_double(self, money_df):
        conn = DuckDBConnector("dd")
        conn.write(money_df, "money")
        assert self._column_type(conn, "money", "weight") == "DOUBLE"

    def test_wide_value_and_none_survive_exactly(self, money_df):
        conn = DuckDBConnector("dd")
        conn.write(money_df, "money")
        digits = conn.connection.execute(
            'SELECT CAST("amount" AS VARCHAR) FROM "money" '
            'WHERE "amount" IS NOT NULL ORDER BY "amount" DESC LIMIT 1'
        ).fetchone()[0]
        assert digits == self.WIDE
        nulls = conn.connection.execute(
            'SELECT COUNT(*) FROM "money" WHERE "amount" IS NULL'
        ).fetchone()[0]
        assert nulls == 1

    def test_append_preserves_decimal_type(self, money_df):
        conn = DuckDBConnector("dd")
        conn.write(money_df, "money")
        conn.write(money_df, "money", if_exists="append")
        assert self._column_type(conn, "money", "amount") == "DECIMAL(38,12)"
        assert len(conn.load("money")) == 2 * len(money_df)
        wide = conn.connection.execute(
            'SELECT COUNT(*) FROM "money" WHERE CAST("amount" AS VARCHAR) = ?',
            [self.WIDE],
        ).fetchone()[0]
        assert wide == 2

    def test_append_decimals_into_all_none_created_table_raises(self):
        # An all-None object column carries no Decimal marker, so the first
        # write lands via DuckDB inference (INTEGER). Appending real
        # Decimals must raise, not silently round 19.99 -> 20.
        conn = DuckDBConnector("dd")
        conn.write(pd.DataFrame({"amount": [None, None]}), "money")
        assert self._column_type(conn, "money", "amount") == "INTEGER"
        with pytest.raises(ValueError, match="'amount'"):
            conn.write(
                pd.DataFrame({"amount": [decimal.Decimal("19.99")]}),
                "money",
                if_exists="append",
            )
        assert len(conn.load("money")) == 2  # nothing was inserted

    def test_append_decimals_into_double_table_raises(self, money_df):
        # A table created before this feature holds the column as DOUBLE;
        # appending Decimals must raise instead of silently narrowing.
        conn = DuckDBConnector("dd")
        conn.connection.execute(
            "CREATE TABLE money (amount DOUBLE); INSERT INTO money VALUES (1.5)"
        )
        with pytest.raises(ValueError) as excinfo:
            conn.write(money_df, "money", if_exists="append")
        message = str(excinfo.value)
        assert "'amount'" in message
        assert "DOUBLE" in message
        assert 'if_exists="replace"' in message

    def test_quoted_identifier_column_round_trips(self):
        col = 'amount "usd"'
        conn = DuckDBConnector("dd")
        conn.write(pd.DataFrame({col: [decimal.Decimal("19.99")]}), "money")
        assert self._column_type(conn, "money", col) == "DECIMAL(38,12)"
        escaped = col.replace('"', '""')
        digits = conn.connection.execute(
            f'SELECT CAST("{escaped}" AS VARCHAR) FROM "money"'
        ).fetchone()[0]
        assert digits == "19.990000000000"
        assert list(conn.load("money").columns) == [col]

    def test_deeper_than_12dp_rounds_at_write(self):
        # Documented behavior: scale beyond 12 is rounded by the CAST,
        # not an error.
        conn = DuckDBConnector("dd")
        conn.write(
            pd.DataFrame({"amount": [decimal.Decimal("1.1234567890126456")]}),
            "money",
        )
        digits = conn.connection.execute(
            'SELECT CAST("amount" AS VARCHAR) FROM "money"'
        ).fetchone()[0]
        assert digits == "1.123456789013"

    def test_mixed_decimal_and_float_lands_as_double(self):
        # Documented behavior: a float-contaminated column has already lost
        # exactness, so it is not promoted to DECIMAL.
        conn = DuckDBConnector("dd")
        conn.write(
            pd.DataFrame({"amount": [decimal.Decimal("1.5"), 2.5]}),
            "money",
        )
        assert self._column_type(conn, "money", "amount") == "DOUBLE"
