"""
Analyst Demo Request
====================
Demonstrates KPI cards, side-by-side layout, heat maps,
conditional formatting, area charts, and value labels.

Run this script directly:
    python requests/analyst_demo.py

Or use the live preview loop (reloads in-browser on every save):
    tracebi dev analyst_demo

Or browse it in the web UI:
    http://localhost:8000  →  Requests  →  analyst_demo
"""

import os
import pandas as pd

from tracebi import DataModel, MemoryConnector, request_params
from tracebi.reports.report import (
    Report, TextSection, TableSection, ChartSection,
    Metric, MetricSection,
)
from tracebi.reports.html_renderer import HTMLRenderer
from tracebi.reports.excel_renderer import ExcelRenderer

# Override from the UI's Requests page or:
#   tracebi run analyst_demo --param status=open --param min_revenue=5000
params = request_params(status="shipped", min_revenue=0.0)


# ── Data ──────────────────────────────────────────────────────────────────────

orders_df = pd.DataFrame({
    "order_id":  list(range(1, 11)),
    "region":    ["North East", "South East", "Midwest", "West", "North East",
                  "Midwest", "South East", "West", "North East", "Midwest"],
    "product":   ["Widget A", "Widget B", "Gadget X", "Widget A", "Gadget X",
                  "Widget B", "Widget A", "Gadget X", "Widget B", "Widget A"],
    "qty":       [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
    "revenue":   [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                  14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
    "cost":      [2100.00, 2800.00, 14000.00, 1050.00, 6600.00,
                  10500.00, 700.00, 7700.00, 2200.00, 12600.00],
    "status":    ["shipped", "shipped", "open", "shipped", "open",
                  "shipped", "shipped", "open", "shipped", "open"],
    "variance":  [498.80, -350.85, 3998.00, -200.60, 1499.05,
                  1498.50, -300.40, 2998.90, 748.25, -1003.00],
})

region_targets_df = pd.DataFrame({
    "region": ["North East", "South East", "Midwest", "West"],
    "target": [15000.0, 9000.0, 30000.0, 11000.0],
})

trend_df = pd.DataFrame({
    "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "revenue": [28000, 31500, 29800, 34200, 38100, 39145],
    "cost":    [19600, 22050, 20860, 23940, 26670, 27400],
})

conn = MemoryConnector("demo", tables={
    "orders": orders_df,
    "trend": trend_df,
    "region_targets": region_targets_df,
})
model = DataModel("demo")
model.add_connector(conn)
model.add_table("orders", connector="demo", source="orders")
model.add_table("trend",  connector="demo", source="trend")
model.add_table("region_targets", connector="demo", source="region_targets")
model.connect()


# ── Transforms ────────────────────────────────────────────────────────────────

shipped = (
    model.load("orders")
    .filter(
        f"status == '{params['status']}' and revenue >= {params['min_revenue']}",
        description=f"{params['status']} orders ≥ {params['min_revenue']:,.0f}",
    )
    .assign(
        margin=lambda df: df["revenue"] - df["cost"],
        description="margin = revenue - cost",
    )
)

by_region = (
    shipped
    .aggregate(by="region",
               revenue="sum", margin="sum", orders=("order_id", "count"),
               description="Aggregate by region")
    .join(model.load("region_targets"), on="region", how="left")
    .assign(vs_target=lambda df: df["revenue"] - df["target"],
            description="vs_target = revenue - target")
    .sort("revenue", ascending=False)
)

variance_ds = (
    model.load("orders")
    .filter("status == 'shipped'", description="Shipped only")
    .transform(
        lambda df: df[["region", "product", "revenue", "variance"]],
        description="Select variance view columns",
    )
)

trend_ds = model.load("trend")

# KPI values
s = shipped.to_pandas()
total_revenue = s["revenue"].sum()
total_margin  = s["margin"].sum()
margin_pct    = total_margin / total_revenue
ship_count    = len(s)
t = trend_ds.to_pandas()
mom_growth = (t["revenue"].iloc[-1] - t["revenue"].iloc[-2]) / t["revenue"].iloc[-2]


# ── Report ────────────────────────────────────────────────────────────────────

report = (
    Report("Analyst Demo")
    .author("TraceBi Demo")
    .description("KPI cards, side-by-side layout, heat maps, area chart, value labels.")

    .add(MetricSection(
        title="Key Metrics",
        metrics=[
            Metric("Revenue",  total_revenue, format="currency0", delta=0.08),
            Metric("Margin",   total_margin,  format="currency0", delta=0.05),
            Metric("Margin %", margin_pct,    format="percent"),
            Metric("Orders",   ship_count,    format="comma"),
            Metric("MoM",      mom_growth,    format="percent",   delta=mom_growth),
        ],
    ))
    .spacer()

    .add(TextSection(title="Revenue by Region", content="Revenue by Region", style="heading2"))
    .row(
        ChartSection(
            title="Bar Chart with Value Labels",
            dataset=by_region,
            chart_type="bar",
            x="region",
            y="revenue",
            ylabel="Revenue ($)",
            figsize=(6, 4),
            show_values=True,
        ),
        TableSection(
            title="Region Table — Color Scale",
            dataset=by_region,
            columns=["region", "revenue", "margin", "orders"],
            column_labels={"revenue": "Revenue ($)", "margin": "Margin ($)"},
            number_formats={"revenue": "currency0", "margin": "currency0"},
            totals=["revenue", "margin", "orders"],
            color_scale={"revenue": "#2563eb"},
            style="striped",
        ),
    )
    .spacer()

    .add(TextSection(title="Revenue Trend", content="Revenue Trend", style="heading2"))
    .add(ChartSection(
        title="Area Chart — Revenue & Cost",
        dataset=trend_ds,
        chart_type="area",
        x="month",
        y=["revenue", "cost"],
        ylabel="USD",
        figsize=(10, 4),
    ))
    .spacer()

    .add(TextSection(title="Variance", content="Variance", style="heading2"))
    .add(TextSection(
        content="Negative variance cells are highlighted red. Revenue uses a green heat map.",
        style="note",
    ))
    .add(TableSection(
        title="Order Variance — Highlight Negatives + Heat Map",
        dataset=variance_ds,
        columns=["region", "product", "revenue", "variance"],
        column_labels={"revenue": "Revenue ($)", "variance": "Variance ($)"},
        number_formats={"revenue": "currency0", "variance": "currency0"},
        highlight_negatives=["variance"],
        color_scale={"revenue": "#16a34a"},
        style="striped",
    ))
)


# ── Render ─────────────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)

    xlsx_path = os.path.join(output_dir, "analyst_demo.xlsx")
    html_path = os.path.join(output_dir, "analyst_demo.html")

    ExcelRenderer().render(report, xlsx_path)
    print(f"Excel: {xlsx_path}")
    HTMLRenderer().render(report, html_path)
    print(f"HTML:  {html_path}")


if __name__ == "__main__":
    run()
