"""
Tests for TraceBi Phase 1: Connectors, DataSet, DataModel
"""

import os
import tempfile
import pytest
import pandas as pd

from tracebi import DataModel, MemoryConnector, CSVConnector, DataSet, LineageNode
from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel


# ─────────────────────────────────────────────
# Fixtures
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


@pytest.fixture
def model_with_data(sample_df):
    customers_df = pd.DataFrame({
        "id":   [1, 2, 3],
        "name": ["Alice", "Bob", "Carol"],
    })
    connector = MemoryConnector("mem", tables={
        "sales":     sample_df,
        "customers": customers_df,
    })
    model = DataModel("TestModel")
    model.add_connector(connector)
    model.add_table("sales",     connector="mem", source="sales")
    model.add_table("customers", connector="mem", source="customers")
    return model


# ─────────────────────────────────────────────
# LineageNode tests
# ─────────────────────────────────────────────

class TestLineageNode:

    def test_defaults(self):
        node = LineageNode(operation="load")
        assert node.operation == "load"
        assert node.description == ""
        assert node.connector is None
        assert node.source is None
        assert node.metadata == {}
        assert node.timestamp  # non-empty string

    def test_to_dict_keys(self):
        node = LineageNode(
            operation="filter",
            description="test filter",
            metadata={"rows_before": 10, "rows_after": 5},
        )
        d = node.to_dict()
        assert set(d.keys()) == {"operation", "description", "connector",
                                 "source", "timestamp", "metadata"}
        assert d["metadata"]["rows_before"] == 10

    def test_attributes_frozen(self):
        node = LineageNode(operation="load")
        with pytest.raises(AttributeError):
            node.operation = "filter"

    def test_metadata_read_only(self):
        node = LineageNode(operation="filter", metadata={"rows_after": 5})
        with pytest.raises(TypeError):
            node.metadata["rows_after"] = 999

    def test_connector_read_only(self):
        node = LineageNode(operation="load", connector={"connector_name": "x"})
        with pytest.raises(TypeError):
            node.connector["connector_name"] = "evil"

    def test_to_dict_returns_mutable_copies(self):
        node = LineageNode(operation="filter", metadata={"rows_after": 5})
        d = node.to_dict()
        d["metadata"]["rows_after"] = 999          # copy is editable...
        assert node.metadata["rows_after"] == 5    # ...the node is not


# ─────────────────────────────────────────────
# DataSet tests
# ─────────────────────────────────────────────

class TestDataSet:

    def test_construction(self, sample_ds, sample_df):
        assert sample_ds.name == "test"
        assert sample_ds.shape == sample_df.shape
        assert len(sample_ds.lineage) == 1

    def test_to_pandas_returns_copy(self, sample_ds):
        df = sample_ds.to_pandas()
        df["new_col"] = 99
        assert "new_col" not in sample_ds.to_pandas().columns

    def test_filter(self, sample_ds):
        filtered = sample_ds.filter("status == 'active'", description="Active only")
        assert len(filtered) == 3
        assert len(filtered.lineage) == 2
        assert filtered.lineage[-1].operation == "filter"
        assert filtered.lineage[-1].metadata["rows_before"] == 5
        assert filtered.lineage[-1].metadata["rows_after"] == 3

    def test_filter_does_not_mutate_original(self, sample_ds):
        _ = sample_ds.filter("value > 100")
        assert len(sample_ds) == 5  # original unchanged

    def test_transform(self, sample_ds):
        transformed = sample_ds.transform(
            lambda df: df.assign(doubled=df["value"] * 2),
            description="double value",
        )
        assert "doubled" in transformed.to_pandas().columns
        assert len(transformed.lineage) == 2
        assert transformed.lineage[-1].operation == "transform"

    def test_sort_ascending(self, sample_ds):
        sorted_ds = sample_ds.sort("value", ascending=True)
        vals = sorted_ds.to_pandas()["value"].tolist()
        assert vals == sorted(vals)
        assert sorted_ds.lineage[-1].operation == "sort"

    def test_sort_descending(self, sample_ds):
        sorted_ds = sample_ds.sort("value", ascending=False)
        vals = sorted_ds.to_pandas()["value"].tolist()
        assert vals == sorted(vals, reverse=True)

    def test_select(self, sample_ds):
        selected = sample_ds.select(["id", "value"])
        assert list(selected.to_pandas().columns) == ["id", "value"]
        assert selected.lineage[-1].operation == "select"

    def test_rename(self, sample_ds):
        renamed = sample_ds.rename({"value": "amount"})
        assert "amount" in renamed.to_pandas().columns
        assert "value" not in renamed.to_pandas().columns
        assert renamed.lineage[-1].operation == "rename"

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

    def test_fingerprint_is_sha256(self, sample_ds):
        fp = sample_ds.fingerprint()
        assert len(fp) == 64
        int(fp, 16)  # valid hex

    def test_fingerprint_changes_on_rename(self, sample_ds):
        renamed = sample_ds.rename({"value": "amount"})
        assert sample_ds.fingerprint() != renamed.fingerprint()

    def test_lineage_to_dict(self, sample_ds):
        result = sample_ds.filter("id > 1").lineage_to_dict()
        assert len(result) == 2
        assert result[0]["operation"] == "load"
        assert result[1]["operation"] == "filter"

    def test_print_lineage(self, sample_ds, capsys):
        sample_ds.filter("value > 50").print_lineage()
        out = capsys.readouterr().out
        assert "test" in out
        assert "filter" in out.lower()

    def test_len(self, sample_ds):
        assert len(sample_ds) == 5

    def test_columns_property(self, sample_ds):
        assert set(sample_ds.columns) == {"id", "region", "value", "status"}

    def test_repr(self, sample_ds):
        r = repr(sample_ds)
        assert "DataSet" in r
        assert "test" in r


