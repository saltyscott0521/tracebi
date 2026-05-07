"""
Dashboard — fluent builder for TraceBi dashboards.

A Dashboard is a pure Python definition — no Dash imports needed here.
Pass a Dashboard to DashboardServer to wire up callbacks and serve it.
"""

from __future__ import annotations

from typing import Optional, Union

from tracebi.dashboard.panels import (
    _BasePanel, TablePanel, ChartPanel, MetricPanel, FilterPanel,
)
from tracebi.model.dataset import DataSet


class Dashboard:
    """
    Code-defined dashboard built with a fluent API.

    Usage:
        from tracebi.dashboard import Dashboard, TablePanel, ChartPanel, MetricPanel, FilterPanel

        dashboard = (
            Dashboard("Q2 Sales Dashboard")
            .description("Live view of Q2 revenue and order metrics.")
            .columns(2)
            .add_filter(FilterPanel(
                panel_id="region-filter",
                label="Region",
                column="region",
                dataset=orders_ds,
            ))
            .add_panel(MetricPanel(
                panel_id="total-revenue",
                title="Total Revenue",
                dataset=orders_ds,
                column="revenue",
                aggregation="sum",
                prefix="$",
            ))
            .add_panel(ChartPanel(
                panel_id="revenue-chart",
                title="Revenue by Region",
                dataset=orders_ds,
                chart_type="bar",
                x="region",
                y="revenue",
            ))
            .add_panel(TablePanel(
                panel_id="orders-table",
                title="Order Detail",
                dataset=orders_ds,
                page_size=10,
            ))
        )

        from tracebi.dashboard import DashboardServer
        DashboardServer(dashboard).run(port=8050, debug=True)
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self._description: str = ""
        self._columns: int = 2
        self._panels: list[_BasePanel] = []
        self._filters: list[FilterPanel] = []

    # ── Fluent configuration ────────────────────────────────────

    def description(self, text: str) -> "Dashboard":
        """Subtitle shown below the dashboard title in the header."""
        self._description = text
        return self

    def columns(self, n: int) -> "Dashboard":
        """Number of columns in the panel grid (default 2)."""
        self._columns = n
        return self

    # ── Adding panels ───────────────────────────────────────────

    def add_panel(self, panel: _BasePanel) -> "Dashboard":
        """Append a data panel (TablePanel, ChartPanel, or MetricPanel)."""
        self._panels.append(panel)
        return self

    def add_filter(self, filter_panel: FilterPanel) -> "Dashboard":
        """Append a filter control."""
        self._filters.append(filter_panel)
        return self

    # ── Shortcut methods ────────────────────────────────────────

    def table(
        self,
        panel_id: str,
        title: str = "",
        *,
        dataset: Optional[DataSet] = None,
        table_name: str = "",
        **kwargs,
    ) -> "Dashboard":
        """Shortcut to add a TablePanel."""
        return self.add_panel(
            TablePanel(panel_id=panel_id, title=title,
                       dataset=dataset, table_name=table_name, **kwargs)
        )

    def chart(
        self,
        panel_id: str,
        title: str = "",
        *,
        dataset: Optional[DataSet] = None,
        table_name: str = "",
        chart_type: str = "bar",
        x: Optional[str] = None,
        y=None,
        **kwargs,
    ) -> "Dashboard":
        """Shortcut to add a ChartPanel."""
        return self.add_panel(
            ChartPanel(panel_id=panel_id, title=title,
                       dataset=dataset, table_name=table_name,
                       chart_type=chart_type, x=x, y=y, **kwargs)
        )

    def metric(
        self,
        panel_id: str,
        title: str = "",
        *,
        dataset: Optional[DataSet] = None,
        table_name: str = "",
        column: str = "",
        aggregation: str = "sum",
        **kwargs,
    ) -> "Dashboard":
        """Shortcut to add a MetricPanel."""
        return self.add_panel(
            MetricPanel(panel_id=panel_id, title=title,
                        dataset=dataset, table_name=table_name,
                        column=column, aggregation=aggregation, **kwargs)
        )

    def filter(
        self,
        panel_id: str,
        label: str,
        column: str,
        *,
        dataset: Optional[DataSet] = None,
        table_name: str = "",
        **kwargs,
    ) -> "Dashboard":
        """Shortcut to add a FilterPanel."""
        return self.add_filter(
            FilterPanel(panel_id=panel_id, label=label, column=column,
                        dataset=dataset, table_name=table_name, **kwargs)
        )

    # ── Inspection ──────────────────────────────────────────────

    def describe(self) -> None:
        sep = "=" * 55
        print(f"\n{sep}")
        print(f"  Dashboard: '{self.title}'")
        if self._description:
            print(f"  {self._description}")
        print(f"  Columns:  {self._columns}")
        print(f"  Filters ({len(self._filters)}): "
              f"{[f.panel_id for f in self._filters]}")
        print(f"  Panels  ({len(self._panels)}):")
        for p in self._panels:
            kind = type(p).__name__
            print(f"    [{kind}] id={p.panel_id!r} title={p.title!r}")
        print(f"{sep}\n")

    def __repr__(self) -> str:
        return (
            f"<Dashboard title={self.title!r} "
            f"panels={len(self._panels)} "
            f"filters={len(self._filters)}>"
        )
