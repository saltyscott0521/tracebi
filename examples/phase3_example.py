"""
TraceBi — Phase 3 Example
=========================
Demonstrates the Dashboard server: panels, associative filters,
and the DashboardServer that wires it all into a live Dash app.

The example uses MemoryConnector so no external files or databases
are needed — just run it and open http://localhost:8050/

Run with:
    pip install 'dash>=2.14' plotly
    python examples/phase3_example.py
"""

import pandas as pd
from tracebi import DataModel, MemoryConnector
from tracebi.dashboard import (
    Dashboard,
    DashboardServer,
    TablePanel,
    ChartPanel,
    MetricPanel,
    FilterPanel,
)


# ── Sample data ───────────────────────────────────────────────────────────────

orders_df = pd.DataFrame({
    "order_id":  [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "region":    ["North East", "South East", "Midwest", "West",
                  "North East", "Midwest", "South East", "West",
                  "North East", "Midwest"],
    "product":   ["Widget A", "Widget B", "Gadget X", "Widget A",
                  "Gadget X", "Widget B", "Widget A", "Gadget X",
                  "Widget B", "Widget A"],
    "qty":       [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
    "revenue":   [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                  14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
    "status":    ["shipped", "shipped", "open", "shipped", "open",
                  "shipped", "shipped", "open", "shipped", "open"],
})

trend_df = pd.DataFrame({
    "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "revenue": [28000, 31500, 29800, 34200, 38100, 39145],
    "orders":  [95, 108, 101, 119, 131, 138],
})


# ── DataModel ─────────────────────────────────────────────────────────────────

connector = MemoryConnector("mem", tables={
    "orders": orders_df,
    "trend":  trend_df,
})

model = DataModel("SalesDashboardModel")
model.add_connector(connector)
model.add_table("orders", connector="mem", source="orders")
model.add_table("trend",  connector="mem", source="trend")


# ── Dashboard definition ──────────────────────────────────────────────────────

dashboard = (
    Dashboard("Q2 Sales Dashboard")
    .description("Live view of Q2 revenue, order metrics, and regional breakdown.")
    .columns(2)

    # ── Filters (associative: selecting a region updates ALL panels) ──────
    .add_filter(FilterPanel(
        panel_id="region-filter",
        label="Region",
        column="region",
        table_name="orders",
        multi=True,
        placeholder="All regions",
    ))
    .add_filter(FilterPanel(
        panel_id="product-filter",
        label="Product",
        column="product",
        table_name="orders",
        placeholder="All products",
    ))

    # ── Row 1: KPI cards (full-width grid of 4, override columns) ─────────
    .add_panel(MetricPanel(
        panel_id="total-revenue",
        title="Total Revenue",
        table_name="orders",
        column="revenue",
        aggregation="sum",
        prefix="$",
        number_format="{:,.0f}",
    ))
    .add_panel(MetricPanel(
        panel_id="total-orders",
        title="Total Orders",
        table_name="orders",
        column="order_id",
        aggregation="count",
        number_format="{:,.0f}",
    ))

    # ── Row 2: Charts ─────────────────────────────────────────────────────
    .add_panel(ChartPanel(
        panel_id="revenue-by-region",
        title="Revenue by Region",
        table_name="orders",
        chart_type="bar",
        x="region",
        y="revenue",
        transform_fn=lambda ds: ds.transform(
            lambda df: df.groupby("region", as_index=False)["revenue"].sum(),
            description="Aggregate revenue by region",
        ),
        ylabel="Revenue (USD)",
        height=300,
    ))
    .add_panel(ChartPanel(
        panel_id="revenue-by-product",
        title="Revenue by Product",
        table_name="orders",
        chart_type="pie",
        x="product",
        y="revenue",
        transform_fn=lambda ds: ds.transform(
            lambda df: df.groupby("product", as_index=False)["revenue"].sum(),
            description="Aggregate revenue by product",
        ),
        height=300,
    ))

    # ── Row 3: Order detail table (spans both columns) ────────────────────
    .add_panel(TablePanel(
        panel_id="orders-table",
        title="Order Detail",
        table_name="orders",
        columns=["order_id", "region", "product", "qty", "revenue", "status"],
        column_labels={"order_id": "Order #", "qty": "Units", "revenue": "Revenue ($)"},
        page_size=8,
        width=2,
    ))
)


# ── Server ────────────────────────────────────────────────────────────────────

def run(port: int = 8050, mode: str = "auto"):
    """
    Start the dashboard.

    Args:
        port: Port to serve on (default 8050).
        mode: ``'auto'`` detects Jupyter automatically.
              ``'inline'`` forces Jupyter inline rendering.
              ``'external'`` opens a browser tab (works in both terminal and Jupyter).
              ``'terminal'`` always uses the blocking Dash dev server.
    """
    dashboard.describe()
    server = DashboardServer(dashboard, model=model)

    in_jupyter = _is_jupyter()

    if mode == "auto":
        mode = "inline" if in_jupyter else "terminal"

    if mode in ("inline", "external") or (mode == "auto" and in_jupyter):
        try:
            from jupyter_dash import JupyterDash
        except ImportError:
            raise ImportError(
                "jupyter-dash is required for notebook rendering.\n"
                "Install with: pip install jupyter-dash"
            )
        app = server.get_app()
        # Re-configure as a JupyterDash app
        app.__class__ = JupyterDash
        print(f"\n  TraceBi Dashboard — '{dashboard.title}'")
        print(f"  Running at http://localhost:{port}/\n")
        app.run(mode=mode, port=port)
    else:
        server.run(port=port, debug=True)


def _is_jupyter() -> bool:
    """Return True when running inside a Jupyter kernel."""
    try:
        shell = get_ipython().__class__.__name__  # noqa: F821
        return shell in ("ZMQInteractiveShell", "google.colab._shell")
    except NameError:
        return False


if __name__ == "__main__":
    run()
