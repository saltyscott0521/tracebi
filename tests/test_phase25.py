"""
Tests for Phase 2.5 — Medallion Architecture + Star Schema + Lineage Diagram.

Coverage:
  - BronzeLayer (load, lineage stamp, repr)
  - SilverLayer (cast, drop_nulls, deduplicate, rename, transform, lineage)
  - StarSchema (add_dimension, add_fact, query: groupby, no-groupby, no-agg, filters)
  - GoldLayer (wraps StarSchema, gold lineage node)
  - LineageDiagram (build, to_mermaid, to_html, repr, Report source)
"""

import os
import tempfile

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, DataSet, LineageNode
from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer
from tracebi.etl.gold import GoldLayer
from tracebi.model.star_schema import StarSchema
from tracebi.lineage.diagram import LineageDiagram


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def orders_df():
    return pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 2],           # row 4 is a duplicate
        "customer_id": [101, 102, 101, 103, 102],
        "qty":         ["10", "20", "30", "40", "20"],  # strings
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
def connector(orders_df, customers_df):
    return MemoryConnector("mem", tables={
        "orders":    orders_df,
        "customers": customers_df,
    })


@pytest.fixture
def model(connector):
    m = DataModel("TestModel")
    m.add_connector(connector)
    m.add_table("orders",    connector="mem", source="orders")
    m.add_table("customers", connector="mem", source="customers")
    return m


@pytest.fixture
def schema(model):
    s = StarSchema("TestSchema", model=model)
    s.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region", "segment"])
    s.add_fact("fact_orders", table_name="orders",
               measures=["revenue", "qty"],
               foreign_keys={"dim_customer": "customer_id"})
    return s


# ── BronzeLayer ───────────────────────────────────────────────────────────────

class TestBronzeLayer:
    def test_load_returns_dataset(self, connector, orders_df):
        bronze = BronzeLayer(connector=connector, source="orders")
        ds = bronze.load(name="orders_bronze")
        assert isinstance(ds, DataSet)
        assert ds.name == "orders_bronze"
        assert ds.shape[0] == len(orders_df)

    def test_load_lineage_operation(self, connector):
        ds = BronzeLayer(connector=connector, source="orders").load()
        assert len(ds.lineage) == 1
        assert ds.lineage[0].operation == "bronze"

    def test_load_lineage_metadata(self, connector, orders_df):
        ds = BronzeLayer(connector=connector, source="orders").load()
        meta = ds.lineage[0].metadata
        assert meta["layer"] == "bronze"
        assert meta["rows_ingested"] == len(orders_df)
        assert "ingestion_time" in meta

    def test_load_default_name(self, connector):
        ds = BronzeLayer(connector=connector, source="orders").load()
        assert ds.name == "orders"

    def test_load_connector_info(self, connector):
        ds = BronzeLayer(connector=connector, source="orders").load()
        node = ds.lineage[0]
        assert node.connector["connector_name"] == "mem"
        assert "MemoryConnector" in node.connector["connector_type"]

    def test_repr(self, connector):
        bronze = BronzeLayer(connector=connector, source="orders")
        assert "BronzeLayer" in repr(bronze)
        assert "orders" in repr(bronze)


# ── SilverLayer ───────────────────────────────────────────────────────────────