# ─────────────────────────────────────────────
# DataSet join / aggregate / assign
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

    def test_join_on_shared_key(self, sample_ds, customers_ds):
        joined = sample_ds.join(customers_ds, on="id", how="left")
        assert len(joined) == 5
        assert "name" in joined.columns
        node = joined.lineage[-1]
        assert node.operation == "join"
        assert node.metadata["right"] == "customers"
        assert node.metadata["how"] == "left"
        assert node.metadata["rows_left"] == 5
        assert node.metadata["rows_right"] == 3
        assert node.metadata["rows_after"] == 5

    def test_join_lineage_keeps_both_sides(self, sample_ds, customers_ds):
        joined = sample_ds.join(customers_ds, on="id")
        ops = [n.operation for n in joined.lineage]
        assert ops == ["load", "load", "join"]

    def test_join_inner_drops_unmatched(self, sample_ds, customers_ds):
        joined = sample_ds.join(customers_ds, on="id", how="inner")
        assert len(joined) == 3

    def test_join_left_on_right_on(self, sample_ds, customers_ds):
        renamed = customers_ds.rename({"id": "customer_id"})
        joined = sample_ds.join(renamed, left_on="id", right_on="customer_id")
        assert len(joined) == 5
        assert joined.lineage[-1].metadata["left_key"] == "id"
        assert joined.lineage[-1].metadata["right_key"] == "customer_id"

    def test_join_does_not_mutate_either_side(self, sample_ds, customers_ds):
        _ = sample_ds.join(customers_ds, on="id")
        assert len(sample_ds) == 5
        assert len(customers_ds) == 3
        assert len(sample_ds.lineage) == 1
        assert len(customers_ds.lineage) == 1

    def test_join_requires_keys(self, sample_ds, customers_ds):
        with pytest.raises(ValueError, match="requires 'on'"):
            sample_ds.join(customers_ds)
        with pytest.raises(ValueError, match="not both"):
            sample_ds.join(customers_ds, on="id", left_on="id", right_on="id")

    def test_join_missing_key_suggests_close_match(self, sample_ds, customers_ds):
        with pytest.raises(ValueError, match="did you mean 'id'"):
            sample_ds.join(customers_ds, on="idd")


class TestAggregate:

    def test_aggregate_same_name_measure(self, sample_ds):
        agg = sample_ds.aggregate(by="region", value="sum")
        assert len(agg) == 4  # North, South, East, West
        node = agg.lineage[-1]
        assert node.operation == "aggregate"
        assert node.metadata["by"] == ["region"]
        assert node.metadata["measures"]["value"] == {"column": "value", "fn": "sum"}

    def test_aggregate_values_correct(self, sample_ds):
        agg = sample_ds.aggregate(by="region", value="sum")
        df = agg.to_pandas().set_index("region")
        assert df.loc["North", "value"] == 400.0  # 100 + 300

    def test_aggregate_tuple_measure(self, sample_ds):
        agg = sample_ds.aggregate(by="region", n=("id", "nunique"))
        df = agg.to_pandas().set_index("region")
        assert df.loc["North", "n"] == 2
        node = agg.lineage[-1]
        assert node.metadata["measures"]["n"] == {"column": "id", "fn": "nunique"}

    def test_aggregate_rows_metadata(self, sample_ds):
        agg = sample_ds.aggregate(by="region", value="sum")
        assert agg.lineage[-1].metadata["rows_before"] == 5
        assert agg.lineage[-1].metadata["rows_after"] == len(agg)

    def test_aggregate_requires_measures(self, sample_ds):
        with pytest.raises(ValueError, match="at least one measure"):
            sample_ds.aggregate(by="region")

    def test_aggregate_missing_column_raises(self, sample_ds):
        with pytest.raises(ValueError, match="did you mean 'value'"):
            sample_ds.aggregate(by="region", valu="sum")


