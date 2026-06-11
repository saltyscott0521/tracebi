"""
Tests for Phase 4 — PipelineRunner + connector write() + layer execute().

Coverage:
  - BaseConnector.write() raises NotImplementedError
  - MemoryConnector.write() (replace / append / fail)
  - SQLConnector.write() via SQLite
  - BronzeLayer.execute() (sink write)
  - SilverLayer.execute() (source load + clean + sink write)
  - GoldLayer.execute() (pre-configured query + sink write)
  - PipelineRunner: register, run (single + refresh), lineage, status,
    register_model (persists relationships + facts + dimensions)
"""

import os
import tempfile

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, DataSet
from tracebi.connectors.base import BaseConnector
from tracebi.connectors.sql_connector import SQLConnector
from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer
from tracebi.etl.gold import GoldLayer
from tracebi.pipeline.runner import PipelineRunner


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def orders_df():
    return pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 2],
        "customer_id": [101, 102, 101, 103, 102],
        "qty":         ["10", "20", "30", "40", "20"],
        "revenue":     [100.0, 200.0, 300.0, 400.0, 200.0],
        "status":      ["shipped", "shipped", "open", "shipped", "shipped"],
    })


@pytest.fixture
def customers_df():
    return pd.DataFrame({
        "customer_id": [101, 102, 103],
        "region":      ["North", "South", "East"],
        "segment":     ["Enterprise", "SMB", "SMB"],
    })


@pytest.fixture
def mem(orders_df, customers_df):
    return MemoryConnector("mem", tables={
        "orders_raw":    orders_df,
        "customers_raw": customers_df,
    })


@pytest.fixture
def sqlite_url(tmp_path):
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def sql_db(sqlite_url, orders_df, customers_df):
    db = SQLConnector("db", url=sqlite_url)
    db.write(orders_df,    "orders_raw")
    db.write(customers_df, "customers_raw")
    return db


@pytest.fixture
def model(sql_db, sqlite_url):
    m = DataModel("M")
    m.add_connector(sql_db)
    m.add_table("orders_silver",    connector="db", source="orders_silver")
    m.add_table("customers_silver", connector="db", source="customers_silver")
    m.add_dimension("dim_customer", table_name="customers_silver",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders_silver",
               measures=["revenue"], foreign_keys={"dim_customer": "customer_id"})
    return m


@pytest.fixture
def runner(sqlite_url):
    return PipelineRunner(db_url=sqlite_url)


# ── Connector write() ─────────────────────────────────────────────────────────

class TestConnectorWrite:
    def test_base_raises(self, orders_df):
        class Dummy(BaseConnector):
            def connect(self): pass
            def load(self, s): return pd.DataFrame()

        with pytest.raises(NotImplementedError):
            Dummy("d").write(orders_df, "t")

    def test_memory_replace(self, mem, orders_df):
        new_df = pd.DataFrame({"a": [1]})
        mem.write(new_df, "orders_raw")
        assert list(mem.load("orders_raw").columns) == ["a"]

    def test_memory_append(self, mem, orders_df):
        extra = pd.DataFrame({"order_id": [99], "customer_id": [999],
                               "qty": ["1"], "revenue": [1.0], "status": ["open"]})
        before = len(mem.load("orders_raw"))
        mem.write(extra, "orders_raw", if_exists="append")
        assert len(mem.load("orders_raw")) == before + 1

    def test_memory_fail(self, mem, orders_df):
        with pytest.raises(ValueError, match="already exists"):
            mem.write(orders_df, "orders_raw", if_exists="fail")

    def test_memory_new_table(self, mem):
        df = pd.DataFrame({"x": [1, 2]})
        mem.write(df, "brand_new")
        assert len(mem.load("brand_new")) == 2

    def test_sql_write_and_read(self, sql_db, orders_df):
        result = sql_db.load("orders_raw")
        assert len(result) == len(orders_df)

    def test_sql_write_replace(self, sql_db):
        small = pd.DataFrame({"order_id": [1], "customer_id": [1],
                               "qty": ["1"], "revenue": [9.99], "status": ["open"]})
        sql_db.write(small, "orders_raw")
        assert len(sql_db.load("orders_raw")) == 1


# ── BronzeLayer.execute() ─────────────────────────────────────────────────────

