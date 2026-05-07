"""
Tests for TraceBi Phase 3: Dashboard Server
"""

import pytest
import pandas as pd

from tracebi import DataModel, MemoryConnector, DataSet, LineageNode
from tracebi.dashboard.panels import TablePanel, ChartPanel, MetricPanel, FilterPanel
from tracebi.dashboard.dashboard import Dashboard


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_ds(name: str = "orders") -> DataSet:
    df = pd.DataFrame({
        "region":  ["North", "South", "East", "West", "North"],
        "product": ["Widget A", "Widget B", "Widget A", "Gadget X", "Gadget X"],
        "revenue": [1000.0, 2000.0, 1500.0, 500.0, 3000.0],
        "qty":     [10, 20, 15, 5, 30],
        "status":  ["shipped", "open", "shipped", "shipped", "open"],
    })
    node = LineageNode(
        operation="load",
        description=f"Load {name}",
        connector={"connector_name": "test", "connector_type": "MemoryConnector"},
        source=f"{name}.csv",
    )
    return DataSet(df=df, name=name, lineage=[node])


def make_model() -> DataModel:
    df = pd.DataFrame({
        "region":  ["North", "South", "East", "West", "North"],
        "product": ["Widget A", "Widget B", "Widget A", "Gadget X", "Gadget X"],
        "revenue": [1000.0, 2000.0, 1500.0, 500.0, 3000.0],
        "qty":     [10, 20, 15, 5, 30],
    })
    connector = MemoryConnector("mem", {"orders": df})
    model = DataModel("TestModel")
    model.add_connector(connector)
    model.add_table("orders", connector="mem", source="orders")
    return model


# ─────────────────────────────────────────────
# Panel construction
# ─────────────────────────────────────────────

class TestPanelConstruction:

    def test_table_panel_defaults(self):
        ds = make_ds()
        p = TablePanel(panel_id="t1", title="Test", dataset=ds)
        assert p.panel_id == "t1"
        assert p.title == "Test"
        assert p.page_size == 10
        assert p.columns is None
        assert p.column_labels is None

    def test_chart_panel_defaults(self):
        ds = make_ds()
        p = ChartPanel(panel_id="c1", title="Chart", dataset=ds,
                       chart_type="bar", x="region", y="revenue")
        assert p.chart_type == "bar"
        assert p.x == "region"
        assert p.y == "revenue"
        assert p.height == 350

    def test_metric_panel_defaults(self):
        ds = make_ds()
        p = MetricPanel(panel_id="m1", title="KPI", dataset=ds,
                        column="revenue", aggregation="sum")
        assert p.aggregation == "sum"
        assert p.number_format == "{:,.0f}"
        assert p.prefix == ""
        assert p.suffix == ""

    def test_filter_panel(self):
        ds = make_ds()
        fp = FilterPanel(panel_id="f1", label="Region", column="region", dataset=ds)
        assert fp.column == "region"
        assert fp.multi is False
        assert fp.placeholder == "All"

    def test_panel_with_transform(self):
        ds = make_ds()
        fn = lambda d: d.filter("status == 'shipped'")
        p = ChartPanel(panel_id="c1", dataset=ds, transform_fn=fn,
                       chart_type="bar", x="region", y="revenue")
        assert p.transform_fn is fn


# ─────────────────────────────────────────────
# Dashboard builder
# ─────────────────────────────────────────────

class TestDashboard:

    def test_fluent_builder(self):
        ds = make_ds()
        dashboard = (
            Dashboard("Test Dashboard")
            .description("A test dashboard")
            .columns(3)
            .add_filter(FilterPanel("f1", "Region", "region", dataset=ds))
            .add_panel(MetricPanel("m1", "Revenue", dataset=ds,
                                   column="revenue", aggregation="sum"))
            .add_panel(ChartPanel("c1", "Chart", dataset=ds,
                                  chart_type="bar", x="region", y="revenue"))
            .add_panel(TablePanel("t1", "Table", dataset=ds))
        )
        assert dashboard.title == "Test Dashboard"
        assert dashboard._description == "A test dashboard"
        assert dashboard._columns == 3
        assert len(dashboard._filters) == 1
        assert len(dashboard._panels) == 3

    def test_shortcut_methods(self):
        ds = make_ds()
        d = (
            Dashboard("D")
            .filter("f1", "Region", "region", dataset=ds)
            .metric("m1", "Revenue", dataset=ds, column="revenue")
            .chart("c1", "Chart", dataset=ds, chart_type="bar", x="region", y="revenue")
            .table("t1", "Table", dataset=ds)
        )
        assert len(d._filters) == 1
        assert len(d._panels) == 3

    def test_describe(self, capsys):
        ds = make_ds()
        d = (
            Dashboard("My Dashboard")
            .add_panel(TablePanel("t1", "Orders", dataset=ds))
        )
        d.describe()
        out = capsys.readouterr().out
        assert "My Dashboard" in out
        assert "t1" in out

    def test_repr(self):
        d = Dashboard("D")
        r = repr(d)
        assert "Dashboard" in r
        assert "D" in r


