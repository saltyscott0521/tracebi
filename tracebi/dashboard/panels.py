"""
Dashboard panel definitions.

Each panel class is a pure Python dataclass — no Dash imports here.
The DashboardServer reads these definitions and turns them into live
Dash components with registered callbacks.

Panel types
-----------
TablePanel  — paginated data table
ChartPanel  — Plotly chart (bar, line, pie, scatter, area)
MetricPanel — single KPI card (aggregate value)
FilterPanel — filter control (dropdown / multi-select) that drives all
              other panels sharing the same DataModel
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from tracebi.model.dataset import DataSet


# ─────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────

@dataclass
class _BasePanel:
    """Common fields shared by all data panels."""

    panel_id: str
    """Unique identifier used as the Dash component ID prefix."""

    title: str = ""
    """Panel heading displayed above the content."""

    # Data source — provide exactly one of these:
    dataset: Optional[DataSet] = None
    """Pre-built DataSet. Filters are applied on top of it at render time."""

    table_name: str = ""
    """Table name to load from the DataModel on each filter change.
    Requires a DataModel to be passed to DashboardServer."""

    transform_fn: Optional[Callable[[DataSet], DataSet]] = None
    """Optional transform applied after loading / filtering.
    Useful for panel-specific aggregations or column selections."""

    width: int = 1
    """Number of grid columns this panel spans (out of Dashboard.columns)."""


# ─────────────────────────────────────────────────────────────
# Data panels
# ─────────────────────────────────────────────────────────────

@dataclass
class TablePanel(_BasePanel):
    """
    A paginated, sortable data table.

    Usage:
        TablePanel(
            panel_id="orders-table",
            title="Order Detail",
            dataset=orders_ds,
            columns=["order_id", "region", "product", "revenue"],
            page_size=15,
        )

    Fields:
        columns:       Subset of columns to display (None = all).
        column_labels: Dict of {col_name: display_label} header overrides.
        max_rows:      Hard cap on rows displayed (None = all, pagination applies).
        page_size:     Rows per page in the interactive table (default 10).
    """

    columns: Optional[list[str]] = None
    column_labels: Optional[dict[str, str]] = None
    max_rows: Optional[int] = None
    page_size: int = 10


@dataclass
class ChartPanel(_BasePanel):
    """
    A Plotly chart panel.

    Usage:
        ChartPanel(
            panel_id="revenue-bar",
            title="Revenue by Region",
            dataset=orders_ds,
            chart_type="bar",
            x="region",
            y="revenue",
        )

    Fields:
        chart_type: ``'bar'``, ``'line'``, ``'pie'``, ``'scatter'``, or ``'area'``.
        x:          X-axis column name.
        y:          Y-axis column name or list of column names.
        color:      Column to use for colour grouping.
        xlabel:     X-axis label override.
        ylabel:     Y-axis label override.
        height:     Chart height in pixels (default 350).
    """

    chart_type: str = "bar"
    x: Optional[str] = None
    y: Optional[Union[str, list[str]]] = None
    color: Optional[str] = None
    xlabel: Optional[str] = None
    ylabel: Optional[str] = None
    height: int = 350


@dataclass
class MetricPanel(_BasePanel):
    """
    A KPI card showing a single aggregated value.

    Usage:
        MetricPanel(
            panel_id="total-revenue",
            title="Total Revenue",
            dataset=orders_ds,
            column="revenue",
            aggregation="sum",
            prefix="$",
            number_format="{:,.2f}",
        )

    Fields:
        column:        Column to aggregate.
        aggregation:   ``'sum'``, ``'mean'``, ``'count'``, ``'min'``, ``'max'``,
                       or ``'median'``.
        prefix:        String prepended to the displayed value (e.g. ``'$'``).
        suffix:        String appended to the displayed value (e.g. ``'%'``).
        number_format: Python format string for the numeric value.
                       Default ``'{:,.0f}'``.
    """

    column: str = ""
    aggregation: str = "sum"
    prefix: str = ""
    suffix: str = ""
    number_format: str = "{:,.0f}"


# ─────────────────────────────────────────────────────────────
# Filter panel
# ─────────────────────────────────────────────────────────────

@dataclass
class FilterPanel:
    """
    A filter control that drives associative filtering across all panels.

    When a value is selected, every data panel whose dataset contains the
    ``column`` will be re-rendered with that filter applied — this is the
    Qlik-style associative behaviour.

    Usage:
        FilterPanel(
            panel_id="region-filter",
            label="Region",
            column="region",
            dataset=orders_ds,   # used to populate dropdown options
        )

        # Or with a DataModel table:
        FilterPanel(
            panel_id="region-filter",
            label="Region",
            column="region",
            table_name="orders",
        )

    Fields:
        panel_id:    Unique identifier.
        label:       Human-readable label shown above the dropdown.
        column:      Column name to filter on.
        dataset:     DataSet used to populate the dropdown options.
        table_name:  Table to load from the DataModel for options
                     (alternative to ``dataset``).
        multi:       Allow multi-select (default False).
        placeholder: Dropdown placeholder text (default ``'All'``).
    """

    panel_id: str
    label: str
    column: str
    dataset: Optional[DataSet] = None
    table_name: str = ""
    multi: bool = False
    placeholder: str = "All"
