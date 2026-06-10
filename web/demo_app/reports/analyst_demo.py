"""
Analyst Demo Report — showcases the new analyst-experience features:
  • MetricSection — KPI cards with green/red delta indicators
  • RowSection    — side-by-side chart + table layout
  • TableSection  — highlight_negatives, color_scale, named number formats
  • ChartSection  — area chart, show_values bar labels
"""

from tracebi.reports.report import (
    Report, TextSection, TableSection, ChartSection,
    Metric, MetricSection,
)
from tracebi.web import register
from web.demo_app.model import model


@register.report(
    "analyst_demo",
    description="KPI cards, side-by-side layout, heat maps, and styled charts.",
)
def analyst_demo():
    # ── Load and transform data ───────────────────────────────────────────────
    all_orders = model.load("orders")

    shipped = all_orders.filter("status == 'shipped'", description="Shipped orders only")
    with_margin = shipped.transform(
        lambda df: df.assign(margin=df["revenue"] - df["cost"]),
        description="margin = revenue - cost",
    )

    by_region = with_margin.transform(
        lambda df: df.groupby("region", as_index=False).agg(
            revenue=("revenue", "sum"),
            margin=("margin", "sum"),
            orders=("order_id", "count"),
        ).sort_values("revenue", ascending=False),
        description="Revenue and margin aggregated by region",
    )

    variance_ds = shipped.transform(
        lambda df: df[["region", "product", "revenue", "cost"]].assign(
            variance=df["revenue"] - df["cost"] - (df["revenue"] * 0.35)
        ),
        description="Variance = margin minus 35% target",
    )

    trend_ds = model.load("trend")

    # ── Compute KPIs ─────────────────────────────────────────────────────────
    s = with_margin.to_pandas()
    total_revenue  = s["revenue"].sum()
    total_margin   = s["margin"].sum()
    margin_pct     = total_margin / total_revenue if total_revenue else 0
    shipped_count  = len(s)

    t = trend_ds.to_pandas()
    mom_growth = (t["revenue"].iloc[-1] - t["revenue"].iloc[-2]) / t["revenue"].iloc[-2]
    prior_revenue = 29593.70
    revenue_delta = (total_revenue - prior_revenue) / prior_revenue

    # ── Build Report ──────────────────────────────────────────────────────────
    return (
        Report("Analyst Demo — Styling & Layout")
        .author("TraceBi Demo")
        .description(
            "Demonstrates KPI metric cards, side-by-side RowSection layout, "
            "heat-map color scales, negative-value highlighting, area chart, "
            "and bar-chart value labels."
        )

        # KPI row
        .add(MetricSection(
            title="Key Metrics",
            metrics=[
                Metric("Total Revenue",  total_revenue, format="currency0", delta=revenue_delta),
                Metric("Total Margin",   total_margin,  format="currency0", delta=revenue_delta * 0.9),
                Metric("Margin %",       margin_pct,    format="percent"),
                Metric("Shipped Orders", shipped_count, format="comma"),
                Metric("MoM Growth",     mom_growth,    format="percent",   delta=mom_growth),
            ],
        ))
        .spacer()

        # Side-by-side: bar chart with labels + region table with heat map
        .add(TextSection(
            title="Regional Performance",
            content="Regional Performance",
            style="heading2",
        ))
        .row(
            ChartSection(
                title="Revenue by Region",
                dataset=by_region,
                chart_type="bar",
                x="region",
                y="revenue",
                ylabel="Revenue (USD)",
                figsize=(6, 4),
                show_values=True,
            ),
            TableSection(
                title="Region Summary",
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

        # Area chart — revenue vs cost trend
        .add(TextSection(title="Revenue Trend", content="Revenue Trend", style="heading2"))
        .add(ChartSection(
            title="Monthly Revenue & Cost — Jan to Jun",
            dataset=trend_ds,
            chart_type="area",
            x="month",
            y=["revenue", "cost"],
            ylabel="USD",
            figsize=(10, 4),
        ))
        .spacer()

        # Variance table — highlight negatives + color scale
        .add(TextSection(title="Variance Analysis", content="Variance Analysis", style="heading2"))
        .add(TextSection(
            content="Variance = margin minus 35% revenue target. Red cells are below target.",
            style="note",
        ))
        .add(TableSection(
            title="Order Variance",
            dataset=variance_ds,
            columns=["region", "product", "revenue", "variance"],
            column_labels={"revenue": "Revenue ($)", "variance": "Variance ($)"},
            number_formats={"revenue": "currency0", "variance": "currency0"},
            highlight_negatives=["variance"],
            color_scale={"revenue": "#16a34a"},
            column_widths={"region": 16, "product": 16, "revenue": 14, "variance": 14},
            style="striped",
        ))
        .spacer()

        # Shipped order detail
        .add(TextSection(
            title="Shipped Order Detail",
            content="Shipped Order Detail",
            style="heading2",
        ))
        .add(TableSection(
            title="Shipped Orders",
            dataset=with_margin,
            columns=["order_id", "region", "product", "qty", "revenue", "margin"],
            column_labels={
                "order_id": "Order #",
                "revenue":  "Revenue ($)",
                "margin":   "Margin ($)",
            },
            number_formats={"revenue": "currency", "margin": "currency"},
            totals=["revenue", "margin", "qty"],
        ))
    )