# ─────────────────────────────────────────────
# DashboardServer — no running server needed
# ─────────────────────────────────────────────

dash = pytest.importorskip("dash", reason="dash not installed")


class TestDashboardServer:

    def _make_server(self, use_model=False):
        from tracebi.dashboard import DashboardServer
        ds = make_ds()
        if use_model:
            model = make_model()
            dashboard = (
                Dashboard("Test")
                .add_filter(FilterPanel("f1", "Region", "region", table_name="orders"))
                .add_panel(MetricPanel("m1", "Revenue", table_name="orders",
                                       column="revenue", aggregation="sum"))
                .add_panel(ChartPanel("c1", "Chart", table_name="orders",
                                      chart_type="bar", x="region", y="revenue"))
                .add_panel(TablePanel("t1", "Table", table_name="orders"))
            )
            return DashboardServer(dashboard, model=model)
        else:
            dashboard = (
                Dashboard("Test")
                .add_filter(FilterPanel("f1", "Region", "region", dataset=ds))
                .add_panel(MetricPanel("m1", "Revenue", dataset=ds,
                                       column="revenue", aggregation="sum"))
                .add_panel(ChartPanel("c1", "Chart", dataset=ds,
                                      chart_type="bar", x="region", y="revenue"))
                .add_panel(TablePanel("t1", "Table", dataset=ds))
            )
            return DashboardServer(dashboard)

    def test_get_app_returns_dash_app(self):
        from tracebi.dashboard import DashboardServer
        server = self._make_server()
        app = server.get_app()
        assert app is not None

    def test_get_app_with_model(self):
        from tracebi.dashboard import DashboardServer
        server = self._make_server(use_model=True)
        app = server.get_app()
        assert app is not None

    def test_filter_options_with_dataset(self):
        from tracebi.dashboard import DashboardServer
        ds = make_ds()
        fp = FilterPanel("f1", "Region", "region", dataset=ds)
        dashboard = Dashboard("T").add_filter(fp)
        server = DashboardServer(dashboard)
        options = server._get_filter_options(fp)
        assert len(options) == 4  # North, South, East, West (sorted unique)
        labels = [o["label"] for o in options]
        assert "North" in labels

    def test_filter_options_with_model(self):
        from tracebi.dashboard import DashboardServer
        model = make_model()
        fp = FilterPanel("f1", "Region", "region", table_name="orders")
        dashboard = Dashboard("T").add_filter(fp)
        server = DashboardServer(dashboard, model=model)
        options = server._get_filter_options(fp)
        assert len(options) == 4


# ─────────────────────────────────────────────
# Filter application
# ─────────────────────────────────────────────

class TestFilterApplication:

    def _make_server(self):
        from tracebi.dashboard import DashboardServer
        dashboard = Dashboard("T")
        return DashboardServer(dashboard)

    def test_apply_filter_string_equality(self):
        from tracebi.dashboard import DashboardServer
        server = DashboardServer(Dashboard("T"))
        ds = make_ds()
        filtered = server._apply_filter(ds, "region", "North")
        assert len(filtered) == 2
        assert all(filtered.to_pandas()["region"] == "North")
        assert filtered.lineage[-1].operation == "filter"

    def test_apply_filter_list(self):
        from tracebi.dashboard import DashboardServer
        server = DashboardServer(Dashboard("T"))
        ds = make_ds()
        filtered = server._apply_filter(ds, "region", ["North", "South"])
        assert len(filtered) == 3

    def test_apply_filter_missing_column_is_noop(self):
        from tracebi.dashboard import DashboardServer
        server = DashboardServer(Dashboard("T"))
        ds = make_ds()
        result = server._apply_filter(ds, "nonexistent_col", "X")
        assert len(result) == len(ds)

    def test_apply_filter_none_value_is_noop(self):
        """None filter value (cleared dropdown) must not be applied."""
        from tracebi.dashboard import DashboardServer
        ds = make_ds()
        dashboard = (
            Dashboard("T")
            .add_filter(FilterPanel("f1", "Region", "region", dataset=ds))
            .add_panel(MetricPanel("m1", "Rev", dataset=ds, column="revenue"))
        )
        server = DashboardServer(dashboard)
        # Pass None as the filter value (filter cleared by user)
        result_ds = server._get_panel_data(dashboard._panels[0], (None,))
        assert len(result_ds) == len(ds)  # unfiltered


