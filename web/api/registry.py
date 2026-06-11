"""
TraceBi Web Registry — single source of truth for the API server.

Register your connectors, models, report factories, and pipeline runners
here (or in your own app module that imports this registry). The API
routers read everything from the registry singleton at request time.

Usage in your app module::

    from web.api.registry import registry
    from tracebi import DataModel, CSVConnector
    from tracebi.reports import Report, TableSection

    connector = CSVConnector("sales", directory="data/")
    model = DataModel("SalesModel")
    model.add_connector(connector)
    model.add_table("orders", connector="sales", source="orders.csv")
    model.connect()

    registry.add_connector(connector)
    registry.add_model(model)

    @registry.report("orders_summary", description="All orders by region")
    def orders_summary():
        ds = model.load("orders")
        return Report("Orders Summary").table(ds, title="Orders")
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class Registry:
    """
    Central registry for TraceBi web resources.

    Holds connectors, data models, report factories, and pipeline runners.
    The API layer only talks to this — it never imports TraceBi internals
    directly, keeping the web layer thin and the library usage visible.

    All mutators and compound reads are guarded by an RLock so the
    registry is safe under threaded servers and dev-mode reloads.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connectors: dict[str, Any] = {}
        self._models: dict[str, Any] = {}
        self._report_factories: dict[str, dict] = {}
        self._scheduled_factories: dict[str, dict] = {}
        self._pipelines: dict[str, Any] = {}
        self._dashboards: dict[str, dict] = {}
        self._default_model_name: Optional[str] = None

    # ── Connectors ─────────────────────────────────────────────

    def add_connector(self, connector) -> "Registry":
        """Register a BaseConnector by its name."""
        with self._lock:
            self._connectors[connector.name] = connector
        return self

    def get_connector(self, name: str):
        with self._lock:
            return self._connectors.get(name)

    def list_connectors(self) -> list[dict]:
        with self._lock:
            connectors = list(self._connectors.values())
        return [c.describe() for c in connectors]

    # ── Models ─────────────────────────────────────────────────

    def add_model(self, model, default: bool = False) -> "Registry":
        """
        Register a DataModel by its name.

        Pass ``default=True`` to mark this model as the project default —
        request scripts can grab it via ``registry.get_default_model()``
        instead of building their own.
        """
        with self._lock:
            self._models[model.name] = model
            if default or self._default_model_name is None:
                self._default_model_name = model.name
        return self

    def set_default_model(self, name: str) -> "Registry":
        """Mark a previously-registered model as the project default."""
        with self._lock:
            if name not in self._models:
                raise KeyError(f"Model '{name}' is not registered.")
            self._default_model_name = name
        return self

    def get_default_model(self):
        """Return the project default DataModel, or None if none is set."""
        with self._lock:
            if self._default_model_name is None:
                return None
            return self._models.get(self._default_model_name)

    def get_model(self, name: str):
        with self._lock:
            return self._models.get(name)

    def list_models(self) -> list[dict]:
        with self._lock:
            models = list(self._models.values())
        out = []
        for m in models:
            info = m.info()
            out.append({
                "name": info["name"],
                "connectors": info["connectors"],
                "tables": [t["name"] for t in info["tables"]],
                "relationships": [r["name"] for r in info["relationships"]],
            })
        return out

    def describe_model(self, name: str) -> Optional[dict]:
        with self._lock:
            m = self._models.get(name)
        if not m:
            return None
        return m.info()

    # ── Reports ────────────────────────────────────────────────

    def add_report(
        self,
        name: str,
        factory: Callable,
        description: str = "",
    ) -> "Registry":
        """Register a report factory (a zero-arg callable that returns a Report)."""
        with self._lock:
            self._report_factories[name] = {
                "description": description,
                "factory": factory,
            }
        return self

    def report(self, name: str, description: str = ""):
        """Decorator for report factory functions."""
        def decorator(fn: Callable) -> Callable:
            self.add_report(name, fn, description)
            return fn
        return decorator

    def list_reports(self) -> list[dict]:
        with self._lock:
            return [
                {"name": k, "description": v["description"]}
                for k, v in self._report_factories.items()
            ]

    def run_report(self, name: str):
        """Call the report factory and return the Report object."""
        with self._lock:
            entry = self._report_factories.get(name)
        if not entry:
            return None
        return entry["factory"]()

    # ── Scheduled reports ──────────────────────────────────────

    def scheduled(
        self,
        name: str,
        cron: str,
        description: str = "",
    ):
        """
        Decorator: register a report factory and also mark it for
        scheduled execution. The PipelineRunner (or any external scheduler)
        can read ``list_scheduled()`` to wire up cron jobs.

        Usage::

            @registry.scheduled("weekly_sales", cron="0 9 * * MON")
            def weekly_sales():
                return Report(...)
        """
        def decorator(fn: Callable) -> Callable:
            self.add_report(name, fn, description)
            with self._lock:
                self._scheduled_factories[name] = {
                    "cron":        cron,
                    "description": description,
                    "factory":     fn,
                }
            return fn
        return decorator

    def list_scheduled(self) -> list[dict]:
        with self._lock:
            return [
                {"name": k, "cron": v["cron"], "description": v["description"]}
                for k, v in self._scheduled_factories.items()
            ]

    # ── Dashboards ─────────────────────────────────────────────

    def add_dashboard(
        self,
        name: str,
        server,
        description: str = "",
    ) -> "Registry":
        """Register a DashboardServer under a logical name."""
        with self._lock:
            self._dashboards[name] = {"server": server, "description": description}
        return self

    def get_dashboard(self, name: str):
        with self._lock:
            return self._dashboards.get(name)

    def dashboards(self) -> dict[str, dict]:
        """All registered dashboards: name -> {server, description}."""
        with self._lock:
            return dict(self._dashboards)

    def list_dashboards(self) -> list[dict]:
        with self._lock:
            return [
                {"name": k, "description": v["description"]}
                for k, v in self._dashboards.items()
            ]

    # ── Pipelines ──────────────────────────────────────────────

    def add_pipeline(self, name: str, runner) -> "Registry":
        """Register a PipelineRunner under a logical name."""
        with self._lock:
            self._pipelines[name] = runner
        return self

    def get_pipeline(self, name: str):
        with self._lock:
            return self._pipelines.get(name)

    def list_pipeline_names(self) -> list[str]:
        with self._lock:
            return list(self._pipelines.keys())


registry = Registry()
