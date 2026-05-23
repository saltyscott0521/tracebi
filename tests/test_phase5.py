"""
Phase 5 — DuckDB integration, push-down filtering, layer renames, CLI,
auto-discovery, and the web auth/lineage additions.

Each TestClass groups one feature so failures point at the right code.
Existing phase tests guarantee back-compat; this file covers what's new.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from tracebi import (
    DataModel,
    MemoryConnector,
    SQLConnector,
    DuckDBConnector,
    StarSchema,
    LandingLayer, ManipulationLayer, FinalLayer,
    BronzeLayer, SilverLayer, GoldLayer,
)
from tracebi.model.data_model import LARGE_LOAD_WARN_ROWS


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def orders_df():
    return pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 5, 6],
        "customer_id": [1, 2, 3, 1, 2, 3],
        "region":      ["NE", "SE", "MW", "NE", "SE", "MW"],
        "status":      ["shipped", "shipped", "open", "shipped", "open", "shipped"],
        "revenue":     [100.0, 200.0, 300.0, 150.0, 250.0, 350.0],
        "qty":         [1, 2, 3, 1, 2, 3],
    })


@pytest.fixture
def customers_df():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "name":        ["Acme", "Globex", "Initech"],
        "segment":     ["enterprise", "smb", "smb"],
    })


@pytest.fixture
def memory_model(orders_df, customers_df):
    conn = MemoryConnector("mem", tables={
        "orders":    orders_df,
        "customers": customers_df,
    })
    model = DataModel("Sales")
    model.add_connector(conn)
    model.add_table("orders",    connector="mem", source="orders")
    model.add_table("customers", connector="mem", source="customers")
    return model


# ── Push-down: MemoryConnector applies filter/columns in pandas ────────────

class TestPushDownPandas:
    def test_memory_connector_filter_applies(self, orders_df):
        conn = MemoryConnector("mem", tables={"orders": orders_df})
        df = conn.load("orders", filter={"status": "shipped"})
        assert len(df) == 4
        assert set(df["status"]) == {"shipped"}

    def test_memory_connector_columns_projects(self, orders_df):
        conn = MemoryConnector("mem", tables={"orders": orders_df})
        df = conn.load("orders", columns=["order_id", "revenue"])
        assert list(df.columns) == ["order_id", "revenue"]

    def test_memory_connector_filter_plus_columns(self, orders_df):
        conn = MemoryConnector("mem", tables={"orders": orders_df})
        df = conn.load("orders", filter={"region": "NE"}, columns=["order_id", "region"])
        assert len(df) == 2
        assert list(df.columns) == ["order_id", "region"]

    def test_pushdown_unsupported_flag(self):
        conn = MemoryConnector("mem", tables={"x": pd.DataFrame({"a": [1]})})
        assert conn.supports_pushdown() is False

    def test_model_load_passes_filter(self, memory_model):
        ds = memory_model.load("orders", filter={"status": "shipped"})
        assert len(ds) == 4
        node = ds.lineage[0]
        assert node.metadata["filter"] == {"status": "shipped"}

    def test_model_load_passes_columns(self, memory_model):
        ds = memory_model.load("orders", columns=["order_id", "revenue"])
        assert list(ds.to_pandas().columns) == ["order_id", "revenue"]


# ── Push-down: SQLConnector uses real SQL WHERE/SELECT ────────────────────

class TestPushDownSQL:
    @pytest.fixture
    def sqlite_connector(self, orders_df, tmp_path):
        from sqlalchemy import create_engine
        url = f"sqlite:///{tmp_path}/test.db"
        orders_df.to_sql("orders", con=create_engine(url), if_exists="replace", index=False)
        conn = SQLConnector("sqlite_test", url=url)
        conn.connect()
        return conn

    def test_sql_filter_via_where(self, sqlite_connector):
        df = sqlite_connector.load("orders", filter={"status": "shipped"})
        assert len(df) == 4
        assert set(df["status"]) == {"shipped"}

    def test_sql_columns_via_select(self, sqlite_connector):
        df = sqlite_connector.load("orders", columns=["order_id", "revenue"])
        assert list(df.columns) == ["order_id", "revenue"]

    def test_sql_supports_pushdown(self, sqlite_connector):
        assert sqlite_connector.supports_pushdown() is True

    def test_sql_raw_query_still_works(self, sqlite_connector):
        df = sqlite_connector.load("SELECT order_id FROM orders WHERE status = 'open'")
        assert len(df) == 2

    def test_sql_invalid_identifier_rejected(self, sqlite_connector):
        with pytest.raises(ValueError):
            sqlite_connector.load("orders", columns=['bad"name'])


# ── DuckDB connector ──────────────────────────────────────────────────────

class TestDuckDBConnector:
    def test_register_and_load(self, orders_df):
        conn = DuckDBConnector("dd")
        conn.register_df("orders", orders_df)
        df = conn.load("orders")
        assert len(df) == 6

    def test_filter_pushdown(self, orders_df):
        conn = DuckDBConnector("dd")
        conn.register_df("orders", orders_df)
        df = conn.load("orders", filter={"status": "shipped"})
        assert len(df) == 4
        assert set(df["status"]) == {"shipped"}

    def test_columns_projection(self, orders_df):
        conn = DuckDBConnector("dd")
        conn.register_df("orders", orders_df)
        df = conn.load("orders", columns=["order_id", "revenue"])
        assert list(df.columns) == ["order_id", "revenue"]

    def test_parquet_file(self, orders_df, tmp_path):
        pyarrow = pytest.importorskip("pyarrow")
        parquet_path = tmp_path / "orders.parquet"
        orders_df.to_parquet(parquet_path, index=False)
        conn = DuckDBConnector("dd", directory=str(tmp_path))
        df = conn.load("orders.parquet", filter={"region": "NE"})
        assert len(df) == 2

    def test_write_and_reload(self, orders_df, tmp_path):
        db_path = tmp_path / "test.duckdb"
        conn = DuckDBConnector("dd", database=str(db_path))
        conn.write(orders_df, "orders")
        df = conn.load("orders")
        assert len(df) == 6

    def test_write_append(self, orders_df, tmp_path):
        db_path = tmp_path / "test.duckdb"
        conn = DuckDBConnector("dd", database=str(db_path))
        conn.write(orders_df, "orders")
        conn.write(orders_df, "orders", if_exists="append")
        df = conn.load("orders")
        assert len(df) == 12

    def test_supports_pushdown(self):
        conn = DuckDBConnector("dd")
        assert conn.supports_pushdown() is True


# ── Lineage warning for large unfiltered loads ────────────────────────────

class TestLargeLoadWarning:
    def test_small_load_no_warning(self, memory_model):
        ds = memory_model.load("orders")
        ops = [n.operation for n in ds.lineage]
        assert "warning" not in ops

    def test_filter_suppresses_warning(self, monkeypatch, memory_model):
        # Pretend the threshold is 1 to force-trigger; filter should still suppress
        monkeypatch.setattr(
            "tracebi.model.data_model.LARGE_LOAD_WARN_ROWS", 1
        )
        ds = memory_model.load("orders", filter={"status": "shipped"})
        ops = [n.operation for n in ds.lineage]
        assert "warning" not in ops

    def test_large_unfiltered_load_warns(self, monkeypatch):
        big = pd.DataFrame({"x": range(10)})
        conn = MemoryConnector("mem", tables={"big": big})
        model = DataModel("m").add_connector(conn)
        model.add_table("big", connector="mem", source="big")
        monkeypatch.setattr(
            "tracebi.model.data_model.LARGE_LOAD_WARN_ROWS", 5
        )
        ds = model.load("big")
        ops = [n.operation for n in ds.lineage]
        assert "warning" in ops
        warning_node = next(n for n in ds.lineage if n.operation == "warning")
        assert warning_node.metadata["rows_loaded"] == 10


# ── StarSchema runs through DuckDB engine ─────────────────────────────────

class TestStarSchemaDuckDB:
    def test_aggregated_query(self, memory_model):
        schema = StarSchema("Sales", model=memory_model)
        schema.add_dimension("dim_customer", "customers",
                             key_col="customer_id", attributes=["segment"])
        schema.add_fact("fact_orders", "orders",
                        measures=["revenue", "qty"],
                        foreign_keys={"dim_customer": "customer_id"})

        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum", "qty": "sum"},
            dimensions=["dim_customer.segment"],
        )
        df = ds.to_pandas()
        assert set(df["dim_customer.segment"]) == {"enterprise", "smb"}
        # enterprise = Acme only = orders 1 + 4 = 100 + 150
        ent = df.loc[df["dim_customer.segment"] == "enterprise", "revenue"].iloc[0]
        assert ent == 250.0

    def test_engine_node_records_duckdb(self, memory_model):
        schema = StarSchema("Sales", model=memory_model)
        schema.add_dimension("dim_customer", "customers",
                             key_col="customer_id", attributes=["segment"])
        schema.add_fact("fact_orders", "orders", measures=["revenue"],
                        foreign_keys={"dim_customer": "customer_id"})

        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.segment"],
        )
        engines = {n.metadata.get("engine") for n in ds.lineage
                   if n.metadata.get("engine")}
        assert "duckdb" in engines
        final_node = ds.lineage[-1]
        assert final_node.metadata.get("engine") == "duckdb"

    def test_filters_applied(self, memory_model):
        schema = StarSchema("Sales", model=memory_model)
        schema.add_dimension("dim_customer", "customers",
                             key_col="customer_id", attributes=["segment"])
        schema.add_fact("fact_orders", "orders", measures=["revenue"],
                        foreign_keys={"dim_customer": "customer_id"})

        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.segment"],
            filters={"status": "shipped"},
        )
        df = ds.to_pandas()
        # shipped: orders 1,2,4,6 → enterprise=100+150=250, smb=200+350=550
        smb_rev = df.loc[df["dim_customer.segment"] == "smb", "revenue"].iloc[0]
        assert smb_rev == 550.0


# ── Layer renames are interchangeable with old names ──────────────────────

class TestLayerRename:
    def test_landing_layer_is_bronze(self):
        assert issubclass(LandingLayer, BronzeLayer)

    def test_manipulation_layer_is_silver(self):
        assert issubclass(ManipulationLayer, SilverLayer)

    def test_final_layer_is_gold(self):
        assert issubclass(FinalLayer, GoldLayer)

    def test_landing_layer_stamps_landing_op(self, orders_df):
        conn = MemoryConnector("mem", tables={"orders": orders_df})
        layer = LandingLayer(connector=conn, source="orders")
        ds = layer.load()
        assert ds.lineage[0].operation == "landing"
        assert ds.lineage[0].metadata["layer"] == "landing"

    def test_manipulation_layer_stamps_manipulation_op(self, orders_df):
        ds_in = MemoryConnector("mem", tables={"orders": orders_df})
        from tracebi.model.dataset import DataSet, LineageNode
        node = LineageNode(operation="load", description="test")
        raw = DataSet(df=orders_df, name="orders", lineage=[node])

        layer = ManipulationLayer().deduplicate(subset=["order_id"])
        out = layer.apply(raw)
        ops = [n.operation for n in out.lineage]
        assert "manipulation" in ops

    def test_final_layer_stamps_final_op(self, memory_model):
        schema = StarSchema("Sales", model=memory_model)
        schema.add_dimension("dim_customer", "customers",
                             key_col="customer_id", attributes=["segment"])
        schema.add_fact("fact_orders", "orders", measures=["revenue"],
                        foreign_keys={"dim_customer": "customer_id"})

        final = FinalLayer(schema=schema)
        ds = final.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.segment"],
        )
        ops = [n.operation for n in ds.lineage]
        assert "final" in ops


# ── CLI ───────────────────────────────────────────────────────────────────

class TestCLI:
    def test_slugify(self):
        from tracebi.cli import _slugify
        assert _slugify("Open orders by region") == "open_orders_by_region"
        assert _slugify("  Q3 -- 2024 ") == "q3_2024"
        assert _slugify("!!!") == "request"

    def test_new_request_creates_file(self, tmp_path):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        rc = main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales",
        ])
        assert rc == 0
        created = requests_dir / "weekly_sales.py"
        assert created.is_file()
        content = created.read_text()
        assert "Weekly Sales" in content
        assert "def run" in content

    def test_new_request_refuses_overwrite(self, tmp_path):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        rc = main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales",
        ])
        assert rc == 0
        rc2 = main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales",
        ])
        assert rc2 != 0

    def test_new_request_force_overwrites(self, tmp_path):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales",
        ])
        rc = main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales",
            "--force",
        ])
        assert rc == 0

    def test_list_requests_empty(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        main(["--requests-dir", str(requests_dir), "list-requests"])
        captured = capsys.readouterr()
        assert "No request scripts" in captured.out


# ── Auto-discovery ────────────────────────────────────────────────────────

class TestAutoDiscover:
    def test_skips_underscore_files(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        (tmp_path / "_template.py").write_text("x = 1\n")
        (tmp_path / "real.py").write_text("y = 2\n")
        discovered = auto_discover(str(tmp_path))
        assert any(name.endswith("real") for name in discovered)
        assert not any(name.endswith("_template") for name in discovered)

    def test_returns_empty_for_missing_dir(self):
        from tracebi.web.discovery import auto_discover
        assert auto_discover("/this/path/does/not/exist") == []

    def test_executes_module(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        marker = tmp_path / "marker.txt"
        script = tmp_path / "register_me.py"
        script.write_text(textwrap.dedent(f"""
            from pathlib import Path
            Path({str(marker)!r}).write_text("hello")
        """))
        auto_discover(str(tmp_path))
        assert marker.read_text() == "hello"


# ── HTTP Basic auth middleware ────────────────────────────────────────────

class TestBasicAuth:
    def test_off_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("TRACEBI_AUTH_USER", raising=False)
        monkeypatch.delenv("TRACEBI_AUTH_PASS", raising=False)
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) is False

    def test_on_when_env_set(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_USER", "user")
        monkeypatch.setenv("TRACEBI_AUTH_PASS", "pass")
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) is True

    def test_rejects_missing_credentials(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.auth import BasicAuthMiddleware
        app = FastAPI()
        app.add_middleware(BasicAuthMiddleware, username="u", password="p")

        @app.get("/api/secret")
        def secret():
            return {"ok": True}

        client = TestClient(app)
        r = client.get("/api/secret")
        assert r.status_code == 401
        assert r.headers["www-authenticate"].startswith("Basic")

    def test_accepts_valid_credentials(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.auth import BasicAuthMiddleware
        app = FastAPI()
        app.add_middleware(BasicAuthMiddleware, username="u", password="p")

        @app.get("/api/secret")
        def secret():
            return {"ok": True}

        client = TestClient(app)
        r = client.get("/api/secret", auth=("u", "p"))
        assert r.status_code == 200

    def test_health_endpoint_exempt(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.auth import BasicAuthMiddleware
        app = FastAPI()
        app.add_middleware(BasicAuthMiddleware, username="u", password="p")

        @app.get("/api/health")
        def health():
            return {"status": "ok"}

        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200