class TestBronzeExecute:
    def test_execute_writes_to_sink(self, mem, orders_df):
        bronze = BronzeLayer(connector=mem, source="orders_raw",
                             sink=mem, sink_table="orders_bronze")
        ds = bronze.execute()
        assert "orders_bronze" in mem._tables
        assert len(ds) == len(orders_df)

    def test_execute_lineage_operation(self, mem):
        bronze = BronzeLayer(connector=mem, source="orders_raw",
                             sink=mem, sink_table="orders_bronze")
        ds = bronze.execute()
        assert ds.lineage[0].operation == "bronze"

    def test_execute_no_sink_raises(self, mem):
        bronze = BronzeLayer(connector=mem, source="orders_raw")
        with pytest.raises(RuntimeError, match="sink"):
            bronze.execute()

    def test_load_does_not_write(self, mem):
        bronze = BronzeLayer(connector=mem, source="orders_raw",
                             sink=mem, sink_table="orders_bronze_x")
        bronze.load()
        assert "orders_bronze_x" not in mem._tables


# ── SilverLayer.execute() ─────────────────────────────────────────────────────

class TestSilverExecute:
    def _setup(self, mem, orders_df):
        # Put bronze data into mem
        mem.write(orders_df, "orders_bronze")
        return (
            SilverLayer(
                source=mem, source_table="orders_bronze",
                sink=mem, sink_table="orders_silver",
            )
            .cast({"qty": "int64"})
            .deduplicate(subset=["order_id"])
        )

    def test_execute_writes_to_sink(self, mem, orders_df):
        silver = self._setup(mem, orders_df)
        ds = silver.execute()
        assert "orders_silver" in mem._tables

    def test_execute_deduplicates(self, mem, orders_df):
        silver = self._setup(mem, orders_df)
        ds = silver.execute()
        assert len(ds) == 4  # one duplicate removed

    def test_execute_lineage_chain(self, mem, orders_df):
        silver = self._setup(mem, orders_df)
        ds = silver.execute()
        ops = [n.operation for n in ds.lineage]
        assert "load" in ops
        assert "silver" in ops

    def test_execute_no_source_raises(self):
        silver = SilverLayer(sink=MemoryConnector("m", {}), sink_table="t")
        with pytest.raises(RuntimeError, match="source"):
            silver.execute()

    def test_execute_no_sink_raises(self, mem, orders_df):
        mem.write(orders_df, "orders_bronze")
        silver = SilverLayer(source=mem, source_table="orders_bronze")
        with pytest.raises(RuntimeError, match="sink"):
            silver.execute()


# ── GoldLayer.execute() ───────────────────────────────────────────────────────

class TestGoldExecute:
    def _setup_silver(self, sql_db, orders_df, customers_df):
        # Write clean silver tables directly
        orders_clean = orders_df.drop_duplicates(subset=["order_id"]).copy()
        orders_clean["qty"] = orders_clean["qty"].astype(int)
        sql_db.write(orders_clean, "orders_silver")
        sql_db.write(customers_df, "customers_silver")

    def test_execute_writes_to_sink(self, sql_db, orders_df, customers_df, model):
        self._setup_silver(sql_db, orders_df, customers_df)
        gold = GoldLayer(
            model=model,
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            sink=sql_db,
            sink_table="revenue_gold",
        )
        ds = gold.execute()
        result = sql_db.load("revenue_gold")
        assert "revenue" in result.columns
        assert len(result) == 3  # 3 regions

    def test_execute_lineage_has_gold_node(self, sql_db, orders_df, customers_df, model):
        self._setup_silver(sql_db, orders_df, customers_df)
        gold = GoldLayer(
            model=model, fact="fact_orders",
            measures={"revenue": "sum"}, dimensions=["dim_customer.region"],
            sink=sql_db, sink_table="revenue_gold2",
        )
        ds = gold.execute()
        ops = [n.operation for n in ds.lineage]
        assert "gold" in ops

    def test_execute_no_fact_raises(self, model):
        gold = GoldLayer(model=model, sink=MemoryConnector("m", {}), sink_table="t")
        with pytest.raises(RuntimeError, match="fact"):
            gold.execute()

    def test_execute_no_sink_raises(self, model):
        gold = GoldLayer(model=model, fact="fact_orders",
                         measures={"revenue": "sum"})
        with pytest.raises(RuntimeError, match="sink"):
            gold.execute()


# ── PipelineRunner ────────────────────────────────────────────────────────────

