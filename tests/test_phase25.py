"""
Tests for Phase 2.5 — Medallion Architecture + Star Schema + Lineage Diagram.

Coverage:
  - BronzeLayer (load, lineage stamp, repr)
  - SilverLayer (cast, drop_nulls, deduplicate, rename, transform, lineage)
  - DataModel star-schema query (add_dimension, add_fact, query: groupby,
    no-groupby, no-agg, filters)
  - GoldLayer (wraps DataModel.query, gold lineage node)
  - LineageDiagram (build, to_mermaid, to_html, repr, Report source)
"""

import os
import tempfile

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, DataSet, LineageNode, QuerySpec
from tracebi.etl.bronze import BronzeLayer
from tracebi.etl.silver import SilverLayer
from tracebi.etl.gold import GoldLayer
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
def star_model(model):
    model.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region", "segment"])
    model.add_fact("fact_orders", table_name="orders",
                   measures=["revenue", "qty"],
                   foreign_keys={"dim_customer": "customer_id"})
    return model


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


# ── DataModel star-schema query ───────────────────────────────────────────────

class TestStarSchemaQuery:
    def test_add_dimension(self, star_model):
        assert "dim_customer" in star_model._dimensions

    def test_add_fact(self, star_model):
        assert "fact_orders" in star_model._facts

    def test_query_grouped(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        df = ds.to_pandas()
        assert "dim_customer.region" in df.columns
        assert "revenue" in df.columns
        assert len(df) == 3  # 3 unique regions

    def test_query_grouped_values(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        df = ds.to_pandas().set_index("dim_customer.region")
        assert df.loc["North", "revenue"] == pytest.approx(100.0 + 300.0)

    def test_query_no_groupby(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum", "order_id": "count"},
            aggregate=True,
        )
        df = ds.to_pandas()
        assert len(df) == 1
        assert df["revenue"].iloc[0] == pytest.approx(100.0 + 200.0 + 300.0 + 400.0 + 200.0)

    def test_query_no_aggregate(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            aggregate=False,
        )
        assert len(ds) == 5  # all rows returned

    def test_query_filter(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
        )
        df = ds.to_pandas()
        total = df["revenue"].sum()
        assert total == pytest.approx(100.0 + 200.0 + 400.0 + 200.0)

    def test_query_lineage_includes_join(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        ops = [n.operation for n in ds.lineage]
        assert "join" in ops

    def test_query_lineage_includes_filter(self, star_model):
        ds = star_model.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
        )
        ops = [n.operation for n in ds.lineage]
        assert "filter" in ops

    def test_unknown_fact_raises(self, star_model):
        with pytest.raises(ValueError, match="not registered"):
            star_model.query(fact="no_such_fact", measures={"revenue": "sum"})

    def test_unknown_dimension_raises(self, star_model):
        with pytest.raises(ValueError, match="not registered"):
            star_model.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["dim_nope.region"],
            )

    def test_bad_dimension_format_raises(self, star_model):
        with pytest.raises(ValueError, match="dot notation"):
            star_model.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["region"],
            )

    def test_unknown_measure_column_raises(self, star_model):
        with pytest.raises(ValueError, match="Measure column 'revnue'"):
            star_model.query(fact="fact_orders", measures={"revnue": "sum"})

    def test_unknown_measure_column_hint(self, star_model):
        with pytest.raises(ValueError, match="Did you mean 'revenue'"):
            star_model.query(fact="fact_orders", measures={"revnue": "sum"})

    def test_unknown_filter_column_raises(self, star_model):
        with pytest.raises(ValueError, match="Filter column 'staus'"):
            star_model.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                filters={"staus": "shipped"},
            )

    def test_undeclared_dim_attribute_raises(self, star_model):
        # 'segment' is declared but 'tier' is not — must fail loudly,
        # never silently drop the dimension from the result.
        with pytest.raises(ValueError, match="not declared on dimension"):
            star_model.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["dim_customer.tier"],
            )

    def test_dim_attribute_missing_from_table_raises(self, model):
        model.add_dimension("dim_customer", table_name="customers",
                            key_col="customer_id")  # no declared attrs
        model.add_fact("fact_orders", table_name="orders",
                       measures=["revenue"],
                       foreign_keys={"dim_customer": "customer_id"})
        with pytest.raises(ValueError, match="not found on dimension table"):
            model.query(
                fact="fact_orders",
                measures={"revenue": "sum"},
                dimensions=["dim_customer.nonexistent"],
            )

    def test_repr(self, star_model):
        assert "DataModel" in repr(star_model)
        assert "fact_orders" in repr(star_model)

    def test_describe(self, star_model, capsys):
        star_model.describe()
        out = capsys.readouterr().out
        assert "fact_orders" in out
        assert "dim_customer" in out