class TestSilverLayer:
    def _bronze_ds(self, connector):
        return BronzeLayer(connector=connector, source="orders").load()

    def test_apply_returns_dataset(self, connector):
        ds = SilverLayer().apply(self._bronze_ds(connector))
        assert isinstance(ds, DataSet)

    def test_default_name(self, connector):
        raw = self._bronze_ds(connector)
        ds = SilverLayer().apply(raw)
        assert ds.name == "orders_silver"

    def test_cast(self, connector):
        ds = SilverLayer().cast({"qty": "int64"}).apply(self._bronze_ds(connector))
        assert ds.to_pandas()["qty"].dtype == "int64"

    def test_cast_lineage(self, connector):
        ds = SilverLayer().cast({"qty": "int64"}).apply(self._bronze_ds(connector))
        silver_nodes = [n for n in ds.lineage if n.operation == "silver"]
        assert len(silver_nodes) == 1
        assert "cast" in silver_nodes[0].description.lower()

    def test_drop_nulls(self, connector):
        raw_df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        mem = MemoryConnector("m2", tables={"t": raw_df})
        raw_ds = BronzeLayer(connector=mem, source="t").load()
        ds = SilverLayer().drop_nulls(subset=["a"]).apply(raw_ds)
        assert ds.shape[0] == 2

    def test_deduplicate(self, connector):
        raw = self._bronze_ds(connector)
        ds = SilverLayer().deduplicate(subset=["order_id"]).apply(raw)
        assert ds.shape[0] == 4  # one duplicate removed

    def test_deduplicate_lineage(self, connector):
        ds = SilverLayer().deduplicate(subset=["order_id"]).apply(self._bronze_ds(connector))
        silver_nodes = [n for n in ds.lineage if n.operation == "silver"]
        assert silver_nodes[0].metadata["duplicates_dropped"] == 1

    def test_rename(self, connector):
        ds = SilverLayer().rename({"qty": "units"}).apply(self._bronze_ds(connector))
        assert "units" in ds.columns
        assert "qty" not in ds.columns

    def test_transform(self, connector):
        ds = (
            SilverLayer()
            .cast({"qty": "int64"})
            .transform(lambda df: df.assign(total=df["revenue"] * 2),
                       description="doubled revenue")
        ).apply(self._bronze_ds(connector))
        assert "total" in ds.columns

    def test_lineage_chain(self, connector):
        ds = (
            SilverLayer()
            .cast({"qty": "int64"})
            .drop_nulls()
            .deduplicate(subset=["order_id"])
        ).apply(self._bronze_ds(connector))
        silver_nodes = [n for n in ds.lineage if n.operation == "silver"]
        assert len(silver_nodes) == 3

    def test_preserves_bronze_lineage(self, connector):
        raw = self._bronze_ds(connector)
        ds = SilverLayer().cast({"qty": "int64"}).apply(raw)
        bronze_nodes = [n for n in ds.lineage if n.operation == "bronze"]
        assert len(bronze_nodes) == 1

    def test_repr(self):
        silver = SilverLayer().cast({"a": "int64"}).drop_nulls()
        assert "SilverLayer" in repr(silver)
        assert "cast" in repr(silver)


# ── StarSchema ────────────────────────────────────────────────────────────────

class TestStarSchema:
    def test_add_dimension(self, schema):
        assert "dim_customer" in schema._dimensions

    def test_add_fact(self, schema):
        assert "fact_orders" in schema._facts

    def test_query_grouped(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        df = ds.to_pandas()
        assert "dim_customer.region" in df.columns
        assert "revenue" in df.columns
        assert len(df) == 3  # 3 unique regions

    def test_query_grouped_values(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        df = ds.to_pandas().set_index("dim_customer.region")
        assert df.loc["North", "revenue"] == pytest.approx(100.0 + 300.0)

    def test_query_no_groupby(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum", "order_id": "count"},
            aggregate=True,
        )
        df = ds.to_pandas()
        assert len(df) == 1
        assert df["revenue"].iloc[0] == pytest.approx(100.0 + 200.0 + 300.0 + 400.0 + 200.0)

    def test_query_no_aggregate(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            aggregate=False,
        )
        assert len(ds) == 5  # all rows returned

    def test_query_filter(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
        )
        df = ds.to_pandas()
        total = df["revenue"].sum()
        assert total == pytest.approx(100.0 + 200.0 + 400.0 + 200.0)

    def test_query_lineage_includes_join(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        ops = [n.operation for n in ds.lineage]
        assert "join" in ops

    def test_query_lineage_includes_filter(self, schema):
        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
        )
        ops = [n.operation for n in ds.lineage]
        assert "filter" in ops

    def test_unknown_fact_raises(self, schema):
        with pytest.raises(ValueError, match="not registered"):
            schema.query(fact="no_such_fact", measures={"revenue": "sum"})

    def test_unknown_dimension_raises(self, schema):
        with pytest.raises(ValueError, match="not registered"):
            schema.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["dim_nope.region"],
            )

    def test_bad_dimension_format_raises(self, schema):
        with pytest.raises(ValueError, match="dot notation"):
            schema.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["region"],
            )

    def test_repr(self, schema):
        assert "StarSchema" in repr(schema)

    def test_describe(self, schema, capsys):
        schema.describe()
        out = capsys.readouterr().out
        assert "fact_orders" in out
        assert "dim_customer" in out


