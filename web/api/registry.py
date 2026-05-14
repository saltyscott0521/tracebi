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

from typing import Any, Callable, Optional


class Registry:
    """
    Central registry for TraceBi web resources.

    Holds connectors, data models, report factories, and pipeline runners.
    The API layer only talks to this — it never imports TraceBi internals
    directly, keeping the web layer thin and the library usage visible.
    """

    def __init__(self) -> None:
        self._connectors: dict[str, Any] = {}
        self._models: dict[str, Any] = {}
        self._report_factories: dict[str, dict] = {}
        self._pipelines: dict[str, Any] = {}
        self._dashboards: dict[str, dict] = {}

    # ── Connectors ─────────────────────────────────────────────

    def add_connector(self, connector) -> "Registry":
        """Register a BaseConnector by its name."""
        self._connectors[connector.name] = connector
        return self

    def get_connector(self, name: str):
        return self._connectors.get(name)

    def list_connectors(self) -> list[dict]:
        out = []
        for c in self._connectors.values():
            entry = {
                "name": c.name,
                "type": type(c).__name__,
            }
            if hasattr(c, "_tables"):
                entry["tables"] = list(c._tables.keys())
            elif hasattr(c, "_directory"):
                entry["directory"] = c._directory
            elif hasattr(c, "_url"):
                entry["url"] = c._url
            out.append(entry)
        return out

    # ── Models ─────────────────────────────────────────────────

    def add_model(self, model) -> "Registry":
        """Register a DataModel by its name."""
        self._models[model.name] = model
        return self

    def get_model(self, name: str):
        return self._models.get(name)

    def list_models(self) -> list[dict]:
        return [
            {
                "name": m.name,
                "connectors": list(m._connectors.keys()),
                "tables": list(m._tables.keys()),
                "relationships": list(m._relationships.keys()),
            }
            for m in self._models.values()
        ]

    def describe_model(self, name: str) -> Optional[dict]:
        m = self._models.get(name)
        if not m:
            return None
        tables = [
            {
                "name": t.name,
                "connector": t.connector_name,
                "source": t.source,
            }
            for t in m._tables.values()
        ]
        relationships = [
            {
                "name": r.name,
                "left_table": r.left_table,
                "right_table": r.right_table,
                "left_key": r.left_key,
                "right_key": r.right_key,
                "how": r.how,
            }
            for r in m._relationships.values()
        ]
        return {
            "name": m.name,
            "connectors": list(m._connectors.keys()),
            "tables": tables,
            "relationships": relationships,
        }

    # ── Reports ────────────────────────────────────────────────

    def add_report(
        self,
        name: str,
        factory: Callable,
        description: str = "",
    ) -> "Registry":
        """Register a report factory (a zero-arg callable that returns a Report)."""
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
        return [
            {"name": k, "description": v["description"]}
            for k, v in self._report_factories.items()
        ]

    def run_report(self, name: str):
        """Call the report factory and return the Report object."""
        entry = self._report_factories.get(name)
        if not entry:
            return None
        return entry["factory"]()

    # ── Dashboards ─────────────────────────────────────────────

    def add_dashboard(
        self,
        name: str,
        server,
        description: str = "",
    ) -> "Registry":
        """Register a DashboardServer under a logical name."""
        self._dashboards[name] = {"server": server, "description": description}
        return self

    def get_dashboard(self, name: str):
        return self._dashboards.get(name)

    def list_dashboards(self) -> list[dict]:
        return [
            {"name": k, "description": v["description"]}
            for k, v in self._dashboards.items()
        ]

    # ── Pipelines ──────────────────────────────────────────────

    def add_pipeline(self, name: str, runner) -> "Registry":
        """Register a PipelineRunner under a logical name."""
        self._pipelines[name] = runner
        return self

    def get_pipeline(self, name: str):
        return self._pipelines.get(name)

    def list_pipeline_names(self) -> list[str]:
        return list(self._pipelines.keys())


registry = Registry()
