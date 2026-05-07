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