# ── GoldLayer ─────────────────────────────────────────────────────────────────

class TestGoldLayer:
    def test_query_returns_dataset(self, star_model):
        gold = GoldLayer(model=star_model)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        assert isinstance(ds, DataSet)

    def test_gold_lineage_node(self, star_model):
        gold = GoldLayer(model=star_model)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        gold_nodes = [n for n in ds.lineage if n.operation == "gold"]
        assert len(gold_nodes) == 1
        assert gold_nodes[0].metadata["layer"] == "gold"

    def test_default_name(self, star_model):
        gold = GoldLayer(model=star_model)
        ds = gold.query(fact="fact_orders", measures={"revenue": "sum"})
        assert ds.name == "fact_orders_gold"

    def test_custom_name(self, star_model):
        gold = GoldLayer(model=star_model)
        ds = gold.query(fact="fact_orders", measures={"revenue": "sum"}, name="my_gold")
        assert ds.name == "my_gold"

    def test_repr(self, star_model):
        gold = GoldLayer(model=star_model)
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

    def test_to_html_gold_ds(self, star_model):
        gold = GoldLayer(model=star_model)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )
        diag = LineageDiagram(ds)
        assert len(diag._nodes) > 0
        mermaid = diag.to_mermaid()
        assert "GOLD" in mermaid


