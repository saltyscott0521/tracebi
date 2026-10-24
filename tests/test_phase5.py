"""
Phase 5 — DuckDB integration, push-down filtering, layer renames, CLI,
auto-discovery, and the web auth/lineage additions.

Each TestClass groups one feature so failures point at the right code.
Existing phase tests guarantee back-compat; this file covers what's new.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
import pytest

from tracebi import (
    DataModel,
    MemoryConnector,
    SQLConnector,
)
from tracebi.model.data_model import LARGE_LOAD_WARN_ROWS


# ── Package-backed report helper ────────────────────────────────────────────
# There is ONE renderer: a served report is built from its own package. These
# helpers register a real one (and, for the failure cases, one whose render
# raises) so the API tests exercise the path the product actually ships.

def _package_model(name: str) -> "DataModel":
    m = DataModel(name).add_connector(MemoryConnector("mem", {
        "orders": pd.DataFrame({"order_id": [1, 2, 3], "customer_id": [1, 2, 1],
                                "revenue": [100.0, 200.0, 300.0]}),
        "customers": pd.DataFrame({"customer_id": [1, 2],
                                   "region": ["West", "NE"]}),
    }))
    m.add_table("orders", connector="mem", source="orders")
    m.add_table("customers", connector="mem", source="customers")
    m.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
               foreign_keys={"dim_customer": "customer_id"})
    m.add_measure("total_revenue", column="revenue", agg="sum")
    m.connect()
    return m


def _client_with_package(tmp_path, name, *, broken=False):
    """Register a package-backed report; returns ``(client, cleanup)``.

    ``broken=True`` binds a model that is never registered, so the package
    loads but its RENDER raises — the failure path the structured-error
    tests need now that there is no second renderer to fall back to.
    """
    import json

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import tracebi.model_registry as model_registry
    from tracebi.web.api.registry import registry
    from tracebi.web.api.routers import reports as reports_router

    model_name = f"{name}_model"
    pkg = tmp_path / name
    pkg.mkdir()
    (pkg / "report.json").write_text(json.dumps({
        "name": name,
        "data": {"by_region": {
            "model": "no_such_model_at_all" if broken else model_name,
            "query": {"fact": "fact_orders", "measures": ["total_revenue"],
                      "dimensions": ["dim_customer.region"]},
        }},
        "figures": {"detail": {"kind": "table", "binding": "by_region"}},
    }), encoding="utf-8")
    (pkg / "template.html").write_text(
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        "<title>{{ title }}</title></head><body>"
        '<main>{{ figure("detail") }}</main></body></html>\n',
        encoding="utf-8")

    if not broken:
        model_registry.register(_package_model(model_name))

    def factory():
        from tracebi.reports.template_package import TemplatePackage
        return TemplatePackage(str(pkg))
    factory._tracebi_package_dir = str(pkg)
    registry.add_report(name, factory)

    app = FastAPI()
    app.include_router(reports_router.router, prefix="/api")

    def cleanup():
        registry._report_factories.pop(name, None)
        model_registry._registry._models.pop(model_name, None)

    return TestClient(app), cleanup


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

    def test_sql_raw_query_still_works(self, sqlite_connector):
        df = sqlite_connector.load("SELECT order_id FROM orders WHERE status = 'open'")
        assert len(df) == 2

    def test_sql_invalid_identifier_rejected(self, sqlite_connector):
        with pytest.raises(ValueError):
            sqlite_connector.load("orders", columns=['bad"name'])


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


# ── HTTP Basic auth middleware ────────────────────────────────────────────

class TestBasicAuth:
    def test_off_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("TRACEBI_AUTH_USER", raising=False)
        monkeypatch.delenv("TRACEBI_AUTH_PASS", raising=False)
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_HEADER", raising=False)
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) is None

    def test_on_when_env_set(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_USER", "user")
        monkeypatch.setenv("TRACEBI_AUTH_PASS", "pass")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_HEADER", raising=False)
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured
        app = FastAPI()
        assert install_if_configured(app) == "basic"

    def test_rejects_missing_credentials(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.auth import BasicAuthMiddleware
        app = FastAPI()
        app.add_middleware(BasicAuthMiddleware, username="u", password="p")

        @app.get("/api/secret")
        def secret():
            return {"ok": True}

        client = TestClient(app)
        r = client.get("/api/secret")
        assert r.status_code == 401
        assert r.headers["www-authenticate"].startswith("Basic")

    def test_share_links_need_a_login_too(self):
        """/r/ sits outside /api, but a client install's login still guards it."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.auth import BasicAuthMiddleware
        app = FastAPI()
        app.add_middleware(BasicAuthMiddleware, username="u", password="p")

        @app.get("/r/{name}")
        def page(name: str):
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/r/x").status_code == 401
        assert client.get("/r/x", auth=("u", "p")).status_code == 200

    def test_accepts_valid_credentials(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.auth import BasicAuthMiddleware
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
        from tracebi.web.api.auth import BasicAuthMiddleware
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
        from tracebi.web.api.auth import ProxyHeaderAuthMiddleware

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
        from tracebi.web.api.auth import ProxyHeaderAuthMiddleware

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
        from tracebi.web.api.auth import install_if_configured
        app = FastAPI()
        # Proxy mode wins when both are set.
        assert install_if_configured(app) == "proxy"

    def test_proxy_without_trusted_ips_warns(self, monkeypatch):
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_TRUSTED_IPS", raising=False)
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured
        app = FastAPI()
        with pytest.warns(UserWarning, match="TRUSTED_IPS"):
            assert install_if_configured(app) == "proxy"

# ── Analyst endpoints: preview metadata, CSV export, report downloads ─────

class TestAnalystEndpoints:
    def _client_with_model(self, memory_model):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.registry import registry
        from tracebi.web.api.routers import models as models_router

        registry.add_model(memory_model)
        app = FastAPI()
        app.include_router(models_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup_model(self, name):
        from tracebi.web.api.registry import registry
        registry._models.pop(name, None)


    def _client_with_report(self, factory, name="t_report"):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.registry import registry
        from tracebi.web.api.routers import reports as reports_router

        registry.add_report(name, factory)
        app = FastAPI()
        app.include_router(reports_router.router, prefix="/api")
        return TestClient(app)

    def _cleanup_report(self, name="t_report"):
        from tracebi.web.api.registry import registry
        registry._report_factories.pop(name, None)

    @staticmethod
    def _sample_report(memory_model):
        from tracebi.reports import Report, TableSection
        ds = memory_model.load("orders")
        return Report("T Report").add(TableSection(title="Orders", dataset=ds))

    def test_a_report_with_no_package_is_refused_not_served_weaker(
            self, memory_model):
        """There is ONE renderer. A registered report with no package used to
        fall back to a page with no runtime, no receipt drawer and a schema-1
        manifest — a report-shaped thing carrying materially less. It is now
        refused, and the refusal says how to fix it."""
        client = self._client_with_report(lambda: self._sample_report(memory_model))
        try:
            r = client.post("/api/reports/t_report/run")
            assert r.status_code == 422
            assert "tracebi new-report" in r.json()["detail"]
        finally:
            self._cleanup_report()


    def test_failing_render_returns_structured_traceback(self, tmp_path,
                                                         monkeypatch):
        monkeypatch.setenv("TRACEBI_DEV_MODE", "1")   # traceback is dev-only
        client, cleanup = _client_with_package(tmp_path, "t_broken", broken=True)
        try:
            r = client.post("/api/reports/t_broken/run")
            assert r.status_code == 500
            detail = r.json()["detail"]
            assert "no_such_model_at_all" in detail["message"]
            assert detail["exception_type"] == "ValueError"
            assert "ValueError" in detail["traceback"]
        finally:
            cleanup()

    def test_error_detail_omits_traceback_by_default(self, tmp_path):
        """Security: without TRACEBI_DEV_MODE the traceback (which leaks paths,
        the server username, and versions) is empty — message and type only."""
        client, cleanup = _client_with_package(tmp_path, "t_broken2", broken=True)
        try:
            detail = client.post("/api/reports/t_broken2/run").json()["detail"]
            assert "no_such_model_at_all" in detail["message"]
            assert detail["exception_type"] == "ValueError"
            assert detail["traceback"] == "", "traceback must not leak by default"
        finally:
            cleanup()


# ── Explore: star-schema query endpoint ───────────────────────────────────

class TestQueryEndpoint:
    def _client(self, memory_model):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.registry import registry
        from tracebi.web.api.routers import models as models_router

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
        from tracebi.web.api.registry import registry
        registry._models.pop("Sales", None)


    def test_having_is_applied_over_rest_not_silently_dropped(self, memory_model):
        """A having clause posted to the REST query endpoint must be applied,
        not swallowed by the request model — a dropped having would return the
        full unfiltered result (a confident wrong number)."""
        client = self._client(memory_model)
        try:
            r = client.post("/api/models/Sales/query", json={
                "fact": "fact_orders",
                "measures": {"revenue": "sum"},
                "dimensions": ["dim_customer.segment"],
                "having": {"revenue": {"gte": 10**12}},
            })
            assert r.status_code == 200
            assert r.json()["rows"] == 0, (
                "an impossibly high having threshold must yield no groups; "
                "a dropped having would return every segment"
            )
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


# ── Shared project model & @scheduled decorator ──────────────────────────

class TestRegistryExtras:
    @pytest.fixture(autouse=True)
    def _reset_registry(self):
        from tracebi.web.api.registry import registry
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


    def test_concurrent_registration_is_safe(self):
        import threading
        from types import SimpleNamespace
        from tracebi.web.api.registry import Registry

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


# ── Pipeline-level run endpoint ───────────────────────────────────────────

class TestPipelineRunEndpoint:
    def test_run_all_layers(self, tmp_path):
        import pandas as pd
        from tracebi import LandingLayer, ManipulationLayer, PipelineRunner, SQLConnector
        from sqlalchemy import create_engine
        from tracebi.web.api.registry import Registry

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

        # Use a fresh registry to keep this isolated from the singleton.
        local = Registry()
        local.add_pipeline("sales", runner)

        # The router bound the singleton at import, and it may already be
        # imported (the web journeys import the app). Swap the router's own
        # binding, so isolation holds whatever the import order.
        from tracebi.web.api.routers import pipelines as pipelines_router
        original = pipelines_router.registry
        pipelines_router.registry = local
        try:
            from fastapi.testclient import TestClient
            from fastapi import FastAPI
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
            pipelines_router.registry = original


# ── Dev-mode reload endpoint ──────────────────────────────────────────────

class TestDevReload:

    def test_endpoint_returns_reload_summary(self, tmp_path):
        from tracebi.web.discovery import auto_discover
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from tracebi.web.api.routers import dev as dev_router

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
        from tracebi.web.api.lineage_graph import lineage_to_graph
        graph = lineage_to_graph(self._joined_lineage())
        join_ids = [n["id"] for n in graph["nodes"]
                    if n["data"]["operation"] == "join"]
        assert len(join_ids) == 1
        incoming = [e for e in graph["edges"] if e["target"] == join_ids[0]]
        assert len(incoming) == 2


# ─────────────────────────────────────────────

class TestVerifyFileAPI:
    """POST /api/verify/file — the `tracebi verify --file` check over HTTP:
    rehash a report's embedded data against its manifest, no model needed."""

    def _client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.routers import verify as verify_router
        app = FastAPI()
        app.include_router(verify_router.router, prefix="/api")
        return TestClient(app)

    def _artifact(self, tmp_path):
        """Build a real, verifiable (html, manifest) pair."""
        import json as _json
        import pandas as pd
        from tracebi import DataModel, MemoryConnector
        from tracebi.reports.template_package import TemplatePackage
        df = pd.DataFrame({"region": ["NE", "SE"], "revenue": [100.0, 250.0]})
        m = DataModel("vf_model")
        m.add_connector(MemoryConnector("vf_mem", tables={"t": df}))
        m.add_table("t", connector="vf_mem", source="t")
        m.add_dimension("dim_r", table_name="t", key_col="region",
                        attributes=["region"])
        m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
        m.add_measure("total", column="revenue", agg="sum")
        m.connect()
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "report.json").write_text(_json.dumps({
            "name": "pkg",
            "data": {
                "kpi": {"model": "vf_model",
                        "query": {"fact": "f", "measures": ["total"]}},
                "by_region": {"model": "vf_model",
                              "query": {"fact": "f",
                                        "measures": {"revenue": "sum"},
                                        "dimensions": ["dim_r.region"]}},
            },
        }))
        (pkg_dir / "template.html").write_text(
            '<html><head><title>x</title></head><body>'
            '<div data-tb-figure="value" data-tb-binding="kpi" '
            'data-tb-cell="total" id="fig"></div>'
            '<table data-tb-figure="table" data-tb-binding="by_region" '
            'id="tbl"></table></body></html>'
        )
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg_dir)).render(
            {"vf_model": m}, str(out)).to_dict()
        return out.read_text(encoding="utf-8"), manifest

    def test_missing_html_is_400(self):
        assert self._client().post(
            "/api/verify/file", json={"manifest": {}}).status_code == 400

    def test_bad_manifest_is_400(self):
        assert self._client().post(
            "/api/verify/file",
            json={"html": "<html></html>", "manifest": 5}).status_code == 400

    def test_intact_file_verifies(self, tmp_path):
        html, manifest = self._artifact(tmp_path)
        r = self._client().post("/api/verify/file",
                                json={"html": html, "manifest": manifest})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True and body["verdict"] == "file_intact"

    def test_tampered_file_is_caught(self, tmp_path):
        html, manifest = self._artifact(tmp_path)
        tampered = html.replace("100.0", "999.0")   # edit an embedded value
        assert tampered != html   # the edit actually landed in an embedded block
        r = self._client().post("/api/verify/file",
                                json={"html": tampered, "manifest": manifest})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False and body["verdict"] == "file_altered"

    def test_manifest_as_json_string_is_accepted(self, tmp_path):
        import json as _json
        html, manifest = self._artifact(tmp_path)
        r = self._client().post(
            "/api/verify/file",
            json={"html": html, "manifest": _json.dumps(manifest)})
        assert r.status_code == 200 and r.json()["ok"] is True


