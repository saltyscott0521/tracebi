"""Contract tests for the Snowflake and BigQuery connectors.

Neither driver is installed in CI. These tests inject a fake module and
never open a network connection. Lineage is attached by ``DataModel.load``,
which is what turns a connector frame into a ``DataSet``.
"""

import sys
import types

import pandas as pd
import pytest

from tracebi.connectors.bigquery_connector import BigQueryConnector
from tracebi.connectors.snowflake_connector import SnowflakeConnector


def _frame():
    return pd.DataFrame({
        "id": [1, 2],
        "region": ["east", "west"],
        "ok": [True, False],
        "n": [2, 3],
        "amt": [1.5, 2.5],
    })


def _install_snowflake(monkeypatch):
    calls = []

    class _Cursor:
        def execute(self, query, params=None):
            calls.append(("execute", query, params))

        def fetch_pandas_all(self):
            return _frame()

        def close(self):
            calls.append(("close",))

    class _Conn:
        def cursor(self):
            return _Cursor()

    mod = types.ModuleType("snowflake.connector")

    def connect(**kwargs):
        calls.append(("connect", kwargs))
        return _Conn()

    mod.connect = connect
    parent = types.ModuleType("snowflake")
    parent.connector = mod
    monkeypatch.setitem(sys.modules, "snowflake", parent)
    monkeypatch.setitem(sys.modules, "snowflake.connector", mod)
    return calls


def _install_bigquery(monkeypatch):
    calls = []

    class ScalarQueryParameter:
        def __init__(self, name, type_, value):
            self.name = name
            self.type_ = type_
            self.value = value

    class QueryJobConfig:
        def __init__(self, query_parameters=None):
            self.query_parameters = query_parameters

    class _Job:
        def to_dataframe(self):
            return _frame()

    class Client:
        def __init__(self, project, credentials):
            calls.append(("client", project, credentials))

        def query(self, query, job_config=None):
            calls.append(("query", query, job_config))
            return _Job()

    bq = types.ModuleType("google.cloud.bigquery")
    bq.Client = Client
    bq.ScalarQueryParameter = ScalarQueryParameter
    bq.QueryJobConfig = QueryJobConfig
    cloud = types.ModuleType("google.cloud")
    cloud.__path__ = []
    cloud.bigquery = bq
    google = types.ModuleType("google")
    google.__path__ = []
    google.cloud = cloud
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bq)
    return calls


def _snowflake(**overrides):
    kwargs = dict(
        account="acct", user="usr", password="secret",
        warehouse="WH", database="DB", schema="SCH",
    )
    kwargs.update(overrides)
    return SnowflakeConnector("sf", **kwargs)


def _bigquery(credentials="adc"):
    return BigQueryConnector("bq", project="proj", dataset="analytics",
                             credentials=credentials)


class TestSnowflake:


    def test_table_load_pushes_columns_and_filter(self, monkeypatch):
        calls = _install_snowflake(monkeypatch)
        df = _snowflake().load("ORDERS", filter={"region": "east"}, columns=["id"])
        assert list(df["id"]) == [1, 2]
        assert calls[0][0] == "connect"
        assert calls[1] == (
            "execute",
            'SELECT "id" FROM "ORDERS" WHERE "region" = %s',
            ("east",),
        )
        assert calls[2] == ("close",)


    def test_a_quote_in_an_identifier_is_refused(self, monkeypatch):
        _install_snowflake(monkeypatch)
        with pytest.raises(ValueError, match="Invalid identifier"):
            _snowflake().load('ORD"ERS')


    def test_describe_omits_the_password_and_schema_comes_from_the_base(self):
        connector = _snowflake()
        described = connector.describe()
        assert described == {"name": "sf", "type": "SnowflakeConnector"}
        assert "secret" not in described.values()
        assert connector.column_schema("ORDERS") is None
        assert connector.supports_pushdown() is True


class TestBigQuery:
    def test_missing_driver_names_the_extra(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "google.cloud.bigquery", None)
        with pytest.raises(ImportError, match=r"tracebi\[bigquery\]"):
            _bigquery().connect()


    def test_table_load_quotes_and_parameterizes(self, monkeypatch):
        calls = _install_bigquery(monkeypatch)
        _bigquery().load(
            "events",
            columns=["id"],
            filter={"ok": True, "n": 2, "amt": 1.5, "region": "east"},
        )
        kind, query, config = calls[1]
        assert kind == "query"
        assert query == (
            "SELECT `id` FROM `proj.analytics.events` "
            "WHERE `ok` = @p0 AND `n` = @p1 AND `amt` = @p2 AND `region` = @p3"
        )
        params = config.query_parameters
        assert [(p.name, p.type_, p.value) for p in params] == [
            ("p0", "BOOL", True),
            ("p1", "INT64", 2),
            ("p2", "FLOAT64", 1.5),
            ("p3", "STRING", "east"),
        ]


    def test_unsupported_filter_type_is_refused(self, monkeypatch):
        _install_bigquery(monkeypatch)
        with pytest.raises(ValueError, match="Unsupported filter value type"):
            _bigquery().load("events", filter={"when": object()})

    def test_a_backtick_in_an_identifier_is_refused(self, monkeypatch):
        _install_bigquery(monkeypatch)
        with pytest.raises(ValueError, match="Invalid identifier"):
            _bigquery().load("ev`ents")


    def test_describe_omits_credentials_and_schema_comes_from_the_base(self):
        connector = _bigquery(credentials="adc-token")
        described = connector.describe()
        assert described == {"name": "bq", "type": "BigQueryConnector"}
        assert "adc-token" not in described.values()
        assert connector.column_schema("events") is None
        assert connector.supports_pushdown() is True