class TestDimensionKeyFanout:
    """
    A star-schema join assumes one dimension row per key. A repeated key
    multiplies fact rows and silently inflates every additive measure —
    returning a confident, fully-lineaged, wrong number. That is the one
    failure mode an auditability product cannot ship with.
    """

    @staticmethod
    def _model(customers=None):
        orders = pd.DataFrame({
            "order_id":    [10, 11],
            "customer_id": [1, 2],
            "revenue":     [100.0, 50.0],
        })
        if customers is None:
            # customer_id 1 appears twice — e.g. SCD-2 rows, or a wrong key_col
            customers = pd.DataFrame({
                "customer_id": [1, 1, 2],
                "region":      ["NE", "NE", "SE"],
            })
        m = DataModel("FanoutDemo").add_connector(
            MemoryConnector("mem", {"orders": orders, "customers": customers})
        )
        m.add_table("orders", connector="mem", source="orders")
        m.add_table("customers", connector="mem", source="customers")
        m.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region"])
        m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
                   foreign_keys={"dim_customer": "customer_id"})
        m.connect()
        return m

    def test_duplicate_dimension_key_raises(self):
        m = self._model()
        with pytest.raises(ValueError, match="non-unique key"):
            m.query(fact="fact_orders", measures={"revenue": "sum"},
                    dimensions=["dim_customer.region"])

    def test_error_names_dimension_key_and_fanout_factor(self):
        m = self._model()
        with pytest.raises(ValueError) as exc:
            m.query(fact="fact_orders", measures={"revenue": "sum"},
                    dimensions=["dim_customer.region"])
        msg = str(exc.value)
        assert "dim_customer" in msg
        assert "customers.customer_id" in msg
        assert "2 → 3 rows" in msg          # the actual multiplication
        assert "allow_fanout=True" in msg   # the escape hatch is discoverable

    def test_the_specific_inflated_total_is_not_produced(self):
        """True revenue is 150.0; the fan-out bug reported 250.0."""
        m = self._model()
        with pytest.raises(ValueError):
            m.query(fact="fact_orders", measures={"revenue": "sum"},
                    dimensions=["dim_customer.region"])

    def test_unique_key_is_unaffected(self):
        clean = pd.DataFrame({"customer_id": [1, 2], "region": ["NE", "SE"]})
        m = self._model(customers=clean)
        res = m.query(fact="fact_orders", measures={"revenue": "sum"},
                      dimensions=["dim_customer.region"])
        assert res.to_pandas()["revenue"].sum() == 150.0

    def test_allow_fanout_proceeds_and_records_a_warning_node(self):
        m = self._model()
        res = m.query(fact="fact_orders", measures={"revenue": "sum"},
                      dimensions=["dim_customer.region"], allow_fanout=True)
        assert res.to_pandas()["revenue"].sum() == 250.0  # inflated, opted into

        warnings = [n for n in res.lineage if n.operation == "warning"]
        assert warnings, "opting into fan-out must be recorded in the lineage"
        meta = [n.metadata for n in warnings if n.metadata.get("allow_fanout")][0]
        assert meta["dimension"] == "dim_customer"
        assert meta["rows_before"] == 2
        assert meta["rows_after"] == 3
        assert meta["fanout_factor"] == 1.5

    def test_null_dimension_key_warns_without_blocking(self):
        customers = pd.DataFrame({"customer_id": [1, None, 2], "region": ["NE", "X", "SE"]})
        m = self._model(customers=customers)
        res = m.query(fact="fact_orders", measures={"revenue": "sum"},
                      dimensions=["dim_customer.region"])
        nulls = [n for n in res.lineage
                 if n.operation == "warning" and n.metadata.get("null_keys")]
        assert nulls and nulls[0].metadata["null_keys"] == 1

    def test_unreferenced_dimension_does_not_block(self):
        """Only dimensions actually joined in this query are checked."""
        m = self._model()
        res = m.query(fact="fact_orders", measures={"revenue": "sum"})
        assert res.to_pandas()["revenue"].sum() == 150.0


class TestModelValidate:
    @staticmethod
    def _model(customers):
        orders = pd.DataFrame({"order_id": [1], "customer_id": [1], "revenue": [10.0]})
        m = DataModel("V").add_connector(
            MemoryConnector("mem", {"orders": orders, "customers": customers})
        )
        m.add_table("orders", connector="mem", source="orders")
        m.add_table("customers", connector="mem", source="customers")
        m.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region"])
        m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
                   foreign_keys={"dim_customer": "customer_id"})
        m.connect()
        return m

    def test_clean_model_validates_ok(self):
        m = self._model(pd.DataFrame({"customer_id": [1, 2], "region": ["NE", "SE"]}))
        result = m.validate()
        assert result["ok"] is True
        assert result["errors"] == []
        assert result["dimensions"][0]["key_unique"] is True

    def test_duplicate_key_reported_as_error(self):
        m = self._model(pd.DataFrame({"customer_id": [1, 1], "region": ["NE", "NE"]}))
        result = m.validate()
        assert result["ok"] is False
        assert len(result["errors"]) == 1
        assert "not unique" in result["errors"][0]
        assert result["dimensions"][0]["duplicate_rows"] == 2

    def test_null_key_reported_as_warning_not_error(self):
        m = self._model(pd.DataFrame({"customer_id": [1, None], "region": ["NE", "SE"]}))
        result = m.validate()
        assert result["ok"] is True          # nulls do not inflate totals
        assert len(result["warnings"]) == 1
        assert result["dimensions"][0]["null_keys"] == 1

    def test_returns_structured_data_not_printed_output(self, capsys):
        m = self._model(pd.DataFrame({"customer_id": [1, 1], "region": ["NE", "NE"]}))
        result = m.validate()
        assert capsys.readouterr().out == ""   # consumable by CLI/API/agents
        assert set(result) == {"ok", "model", "dimensions", "errors", "warnings"}