# ─────────────────────────────────────────────

class TestDocsEndpoints:
    """GET /api/docs serves the markdown guides in docs/ read-only."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from tracebi.web.api.routers import docs
        app = FastAPI()
        app.include_router(docs.router, prefix="/api")
        return TestClient(app)


    def test_get_guide_content(self, client):
        r = client.get("/api/docs/guides--analyst-guide")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "guides--analyst-guide"
        assert body["title"] == "TraceBi Analyst Guide"
        assert "TraceBi" in body["content"]


    def test_listing_is_the_sites_order(self, client):
        # docs/toc.yaml is the one order: the app's sidebar is this listing,
        # and the static site's nav is generated from the same file. If the
        # two ever disagree, the app and tracebi.com show different handbooks.
        import re
        body = client.get("/api/docs").json()
        app_order = [g["name"].replace("--", "/")
                     for s in body["sections"] for g in s["pages"]]
        site_nav = (Path(__file__).parent.parent / "site/docs/index.html").read_text()
        nav = site_nav[site_nav.index('<div class="links">'):site_nav.index("</details>")]
        site_order = re.findall(r'href="([a-z-]+/[a-z0-9-]+)\.html"', nav)
        assert app_order == site_order
        # An old address names the page that replaced it.
        assert body["moved"]["guides--quickstart"] == "start--quickstart"

    def test_path_traversal_is_unaddressable(self, client):
        # Names are matched against a directory listing of docs/*.md, so
        # traversal inputs can never resolve to a file.
        for evil in ["../README", "..%2F..%2Fpyproject", "etc/passwd"]:
            assert client.get(f"/api/docs/{evil}").status_code == 404


class TestCapabilitySurface:
    """
    The framework's vocabulary as data, for tools that author TraceBi
    projects. Generated from the code — a hand-maintained copy would drift
    the first time a field was added.
    """


    def test_published_enums_match_what_is_enforced(self):
        """
        The advertised values must be the ones the constructor accepts —
        publishing a value that raises would be worse than publishing none.
        """
        from tracebi.capabilities import describe
        from tracebi.reports.report import ChartSection, TextSection

        sections = {s["class"]: s for s in describe()["report_sections"]}
        for value in next(f for f in sections["ChartSection"]["fields"]
                          if f["name"] == "chart_type")["allowed"]:
            ChartSection(chart_type=value)
        for value in next(f for f in sections["TextSection"]["fields"]
                          if f["name"] == "style")["allowed"]:
            TextSection(style=value)

    def test_semantic_model_vocabulary_matches_the_code(self):
        from tracebi.capabilities import describe
        from tracebi.model.data_model import _AGG_FUNCS, FILTER_OPS

        sm = describe()["semantic_model"]
        assert sm["filter_operators"] == list(FILTER_OPS)
        # The named aggregations plus the parameterised percentile family.
        assert _AGG_FUNCS <= set(sm["aggregations"])
        assert any("percentile" in str(a) for a in sm["aggregations"])
        assert {k["kind"] for k in sm["measure_kinds"]} == {
            "simple", "expression", "ratio", "share", "rank", "running",
            "period_end", "offset", "growth", "to_date", "combine"
        }


class TestHelpTextIsReadable:
    """
    help() printed and returned None, so an in-process tool had to capture
    stdout to read the cheat sheet.
    """

    def test_cheat_sheet_kwargs_are_real_parameters(self):
        """A cheat sheet that names a keyword the method does not take is
        worse than no cheat sheet: it is copied verbatim and raises TypeError.

        This shipped — the DataModel sheet advertised ``add_dimension(table=,
        key=)`` against real parameters ``table_name=`` / ``key_col=``, and
        ``tracebi context`` republished it to every agent. Pin the sheets to
        the signatures so the next rename cannot quietly reintroduce it.
        """
        import inspect
        import re

        import pandas as pd

        from tracebi import DataModel, DataSet
        from tracebi.reports.report import Report

        subjects = [
            DataSet(pd.DataFrame(), name="t"),
            DataModel("m"),
            Report("r"),
        ]
        checked = 0
        problems = []
        for obj in subjects:
            for line in obj.help_text().splitlines():
                m = re.search(r"\.(\w+)\(([^)]*)", line)
                if not m:
                    continue
                method = getattr(type(obj), m.group(1), None)
                if method is None or not callable(method):
                    continue
                sig = inspect.signature(method)
                # A **kwargs method (``assign(margin=…)``, ``aggregate(
                # revenue="sum")``) legitimately takes any keyword — the
                # user's column names are the arguments.
                if any(p.kind is inspect.Parameter.VAR_KEYWORD
                       for p in sig.parameters.values()):
                    continue
                params = set(sig.parameters)
                for kw in re.findall(r"(\w+)=", m.group(2)):
                    checked += 1
                    if kw not in params:
                        problems.append(
                            f"{type(obj).__name__}.{m.group(1)}() has no "
                            f"parameter '{kw}' — the cheat sheet says "
                            f"'{line.strip()}'"
                        )
        assert checked > 10, "the cheat sheets must advertise keyword arguments"
        assert not problems, "\n".join(problems)


# ── Authorization (roles) ─────────────────────────────────────────────────────
# Both auth middlewares set request.state.user and, until now, nothing read it:
# any authenticated principal could run every report and every pipeline layer.
# Roles are ordered viewer < analyst < admin and split by side effect — reads,
# executing report/request code, writing to the warehouse.

class TestAuthorization:
    def _authorizer(self, monkeypatch, trust_role_header=True, **env):
        # trust_role_header=True is the proxy case: an upstream sets the
        # header. Basic auth passes False — see TestRoleHeaderTrust.
        for k in ("TRACEBI_AUTH_ROLE_HEADER", "TRACEBI_AUTH_ROLE_MAP",
                  "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        from tracebi.web.api.auth import _Authorizer
        return _Authorizer(trust_role_header=trust_role_header)

    def _request(self, path="/api/models", method="GET", headers=None):
        from starlette.requests import Request
        raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
        return Request({
            "type": "http", "method": method, "path": path,
            "headers": raw, "query_string": b"", "scheme": "http",
            "server": ("test", 80), "client": ("1.2.3.4", 1234),
        })

    # ── required role by side effect ──
    def test_reads_require_viewer(self):
        from tracebi.web.api.auth import _required_role
        assert _required_role("GET", "/api/models") == "viewer"
        assert _required_role("GET", "/api/reports") == "viewer"
        assert _required_role("GET", "/api/runs") == "viewer"
        # A run's log is whatever its steps printed, so it is read as an analyst.
        assert _required_role("GET", "/api/pipelines/p/runs/1") == "viewer"
        assert _required_role("GET", "/api/pipelines/p/runs/1/log") == "analyst"

    def test_executing_report_code_requires_analyst(self):
        from tracebi.web.api.auth import _required_role
        assert _required_role("POST", "/api/reports/x/run") == "analyst"
        # Any unlisted non-GET route falls through to analyst by default.
        assert _required_role("POST", "/api/unlisted/x/run") == "analyst"

    def test_writing_to_the_warehouse_requires_admin(self):
        from tracebi.web.api.auth import _required_role
        assert _required_role("POST", "/api/pipelines/p/layers/l/run") == "admin"
        assert _required_role("POST", "/api/_dev/reload") == "admin"

    def test_keeping_a_selection_cut_requires_admin(self, monkeypatch):
        # Keep writes the published report.json. Recomputing a selection
        # persists nothing and stays at analyst. Foldered names contain
        # slashes, so the path is not a single segment.
        authz = self._authorizer(
            monkeypatch, TRACEBI_AUTH_ROLE_MAP="bob:analyst,alice:admin",
        )
        assert authz.enabled is True
        for path in (
            "/api/reports/weekly/selection/keep",
            "/api/reports/a/b/selection/keep",
        ):
            denied = authz.check(self._request(path, "POST"), "bob")
            assert denied is not None and denied.status_code == 403
            assert authz.check(self._request(path, "POST"), "alice") is None
        assert authz.check(
            self._request("/api/reports/weekly/selection", "POST"), "bob",
        ) is None

    def test_explore_and_validate_are_reads(self):
        # They compute but persist nothing, so they sit with the reads.
        from tracebi.web.api.auth import _required_role
        assert _required_role("POST", "/api/models/m/query") == "viewer"
        assert _required_role("POST", "/api/spec/validate") == "viewer"

    def test_unlisted_write_defaults_to_analyst_not_open(self):
        # A route added later must be guarded by default.
        from tracebi.web.api.auth import _required_role
        assert _required_role("POST", "/api/something/new") == "analyst"
        assert _required_role("DELETE", "/api/whatever") == "analyst"

    # ── opt-in enforcement ──
    def test_unconfigured_grants_admin_so_upgrades_do_not_lock_out(self, monkeypatch):
        # The important back-compat property: adding authorization must not
        # silently forbid what a running deployment could already do.
        authz = self._authorizer(monkeypatch)
        assert authz.enabled is False
        assert authz.role_for(self._request(), "anyone") == "admin"
        assert authz.check(self._request("/api/pipelines/p/layers/l/run", "POST"),
                           "anyone") is None

    def test_role_header_switches_enforcement_on(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        assert authz.enabled is True
        req = self._request("/api/pipelines/p/layers/l/run", "POST",
                            {"X-Groups": "viewer"})
        denied = authz.check(req, "alice")
        assert denied is not None and denied.status_code == 403

    def test_role_map_switches_enforcement_on(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_MAP="bob:analyst")
        assert authz.enabled is True
        assert authz.role_for(self._request(), "bob") == "analyst"

    # ── role resolution ──
    def test_highest_role_wins_among_group_claims(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        req = self._request(headers={"X-Groups": "viewer,admin,analyst"})
        assert authz.role_for(req, "alice") == "admin"

    def test_space_separated_claims_are_accepted(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        req = self._request(headers={"X-Groups": "viewer analyst"})
        assert authz.role_for(req, "alice") == "analyst"

    def test_unknown_group_falls_back_to_default_not_admin(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        req = self._request(headers={"X-Groups": "sales-team"})
        assert authz.role_for(req, "dave") == "viewer"

    def test_default_role_is_configurable(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups",
                                 TRACEBI_AUTH_DEFAULT_ROLE="analyst")
        assert authz.role_for(self._request(headers={"X-Groups": "nope"}), "d") == "analyst"

    def test_bad_default_role_fails_loudly_at_construction(self, monkeypatch):
        with pytest.raises(ValueError, match="TRACEBI_AUTH_DEFAULT_ROLE"):
            self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups",
                             TRACEBI_AUTH_DEFAULT_ROLE="superuser")

    def test_role_map_ignores_malformed_and_unknown_roles(self, monkeypatch):
        authz = self._authorizer(
            monkeypatch,
            TRACEBI_AUTH_ROLE_MAP="alice:admin,garbage,bob:wizard, carol:analyst ",
        )
        assert authz.role_map == {"alice": "admin", "carol": "analyst"}

    def test_bad_role_map_entries_warn_and_alice_stays_admin(self, monkeypatch):
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            authz = self._authorizer(
                monkeypatch,
                TRACEBI_AUTH_ROLE_MAP="alice:admin,bob:superuser,carol,:admin",
            )
        messages = [str(w.message) for w in caught]
        assert any("bob:superuser" in m for m in messages)
        assert any("carol" in m and "no ':'" in m for m in messages)
        assert any(":admin" in m and "no user name" in m for m in messages)
        assert authz.role_map == {"alice": "admin"}
        assert authz.role_for(self._request(), "alice") == "admin"

    def test_no_role_source_logs_that_enforcement_is_off(self, monkeypatch, caplog):
        import logging
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_PROXY_HEADER", "TRACEBI_AUTH_ROLE_HEADER",
                  "TRACEBI_AUTH_ROLE_MAP", "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        with caplog.at_level(logging.INFO, logger="tracebi.auth"):
            assert install_if_configured(FastAPI()) is None
        posture = [r.getMessage() for r in caplog.records if r.name == "tracebi.auth"]
        assert len(posture) == 1
        assert "enforcement is off" in posture[0]
        assert "role source: none" in posture[0]

    def test_role_map_without_auth_logs_that_enforcement_is_off(
        self, monkeypatch, caplog
    ):
        # A role map with no authentication mode installs no middleware.
        # The posture line must not claim that map is enforced.
        import logging
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_PROXY_HEADER", "TRACEBI_AUTH_ROLE_HEADER",
                  "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_ROLE_MAP", "alice:admin")
        with caplog.at_level(logging.INFO, logger="tracebi.auth"):
            assert install_if_configured(FastAPI()) is None
        posture = [r.getMessage() for r in caplog.records if r.name == "tracebi.auth"]
        assert len(posture) == 1
        assert (
            "enforcement is off: no authentication configured, "
            "every request is admin"
        ) in posture[0]
        assert "role source: role map (1 users)" in posture[0]
        assert "enforcement on" not in posture[0]

    def test_denial_names_the_role_and_what_was_needed(self, monkeypatch):
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        req = self._request("/api/pipelines/p/layers/l/run", "POST",
                            {"X-Groups": "analyst"})
        denied = authz.check(req, "bob")
        body = denied.body.decode()
        assert "analyst" in body and "admin" in body

    def test_role_is_exposed_on_request_state(self, monkeypatch):
        # So handlers and, later, the audit trail can attribute an action.
        authz = self._authorizer(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        req = self._request(headers={"X-Groups": "analyst"})
        authz.check(req, "bob")
        assert req.state.role == "analyst"

    # ── where the role header came from ──
    def test_untrusted_role_header_is_not_a_role_source(self, monkeypatch):
        # With no upstream to set it, the header is written by the principal
        # it would promote, so the explicit map decides instead.
        authz = self._authorizer(monkeypatch, trust_role_header=False,
                                 TRACEBI_AUTH_ROLE_HEADER="X-Groups",
                                 TRACEBI_AUTH_ROLE_MAP="bob:viewer")
        req = self._request(headers={"X-Groups": "admin"})
        assert authz.role_for(req, "bob") == "viewer"

    def test_untrusted_role_header_alone_leaves_enforcement_off(self, monkeypatch):
        # It is not a usable source, so it must not switch enforcement on —
        # that would demote a running deployment to viewer with no way up.
        authz = self._authorizer(monkeypatch, trust_role_header=False,
                                 TRACEBI_AUTH_ROLE_HEADER="X-Groups")
        assert authz.enabled is False
        assert authz.role_for(self._request(headers={"X-Groups": "viewer"}),
                              "bob") == "admin"

    def test_stated_default_role_keeps_enforcement_on_without_the_header(
        self, monkeypatch
    ):
        # The lockout the case above avoids is "nobody named a role". Here the
        # operator named one, so it applies to everyone and the ignored header
        # must not silently turn enforcement off.
        authz = self._authorizer(monkeypatch, trust_role_header=False,
                                 TRACEBI_AUTH_ROLE_HEADER="X-Groups",
                                 TRACEBI_AUTH_DEFAULT_ROLE="analyst")
        assert authz.enabled is True
        assert authz.role_for(self._request(headers={"X-Groups": "admin"}),
                              "bob") == "analyst"


# ── Authorization over real HTTP ──────────────────────────────────────────────
# The unit tests above hand _Authorizer a synthetic Request; these drive the
# middleware that install_if_configured actually installs, and check the side
# effect a denial is supposed to prevent — a pipeline layer writing to the
# warehouse — not only the status code.

class TestRoleHeaderTrust:
    def _warehouse(self, tmp_path):
        """A registered landing layer whose run writes a visible sink table."""
        import pandas as pd
        from sqlalchemy import create_engine
        from tracebi import LandingLayer, PipelineRunner, SQLConnector

        url = f"sqlite:///{tmp_path}/warehouse.db"
        eng = create_engine(url)
        pd.DataFrame({"id": [1, 2, 3]}).to_sql("orders_raw", eng, index=False)
        db = SQLConnector("db", url=url)
        runner = PipelineRunner(db_url=f"sqlite:///{tmp_path}/runner_meta.db")
        runner.register(
            LandingLayer(connector=db, source="orders_raw",
                         sink=db, sink_table="orders_bronze"),
            name="orders_bronze",
        )
        return eng, runner

    def _app(self, runner):
        from fastapi import FastAPI
        app = FastAPI()

        @app.post("/api/pipelines/sales/layers/{layer}/run")
        def run_layer(layer: str):
            runner.run(layer)
            return {"status": "ok"}

        return app

    def _basic_env(self, monkeypatch, **env):
        for k in ("TRACEBI_AUTH_PROXY_HEADER", "TRACEBI_AUTH_PROXY_TRUSTED_IPS",
                  "TRACEBI_AUTH_ROLE_HEADER", "TRACEBI_AUTH_ROLE_MAP",
                  "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_USER", "bob")
        monkeypatch.setenv("TRACEBI_AUTH_PASS", "hunter2")
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    def test_basic_user_cannot_self_promote_and_nothing_runs(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from sqlalchemy import inspect
        from tracebi.web.api.auth import install_if_configured

        self._basic_env(monkeypatch,
                        TRACEBI_AUTH_ROLE_HEADER="X-Forwarded-Groups",
                        TRACEBI_AUTH_ROLE_MAP="bob:viewer")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        assert install_if_configured(app) == "basic"

        r = TestClient(app).post(
            "/api/pipelines/sales/layers/orders_bronze/run",
            auth=("bob", "hunter2"),
            headers={"X-Forwarded-Groups": "admin"},
        )
        assert r.status_code == 403
        # The point is not the status code: the layer must not have run.
        assert "orders_bronze" not in inspect(eng).get_table_names()
        assert runner.last_run("orders_bronze") is None

    def test_client_header_does_not_override_the_role_map(self, monkeypatch, tmp_path):
        # An operator pinned bob to analyst; bob claiming admin stays analyst.
        from fastapi.testclient import TestClient
        from tracebi.web.api.auth import install_if_configured

        self._basic_env(monkeypatch,
                        TRACEBI_AUTH_ROLE_HEADER="X-Forwarded-Groups",
                        TRACEBI_AUTH_ROLE_MAP="bob:analyst")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        install_if_configured(app)

        r = TestClient(app).post(
            "/api/pipelines/sales/layers/orders_bronze/run",
            auth=("bob", "hunter2"),
            headers={"X-Forwarded-Groups": "admin"},
        )
        assert r.status_code == 403
        assert r.json()["detail"]["role"] == "analyst"
        assert runner.last_run("orders_bronze") is None

    def test_basic_with_role_header_and_no_map_is_not_locked_out(self, monkeypatch, tmp_path):
        # Enforcement is opt-in: the only configured source is one Basic auth
        # cannot trust, so this deployment keeps running its own pipelines.
        from fastapi.testclient import TestClient
        from sqlalchemy import inspect
        from tracebi.web.api.auth import install_if_configured

        self._basic_env(monkeypatch, TRACEBI_AUTH_ROLE_HEADER="X-Forwarded-Groups")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        # The warning has to name the consequence, not just the fact: this is
        # the configuration where nothing is enforced.
        with pytest.warns(UserWarning,
                          match="every authenticated caller is admin"):
            install_if_configured(app)

        r = TestClient(app).post(
            "/api/pipelines/sales/layers/orders_bronze/run",
            auth=("bob", "hunter2"),
        )
        assert r.status_code == 200
        assert "orders_bronze" in inspect(eng).get_table_names()

    def test_proxy_mode_still_takes_the_role_from_the_header(self, monkeypatch, tmp_path):
        # Unchanged: the proxy is the identity source, so it is the role
        # source too. It must strip client-supplied role headers.
        from fastapi.testclient import TestClient
        from sqlalchemy import inspect
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_ROLE_MAP", "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_TRUSTED_IPS", raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_ROLE_HEADER", "X-Forwarded-Groups")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        # TestClient reports a non-IP peer, so trusted_ips is left unset here.
        with pytest.warns(UserWarning, match="TRUSTED_IPS"):
            assert install_if_configured(app) == "proxy"

        client = TestClient(app)
        denied = client.post("/api/pipelines/sales/layers/orders_bronze/run",
                             headers={"X-Forwarded-User": "alice",
                                      "X-Forwarded-Groups": "analyst"})
        assert denied.status_code == 403
        assert "orders_bronze" not in inspect(eng).get_table_names()

        allowed = client.post("/api/pipelines/sales/layers/orders_bronze/run",
                              headers={"X-Forwarded-User": "alice",
                                       "X-Forwarded-Groups": "admin"})
        assert allowed.status_code == 200
        assert "orders_bronze" in inspect(eng).get_table_names()

    def test_role_config_without_an_auth_mode_warns_that_nothing_is_enforced(
        self, monkeypatch
    ):
        # No auth mode means no middleware, so the role config does nothing.
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_PROXY_HEADER"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_ROLE_MAP", "bob:viewer")
        app = FastAPI()
        with pytest.warns(UserWarning, match="no role is enforced"):
            assert install_if_configured(app) is None

    def test_blank_role_header_with_no_auth_mode_does_not_warn(self, monkeypatch):
        # A whitespace-only value is inert everywhere else; it must not be
        # the one place that reports role config the deployment does not have.
        import warnings
        from fastapi import FastAPI
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_PROXY_HEADER", "TRACEBI_AUTH_ROLE_MAP"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_ROLE_HEADER", "   ")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert install_if_configured(FastAPI()) is None
        assert [str(w.message) for w in caught] == []

    def test_basic_stated_default_role_still_enforces_without_a_map(
        self, monkeypatch, tmp_path
    ):
        # The operator set a role header (ignored here) *and* named the role
        # everyone else gets. Ignoring the header must not also discard the
        # default and hand every authenticated caller admin.
        from fastapi.testclient import TestClient
        from sqlalchemy import inspect
        from tracebi.web.api.auth import install_if_configured

        self._basic_env(monkeypatch,
                        TRACEBI_AUTH_ROLE_HEADER="X-Forwarded-Groups",
                        TRACEBI_AUTH_DEFAULT_ROLE="analyst")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        install_if_configured(app)

        # An honest caller, sending no role header at all.
        r = TestClient(app).post(
            "/api/pipelines/sales/layers/orders_bronze/run",
            auth=("bob", "hunter2"),
        )
        assert r.status_code == 403
        assert r.json()["detail"]["role"] == "analyst"
        assert "orders_bronze" not in inspect(eng).get_table_names()

    def test_proxy_takes_the_last_role_header_not_the_first(
        self, monkeypatch, tmp_path
    ):
        # A proxy that appends rather than replaces leaves the client's copy
        # in front of its own; reading the first would restore the very
        # self-promotion this module closes one mode over.
        from fastapi.testclient import TestClient
        from sqlalchemy import inspect
        from tracebi.web.api.auth import install_if_configured

        for k in ("TRACEBI_AUTH_USER", "TRACEBI_AUTH_PASS",
                  "TRACEBI_AUTH_ROLE_MAP", "TRACEBI_AUTH_DEFAULT_ROLE"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_PROXY_HEADER", "X-Forwarded-User")
        monkeypatch.delenv("TRACEBI_AUTH_PROXY_TRUSTED_IPS", raising=False)
        monkeypatch.setenv("TRACEBI_AUTH_ROLE_HEADER", "X-Forwarded-Groups")
        eng, runner = self._warehouse(tmp_path)
        app = self._app(runner)
        with pytest.warns(UserWarning, match="TRUSTED_IPS"):
            install_if_configured(app)

        r = TestClient(app).post(
            "/api/pipelines/sales/layers/orders_bronze/run",
            headers=[("x-forwarded-user", "alice"),
                     ("x-forwarded-groups", "admin"),    # the client's claim
                     ("x-forwarded-groups", "viewer")],  # the proxy's, appended
        )
        assert r.status_code == 403
        assert r.json()["detail"]["role"] == "viewer"
        assert "orders_bronze" not in inspect(eng).get_table_names()


# ── Web parity: artifact-backed reports serve the real render ────────────────
# Architecture v2 §2.3 (M3): a report backed by a template package must serve
# the same self-contained page + schema-2 manifest the build step produces, so
# what the browser shows is what `verify --file` can check.

class TestArtifactWebParity:
    def _package(self, tmp_path):
        import json as _json

        import pandas as pd

        from tracebi import DataModel, MemoryConnector, model_registry

        df = pd.DataFrame({"region": ["NE", "SE"], "revenue": [100.0, 250.0]})
        m = DataModel("parity_model")
        m.add_connector(MemoryConnector("par_mem", tables={"t": df}))
        m.add_table("t", connector="par_mem", source="t")
        m.add_dimension("dim_r", table_name="t", key_col="region",
                        attributes=["region"])
        m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
        m.add_measure("total", column="revenue", agg="sum")
        m.connect()
        model_registry.register(m)

        pkg = tmp_path / "parity_pkg"
        pkg.mkdir()
        (pkg / "report.json").write_text(_json.dumps({
            "name": "parity_pkg",
            "data": {"kpi": {"model": "parity_model",
                             "query": {"fact": "f", "measures": ["total"]}}},
        }))
        (pkg / "template.html").write_text(
            "<html><head><title>p</title></head><body>"
            '<div data-tb-figure="value" data-tb-binding="kpi" '
            'data-tb-cell="total" id="fig-kpi"></div>'
            "</body></html>"
        )
        return pkg

    def test_web_rendered_artifact_html_passes_verify_file(self, tmp_path, monkeypatch):
        from tracebi.verify import verify_file
        from tracebi.web.api.routers import reports as reports_router
        from tracebi.web.discovery import _register_template_package

        pkg = self._package(tmp_path)
        out = _register_template_package(str(pkg), "parity_pkg")
        assert out["status"] == "registered", out

        monkeypatch.chdir(tmp_path)
        reports_router._ARTIFACT_CACHE.pop("parity_pkg", None)
        payload = reports_router._artifact_payload("parity_pkg")
        assert payload is not None, "package-backed report must take the artifact path"
        assert payload["retained"] is True
        assert (tmp_path / "output" / "parity_pkg.html").is_file()
        assert (tmp_path / "output" / "parity_pkg.html.manifest.json").is_file()
        manifest = payload["manifest"]
        assert manifest["schema_version"] == 2
        assert manifest["figures"], "the figure claims layer must ride the web render"
        assert "tracebi-data-kpi" in payload["html"], "embedded data over HTTP"

        result = verify_file(payload["html"], manifest)
        assert result["ok"], result["verdict_detail"]
