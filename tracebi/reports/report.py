"""
Report — declarative, code-defined report structure.

A Report is built from Sections. Each section holds a DataSet (with its
full lineage) and rendering hints. The same Report object can be rendered
to Excel, HTML, or PDF without changing the definition.

Every rendered report carries a ReportManifest: a complete record of
what data was used, what code produced it, and when it was run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union

import pandas as pd

from tracebi.model.dataset import DataSet


# ─────────────────────────────────────────────────────────────
# Section types
# ─────────────────────────────────────────────────────────────

class SectionType(str, Enum):
    TEXT  = "text"
    TABLE = "table"
    CHART = "chart"
    SPACER = "spacer"
    METRICS = "metrics"
    ROW = "row"


# Named number-format shortcuts accepted anywhere a Python format string is.
# e.g. number_formats={"revenue": "currency"} instead of "${:,.2f}".
NAMED_NUMBER_FORMATS = {
    "currency":  "${:,.2f}",
    "currency0": "${:,.0f}",
    "percent":   "{:.1%}",
    "comma":     "{:,.0f}",
    "decimal":   "{:,.2f}",
}


def resolve_number_format(fmt: str) -> str:
    """Resolve a named format shortcut ('currency', 'percent', …) to a
    Python format string. Unrecognised values pass through unchanged."""
    return NAMED_NUMBER_FORMATS.get(fmt, fmt)


@dataclass
class ReportSection:
    """Base class for all report sections."""
    title: Optional[str] = None
    section_type: SectionType = SectionType.TEXT

    def to_manifest_dict(self) -> dict:
        return {
            "section_type": self.section_type.value,
            "title": self.title,
        }


@dataclass
class TextSection(ReportSection):
    """
    A block of text or markdown content.

    Fields:
        content:   The text string (plain text or markdown).
        style:     One of 'normal', 'heading1', 'heading2', 'note', 'callout'.
    """
    content: str = ""
    style: str = "normal"   # normal | heading1 | heading2 | note | callout

    def __post_init__(self):
        self.section_type = SectionType.TEXT

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        d["style"] = self.style
        d["content_length"] = len(self.content)
        return d


@dataclass
class TableSection(ReportSection):
    """
    A data table rendered from a DataSet.

    Fields:
        dataset:        The DataSet to render. Its lineage is automatically
                        included in the report manifest.
        columns:        Columns to include (None = all).
        column_labels:  Dict of {col_name: display_label} renames for headers.
        max_rows:       Cap the number of rows shown (None = all).
        number_formats: Dict of {col_name: format_string}
                        e.g. {"revenue": "{:,.2f}", "date": "%Y-%m-%d"}
                        Named shortcuts also work: 'currency', 'currency0',
                        'percent', 'comma', 'decimal'.
        freeze_header:  Whether to freeze the header row (Excel only).
        totals:         List of column names to sum in a totals row.
        style:          Table style hint: 'default', 'striped', 'compact'.
        highlight_negatives: Column names whose negative values render in red.
        color_scale:    Dict of {col_name: hex_color} — cells in the column get
                        a white→color background scaled by value (heat map).
        column_widths:  Dict of {col_name: width} in approximate character
                        units (Excel column width; converted to px for HTML).
    """
    dataset: Optional[DataSet] = None
    columns: Optional[list[str]] = None
    column_labels: Optional[dict[str, str]] = None
    max_rows: Optional[int] = None
    number_formats: Optional[dict[str, str]] = None
    freeze_header: bool = True
    totals: Optional[list[str]] = None
    style: str = "default"   # default | striped | compact
    highlight_negatives: Optional[list[str]] = None
    color_scale: Optional[dict[str, str]] = None
    column_widths: Optional[dict[str, int]] = None

    def __post_init__(self):
        self.section_type = SectionType.TABLE

    def get_display_df(self) -> pd.DataFrame:
        """Return the DataFrame ready for display (columns selected, rows capped)."""
        if self.dataset is None:
            return pd.DataFrame()
        df = self.dataset.to_pandas()
        if self.columns:
            df = df[self.columns]
        if self.max_rows:
            df = df.head(self.max_rows)
        if self.column_labels:
            df = df.rename(columns=self.column_labels)
        return df

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        if self.dataset:
            d["dataset_name"] = self.dataset.name
            d["dataset_shape"] = list(self.dataset.shape)
            d["dataset_lineage"] = self.dataset.lineage_to_dict()
            d["dataset_fingerprint"] = self.dataset.fingerprint()
        d["columns"] = self.columns
        d["max_rows"] = self.max_rows
        return d


@dataclass
class ChartSection(ReportSection):
    """
    A chart rendered from a DataSet.

    For HTML/PDF output, charts are rendered as SVG using matplotlib.
    For Excel, they are embedded as image objects.

    Fields:
        dataset:    Source DataSet.
        chart_type: 'bar', 'line', 'pie', 'scatter', 'area', 'barh'.
        x:          Column name for the X axis.
        y:          Column name(s) for the Y axis (str or list).
        color:      Column to use for color grouping (optional).
        xlabel:     X axis label override.
        ylabel:     Y axis label override.
        figsize:    Tuple (width_inches, height_inches). Default (10, 5).
        style:      Matplotlib style string (e.g. 'seaborn-v0_8-whitegrid').
        palette:    List of hex colors to use.
        show_values: Draw value labels on bars / line points (HTML output).
    """
    dataset: Optional[DataSet] = None
    chart_type: str = "bar"
    x: Optional[str] = None
    y: Optional[Union[str, list[str]]] = None
    color: Optional[str] = None
    xlabel: Optional[str] = None
    ylabel: Optional[str] = None
    figsize: tuple[float, float] = (10, 5)
    style: str = "seaborn-v0_8-whitegrid"
    palette: Optional[list[str]] = None
    show_values: bool = False

    def __post_init__(self):
        self.section_type = SectionType.CHART

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        if self.dataset:
            d["dataset_name"] = self.dataset.name
            d["dataset_shape"] = list(self.dataset.shape)
            d["dataset_lineage"] = self.dataset.lineage_to_dict()
            d["dataset_fingerprint"] = self.dataset.fingerprint()
        d["chart_type"] = self.chart_type
        d["x"] = self.x
        d["y"] = self.y
        return d


@dataclass
class SpacerSection(ReportSection):
    """A blank spacer row/line between sections."""
    height: int = 1   # number of blank rows (Excel) or <br> (HTML)

    def __post_init__(self):
        self.section_type = SectionType.SPACER


@dataclass
class Metric:
    """
    A single KPI value displayed as a card in a MetricSection.

    Fields:
        label:  Short caption shown above the value, e.g. "Total Revenue".
        value:  The number (or string) to display.
        format: Python format string or named shortcut ('currency', 'percent',
                'comma', 'decimal') applied to numeric values.
        delta:  Optional change vs. a prior period. Rendered as ▲/▼ with
                green/red coloring.
        good_when_up: When False, a positive delta renders red and a negative
                one green (e.g. for costs or error rates).
    """
    label: str
    value: Any
    format: Optional[str] = None
    delta: Optional[float] = None
    good_when_up: bool = True

    def formatted_value(self) -> str:
        if self.format and isinstance(self.value, (int, float)):
            try:
                return resolve_number_format(self.format).format(self.value)
            except Exception:
                return str(self.value)
        return str(self.value)


@dataclass
class MetricSection(ReportSection):
    """
    A horizontal row of KPI cards.

    Usage:
        report.add(MetricSection(title="Key Metrics", metrics=[
            Metric("Total Revenue", 1_250_000, format="currency0", delta=0.12),
            Metric("Orders", 8421, format="comma", delta=-0.03),
        ]))
    """
    metrics: list[Metric] = field(default_factory=list)

    def __post_init__(self):
        self.section_type = SectionType.METRICS

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        d["metrics"] = [
            {"label": m.label, "value": m.value, "delta": m.delta}
            for m in self.metrics
        ]
        return d


@dataclass
class RowSection(ReportSection):
    """
    A layout container that renders its child sections side by side.

    HTML renders children in equal-width columns (or weighted by ``widths``).
    Excel has no side-by-side flow, so children render stacked vertically.

    Usage:
        report.add(RowSection(sections=[
            ChartSection(title="By Region", dataset=ds, chart_type="bar", x="region", y="revenue"),
            TableSection(title="Detail", dataset=ds),
        ]))
    """
    sections: list[ReportSection] = field(default_factory=list)
    widths: Optional[list[float]] = None   # relative column weights (HTML only)

    def __post_init__(self):
        self.section_type = SectionType.ROW

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        d["sections"] = [s.to_manifest_dict() for s in self.sections]
        return d


# ─────────────────────────────────────────────────────────────
# Report manifest
# ─────────────────────────────────────────────────────────────

@dataclass
class ReportManifest:
    """
    A complete audit record produced when a report is rendered.

    This is what makes every TraceBi report traceable. The manifest
    records the report name, run timestamp, all section definitions,
    and the full data lineage of every DataSet used.
    """
    report_name: str
    rendered_at: str
    rendered_by: str
    format: str
    output_path: str
    sections: list[dict]
    parameters: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "report_name": self.report_name,
            "rendered_at": self.rendered_at,
            "rendered_by": self.rendered_by,
            "format": self.format,
            "output_path": self.output_path,
            "parameters": self.parameters,
            "sections": self.sections,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())


# ─────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────

class Report:
    """
    A code-defined, renderer-agnostic report.

    Usage:
        from tracebi.reports import Report, TableSection, TextSection, ChartSection

        report = (
            Report("Monthly Sales Summary")
            .author("Data Team")
            .description("Top-line revenue and order metrics for the month.")
            .parameter("month", "2024-01")
            .add(TextSection(
                title="Executive Summary",
                content="Revenue was up 12% vs prior month, driven by Widget A.",
                style="heading1",
            ))
            .add(TableSection(
                title="Orders by Region",
                dataset=orders_by_region_ds,
                columns=["region", "orders", "revenue"],
                column_labels={"revenue": "Revenue ($)"},
                totals=["orders", "revenue"],
                number_formats={"revenue": "{:,.2f}"},
            ))
            .add(ChartSection(
                title="Revenue Trend",
                dataset=trend_ds,
                chart_type="line",
                x="month",
                y="revenue",
            ))
        )

        # Render to Excel
        from tracebi.reports import ExcelRenderer
        ExcelRenderer().render(report, "output/monthly_sales.xlsx")

        # Render to HTML
        from tracebi.reports import HTMLRenderer
        HTMLRenderer().render(report, "output/monthly_sales.html")
    """

    def __init__(self, name: str):
        self.name = name
        self._author: str = ""
        self._description: str = ""
        self._parameters: dict[str, Any] = {}
        self._sections: list[ReportSection] = []
        self._logo_path: Optional[str] = None
        self._created_at = datetime.now(timezone.utc).isoformat()

    # ── Fluent builder ─────────────────────────────────────────

    def author(self, author: str) -> Report:
        self._author = author
        return self

    def description(self, description: str) -> Report:
        self._description = description
        return self

    def parameter(self, key: str, value: Any) -> Report:
        """Record a named parameter (e.g. date range, filter values)."""
        self._parameters[key] = value
        return self

    def logo(self, path: str) -> Report:
        """Path to a logo image file (used by HTML/PDF renderers)."""
        self._logo_path = path
        return self

    def add(self, section: ReportSection) -> Report:
        """Append a section to the report."""
        self._sections.append(section)
        return self

    def text(self, content: str, title: Optional[str] = None, style: str = "normal") -> Report:
        """Shortcut to add a TextSection."""
        return self.add(TextSection(title=title, content=content, style=style))

    def table(self, dataset: DataSet, title: Optional[str] = None, **kwargs) -> Report:
        """Shortcut to add a TableSection."""
        return self.add(TableSection(title=title, dataset=dataset, **kwargs))

    def chart(self, dataset: DataSet, chart_type: str = "bar",
              x: Optional[str] = None, y=None,
              title: Optional[str] = None, **kwargs) -> Report:
        """Shortcut to add a ChartSection."""
        return self.add(ChartSection(
            title=title, dataset=dataset,
            chart_type=chart_type, x=x, y=y, **kwargs
        ))

    def spacer(self, height: int = 1) -> Report:
        """Shortcut to add a SpacerSection."""
        return self.add(SpacerSection(height=height))

    def metrics(self, metrics: list[Metric], title: Optional[str] = None) -> Report:
        """Shortcut to add a MetricSection (row of KPI cards)."""
        return self.add(MetricSection(title=title, metrics=metrics))

    def row(self, *sections: ReportSection, title: Optional[str] = None,
            widths: Optional[list[float]] = None) -> Report:
        """Shortcut to add a RowSection (children rendered side by side)."""
        return self.add(RowSection(title=title, sections=list(sections), widths=widths))

    # ── Inspection ─────────────────────────────────────────────

    @property
    def sections(self) -> list[ReportSection]:
        return list(self._sections)

    def data_sections(self) -> list[ReportSection]:
        """All leaf sections in order, descending into RowSection containers.

        Use this when walking the report for datasets/lineage so sections
        nested inside layout rows are not missed.
        """
        out: list[ReportSection] = []
        for s in self._sections:
            if isinstance(s, RowSection):
                out.extend(s.sections)
            else:
                out.append(s)
        return out

    def build_manifest(self, format: str, output_path: str) -> ReportManifest:
        """Build the audit manifest for a render run."""
        return ReportManifest(
            report_name=self.name,
            rendered_at=datetime.now(timezone.utc).isoformat(),
            rendered_by=self._author or "unknown",
            format=format,
            output_path=output_path,
            sections=[s.to_manifest_dict() for s in self._sections],
            parameters=self._parameters,
        )

    def describe(self) -> None:
        print(f"\n{'='*55}")
        print(f"  Report: '{self.name}'")
        if self._author:
            print(f"  Author: {self._author}")
        if self._description:
            print(f"  {self._description}")
        if self._parameters:
            print(f"  Parameters: {self._parameters}")
        print(f"  Sections ({len(self._sections)}):")
        for i, s in enumerate(self._sections, 1):
            label = f"[{s.section_type.value.upper()}]"
            print(f"    {i}. {label} {s.title or '(untitled)'}")
        print(f"{'='*55}\n")

    def __repr__(self) -> str:
        return (
            f"<Report name={self.name!r} "
            f"sections={len(self._sections)} "
            f"author={self._author!r}>"
        )