class TestDimensionAttributeFilters:
    """
    Filtering by a dimension attribute is the most common analytic gesture
    and used to raise ValueError — query() only accepted fact columns.
    """

    @staticmethod
    def _model():
        orders = pd.DataFrame({
            "order_id":    [1, 2, 3, 4, 5, 6],
            "customer_id": [1, 2, 3, 1, 2, 3],
            "revenue":     [100.0, 200.0, 300.0, 50.0, 80.0, 400.0],
            "status": ["shipped", "open", "shipped", "shipped", "open", "shipped"],
        })
        customers = pd.DataFrame({
            "customer_id": [1, 2, 3],
            "region":      ["West", "NE", "West"],
            "tier":        ["ent", "smb", "ent"],
        })
        m = DataModel("F").add_connector(
            MemoryConnector("mem", {"orders": orders, "customers": customers})
        )
        m.add_table("orders", connector="mem", source="orders")
        m.add_table("customers", connector="mem", source="customers")
        m.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region", "tier"])
        m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
                   foreign_keys={"dim_customer": "customer_id"})
        m.connect()
        return m

    def _sum(self, **kw):
        df = self._model().query(
            fact="fact_orders", measures={"revenue": "sum"}, **kw
        ).to_pandas()
        return float(df["revenue"].sum()) if len(df) else 0.0

    def test_filter_on_dimension_attribute(self):
        # West = customers 1 and 3 → 100 + 300 + 50 + 400
        assert self._sum(filters={"dim_customer.region": "West"}) == 850.0

    def test_dimension_joined_even_when_not_grouped_by(self):
        """A filter-only dimension still has to be joined."""
        df = self._model().query(
            fact="fact_orders", measures={"revenue": "sum"},
            filters={"dim_customer.region": "NE"},
        ).to_pandas()
        assert float(df["revenue"].sum()) == 280.0

    def test_fact_and_dimension_predicates_combine(self):
        assert self._sum(filters={"status": "shipped",
                                  "dim_customer.tier": "ent"}) == 850.0

    def test_bare_dimension_attribute_says_how_to_reference_it(self):
        with pytest.raises(ValueError, match=r"reference it as 'dim_customer\.region'"):
            self._sum(filters={"region": "West"})

    def test_unknown_dimension_suggests_a_match(self):
        with pytest.raises(ValueError, match="Did you mean 'dim_customer'"):
            self._sum(filters={"dim_custmer.region": "West"})

    def test_undeclared_dimension_attribute_rejected(self):
        with pytest.raises(ValueError, match="not declared on dimension"):
            self._sum(filters={"dim_customer.zipcode": "90210"})


class TestFilterOperators:
    """Equality-only filters were too thin for a semantic layer."""

    def _sum(self, **kw):
        return TestDimensionAttributeFilters()._sum(**kw)

    def test_scalar_shorthand_is_equality(self):
        assert self._sum(filters={"status": "shipped"}) == 850.0

    def test_list_shorthand_is_in(self):
        assert self._sum(filters={"status": ["shipped"]}) == 850.0

    def test_gte(self):
        assert self._sum(filters={"revenue": {"gte": 200}}) == 900.0

    def test_ne(self):
        assert self._sum(filters={"status": {"ne": "open"}}) == 850.0

    def test_between(self):
        assert self._sum(filters={"revenue": {"between": [100, 300]}}) == 600.0

    def test_not_in_on_a_dimension(self):
        assert self._sum(filters={"dim_customer.region": {"not_in": ["West"]}}) == 280.0

    def test_contains(self):
        assert self._sum(filters={"status": {"contains": "ship"}}) == 850.0

    def test_empty_in_matches_nothing(self):
        assert self._sum(filters={"revenue": {"in": []}}) == 0.0

    def test_unknown_operator_suggests_a_match(self):
        with pytest.raises(ValueError, match="Did you mean 'gte'"):
            self._sum(filters={"revenue": {"greater": 100}})

    def test_between_needs_two_values(self):
        with pytest.raises(ValueError, match="two-element"):
            self._sum(filters={"revenue": {"between": [1]}})

    def test_in_needs_a_list(self):
        with pytest.raises(ValueError, match="needs a list"):
            self._sum(filters={"status": {"in": "shipped"}})

    def test_one_operator_per_filter_entry(self):
        with pytest.raises(ValueError, match="exactly one operator"):
            self._sum(filters={"revenue": {"gte": 1, "lte": 2}})

    def test_predicates_are_recorded_in_lineage(self):
        ds = TestDimensionAttributeFilters._model().query(
            fact="fact_orders", measures={"revenue": "sum"},
            filters={"dim_customer.region": "West"},
        )
        nodes = [n for n in ds.lineage if n.operation == "filter"]
        assert nodes, "every predicate must appear in the audit chain"
        meta = nodes[-1].metadata
        assert meta["target"] == "dim_customer.region"
        assert meta["operator"] == "eq"
        assert meta["on"] == "dimension"