# ── GoldLayer ─────────────────────────────────────────────────────────────────

class TestGoldLayer:
    def test_query_returns_dataset(self, schema):
        gold = GoldLayer(schema=schema)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        assert isinstance(ds, DataSet)

    def test_gold_lineage_node(self, schema):
        gold = GoldLayer(schema=schema)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        gold_nodes = [n for n in ds.lineage if n.operation == "gold"]
        assert len(gold_nodes) == 1
        assert gold_nodes[0].metadata["layer"] == "gold"

    def test_default_name(self, schema):
        gold = GoldLayer(schema=schema)
        ds = gold.query(fact="fact_orders", measures={"revenue": "sum"})
        assert ds.name == "fact_orders_gold"

    def test_custom_name(self, schema):
        gold = GoldLayer(schema=schema)
        ds = gold.query(fact="fact_orders", measures={"revenue": "sum"}, name="my_gold")
        assert ds.name == "my_gold"

    def test_repr(self, schema):
        gold = GoldLayer(schema=schema)
        assert "GoldLayer" in repr(gold)


# ── LineageDiagram ────────────────────────────────────────────────────────────

class TestLineageDiagram:
    def _make_ds(self):
        node1 = LineageNode(operation="load", description="Load orders")
        node2 = LineageNode(operation="filter", description="Shipped only")
        node3 = LineageNode(operation="transform", description="Calc margin")
        return DataSet(
            df=pd.DataFrame({"x": [1, 2]}),
            name="orders",
            lineage=[node1, node2, node3],
        )

    def test_from_dataset(self):
        ds = self._make_ds()
        diag = LineageDiagram(ds)
        assert diag._title == "orders"
        assert len(diag._nodes) == 3

    def test_from_empty_dataset(self):
        ds = DataSet(df=pd.DataFrame(), name="empty", lineage=[])
        diag = LineageDiagram(ds)
        assert len(diag._nodes) == 0

    def test_invalid_source_raises(self):
        with pytest.raises(TypeError):
            LineageDiagram("not a dataset")

    def test_repr(self):
        ds = self._make_ds()
        diag = LineageDiagram(ds)
        assert "LineageDiagram" in repr(diag)
        assert "orders" in repr(diag)

    def test_to_mermaid_empty(self):
        ds = DataSet(df=pd.DataFrame(), name="empty", lineage=[])
        diag = LineageDiagram(ds)
        mermaid = diag.to_mermaid()
        assert "graph LR" in mermaid

    def test_to_mermaid_nodes(self):
        ds = self._make_ds()
        diag = LineageDiagram(ds)
        mermaid = diag.to_mermaid()
        assert "LOAD" in mermaid
        assert "FILTER" in mermaid
        assert "TRANSFORM" in mermaid
        assert "N0 --> N1" in mermaid

    def test_to_mermaid_colors(self):
        ds = self._make_ds()
        diag = LineageDiagram(ds)
        mermaid = diag.to_mermaid()
        assert "#003366" in mermaid   # load = navy
        assert "#2E7D32" in mermaid   # filter = green

    def test_to_html(self):
        ds = self._make_ds()
        diag = LineageDiagram(ds)
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name
        try:
            diag.to_html(path)
            with open(path, "r") as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "svg" in content.lower()
            assert "orders" in content
        finally:
            os.unlink(path)

    def test_to_html_gold_ds(self, schema):
        gold = GoldLayer(schema=schema)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        diag = LineageDiagram(ds)
        assert len(diag._nodes) > 0
        mermaid = diag.to_mermaid()
        assert "GOLD" in mermaid