# ─────────────────────────────────────────────
# Metric rendering
# ─────────────────────────────────────────────

class TestMetricRendering:

    def _server(self):
        from tracebi.dashboard import DashboardServer
        return DashboardServer(Dashboard("T"))

    def test_sum(self):
        server = self._server()
        ds = make_ds()
        panel = MetricPanel("m1", "Total", dataset=ds, column="revenue",
                             aggregation="sum")
        val = server._render_metric_value(panel, ds)
        assert "8,000" in val  # 1000+2000+1500+500+3000 = 8000

    def test_count(self):
        server = self._server()
        ds = make_ds()
        panel = MetricPanel("m1", "Count", dataset=ds, column="revenue",
                             aggregation="count")
        val = server._render_metric_value(panel, ds)
        assert "5" in val

    def test_mean(self):
        server = self._server()
        ds = make_ds()
        panel = MetricPanel("m1", "Avg", dataset=ds, column="revenue",
                             aggregation="mean", number_format="{:,.0f}")
        val = server._render_metric_value(panel, ds)
        assert "1,600" in val  # 8000/5

    def test_prefix_suffix(self):
        server = self._server()
        ds = make_ds()
        panel = MetricPanel("m1", "Rev", dataset=ds, column="revenue",
                             aggregation="sum", prefix="$", suffix=" USD")
        val = server._render_metric_value(panel, ds)
        assert val.startswith("$")
        assert val.endswith(" USD")

    def test_empty_df(self):
        from tracebi.dashboard import DashboardServer
        server = DashboardServer(Dashboard("T"))
        empty_ds = DataSet(df=pd.DataFrame({"revenue": []}), name="empty",
                           lineage=[LineageNode("load")])
        panel = MetricPanel("m1", "Rev", dataset=empty_ds, column="revenue")
        val = server._render_metric_value(panel, empty_ds)
        assert val == "—"


# ─────────────────────────────────────────────
# Figure generation
# ─────────────────────────────────────────────

plotly = pytest.importorskip("plotly", reason="plotly not installed")


class TestFigureGeneration:

    def _server(self):
        from tracebi.dashboard import DashboardServer
        return DashboardServer(Dashboard("T"))

    def test_bar_chart(self):
        server = self._server()
        ds = make_ds()
        panel = ChartPanel("c1", "Bar", dataset=ds,
                           chart_type="bar", x="region", y="revenue")
        fig = server._make_figure(panel, ds)
        assert fig is not None
        assert hasattr(fig, "data")

    def test_line_chart(self):
        server = self._server()
        df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "revenue": [100, 200, 150]})
        ds = DataSet(df=df, name="trend", lineage=[LineageNode("load")])
        panel = ChartPanel("c1", "Line", dataset=ds,
                           chart_type="line", x="month", y="revenue")
        fig = server._make_figure(panel, ds)
        assert fig is not None

    def test_pie_chart(self):
        server = self._server()
        ds = make_ds()
        panel = ChartPanel("c1", "Pie", dataset=ds,
                           chart_type="pie", x="region", y="revenue")
        fig = server._make_figure(panel, ds)
        assert fig is not None

    def test_empty_df_returns_empty_figure(self):
        server = self._server()
        empty_df = pd.DataFrame({"region": [], "revenue": []})
        empty_ds = DataSet(df=empty_df, name="empty", lineage=[LineageNode("load")])
        panel = ChartPanel("c1", "Empty", dataset=empty_ds,
                           chart_type="bar", x="region", y="revenue")
        fig = server._make_figure(panel, empty_ds)
        assert fig is not None  # returns an empty figure, not an error

    def test_chart_layout_colors(self):
        server = self._server()
        ds = make_ds()
        panel = ChartPanel("c1", "Chart", dataset=ds,
                           chart_type="bar", x="region", y="revenue")
        fig = server._make_figure(panel, ds)
        assert fig.layout.plot_bgcolor == "#ffffff"

    def test_chart_with_transform(self):
        server = self._server()
        ds = make_ds()
        panel = ChartPanel(
            panel_id="c1",
            title="Aggregated",
            dataset=ds,
            chart_type="bar",
            x="region",
            y="revenue",
            transform_fn=lambda d: d.transform(
                lambda df: df.groupby("region", as_index=False)["revenue"].sum(),
                description="Sum by region",
            ),
        )
        # Simulate _get_panel_data then _make_figure
        result_ds = server._get_panel_data(panel, ())
        fig = server._make_figure(panel, result_ds)
        assert fig is not None
