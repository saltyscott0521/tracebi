"""
Phase 5 — DuckDB integration, push-down filtering, layer renames, CLI,
auto-discovery, and the web auth/lineage additions.

Each TestClass groups one feature so failures point at the right code.
Existing phase tests guarantee back-compat; this file covers what's new.
"""

from __future__ import annotations

import importlib.util
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
    pytestmark = pytest.mark.skipif(
        importlib.util.find_spec("duckdb") is None,
        reason="duckdb not installed",
    )

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


# ── DataModel.query() runs through DuckDB engine ──────────────────────────

class TestStarSchemaDuckDB:
    def test_aggregated_query(self, memory_model):
        memory_model.add_dimension("dim_customer", "customers",
                                   key_col="customer_id", attributes=["segment"])
        memory_model.add_fact("fact_orders", "orders",
                              measures=["revenue", "qty"],
                              foreign_keys={"dim_customer": "customer_id"})

        ds = memory_model.query(
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
        pytest.importorskip("duckdb")
        memory_model.add_dimension("dim_customer", "customers",
                                   key_col="customer_id", attributes=["segment"])
        memory_model.add_fact("fact_orders", "orders", measures=["revenue"],
                              foreign_keys={"dim_customer": "customer_id"})

        ds = memory_model.query(
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
        memory_model.add_dimension("dim_customer", "customers",
                                   key_col="customer_id", attributes=["segment"])
        memory_model.add_fact("fact_orders", "orders", measures=["revenue"],
                              foreign_keys={"dim_customer": "customer_id"})

        ds = memory_model.query(
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
        memory_model.add_dimension("dim_customer", "customers",
                                   key_col="customer_id", attributes=["segment"])
        memory_model.add_fact("fact_orders", "orders", measures=["revenue"],
                              foreign_keys={"dim_customer": "customer_id"})

        final = FinalLayer(model=memory_model)
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
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_HEADER", raising=False)
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) is None

    def test_on_when_env_set(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_USER", "user")
        monkeypatch.setenv("TRACEBI_AUTH_PASS", "pass")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_HEADER", raising=False)
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) == "basic"

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


# ── Proxy header-trust auth ───────────────────────────────────────────────

class TestProxyHeaderAuth:
    def _build_app(self, trusted_ips=None, header="X-Forwarded-User"):
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from web.api.auth import ProxyHeaderAuthMiddleware

        async def me(request):
            return JSONResponse({"user": getattr(request.state, "user", None)})

        async def health(request):
            return JSONResponse({"status": "ok"})

        app = Starlette(routes=[
            Route("/api/me", me),
            Route("/api/health", health),
        ])
        app.add_middleware(
            ProxyHeaderAuthMiddleware,
            header=header,
            trusted_ips=trusted_ips,
        )
        return app

    def test_missing_header_rejected(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._build_app())
        r = client.get("/api/me")
        assert r.status_code == 401

    def test_header_exposed_on_request_state(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._build_app())
        r = client.get("/api/me", headers={"X-Forwarded-User": "alice"})
        assert r.status_code == 200
        assert r.json() == {"user": "alice"}

    def test_custom_header_name(self):
        from fastapi.testclient import TestClient
        app = self._build_app(header="X-Auth-User")
        client = TestClient(app)
        r = client.get("/api/me", headers={"X-Auth-User": "bob"})
        assert r.status_code == 200
        assert r.json() == {"user": "bob"}

    def test_trusted_ips_reject_unknown_client(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._build_app(trusted_ips=["10.0.0.0/8"]))
        r = client.get("/api/me", headers={"X-Forwarded-User": "alice"})
        assert r.status_code == 401

    def test_trusted_ips_accept_known_client(self):
        """Unit-test the trust check directly — TestClient lies about client IP."""
        from types import SimpleNamespace
        from web.api.auth import ProxyHeaderAuthMiddleware

        mw = ProxyHeaderAuthMiddleware(
            app=None, header="X-Forwarded-User", trusted_ips=["10.0.0.0/8"],
        )
        req = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"))
        assert mw._is_trusted_client(req) is True

        req_outside = SimpleNamespace(client=SimpleNamespace(host="192.168.1.1"))
        assert mw._is_trusted_client(req_outside) is False

    def test_health_exempt(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._build_app())
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_proxy_mode_selected_by_env(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.setenv("TRACEBI_AUTH_USER", "ignored")
        monkeypatch.setenv("TRACEBI_AUTH_PASS", "ignored")
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        # Proxy mode wins when both are set.
        assert install_if_configured(app) == "proxy"

    def test_proxy_without_trusted_ips_warns(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_TRUSTED_IPS", raising=False)
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        with pytest.warns(UserWarning, match="TRUSTED_IPS"):
            assert install_if_configured(app) == "proxy"

    def test_proxy_with_trusted_ips_does_not_warn(self, monkeypatch, recwarn):
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_TRUSTED_IPS", "10.0.0.0/8")
        from fastapi import FastAPI
        from web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) == "proxy"
        assert not [w for w in recwarn if "TRUSTED_IPS" in str(w.message)]


# ── Analyst endpoints: preview metadata, CSV export, report downloads ─────

class TestAnalystEndpoints:
    def _client_with_model(self, memory_model):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.registry import registry
        from web.api.routers import models as models_router

        registry.add_model(memory_model)
        app = FastAPI()
        app.include_router(models_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup_model(self, name):
        from web.api.registry import registry
        registry._models.pop(name, None)

    def test_preview_includes_dtypes_and_total_rows(self, memory_model):
        client = self._client_with_model(memory_model)
        try:
            r = client.get("/api/models/Sales/tables/orders/preview?rows=2")
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 2
            assert body["total_rows"] == 6
            assert set(body["dtypes"]) == set(body["columns"])
        finally:
            self._cleanup_model("Sales")

    def test_csv_export_streams_full_table(self, memory_model):
        client = self._client_with_model(memory_model)
        try:
            r = client.get("/api/models/Sales/tables/orders/export.csv")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/csv")
            assert 'filename="orders.csv"' in r.headers["content-disposition"]
            lines = r.text.strip().splitlines()
            assert len(lines) == 7  # header + 6 rows
            assert lines[0].startswith("order_id")
        finally:
            self._cleanup_model("Sales")

    def _client_with_report(self, factory, name="t_report"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.registry import registry
        from web.api.routers import reports as reports_router

        registry.add_report(name, factory)
        app = FastAPI()
        app.include_router(reports_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup_report(self, name="t_report"):
        from web.api.registry import registry
        registry._report_factories.pop(name, None)

    @staticmethod
    def _sample_report(memory_model):
        from tracebi.reports import Report, TableSection
        ds = memory_model.load("orders")
        return Report("T Report").add(TableSection(title="Orders", dataset=ds))

    def test_download_html_attachment(self, memory_model):
        client = self._client_with_report(lambda: self._sample_report(memory_model))
        try:
            r = client.get("/api/reports/t_report/download?format=html")
            assert r.status_code == 200
            assert "attachment" in r.headers["content-disposition"]
            assert r.text.startswith("<!DOCTYPE html>")
        finally:
            self._cleanup_report()

    def test_download_xlsx_attachment(self, memory_model):
        pytest.importorskip("openpyxl")
        client = self._client_with_report(lambda: self._sample_report(memory_model))
        try:
            r = client.get("/api/reports/t_report/download?format=xlsx")
            assert r.status_code == 200
            assert "spreadsheetml" in r.headers["content-type"]
            assert r.content[:2] == b"PK"  # xlsx is a zip container
        finally:
            self._cleanup_report()

    def test_download_bad_format_400(self, memory_model):
        client = self._client_with_report(lambda: self._sample_report(memory_model))
        try:
            r = client.get("/api/reports/t_report/download?format=exe")
            assert r.status_code == 400
        finally:
            self._cleanup_report()

    def test_failing_factory_returns_structured_traceback(self):
        def boom():
            raise RuntimeError("kapow")

        client = self._client_with_report(boom)
        try:
            r = client.post("/api/reports/t_report/run")
            assert r.status_code == 500
            detail = r.json()["detail"]
            assert "kapow" in detail["message"]
            assert detail["exception_type"] == "RuntimeError"
            assert "RuntimeError: kapow" in detail["traceback"]
        finally:
            self._cleanup_report()


# ── Explore: star-schema query endpoint ───────────────────────────────────

class TestQueryEndpoint:
    def _client(self, memory_model):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.registry import registry
        from web.api.routers import models as models_router

        memory_model.add_dimension("dim_customer", "customers",
                                   key_col="customer_id", attributes=["segment"])
        memory_model.add_fact("fact_orders", "orders",
                              measures=["revenue", "qty"],
                              foreign_keys={"dim_customer": "customer_id"})
        registry.add_model(memory_model)
        app = FastAPI()
        app.include_router(models_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup(self):
        from web.api.registry import registry
        registry._models.pop("Sales", None)

    def test_aggregated_query_returns_rows_and_lineage(self, memory_model):
        client = self._client(memory_model)
        try:
            r = client.post("/api/models/Sales/query", json={
                "fact": "fact_orders",
                "measures": {"revenue": "sum"},
                "dimensions": ["dim_customer.segment"],
            })
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 2
            assert "dim_customer.segment" in body["columns"]
            assert body["lineage_graph"]["nodes"]
            assert body["engine"] in ("duckdb", "pandas")
        finally:
            self._cleanup()

    def test_unknown_fact_is_400(self, memory_model):
        client = self._client(memory_model)
        try:
            r = client.post("/api/models/Sales/query", json={
                "fact": "nope", "measures": {"revenue": "sum"},
            })
            assert r.status_code == 400
            assert "nope" in r.json()["detail"]
        finally:
            self._cleanup()

    def test_filters_apply_to_fact(self, memory_model):
        client = self._client(memory_model)
        try:
            r = client.post("/api/models/Sales/query", json={
                "fact": "fact_orders",
                "measures": {"revenue": "sum"},
                "filters": {"status": "shipped"},
            })
            assert r.status_code == 200
            body = r.json()
            assert body["rows"] == 1
        finally:
            self._cleanup()


# ── Connector SQL identifier hygiene ──────────────────────────────────────

class TestConnectorIdentifierQuoting:
    def test_base_quote_ident_rejects_embedded_quote(self):
        from tracebi.connectors.base import BaseConnector
        with pytest.raises(ValueError):
            BaseConnector._quote_ident('bad"name')
        with pytest.raises(ValueError):
            BaseConnector._quote_ident("bad`name", quote="`")
        assert BaseConnector._quote_ident("ok_name") == '"ok_name"'

    def test_bigquery_param_type_mapping(self):
        from tracebi.connectors.bigquery_connector import BigQueryConnector
        assert BigQueryConnector._bq_param_type(True) == "BOOL"
        assert BigQueryConnector._bq_param_type(3) == "INT64"
        assert BigQueryConnector._bq_param_type(3.5) == "FLOAT64"
        assert BigQueryConnector._bq_param_type("x") == "STRING"
        with pytest.raises(ValueError):
            BigQueryConnector._bq_param_type(object())


# ── Shared project model & @scheduled decorator ──────────────────────────

class TestRegistryExtras:
    @pytest.fixture(autouse=True)
    def _reset_registry(self):
        from web.api.registry import registry
        saved = {
            "models":     dict(registry._models),
            "default":    registry._default_model_name,
            "reports":    dict(registry._report_factories),
            "scheduled":  dict(registry._scheduled_factories),
        }
        yield
        registry._models = saved["models"]
        registry._default_model_name = saved["default"]
        registry._report_factories = saved["reports"]
        registry._scheduled_factories = saved["scheduled"]

    def test_default_model_via_add_model(self, memory_model):
        from web.api.registry import Registry
        r = Registry()
        r.add_model(memory_model, default=True)
        assert r.get_default_model() is memory_model

    def test_first_model_becomes_default(self, memory_model):
        from web.api.registry import Registry
        r = Registry()
        r.add_model(memory_model)
        assert r.get_default_model() is memory_model

    def test_set_default_model_after_adding(self, memory_model):
        from web.api.registry import Registry
        r = Registry()
        r.add_model(memory_model)
        r.set_default_model("Sales")
        assert r.get_default_model() is memory_model

    def test_set_default_unknown_raises(self):
        from web.api.registry import Registry
        r = Registry()
        with pytest.raises(KeyError):
            r.set_default_model("nope")

    def test_register_notebook_helper_default(self, memory_model):
        from tracebi.web import register
        register.model(memory_model, default=True)
        assert register.get_default_model() is memory_model

    def test_scheduled_decorator_registers_report_and_cron(self):
        from web.api.registry import Registry
        r = Registry()

        @r.scheduled("weekly", cron="0 9 * * MON", description="weekly KPIs")
        def fac():
            return "report"

        reports = [x["name"] for x in r.list_reports()]
        scheduled = r.list_scheduled()
        assert "weekly" in reports
        assert scheduled == [
            {"name": "weekly", "cron": "0 9 * * MON", "description": "weekly KPIs"}
        ]

    def test_concurrent_registration_is_safe(self):
        import threading
        from types import SimpleNamespace
        from web.api.registry import Registry

        r = Registry()
        errors = []

        def add_many(prefix):
            try:
                for i in range(100):
                    r.add_connector(SimpleNamespace(name=f"{prefix}_{i}"))
                    r.add_report(f"{prefix}_{i}", lambda: None)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=add_many, args=(f"t{n}",))
                   for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(r.list_reports()) == 400
        assert r.get_connector("t0_99") is not None

    def test_scheduled_via_notebook_helper(self):
        from tracebi.web import register
        from web.api.registry import registry

        @register.scheduled("nightly", cron="0 2 * * *", description="nightly")
        def fac():
            return "report"

        scheduled_names = [x["name"] for x in registry.list_scheduled()]
        assert "nightly" in scheduled_names


# ── ipynb scaffolding ─────────────────────────────────────────────────────

class TestNotebookScaffold:
    def test_creates_ipynb_file(self, tmp_path):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        rc = main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales", "--notebook",
        ])
        assert rc == 0
        out = requests_dir / "weekly_sales.ipynb"
        assert out.is_file()

    def test_ipynb_is_valid_json(self, tmp_path):
        import json
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales", "--notebook",
        ])
        nb = json.loads((requests_dir / "weekly_sales.ipynb").read_text())
        assert nb["nbformat"] == 4
        assert any(c["cell_type"] == "code" for c in nb["cells"])

    def test_list_requests_includes_ipynb(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        main([
            "--requests-dir", str(requests_dir),
            "new-request", "Weekly Sales", "--notebook",
        ])
        main(["--requests-dir", str(requests_dir), "list-requests"])
        captured = capsys.readouterr()
        assert "weekly_sales.ipynb" in captured.out


# ── Pipeline-level run endpoint ───────────────────────────────────────────

class TestPipelineRunEndpoint:
    def test_run_all_layers(self, tmp_path):
        import pandas as pd
        from tracebi import LandingLayer, ManipulationLayer, PipelineRunner, SQLConnector
        from sqlalchemy import create_engine
        from web.api.registry import Registry

        url = f"sqlite:///{tmp_path}/runner.db"
        eng = create_engine(url)
        pd.DataFrame({"id": [1, 2, 2, 3]}).to_sql("orders_raw", eng, index=False)
        db = SQLConnector("db", url=url)

        landing = LandingLayer(connector=db, source="orders_raw",
                               sink=db, sink_table="orders_bronze")
        manip = (
            ManipulationLayer(source=db, source_table="orders_bronze",
                              sink=db, sink_table="orders_silver")
            .deduplicate(subset=["id"])
        )
        runner = PipelineRunner(db_url=f"sqlite:///{tmp_path}/runner_meta.db")
        runner.register(landing, name="orders_bronze")
        runner.register(manip,   name="orders_silver", depends_on="orders_bronze")

        # Use a fresh registry to keep this isolated from the singleton
        local = Registry()
        local.add_pipeline("sales", runner)

        # Swap singleton just for the test
        import web.api.registry as reg_mod
        original = reg_mod.registry
        reg_mod.registry = local
        try:
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            from web.api.routers import pipelines as pipelines_router
            app = FastAPI()
            app.include_router(pipelines_router.router, prefix="/api")

            client = TestClient(app)
            r = client.post("/api/pipelines/sales/run")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            # Both layers executed in dependency order
            assert body["ran"] == ["orders_bronze", "orders_silver"]
        finally:
            reg_mod.registry = original

    def test_run_missing_pipeline_404(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from web.api.routers import pipelines as pipelines_router
        app = FastAPI()
        app.include_router(pipelines_router.router, prefix="/api")
        client = TestClient(app)
        r = client.post("/api/pipelines/nope/run")
        assert r.status_code == 404


# ── Dashboard lineage endpoint ────────────────────────────────────────────

class TestDashboardLineageEndpoint:
    def test_returns_combined_graph(self, memory_model):
        import web.api.registry as reg_mod
        from web.api.registry import Registry
        from tracebi.dashboard import Dashboard, DashboardServer, FilterPanel, TablePanel

        local = Registry()
        local.add_model(memory_model)
        dash = (
            Dashboard("Sales")
            .add_filter(FilterPanel("r", label="Region", column="region", table_name="orders"))
            .add_panel(TablePanel("t", title="Orders", table_name="orders",
                                  columns=["order_id", "region"]))
        )
        local.add_dashboard("sales", DashboardServer(dash, model=memory_model))

        original = reg_mod.registry
        reg_mod.registry = local
        try:
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
            from web.api.routers import dashboards as dash_router
            app = FastAPI()
            app.include_router(dash_router.router, prefix="/api")

            client = TestClient(app)
            r = client.get("/api/dashboards/sales/lineage")
            assert r.status_code == 200
            body = r.json()
            assert body["dashboard"] == "sales"
            assert "combined_graph" in body
            assert len(body["combined_graph"]["nodes"]) >= 1
            assert len(body["panels"]) == 2
        finally:
            reg_mod.registry = original

    def test_unknown_dashboard_404(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from web.api.routers import dashboards as dash_router
        app = FastAPI()
        app.include_router(dash_router.router, prefix="/api")
        client = TestClient(app)
        r = client.get("/api/dashboards/nope/lineage")
        assert r.status_code == 404


# ── Dev-mode reload endpoint ──────────────────────────────────────────────

class TestDevReload:
    def test_reload_re_imports_discovered_modules(self, tmp_path):
        import sys
        from tracebi.web.discovery import auto_discover, reload_modules

        path = tmp_path / "reload_target.py"
        path.write_text("VALUE = 'one'\n")
        discovered = auto_discover(str(tmp_path))
        mod_name = next(n for n in discovered if n.endswith("reload_target"))
        assert sys.modules[mod_name].VALUE == "one"

        # Edit the file, then reload.
        path.write_text("VALUE = 'two'\n")
        reloaded = reload_modules()
        assert mod_name in reloaded
        assert sys.modules[mod_name].VALUE == "two"

    def test_endpoint_returns_reload_summary(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from web.api.routers import dev as dev_router

        path = tmp_path / "x.py"
        path.write_text("MARK = 1\n")
        auto_discover(str(tmp_path))

        app = FastAPI()
        app.include_router(dev_router.router, prefix="/api")
        client = TestClient(app)

        r = client.post("/api/_dev/reload")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1


# ── notebook_to_source helper ─────────────────────────────────────────────

class TestNotebookToSource:
    def _make_nb(self, tmp_path, cells: list[dict]) -> str:
        import json
        nb = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": cells,
        }
        p = tmp_path / "test_nb.ipynb"
        p.write_text(json.dumps(nb))
        return str(p)

    def test_extracts_code_cells(self, tmp_path):
        from tracebi._notebook import notebook_to_source
        path = self._make_nb(tmp_path, [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Title\n"]},
            {"cell_type": "code",     "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["x = 1\n", "y = x + 1\n"]},
        ])
        src = notebook_to_source(path)
        assert "x = 1" in src
        assert "# Title" not in src

    def test_drops_magic_lines(self, tmp_path):
        from tracebi._notebook import notebook_to_source
        path = self._make_nb(tmp_path, [
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["%matplotlib inline\n", "import pandas as pd\n", "!pip install foo\n"]},
        ])
        src = notebook_to_source(path)
        assert "%matplotlib" not in src
        assert "!pip" not in src
        assert "import pandas" in src

    def test_multiple_cells_separated_by_blank_line(self, tmp_path):
        from tracebi._notebook import notebook_to_source
        path = self._make_nb(tmp_path, [
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["a = 1\n"]},
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": ["b = 2\n"]},
        ])
        src = notebook_to_source(path)
        assert "a = 1" in src
        assert "b = 2" in src

    def test_empty_notebook_returns_empty_string(self, tmp_path):
        from tracebi._notebook import notebook_to_source
        path = self._make_nb(tmp_path, [])
        assert notebook_to_source(path) == ""

    def test_source_as_string_not_list(self, tmp_path):
        from tracebi._notebook import notebook_to_source
        path = self._make_nb(tmp_path, [
            {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
             "source": "z = 42\n"},
        ])
        src = notebook_to_source(path)
        assert "z = 42" in src


# ── tracebi run with .ipynb ───────────────────────────────────────────────

class TestCliRunNotebook:
    def _make_nb(self, path, source_lines: list[str]):
        import json
        nb = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "code", "metadata": {}, "execution_count": None,
                 "outputs": [], "source": source_lines},
            ],
        }
        path.write_text(json.dumps(nb))

    def test_run_ipynb_executes_code(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        nb_path = requests_dir / "my_report.ipynb"
        self._make_nb(nb_path, ["print('notebook ran')\n"])
        rc = main(["--requests-dir", str(requests_dir), "run", "my_report"])
        assert rc == 0
        assert "notebook ran" in capsys.readouterr().out

    def test_run_ipynb_explicit_suffix(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        nb_path = requests_dir / "report2.ipynb"
        self._make_nb(nb_path, ["print('explicit suffix')\n"])
        rc = main(["--requests-dir", str(requests_dir), "run", "report2.ipynb"])
        assert rc == 0
        assert "explicit suffix" in capsys.readouterr().out

    def test_run_prefers_py_over_ipynb(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        (requests_dir / "dupe.py").write_text("print('python')\n")
        self._make_nb(requests_dir / "dupe.ipynb", ["print('notebook')\n"])
        main(["--requests-dir", str(requests_dir), "run", "dupe"])
        out = capsys.readouterr().out
        assert "python" in out

    def test_run_missing_returns_nonzero(self, tmp_path):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        rc = main(["--requests-dir", str(requests_dir), "run", "nope"])
        assert rc != 0

    def test_run_calls_run_function_if_present(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        nb_path = requests_dir / "has_run.ipynb"
        self._make_nb(nb_path, [
            "def run():\n",
            "    print('run called')\n",
        ])
        rc = main(["--requests-dir", str(requests_dir), "run", "has_run"])
        assert rc == 0
        assert "run called" in capsys.readouterr().out


# ── auto_discover with .ipynb ─────────────────────────────────────────────

class TestAutoDiscoverNotebook:
    def _make_nb(self, path, source_lines: list[str]):
        import json
        nb = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "code", "metadata": {}, "execution_count": None,
                 "outputs": [], "source": source_lines},
            ],
        }
        path.write_text(json.dumps(nb))

    def test_discovers_ipynb(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        self._make_nb(tmp_path / "my_notebook.ipynb", ["NB_VALUE = 'hello'\n"])
        discovered = auto_discover(str(tmp_path))
        assert any("my_notebook" in n for n in discovered)

    def test_notebook_code_is_executed(self, tmp_path):
        import sys
        from tracebi.web.discovery import auto_discover
        marker = tmp_path / "nb_ran.txt"
        self._make_nb(tmp_path / "side_effect.ipynb", [
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        ])
        auto_discover(str(tmp_path))
        assert marker.read_text() == "ran"

    def test_skips_underscore_notebooks(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        self._make_nb(tmp_path / "_private.ipynb", ["PRIVATE = True\n"])
        self._make_nb(tmp_path / "public.ipynb", ["PUBLIC = True\n"])
        discovered = auto_discover(str(tmp_path))
        assert not any("_private" in n for n in discovered)
        assert any("public" in n for n in discovered)

    def test_magic_lines_dropped_during_discovery(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        self._make_nb(tmp_path / "with_magic.ipynb", [
            "%matplotlib inline\n",
            "MAGIC_OK = True\n",
        ])
        auto_discover(str(tmp_path))  # would raise SyntaxError if magic not stripped


# ── Request runner & dev preview ──────────────────────────────────────────

_GOOD_REQUEST = textwrap.dedent("""
    import pandas as pd
    from tracebi.model.dataset import DataSet, LineageNode
    from tracebi.reports.report import Report, TableSection

    ds = DataSet(
        df=pd.DataFrame({"region": ["N", "S"], "revenue": [10.0, 20.0]}),
        name="orders",
        lineage=[LineageNode(operation="load", description="Load orders")],
    )
    report = Report("Good Report").add(TableSection(title="Orders", dataset=ds))

    if __name__ == "__main__":
        raise RuntimeError("main block must not fire during preview")
""")


class TestRequestRunner:
    def test_finds_report_variable(self, tmp_path):
        from tracebi._request_runner import execute_request
        script = tmp_path / "good.py"
        script.write_text(_GOOD_REQUEST)
        report = execute_request(script)
        assert report.name == "Good Report"

    def test_main_block_does_not_fire(self, tmp_path):
        # _GOOD_REQUEST raises inside __main__ — execute_request must not trip it
        from tracebi._request_runner import execute_request
        script = tmp_path / "good.py"
        script.write_text(_GOOD_REQUEST)
        execute_request(script)   # no RuntimeError

    def test_finds_report_under_other_name(self, tmp_path):
        from tracebi._request_runner import execute_request
        script = tmp_path / "other.py"
        script.write_text(textwrap.dedent("""
            from tracebi.reports.report import Report
            my_summary = Report("Other Name")
        """))
        assert execute_request(script).name == "Other Name"

    def test_no_report_raises_lookup_error(self, tmp_path):
        from tracebi._request_runner import execute_request
        script = tmp_path / "empty.py"
        script.write_text("x = 1\n")
        with pytest.raises(LookupError, match="No Report object"):
            execute_request(script)

    def test_script_errors_propagate(self, tmp_path):
        from tracebi._request_runner import execute_request
        script = tmp_path / "broken.py"
        script.write_text("raise ValueError('boom')\n")
        with pytest.raises(ValueError, match="boom"):
            execute_request(script)


class TestDevServer:
    def test_render_request_returns_report_html(self, tmp_path):
        from tracebi._dev_server import render_request
        script = tmp_path / "good.py"
        script.write_text(_GOOD_REQUEST)
        html = render_request(script)
        assert "Good Report" in html
        assert "<!DOCTYPE html>" in html

    def test_render_request_error_page(self, tmp_path):
        from tracebi._dev_server import render_request
        script = tmp_path / "broken.py"
        script.write_text("raise ValueError('boom')\n")
        html = render_request(script)
        assert "Request script failed" in html
        assert "boom" in html
        assert "broken.py" in html

    def test_inject_refresh(self):
        from tracebi._dev_server import _inject_refresh
        html = _inject_refresh("<html><body>hi</body></html>", 7)
        assert "var current = 7" in html
        assert html.index("hi") < html.index("/__status")

    def test_cli_dev_missing_request(self, tmp_path, capsys):
        from tracebi.cli import main
        requests_dir = tmp_path / "requests"
        requests_dir.mkdir()
        rc = main(["--requests-dir", str(requests_dir), "dev", "nope",
                   "--no-browser"])
        assert rc == 1
        assert "not found" in capsys.readouterr().err


class TestRequestsAPI:
    def _client(self, requests_dir, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.routers import requests as requests_router
        monkeypatch.setenv("TRACEBI_REQUESTS_DIR", str(requests_dir))
        app = FastAPI()
        app.include_router(requests_router.router, prefix="/api")
        return TestClient(app)

    def test_list_requests(self, tmp_path, monkeypatch):
        (tmp_path / "good.py").write_text(_GOOD_REQUEST)
        (tmp_path / "_template.py").write_text("x = 1\n")
        client = self._client(tmp_path, monkeypatch)
        items = client.get("/api/requests").json()
        assert [i["name"] for i in items] == ["good"]
        assert items[0]["type"] == "script"
        assert items[0]["file"] == "good.py"

    def test_list_missing_dir_returns_empty(self, tmp_path, monkeypatch):
        client = self._client(tmp_path / "nope", monkeypatch)
        assert client.get("/api/requests").json() == []

    def test_run_request(self, tmp_path, monkeypatch):
        (tmp_path / "good.py").write_text(_GOOD_REQUEST)
        client = self._client(tmp_path, monkeypatch)
        r = client.post("/api/requests/good/run")
        assert r.status_code == 200
        body = r.json()
        assert "Good Report" in body["html"]
        assert body["manifest"]["report_name"] == "Good Report"

    def test_run_missing_returns_404(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        assert client.post("/api/requests/nope/run").status_code == 404

    def test_run_broken_returns_structured_500(self, tmp_path, monkeypatch):
        (tmp_path / "broken.py").write_text("raise ValueError('boom')\n")
        client = self._client(tmp_path, monkeypatch)
        r = client.post("/api/requests/broken/run")
        assert r.status_code == 500
        detail = r.json()["detail"]
        assert detail["message"].startswith("Request script failed")
        assert detail["exception_type"] == "ValueError"
        assert "boom" in detail["traceback"]

    def test_path_traversal_rejected(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        # Slash-bearing names never reach the route (Starlette 404s them);
        # backslash and dot-prefixed names must be rejected by the router.
        assert client.post("/api/requests/..%5Csecret/run").status_code == 400
        assert client.post("/api/requests/.hidden/run").status_code == 400

    def test_lineage(self, tmp_path, monkeypatch):
        (tmp_path / "good.py").write_text(_GOOD_REQUEST)
        client = self._client(tmp_path, monkeypatch)
        r = client.get("/api/requests/good/lineage")
        assert r.status_code == 200
        body = r.json()
        assert body["combined_graph"]["nodes"]
        assert body["sections"][0]["dataset_name"] == "orders"


# ─────────────────────────────────────────────
# Lineage graph branching (joins render as a DAG)
# ─────────────────────────────────────────────

class TestLineageGraphBranching:

    @staticmethod
    def _joined_lineage():
        from tracebi.model.dataset import DataSet, LineageNode
        left = DataSet(
            df=pd.DataFrame({"id": [1, 2], "v": [10, 20]}),
            name="orders",
            lineage=[LineageNode(operation="load", description="load orders")],
        ).filter("v > 0")
        right = DataSet(
            df=pd.DataFrame({"id": [1, 2], "n": ["a", "b"]}),
            name="customers",
            lineage=[LineageNode(operation="load", description="load customers")],
        )
        return left.join(right, on="id").lineage_to_dict()

    def test_join_node_has_two_incoming_edges(self):
        from web.api.lineage_graph import lineage_to_graph
        graph = lineage_to_graph(self._joined_lineage())
        join_ids = [n["id"] for n in graph["nodes"]
                    if n["data"]["operation"] == "join"]
        assert len(join_ids) == 1
        incoming = [e for e in graph["edges"] if e["target"] == join_ids[0]]
        assert len(incoming) == 2

    def test_branches_on_separate_lanes(self):
        from web.api.lineage_graph import lineage_to_graph
        graph = lineage_to_graph(self._joined_lineage())
        load_ys = {n["data"]["description"]: n["position"]["y"]
                   for n in graph["nodes"] if n["data"]["operation"] == "load"}
        assert load_ys["load orders"] != load_ys["load customers"]

    def test_linear_lineage_unchanged(self):
        from web.api.lineage_graph import lineage_to_graph
        from tracebi.model.dataset import DataSet, LineageNode
        ds = DataSet(
            df=pd.DataFrame({"v": [1, 2, 3]}),
            name="t",
            lineage=[LineageNode(operation="load")],
        ).filter("v > 1").sort("v")
        graph = lineage_to_graph(ds.lineage_to_dict())
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2
        assert all(n["position"]["y"] == 0 for n in graph["nodes"])


# ─────────────────────────────────────────────
# Background report runs
# ─────────────────────────────────────────────

class TestBackgroundReportRuns:

    def _client_with_report(self, factory, name="bg_report"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.registry import registry
        from web.api.routers import reports as reports_router

        registry.add_report(name, factory)
        app = FastAPI()
        app.include_router(reports_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup_report(self, name="bg_report"):
        from web.api.registry import registry
        registry._report_factories.pop(name, None)

    @staticmethod
    def _poll(client, name, run_id, timeout=10.0):
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = client.get(f"/api/reports/{name}/runs/{run_id}")
            assert r.status_code == 200
            body = r.json()
            if body["status"] != "running":
                return body
            time.sleep(0.05)
        raise AssertionError("background run did not finish in time")

    def test_run_succeeds_and_returns_payload(self, memory_model):
        from tracebi.reports import Report, TableSection

        def factory():
            ds = memory_model.load("orders")
            return Report("BG").add(TableSection(title="Orders", dataset=ds))

        client = self._client_with_report(factory)
        try:
            r = client.post("/api/reports/bg_report/runs")
            assert r.status_code == 202
            run_id = r.json()["run_id"]
            body = self._poll(client, "bg_report", run_id)
            assert body["status"] == "succeeded"
            assert "<html" in body["result"]["html"].lower()
            assert body["result"]["manifest"]
            assert body["finished_at"]
        finally:
            self._cleanup_report()

    def test_failed_run_carries_structured_error(self):
        def boom():
            raise RuntimeError("bg kapow")

        client = self._client_with_report(boom)
        try:
            run_id = client.post("/api/reports/bg_report/runs").json()["run_id"]
            body = self._poll(client, "bg_report", run_id)
            assert body["status"] == "failed"
            assert "bg kapow" in body["error"]["message"]
            assert body["error"]["exception_type"] == "RuntimeError"
            assert "RuntimeError: bg kapow" in body["error"]["traceback"]
        finally:
            self._cleanup_report()

    def test_history_lists_runs_without_payload(self, memory_model):
        from tracebi.reports import Report, TableSection

        def factory():
            ds = memory_model.load("orders")
            return Report("BG").add(TableSection(title="Orders", dataset=ds))

        client = self._client_with_report(factory)
        try:
            run_id = client.post("/api/reports/bg_report/runs").json()["run_id"]
            self._poll(client, "bg_report", run_id)
            r = client.get("/api/reports/bg_report/runs")
            assert r.status_code == 200
            runs = r.json()
            assert runs[0]["run_id"] == run_id
            assert runs[0]["status"] == "succeeded"
            assert "result" not in runs[0]
        finally:
            self._cleanup_report()

    def test_unknown_run_or_report_404(self, memory_model):
        from tracebi.reports import Report, TableSection

        def factory():
            ds = memory_model.load("orders")
            return Report("BG").add(TableSection(title="Orders", dataset=ds))

        client = self._client_with_report(factory)
        try:
            assert client.post("/api/reports/nope/runs").status_code == 404
            assert client.get("/api/reports/bg_report/runs/zzz").status_code == 404
        finally:
            self._cleanup_report()


# ─────────────────────────────────────────────
# Request parameters (request_params / discovery / API)
# ─────────────────────────────────────────────

PARAM_SCRIPT = '''
import pandas as pd
from tracebi import request_params
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.reports import Report, TableSection

params = request_params(period="Q2", top_n=3, strict=False)

df = pd.DataFrame({"v": range(10)}).head(params["top_n"])
ds = DataSet(df=df, name="t", lineage=[LineageNode(operation="load")])
report = (
    Report(f"Params {params['period']}")
    .parameter("period", params["period"])
    .add(TableSection(title="T", dataset=ds))
)
'''


class TestRequestParams:

    def test_defaults_without_overrides(self):
        from tracebi import request_params
        assert request_params(a=1, b="x") == {"a": 1, "b": "x"}

    def test_overrides_coerced_to_default_types(self):
        from tracebi._params import (request_params, reset_param_overrides,
                                     set_param_overrides)
        token = set_param_overrides({"n": "5", "ratio": "0.5", "flag": "true"})
        try:
            out = request_params(n=1, ratio=1.0, flag=False, label="x")
            assert out == {"n": 5, "ratio": 0.5, "flag": True, "label": "x"}
        finally:
            reset_param_overrides(token)

    def test_unknown_override_raises(self):
        from tracebi._params import (request_params, reset_param_overrides,
                                     set_param_overrides)
        token = set_param_overrides({"nope": "1"})
        try:
            with pytest.raises(ValueError, match="Unknown request parameter"):
                request_params(a=1)
        finally:
            reset_param_overrides(token)

    def test_bad_coercion_raises(self):
        from tracebi._params import (request_params, reset_param_overrides,
                                     set_param_overrides)
        token = set_param_overrides({"n": "not-a-number"})
        try:
            with pytest.raises(ValueError, match="Parameter 'n'"):
                request_params(n=1)
        finally:
            reset_param_overrides(token)

    def test_discover_params_static(self, tmp_path):
        from tracebi._params import discover_params
        script = tmp_path / "r.py"
        script.write_text(PARAM_SCRIPT, encoding="utf-8")
        found = {p["name"]: p for p in discover_params(script)}
        assert found["period"] == {"name": "period", "default": "Q2", "type": "str"}
        assert found["top_n"]["type"] == "int"
        assert found["strict"]["default"] is False

    def test_discover_params_none_declared(self, tmp_path):
        from tracebi._params import discover_params
        script = tmp_path / "r.py"
        script.write_text("x = 1\n", encoding="utf-8")
        assert discover_params(script) == []

    def test_execute_request_with_overrides(self, tmp_path):
        from tracebi._request_runner import execute_request
        script = tmp_path / "r.py"
        script.write_text(PARAM_SCRIPT, encoding="utf-8")
        report = execute_request(script, params={"period": "Q4", "top_n": "7"})
        assert report.name == "Params Q4"
        section = report.data_sections()[0]
        assert len(section.dataset) == 7


class TestRequestParamsAPI:

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.routers import requests as requests_router

        (tmp_path / "param_req.py").write_text(PARAM_SCRIPT, encoding="utf-8")
        monkeypatch.setenv("TRACEBI_REQUESTS_DIR", str(tmp_path))
        app = FastAPI()
        app.include_router(requests_router.router, prefix="/api")
        return TestClient(app)

    def test_params_endpoint_lists_declared(self, client):
        r = client.get("/api/requests/param_req/params")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["params"]]
        assert names == ["period", "top_n", "strict"]

    def test_run_with_param_overrides(self, client):
        r = client.post("/api/requests/param_req/run",
                        json={"params": {"period": "Q4", "top_n": 2}})
        assert r.status_code == 200
        body = r.json()
        assert "Params Q4" in body["html"]
        assert body["params"] == {"period": "Q4", "top_n": 2}

    def test_run_unknown_param_is_structured_500(self, client):
        r = client.post("/api/requests/param_req/run",
                        json={"params": {"bogus": 1}})
        assert r.status_code == 500
        assert "Unknown request parameter" in r.json()["detail"]["message"]

    def test_lineage_accepts_params_json(self, client):
        r = client.get('/api/requests/param_req/lineage?params_json={"top_n":2}')
        assert r.status_code == 200
        assert r.json()["combined_graph"]["nodes"]

    def test_lineage_bad_params_json_400(self, client):
        r = client.get("/api/requests/param_req/lineage?params_json=notjson")
        assert r.status_code == 400


# ─────────────────────────────────────────────
# Docs guide endpoints
# ─────────────────────────────────────────────

class TestDocsEndpoints:
    """GET /api/docs serves the markdown guides in docs/ read-only."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from web.api.routers import docs
        app = FastAPI()
        app.include_router(docs.router, prefix="/api")
        return TestClient(app)

    def test_list_guides(self, client):
        r = client.get("/api/docs")
        assert r.status_code == 200
        guides = r.json()
        names = {g["name"] for g in guides}
        assert "analyst-guide" in names
        for g in guides:
            assert set(g) == {"name", "title", "bytes"}

    def test_get_guide_content(self, client):
        r = client.get("/api/docs/analyst-guide")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "analyst-guide"
        assert body["title"] == "TraceBi Analyst Guide"
        assert "tracebi new-request" in body["content"]

    def test_unknown_guide_404(self, client):
        assert client.get("/api/docs/nope").status_code == 404

    def test_path_traversal_is_unaddressable(self, client):
        # Names are matched against a directory listing of docs/*.md, so
        # traversal inputs can never resolve to a file.
        for evil in ["../README", "..%2F..%2Fpyproject", "etc/passwd"]:
            assert client.get(f"/api/docs/{evil}").status_code == 404