class TestEngineParity:
    """
    DuckDB is preferred, pandas is the fallback. They must never disagree —
    a query returning different numbers depending on what is installed would
    make the lineage meaningless.
    """

    CASES = [
        {"filters": {"dim_customer.region": "West"}},
        {"filters": {"revenue": {"gte": 200}}},
        {"filters": {"status": ["shipped"]}},
        {"filters": {"revenue": {"between": [100, 300]}}},
        {"filters": {"dim_customer.region": {"not_in": ["West"]}}},
        {"filters": {"status": "shipped", "dim_customer.tier": "ent"}},
        {"dimensions": ["dim_customer.tier"], "filters": {"dim_customer.region": "West"}},
        {"filters": {"status": {"contains": "ship"}}},
    ]

    @staticmethod
    def _run(case):
        return TestDimensionAttributeFilters._model().query(
            fact="fact_orders", measures={"revenue": "sum"}, **case
        ).to_pandas()

    def test_engines_agree(self, monkeypatch):
        import sys

        duck_results = [self._run(c) for c in self.CASES]

        class _Block:
            # find_spec, not find_module: the legacy protocol was removed
            # from meta-path finders in 3.12, where a find_module blocker
            # would silently not block — making this compare duckdb to
            # itself and pass for the wrong reason.
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[0] == "duckdb":
                    raise ImportError(fullname)
                return None

        blocker = _Block()
        saved = {k: v for k, v in sys.modules.items() if k.startswith("duckdb")}
        for k in saved:
            del sys.modules[k]
        sys.meta_path.insert(0, blocker)
        try:
            pandas_results = [self._run(c) for c in self.CASES]
        finally:
            sys.meta_path.remove(blocker)
            sys.modules.update(saved)

        for case, d, p in zip(self.CASES, duck_results, pandas_results):
            assert len(d) == len(p), f"row count differs for {case}"
            assert abs(float(d["revenue"].sum()) - float(p["revenue"].sum())) < 1e-9, (
                f"engines disagree for {case}"
            )
            # Row ORDER too, not just totals. pandas' groupby sorts by
            # default and DuckDB returned hash order, so the two engines
            # produced different frames for the same query — and
            # DataSet.fingerprint() hashes row order, so identical runs
            # produced different fingerprints.
            pd.testing.assert_frame_equal(
                d.reset_index(drop=True), p.reset_index(drop=True),
                check_dtype=False,
                obj=f"engine output for {case}",
            )


class TestQueryDeterminism:
    """
    A fingerprint that changes between identical runs makes the manifest
    unverifiable, which is the whole product promise.
    """

    def test_repeated_identical_queries_have_one_fingerprint(self):
        model = TestDimensionAttributeFilters._model()
        prints = {
            model.query(
                fact="fact_orders", measures={"revenue": "sum"},
                dimensions=["dim_customer.region"],
            ).fingerprint()
            for _ in range(12)
        }
        assert len(prints) == 1, (
            "identical queries produced different fingerprints — grouped "
            "results must have a deterministic row order"
        )

    def test_grouped_rows_come_back_sorted_by_dimension(self):
        df = TestDimensionAttributeFilters._model().query(
            fact="fact_orders", measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        ).to_pandas()
        col = list(df["dim_customer.region"])
        assert col == sorted(col)


