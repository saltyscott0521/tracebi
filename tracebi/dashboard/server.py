"""
DashboardServer — wires a Dashboard definition into a live Dash application.

Key behaviours
--------------
* Associative filtering: selecting a value in any FilterPanel re-renders
  every data panel whose dataset contains the filtered column — exactly
  the Qlik-style behaviour described in the README.
* Every data refresh calls DataModel.load() (when table_name is used),
  so lineage is tracked on every render.
* Panels that provide a pre-built DataSet apply filters on top of that
  DataSet without re-reading from the source.
* Dev mode with hot-reload is enabled by passing ``debug=True`` to run().

Requires: pip install dash>=2.14 plotly>=5.0
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from tracebi.dashboard.dashboard import Dashboard
from tracebi.dashboard.panels import (
    _BasePanel, TablePanel, ChartPanel, MetricPanel, FilterPanel,
)
from tracebi.model.dataset import DataSet, LineageNode


# TraceBi colour palette — mirrors html_renderer.py
_COLORS = {
    "navy":      "#1F3864",
    "blue":      "#2E74B5",
    "light_bg":  "#EBF0F7",
    "page_bg":   "#f5f7fa",
    "card_bg":   "#ffffff",
    "border":    "#dde4ef",
    "text":      "#1a1a2e",
    "muted":     "#666666",
}

_CHART_PALETTE = [
    "#2E74B5", "#ED7D31", "#A9D18E", "#FFC000",
    "#5B9BD5", "#70AD47", "#FF0000", "#7030A0",
]


class DashboardServer:
    """
    Wraps a Dashboard definition and serves it as a Dash web application.

    Usage:
        from tracebi.dashboard import Dashboard, DashboardServer, ChartPanel, FilterPanel

        dashboard = (
            Dashboard("Sales Dashboard")
            .add_filter(FilterPanel("region-filter", "Region", "region", dataset=orders_ds))
            .add_panel(ChartPanel("rev-chart", "Revenue by Region",
                                  dataset=orders_ds, chart_type="bar",
                                  x="region", y="revenue"))
        )

        server = DashboardServer(dashboard)
        server.run(port=8050, debug=True)

    Args:
        dashboard: A Dashboard instance built with the fluent API.
        model:     Optional DataModel. Required when any panel uses
                   ``table_name`` instead of a pre-built ``dataset``.
    """

    def __init__(
        self,
        dashboard: Dashboard,
        model=None,  # tracebi.model.data_model.DataModel — optional
    ) -> None:
        self.dashboard = dashboard
        self.model = model
        self._app = None

    # ── Public API ─────────────────────────────────────────────────────────

    def run(self, port: int = 8050, debug: bool = False) -> None:
        """
        Start the Dash development server.

        Args:
            port:  TCP port to listen on (default 8050).
            debug: Enable Dash hot-reload and debug overlay (default False).
        """
        app = self._build_app()
        print(f"\n  TraceBi Dashboard — '{self.dashboard.title}'")
        print(f"  Running at http://localhost:{port}/\n")
        app.run(debug=debug, port=port)

    def get_app(self):
        """Return the underlying Dash app object (useful for testing / WSGI)."""
        return self._build_app()

    # ── App construction ───────────────────────────────────────────────────

    def _build_app(self):
        try:
            import dash
            from dash import Dash, html, dcc
        except ImportError:
            raise ImportError(
                "dash is required for DashboardServer.\n"
                "Install with: pip install 'dash>=2.14'"
            )

        app = Dash(
            __name__,
            title=self.dashboard.title,
            suppress_callback_exceptions=True,
        )
        app.layout = self._build_layout(app)
        self._register_callbacks(app)
        return app

    # ── Layout ─────────────────────────────────────────────────────────────

    def _build_layout(self, app):
        from dash import html, dcc

        header = self._build_header()
        filter_row = self._build_filter_row()
        panel_grid = self._build_panel_grid()

        return html.Div(
            [
                # Init store — triggers initial render when there are no filters
                dcc.Store(id="tracebi-init-store", data=0),
                header,
                filter_row,
                html.Div(panel_grid, style={"padding": "0 24px 40px 24px"}),
            ],
            style={
                "fontFamily": "Segoe UI, Calibri, Arial, sans-serif",
                "background":  _COLORS["page_bg"],
                "minHeight":   "100vh",
            },
        )

    def _build_header(self):
        from dash import html

        children = [
            html.H1(
                self.dashboard.title,
                style={
                    "color":        "#ffffff",
                    "margin":       0,
                    "fontSize":     26,
                    "fontWeight":   700,
                    "letterSpacing": "0.3px",
                },
            )
        ]
        if self.dashboard._description:
            children.append(
                html.P(
                    self.dashboard._description,
                    style={"color": "#cde4f7", "margin": "4px 0 0 0", "fontSize": 13},
                )
            )

        return html.Div(
            children,
            style={
                "background": f"linear-gradient(135deg, {_COLORS['navy']} 0%, {_COLORS['blue']} 100%)",
                "padding":    "20px 32px",
                "marginBottom": 0,
            },
        )

    def _build_filter_row(self):
        from dash import html, dcc

        if not self.dashboard._filters:
            return html.Div()

        controls = []
        for fp in self.dashboard._filters:
            options = self._get_filter_options(fp)
            controls.append(
                html.Div(
                    [
                        html.Label(
                            fp.label,
                            style={
                                "fontWeight":   600,
                                "fontSize":     12,
                                "color":        _COLORS["muted"],
                                "textTransform": "uppercase",
                                "letterSpacing": "0.4px",
                                "display":      "block",
                                "marginBottom": 4,
                            },
                        ),
                        dcc.Dropdown(
                            id=f"filter-{fp.panel_id}",
                            options=options,
                            placeholder=fp.placeholder,
                            multi=fp.multi,
                            clearable=True,
                            style={"minWidth": 180, "fontSize": 13},
                        ),
                    ],
                    style={"marginRight": 16, "minWidth": 200},
                )
            )

        return html.Div(
            controls,
            style={
                "display":        "flex",
                "flexWrap":       "wrap",
                "alignItems":     "flex-end",
                "gap":            "12px",
                "padding":        "16px 24px",
                "background":     "#ffffff",
                "borderBottom":   f"1px solid {_COLORS['border']}",
                "borderTop":      f"1px solid {_COLORS['border']}",
                "marginBottom":   "24px",
            },
        )

    def _build_panel_grid(self):
        from dash import html

        col_count = self.dashboard._columns
        panel_components = [self._build_panel_shell(p) for p in self.dashboard._panels]

        rows = []
        for i in range(0, len(panel_components), col_count):
            chunk = panel_components[i : i + col_count]
            rows.append(
                html.Div(
                    chunk,
                    style={
                        "display":               "grid",
                        "gridTemplateColumns":   f"repeat({col_count}, 1fr)",
                        "gap":                   "20px",
                        "marginBottom":          "20px",
                    },
                )
            )
        return rows

    def _build_panel_shell(self, panel: _BasePanel):
        """Build the static HTML shell (card) for a panel; content filled by callback."""
        from dash import html, dcc, dash_table

        card_style = {
            "background":    _COLORS["card_bg"],
            "borderRadius":  "6px",
            "boxShadow":     "0 2px 8px rgba(0,0,0,0.07)",
            "padding":       "16px 20px",
            "border":        f"1px solid {_COLORS['border']}",
        }
        title_style = {
            "color":        _COLORS["navy"],
            "fontSize":     13,
            "fontWeight":   600,
            "margin":       "0 0 12px 0",
            "paddingBottom": "8px",
            "borderBottom": f"2px solid {_COLORS['light_bg']}",
        }

        if isinstance(panel, ChartPanel):
            return html.Div(
                [
                    html.H4(panel.title or "", style=title_style),
                    dcc.Graph(
                        id=f"panel-{panel.panel_id}",
                        config={"displayModeBar": False},
                        style={"height": panel.height},
                    ),
                ],
                style=card_style,
            )

        if isinstance(panel, TablePanel):
            return html.Div(
                [
                    html.H4(panel.title or "", style=title_style),
                    dash_table.DataTable(
                        id=f"panel-{panel.panel_id}",
                        page_size=panel.page_size,
                        page_action="native",
                        sort_action="native",
                        style_table={"overflowX": "auto"},
                        style_header={
                            "backgroundColor": _COLORS["navy"],
                            "color":           "white",
                            "fontWeight":      "bold",
                            "fontSize":        11,
                            "padding":         "9px 12px",
                            "border":          "none",
                        },
                        style_cell={
                            "padding":     "7px 12px",
                            "fontSize":    12,
                            "fontFamily":  "Segoe UI, Calibri, Arial, sans-serif",
                            "border":      f"1px solid {_COLORS['border']}",
                            "color":       _COLORS["text"],
                        },
                        style_data_conditional=[
                            {
                                "if": {"row_index": "odd"},
                                "backgroundColor": _COLORS["light_bg"],
                            }
                        ],
                    ),
                ],
                style=card_style,
            )

        if isinstance(panel, MetricPanel):
            return html.Div(
                [
                    html.Div(
                        panel.title or "",
                        style={
                            "color":         _COLORS["muted"],
                            "fontSize":      11,
                            "fontWeight":    600,
                            "textTransform": "uppercase",
                            "letterSpacing": "0.5px",
                            "marginBottom":  10,
                        },
                    ),
                    html.Div(
                        id=f"panel-{panel.panel_id}",
                        children="—",
                        style={
                            "fontSize":   34,
                            "fontWeight": 700,
                            "color":      _COLORS["navy"],
                        },
                    ),
                ],
                style={
                    **card_style,
                    "textAlign": "center",
                    "padding":   "28px 20px",
                },
            )

        return html.Div()

    # ── Callbacks ──────────────────────────────────────────────────────────

    def _register_callbacks(self, app) -> None:
        from dash import Input, Output

        # Build the list of filter inputs (always include init-store for initial load)
        filter_inputs = [Input("tracebi-init-store", "data")] + [
            Input(f"filter-{fp.panel_id}", "value")
            for fp in self.dashboard._filters
        ]

        for panel in self.dashboard._panels:
            self._register_panel_callback(app, panel, filter_inputs)

    def _register_panel_callback(self, app, panel: _BasePanel, filter_inputs) -> None:
        from dash import Input, Output

        if isinstance(panel, ChartPanel):
            self._register_chart_callback(app, panel, filter_inputs)
        elif isinstance(panel, TablePanel):
            self._register_table_callback(app, panel, filter_inputs)
        elif isinstance(panel, MetricPanel):
            self._register_metric_callback(app, panel, filter_inputs)

    def _register_chart_callback(self, app, panel: ChartPanel, filter_inputs) -> None:
        from dash import Output

        server = self  # capture for closure

        @app.callback(
            Output(f"panel-{panel.panel_id}", "figure"),
            filter_inputs,
        )
        def update_chart(*args, _panel=panel):
            filter_values = args[1:]  # skip init-store value
            ds = server._get_panel_data(_panel, filter_values)
            return server._make_figure(_panel, ds)

    def _register_table_callback(self, app, panel: TablePanel, filter_inputs) -> None:
        from dash import Output

        server = self

        @app.callback(
            [
                Output(f"panel-{panel.panel_id}", "data"),
                Output(f"panel-{panel.panel_id}", "columns"),
            ],
            filter_inputs,
        )
        def update_table(*args, _panel=panel):
            filter_values = args[1:]
            ds = server._get_panel_data(_panel, filter_values)
            df = ds.to_pandas()
            if _panel.columns:
                df = df[[c for c in _panel.columns if c in df.columns]]
            if _panel.column_labels:
                df = df.rename(columns=_panel.column_labels)
            if _panel.max_rows:
                df = df.head(_panel.max_rows)
            records = df.to_dict("records")
            columns = [{"name": str(c), "id": str(c)} for c in df.columns]
            return records, columns

    def _register_metric_callback(self, app, panel: MetricPanel, filter_inputs) -> None:
        from dash import Output

        server = self

        @app.callback(
            Output(f"panel-{panel.panel_id}", "children"),
            filter_inputs,
        )
        def update_metric(*args, _panel=panel):
            filter_values = args[1:]
            ds = server._get_panel_data(_panel, filter_values)
            return server._render_metric_value(_panel, ds)

    # ── Data helpers ───────────────────────────────────────────────────────

    def _get_panel_data(self, panel: _BasePanel, filter_values: tuple) -> DataSet:
        """Load data for a panel and apply all active filters."""
        # 1. Get base DataSet
        if panel.table_name and self.model is not None:
            ds = self.model.load(panel.table_name)
        elif panel.dataset is not None:
            ds = panel.dataset
        else:
            raise ValueError(
                f"Panel '{panel.panel_id}' has neither 'dataset' nor 'table_name'. "
                f"Provide one of them."
            )

        # 2. Apply panel-specific transform (e.g. aggregation)
        if panel.transform_fn is not None:
            ds = panel.transform_fn(ds)

        # 3. Apply associative filters
        filters = self.dashboard._filters
        for fp, val in zip(filters, filter_values):
            if val is None or val == [] or val == "":
                continue
            ds = self._apply_filter(ds, fp.column, val)

        return ds

    def _apply_filter(self, ds: DataSet, column: str, value: Any) -> DataSet:
        """Apply a single filter value to a DataSet if the column exists."""
        df = ds.to_pandas()
        if column not in df.columns:
            return ds  # column not present — skip (associative: no error)

        col_series = df[column]

        if isinstance(value, list):
            # Coerce types for numeric columns
            if pd.api.types.is_numeric_dtype(col_series):
                try:
                    value = [type(col_series.iloc[0])(v) for v in value if v is not None]
                except (ValueError, TypeError, IndexError):
                    pass
            mask = col_series.isin(value)
            desc = f"Filter {column} in [{', '.join(str(v) for v in value)}]"
        else:
            if pd.api.types.is_numeric_dtype(col_series):
                try:
                    value = type(col_series.iloc[0])(value)
                except (ValueError, TypeError, IndexError):
                    pass
            mask = col_series == value
            desc = f"Filter {column} = {value}"

        node = LineageNode(
            operation="filter",
            description=desc,
            metadata={"column": column, "value": value},
        )
        filtered_df = df[mask].reset_index(drop=True)
        return DataSet(df=filtered_df, name=ds.name, lineage=ds.lineage + [node])

    # ── Rendering helpers ──────────────────────────────────────────────────

    def _make_figure(self, panel: ChartPanel, ds: DataSet):
        """Build a Plotly figure from a ChartPanel and DataSet."""
        try:
            import plotly.express as px
            import plotly.graph_objects as go
        except ImportError:
            raise ImportError(
                "plotly is required for ChartPanel.\n"
                "Install with: pip install plotly"
            )

        df = ds.to_pandas()
        if df.empty:
            fig = go.Figure()
            fig.update_layout(
                title=panel.title or "",
                annotations=[{
                    "text":     "No data",
                    "xref":     "paper",
                    "yref":     "paper",
                    "showarrow": False,
                    "font":     {"size": 14, "color": _COLORS["muted"]},
                }],
            )
            return fig

        y_cols = (
            [panel.y] if isinstance(panel.y, str)
            else list(panel.y) if panel.y
            else []
        )
        chart_type = (panel.chart_type or "bar").lower()

        try:
            if chart_type == "bar":
                y_arg = y_cols[0] if len(y_cols) == 1 else y_cols
                fig = px.bar(
                    df, x=panel.x, y=y_arg, color=panel.color,
                    color_discrete_sequence=_CHART_PALETTE,
                )
            elif chart_type == "line":
                y_arg = y_cols[0] if len(y_cols) == 1 else y_cols
                fig = px.line(
                    df, x=panel.x, y=y_arg, color=panel.color,
                    color_discrete_sequence=_CHART_PALETTE,
                    markers=True,
                )
            elif chart_type == "area":
                y_arg = y_cols[0] if len(y_cols) == 1 else y_cols
                fig = px.area(
                    df, x=panel.x, y=y_arg, color=panel.color,
                    color_discrete_sequence=_CHART_PALETTE,
                )
            elif chart_type == "pie":
                fig = px.pie(
                    df,
                    names=panel.x,
                    values=y_cols[0] if y_cols else None,
                    color_discrete_sequence=_CHART_PALETTE,
                )
            elif chart_type == "scatter":
                fig = px.scatter(
                    df, x=panel.x, y=y_cols[0] if y_cols else None,
                    color=panel.color,
                    color_discrete_sequence=_CHART_PALETTE,
                )
            else:
                y_arg = y_cols[0] if y_cols else None
                fig = px.bar(
                    df, x=panel.x, y=y_arg,
                    color_discrete_sequence=_CHART_PALETTE,
                )
        except Exception as exc:
            fig = go.Figure()
            fig.add_annotation(
                text=f"Chart error: {exc}",
                xref="paper", yref="paper",
                showarrow=False,
                font={"color": "red"},
            )
            return fig

        fig.update_layout(
            title={
                "text":     panel.title or "",
                "font":     {"color": _COLORS["navy"], "size": 13},
                "x":        0,
                "xanchor":  "left",
                "pad":      {"l": 0},
            },
            plot_bgcolor=_COLORS["card_bg"],
            paper_bgcolor=_COLORS["card_bg"],
            font={
                "family": "Segoe UI, Calibri, Arial, sans-serif",
                "color":  _COLORS["text"],
                "size":   12,
            },
            margin={"l": 40, "r": 20, "t": 40, "b": 40},
            height=panel.height,
            xaxis_title=panel.xlabel or panel.x or "",
            yaxis_title=panel.ylabel or (y_cols[0] if len(y_cols) == 1 else ""),
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        )
        fig.update_xaxes(showgrid=False, linecolor=_COLORS["border"])
        fig.update_yaxes(gridcolor=_COLORS["light_bg"], linecolor=_COLORS["border"])

        return fig

    def _render_metric_value(self, panel: MetricPanel, ds: DataSet) -> str:
        """Compute the aggregated metric value and return a formatted string."""
        df = ds.to_pandas()
        if df.empty or panel.column not in df.columns:
            return "—"

        agg_fn = panel.aggregation.lower()
        try:
            if agg_fn == "sum":
                val = df[panel.column].sum()
            elif agg_fn == "mean":
                val = df[panel.column].mean()
            elif agg_fn == "count":
                val = df[panel.column].count()
            elif agg_fn == "min":
                val = df[panel.column].min()
            elif agg_fn == "max":
                val = df[panel.column].max()
            elif agg_fn == "median":
                val = df[panel.column].median()
            else:
                val = df[panel.column].agg(agg_fn)

            formatted = panel.number_format.format(val)
        except Exception:
            formatted = str(val) if "val" in dir() else "—"

        return f"{panel.prefix}{formatted}{panel.suffix}"

    def _get_filter_options(self, fp: FilterPanel) -> list[dict]:
        """Get sorted distinct values for a FilterPanel dropdown."""
        if fp.dataset is not None:
            df = fp.dataset.to_pandas()
        elif fp.table_name and self.model is not None:
            df = self.model.load(fp.table_name).to_pandas()
        else:
            return []

        if fp.column not in df.columns:
            return []

        values = sorted(df[fp.column].dropna().unique(), key=lambda v: str(v))
        return [{"label": str(v), "value": v} for v in values]
