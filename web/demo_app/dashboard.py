"""
Sales dashboard for the demo app.

Exports `dashboard_server` for registration in registry.py.
"""

from tracebi.dashboard import Dashboard, DashboardServer, FilterPanel, MetricPanel, ChartPanel, TablePanel
from tracebi.model_registry import get_model

model = get_model("sales_model")

sales_dashboard = (
    Dashboard("Sales Dashboard")
    .description("Live sales overview with associative region filter.")
    .columns(2)
    .add_filter(FilterPanel(
        "region-filter", label="Region", column="region", table_name="orders",
    ))
    .add_panel(MetricPanel(
        "total-revenue", title="Total Revenue",
        table_name="orders", column="revenue",
        aggregation="sum", prefix="$", number_format="{:,.0f}",
    ))
    .add_panel(MetricPanel(
        "total-orders", title="Total Orders",
        table_name="orders", column="order_id",
        aggregation="count", number_format="{:,.0f}",
    ))
    .add_panel(ChartPanel(
        "revenue-by-region", title="Revenue by Region",
        table_name="orders", chart_type="bar",
        x="region", y="revenue", ylabel="Revenue (USD)",
    ))
    .add_panel(ChartPanel(
        "revenue-trend", title="Revenue Trend",
        table_name="trend", chart_type="line",
        x="month", y=["revenue", "cost"], ylabel="USD",
    ))
    .add_panel(TablePanel(
        "orders-table", title="Orders",
        table_name="orders",
        columns=["order_id", "region", "product", "qty", "revenue", "status"],
        column_labels={"order_id": "Order #", "revenue": "Revenue ($)"},
    ))
)

dashboard_server = DashboardServer(sales_dashboard, model=model)