class TestNamedMeasures:
    """
    Measures declared once on the model, reviewed in a PR, versioned in
    git, and referenced by name — the difference between a governed
    semantic model and a pile of ad-hoc groupbys.
    """

    @staticmethod
    def _model():
        orders = pd.DataFrame({
            "order_id":    [1, 2, 3, 4],
            "customer_id": [1, 2, 1, 2],
            "revenue":     [100.0, 200.0, 300.0, 400.0],
            "cost":        [60.0, 150.0, 180.0, 320.0],
        })
        customers = pd.DataFrame({"customer_id": [1, 2], "region": ["West", "NE"]})
        m = DataModel("Meas").add_connector(
            MemoryConnector("mem", {"orders": orders, "customers": customers})
        )
        m.add_table("orders", connector="mem", source="orders")
        m.add_table("customers", connector="mem", source="customers")
        m.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region"])
        m.add_fact("fact_orders", table_name="orders",
                   measures=["revenue", "cost"],
                   foreign_keys={"dim_customer": "customer_id"})
        m.add_measure("revenue", column="revenue", agg="sum",
                      description="Gross booked revenue")
        m.add_measure("orders", column="order_id", agg="nunique")
        m.add_measure("gross_margin", expr="revenue - cost", agg="sum")
        m.add_measure("margin_pct", ratio=("gross_margin", "revenue"),
                      format="percent")
        m.connect()
        return m

    def test_simple_measure_by_name(self):
        df = self._model().query(fact="fact_orders", measures=["revenue"]).to_pandas()
        assert float(df["revenue"].iloc[0]) == 1000.0

    def test_expression_measure(self):
        df = self._model().query(fact="fact_orders", measures=["gross_margin"]).to_pandas()
        assert float(df["gross_margin"].iloc[0]) == 290.0   # 1000 - 710

    def test_ratio_divides_totals_not_rows(self):
        """sum(margin)/sum(revenue), not the mean of per-row ratios."""
        df = self._model().query(fact="fact_orders", measures=["margin_pct"]).to_pandas()
        assert abs(float(df["margin_pct"].iloc[0]) - 0.29) < 1e-9

    def test_measures_group_by_dimension(self):
        df = self._model().query(
            fact="fact_orders", measures=["revenue", "gross_margin", "margin_pct"],
            dimensions=["dim_customer.region"],
        ).to_pandas().set_index("dim_customer.region")
        assert float(df.loc["West", "revenue"]) == 400.0
        assert float(df.loc["West", "gross_margin"]) == 160.0
        assert abs(float(df.loc["West", "margin_pct"]) - 0.40) < 1e-9

    def test_legacy_dict_form_still_works(self):
        df = self._model().query(
            fact="fact_orders", measures={"revenue": "sum"}
        ).to_pandas()
        assert float(df["revenue"].iloc[0]) == 1000.0

    # ── The constraint that protects reproducibility ───────────────────

    def test_callables_are_rejected(self):
        m = self._model()
        with pytest.raises(TypeError, match="not a callable"):
            m.add_measure("bad", column=lambda df: df.revenue, agg="sum")

    def test_function_calls_rejected_in_expressions(self):
        m = self._model()
        with pytest.raises(ValueError, match="function call"):
            m.add_measure("bad", expr="SUM(revenue)", agg="sum")

    def test_sql_fragments_rejected_in_expressions(self):
        m = self._model()
        with pytest.raises(ValueError, match="may only contain"):
            m.add_measure("bad", expr="revenue); DROP TABLE x--", agg="sum")

    def test_arithmetic_with_parens_allowed(self):
        m = self._model()
        m.add_measure("half_margin", expr="(revenue - cost) / 2", agg="sum")
        df = m.query(fact="fact_orders", measures=["half_margin"]).to_pandas()
        assert float(df["half_margin"].iloc[0]) == 145.0

    # ── Declaration-time validation ────────────────────────────────────

    def test_exactly_one_kind_required(self):
        m = self._model()
        with pytest.raises(ValueError, match="exactly one of"):
            m.add_measure("bad", column="revenue", expr="revenue - cost", agg="sum")

    def test_agg_required_for_non_ratio(self):
        m = self._model()
        with pytest.raises(ValueError, match="needs an agg"):
            m.add_measure("bad", column="revenue")

    def test_unknown_agg_suggests_a_match(self):
        m = self._model()
        with pytest.raises(ValueError, match="Did you mean 'sum'"):
            m.add_measure("bad", column="revenue", agg="summ")

    def test_ratio_takes_no_agg(self):
        m = self._model()
        with pytest.raises(ValueError, match="take no agg"):
            m.add_measure("bad", ratio=("revenue", "cost"), agg="sum")

    # ── Query-time validation ──────────────────────────────────────────

    def test_expression_referencing_missing_column_fails_loudly(self):
        m = self._model()
        m.add_measure("bogus", expr="revenue - nope", agg="sum")
        with pytest.raises(ValueError, match="references column 'nope'"):
            m.query(fact="fact_orders", measures=["bogus"])

    def test_undeclared_measure_name_is_actionable(self):
        m = self._model()
        with pytest.raises(ValueError, match="add_measure"):
            m.query(fact="fact_orders", measures=["revenu"])

    def test_self_referential_ratio_detected(self):
        m = self._model()
        m.add_measure("loop", ratio=("loop", "revenue"))
        with pytest.raises(ValueError, match="defined in terms of itself"):
            m.query(fact="fact_orders", measures=["loop"])

    def test_info_exposes_the_vocabulary(self):
        info = self._model().info()
        by_name = {m["name"]: m for m in info["measures"]}
        assert by_name["revenue"]["description"] == "Gross booked revenue"
        assert by_name["gross_margin"]["expr"] == "revenue - cost"
        assert by_name["margin_pct"]["ratio"] == ["gross_margin", "revenue"]
        assert "between" in info["filter_operators"]