class TestPipelineRunner:
    def _make_bronze(self, mem):
        return BronzeLayer(connector=mem, source="orders_raw",
                           sink=mem, sink_table="orders_bronze")

    def _make_silver(self, mem):
        mem.write(mem.load("orders_raw"), "orders_bronze")
        return (
            SilverLayer(source=mem, source_table="orders_bronze",
                        sink=mem, sink_table="orders_silver")
            .deduplicate(subset=["order_id"])
        )

    def test_register_stores_layer(self, runner, mem):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        assert "orders_bronze" in runner._layers

    def test_register_depends_on_must_exist(self, runner, mem):
        silver = self._make_silver(mem)
        with pytest.raises(ValueError, match="not registered"):
            runner.register(silver, name="orders_silver", depends_on="orders_bronze")

    def test_register_persists_to_db(self, runner, mem):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        df = pd.read_sql("SELECT * FROM tracebi_layers WHERE name='orders_bronze'",
                         con=runner._engine_())
        assert len(df) == 1
        assert df.iloc[0]["layer_type"] == "bronze"

    def test_run_single(self, runner, mem, orders_df):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        runner.run("orders_bronze")
        assert "orders_bronze" in mem._tables

    def test_run_records_success(self, runner, mem, orders_df):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        runner.run("orders_bronze")
        df = pd.read_sql("SELECT * FROM tracebi_runs WHERE layer_name='orders_bronze'",
                         con=runner._engine_())
        assert df.iloc[0]["status"] == "success"
        assert df.iloc[0]["rows_out"] > 0

    def test_concurrent_run_of_same_layer_rejected(self, runner, mem):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        # Simulate an in-flight run by holding the layer's lock.
        lock = runner._layer_lock("orders_bronze")
        lock.acquire()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                runner.run("orders_bronze")
        finally:
            lock.release()
        # Once released, the layer runs normally again.
        runner.run("orders_bronze")
        assert "orders_bronze" in mem._tables

    def test_run_unknown_raises(self, runner):
        with pytest.raises(ValueError, match="not registered"):
            runner.run("no_such_layer")

    def test_run_refresh_full_chain(self, runner, mem, orders_df):
        bronze = self._make_bronze(mem)
        silver = self._make_silver(mem)
        runner.register(bronze, name="orders_bronze")
        runner.register(silver, name="orders_silver", depends_on="orders_bronze")
        runner.run("orders_silver", refresh=True)
        assert "orders_bronze" in mem._tables
        assert "orders_silver" in mem._tables

    def test_run_refresh_records_upstream_id(self, runner, mem, orders_df):
        bronze = self._make_bronze(mem)
        silver = self._make_silver(mem)
        runner.register(bronze, name="orders_bronze")
        runner.register(silver, name="orders_silver", depends_on="orders_bronze")
        runner.run("orders_silver", refresh=True)
        df = pd.read_sql("SELECT * FROM tracebi_runs WHERE layer_name='orders_silver'",
                         con=runner._engine_())
        assert df.iloc[0]["upstream_run_id"] is not None

    def test_resolve_chain(self, runner, mem):
        bronze = self._make_bronze(mem)
        silver = self._make_silver(mem)
        runner.register(bronze, name="orders_bronze")
        runner.register(silver, name="orders_silver", depends_on="orders_bronze")
        chain = runner._resolve_chain("orders_silver")
        assert chain == ["orders_bronze", "orders_silver"]

    def test_register_model_persists_facts_and_dims(self, runner, model):
        runner.register_model(model)
        df = pd.read_sql("SELECT * FROM tracebi_schemas", con=runner._engine_())
        assert len(df) == 1
        dims = pd.read_sql("SELECT * FROM tracebi_dimensions", con=runner._engine_())
        assert len(dims) >= 1
        facts = pd.read_sql("SELECT * FROM tracebi_facts", con=runner._engine_())
        assert len(facts) >= 1

    def test_register_model_no_facts_skips_schema_row(self, runner, sql_db):
        m = DataModel("Plain")
        m.add_connector(sql_db)
        m.add_table("orders_silver", connector="db", source="orders_silver")
        runner.register_model(m)
        df = pd.read_sql("SELECT * FROM tracebi_schemas", con=runner._engine_())
        assert len(df) == 0

    def test_repr(self, runner):
        assert "PipelineRunner" in repr(runner)

    def test_status_runs_without_error(self, runner, mem, capsys):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        runner.run("orders_bronze")
        runner.status()
        out = capsys.readouterr().out
        assert "orders_bronze" in out

    def test_lineage_runs_without_error(self, runner, mem, capsys):
        bronze = self._make_bronze(mem)
        runner.register(bronze, name="orders_bronze")
        runner.run("orders_bronze")
        runner.lineage("orders_bronze")
        out = capsys.readouterr().out
        assert "orders_bronze" in out