class TestAssign:

    def test_assign_callable(self, sample_ds):
        ds = sample_ds.assign(doubled=lambda df: df["value"] * 2)
        assert "doubled" in ds.columns
        assert ds.lineage[-1].operation == "assign"
        assert ds.lineage[-1].metadata["columns_added"] == ["doubled"]

    def test_assign_replace_tracked(self, sample_ds):
        ds = sample_ds.assign(value=lambda df: df["value"] * 0)
        assert ds.lineage[-1].metadata["columns_replaced"] == ["value"]
        assert "columns_added" not in ds.lineage[-1].metadata

    def test_assign_does_not_mutate_original(self, sample_ds):
        _ = sample_ds.assign(doubled=lambda df: df["value"] * 2)
        assert "doubled" not in sample_ds.columns

    def test_assign_requires_columns(self, sample_ds):
        with pytest.raises(ValueError, match="at least one column"):
            sample_ds.assign()


# ─────────────────────────────────────────────
# Public API exports
# ─────────────────────────────────────────────

class TestPublicExports:

    def test_all_connectors_importable_from_top_level(self):
        # Optional-dep connectors import lazily, so the names must always resolve
        from tracebi import (  # noqa: F401
            BaseConnector, CSVConnector, SQLConnector, MemoryConnector,
            DuckDBConnector, BigQueryConnector, SnowflakeConnector,
        )


# ─────────────────────────────────────────────
# MemoryConnector tests
# ─────────────────────────────────────────────

class TestMemoryConnector:

    def test_connect_is_noop(self, sample_df):
        c = MemoryConnector("test", {"t": sample_df})
        c.connect()  # should not raise

    def test_load_returns_copy(self, sample_df):
        c = MemoryConnector("test", {"t": sample_df})
        df = c.load("t")
        df["new"] = 1
        assert "new" not in c.load("t").columns

    def test_load_missing_raises(self, sample_df):
        c = MemoryConnector("test", {"t": sample_df})
        with pytest.raises(KeyError, match="missing"):
            c.load("missing")

    def test_add_table(self, sample_df):
        c = MemoryConnector("test", {})
        c.add_table("t", sample_df)
        assert len(c.load("t")) == len(sample_df)


# ─────────────────────────────────────────────
# CSVConnector tests
# ─────────────────────────────────────────────

class TestCSVConnector:

    def test_load_csv(self, sample_df):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.csv")
            sample_df.to_csv(path, index=False)
            c = CSVConnector("csv_test", directory=tmp)
            c.connect()
            df = c.load("test.csv")
            assert list(df.columns) == list(sample_df.columns)
            assert len(df) == len(sample_df)

    def test_connect_missing_dir(self):
        c = CSVConnector("bad", directory="/nonexistent/path")
        with pytest.raises(FileNotFoundError):
            c.connect()


# ─────────────────────────────────────────────
# DataModel tests
# ─────────────────────────────────────────────

class TestDataModel:

    def test_load(self, model_with_data, sample_df):
        ds = model_with_data.load("sales")
        assert isinstance(ds, DataSet)
        assert ds.name == "sales"
        assert ds.shape == sample_df.shape
        assert len(ds.lineage) == 1
        assert ds.lineage[0].operation == "load"

    def test_load_unknown_table_raises(self, model_with_data):
        with pytest.raises(ValueError, match="not registered"):
            model_with_data.load("nonexistent")

    def test_add_table_unknown_connector_raises(self, model_with_data):
        with pytest.raises(ValueError, match="not registered"):
            model_with_data.add_table("x", connector="missing", source="x")

    def test_add_relationship_unknown_table_raises(self, model_with_data):
        with pytest.raises(ValueError, match="not registered"):
            model_with_data.add_relationship(
                "bad_rel", "sales", "nonexistent", "id"
            )

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

    def test_describe(self, model_with_data, capsys):
        model_with_data.describe()
        out = capsys.readouterr().out
        assert "TestModel" in out
        assert "sales" in out

    def test_repr(self, model_with_data):
        r = repr(model_with_data)
        assert "DataModel" in r
        assert "sales" in r

    def test_connect_calls_connector(self, sample_df):
        connected = []

        class TrackingConnector(MemoryConnector):
            def connect(self):
                connected.append(True)

        c = TrackingConnector("t", {"x": sample_df})
        m = DataModel("M")
        m.add_connector(c)
        m.add_table("x", connector="t", source="x")
        m.connect()
        assert connected == [True]