class TestQuerySpec:
    """A query as data: serializable, diffable, committable, replayable."""

    def test_round_trips_through_json(self):
        import json

        spec = QuerySpec(
            fact="fact_orders", measures=["revenue"],
            dimensions=("dim_customer.region",),
            filters={"dim_customer.region": "West"},
        )
        again = QuerySpec.from_dict(json.loads(json.dumps(spec.to_dict())))
        assert again.to_dict() == spec.to_dict()

    def test_execute_matches_query(self):
        m = TestNamedMeasures._model()
        via_query = m.query(
            fact="fact_orders", measures=["revenue"],
            dimensions=["dim_customer.region"],
        ).to_pandas()
        via_spec = m.execute(QuerySpec(
            fact="fact_orders", measures=["revenue"],
            dimensions=("dim_customer.region",),
        )).to_pandas()
        pd.testing.assert_frame_equal(via_query, via_spec)

    def test_spec_is_stamped_into_lineage(self):
        m = TestNamedMeasures._model()
        ds = m.query(fact="fact_orders", measures=["revenue"])
        stamped = [n for n in ds.lineage if n.metadata.get("query_spec")]
        assert stamped, "the executed spec must be recorded for reproducibility"
        assert stamped[-1].metadata["query_spec"]["fact"] == "fact_orders"

    def test_missing_required_fields_rejected(self):
        with pytest.raises(ValueError, match="requires a 'fact'"):
            QuerySpec.from_dict({"measures": ["revenue"]})
        with pytest.raises(ValueError, match="requires 'measures'"):
            QuerySpec.from_dict({"fact": "fact_orders"})

    def test_unknown_fields_rejected(self):
        # "limit" was this test's example until the grammar gained
        # order_by/limit (M0 flip ledger) — "top" stays unknown.
        with pytest.raises(ValueError, match="Unknown QuerySpec field"):
            QuerySpec.from_dict({"fact": "f", "measures": ["m"], "top": 10})
