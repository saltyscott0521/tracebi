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