# ─────────────────────────────────────────────
# Notebook integration tests
# ─────────────────────────────────────────────

class TestNotebookReprs:

    def test_dataset_repr_html(self, sample_df):
        ds = DataSet(df=sample_df, name="orders", lineage=[
            LineageNode(operation="load", description="Loaded orders"),
        ]).filter("value > 100")
        html = ds._repr_html_()
        assert "orders" in html
        # Lineage chain badges
        assert ">load<" in html
        assert ">filter<" in html
        # Column headers with dtypes
        assert "region" in html
        assert "float64" in html

    def test_dataset_repr_html_caps_preview(self, sample_df):
        big = pd.concat([sample_df] * 5, ignore_index=True)   # 25 rows
        ds = DataSet(df=big, name="big", lineage=[])
        html = ds._repr_html_()
        assert "15 more rows" in html

    def test_dataset_repr_html_escapes(self):
        df = pd.DataFrame({"col": ["<script>alert(1)</script>"]})
        ds = DataSet(df=df, name="<evil>", lineage=[])
        html = ds._repr_html_()
        assert "<script>" not in html
        assert "<evil>" not in html

    def test_dataset_help_prints(self, sample_df, capsys):
        DataSet(df=sample_df, name="x", lineage=[]).help()
        out = capsys.readouterr().out
        assert ".filter(" in out
        assert ".transform(" in out
        assert ".print_lineage()" in out

    def test_datamodel_repr_html(self, sample_df):
        model = DataModel("Sales").add_connector(
            MemoryConnector("mem", {"orders": sample_df}))
        model.add_table("orders", connector="mem", source="orders")
        html = model._repr_html_()
        assert "DataModel: Sales" in html
        assert "orders" in html
        assert "mem" in html

    def test_datamodel_help_prints(self, capsys):
        DataModel("M").help()
        out = capsys.readouterr().out
        assert ".load(" in out
        assert ".query(" in out


class TestLineageRowCounts:
    """Every operation records row counts so the lineage UI can show what
    each step did to the data — without storing any detail records."""

    def test_transform_records_counts_and_columns(self, sample_df):
        ds = DataSet(df=sample_df, name="x", lineage=[])
        out = ds.transform(lambda df: df.assign(double=df.value * 2).drop(columns=["status"]))
        meta = out.lineage[-1].metadata
        assert meta["rows_before"] == 5
        assert meta["rows_after"] == 5
        assert meta["columns_added"] == ["double"]
        assert meta["columns_removed"] == ["status"]

    def test_transform_omits_column_keys_when_unchanged(self, sample_df):
        ds = DataSet(df=sample_df, name="x", lineage=[])
        meta = ds.transform(lambda df: df).lineage[-1].metadata
        assert "columns_added" not in meta
        assert "columns_removed" not in meta

    def test_sort_select_rename_record_rows(self, sample_df):
        ds = DataSet(df=sample_df, name="x", lineage=[])
        assert ds.sort("value").lineage[-1].metadata["rows"] == 5
        assert ds.select(["id"]).lineage[-1].metadata["rows"] == 5
        assert ds.rename({"id": "key"}).lineage[-1].metadata["rows"] == 5

    def test_join_records_row_counts(self, sample_df):
        regions = pd.DataFrame({
            "region": ["North", "South", "East", "West"],
            "manager": ["a", "b", "c", "d"],
        })
        model = DataModel("M").add_connector(
            MemoryConnector("mem", {"orders": sample_df, "regions": regions}))
        model.add_table("orders", connector="mem", source="orders")
        model.add_table("regions", connector="mem", source="regions")
        model.add_relationship("orders_regions",
                               left_table="orders", right_table="regions",
                               left_key="region", right_key="region")
        ds = model.resolve("orders_regions")
        join_meta = [n for n in ds.lineage if n.operation == "join"][-1].metadata
        assert join_meta["rows_left"] == 5
        assert join_meta["rows_right"] == 4
        assert join_meta["rows_after"] == len(ds)
