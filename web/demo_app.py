"""
TraceBi demo app — populates the registry with sample data.

This module is imported automatically by web/api/main.py on startup.
It serves as a working example of how to wire your own data sources into
the TraceBi web layer — replace (or extend) it with your real config.

To use your own module instead:
    TRACEBI_APP=mypackage.tracebi_config uvicorn web.api.main:app --reload
"""

import pandas as pd

from tracebi import DataModel, MemoryConnector
from tracebi.reports import Report, TableSection, TextSection, ChartSection
from web.api.registry import registry


# ── Sample data ───────────────────────────────────────────────────────────────

orders_df = pd.DataFrame({
    "order_id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "region":   ["North East", "South East", "Midwest", "West",
                 "North East", "Midwest", "South East", "West",
                 "North East", "Midwest"],
    "product":  ["Widget A", "Widget B", "Gadget X", "Widget A",
                 "Gadget X", "Widget B", "Widget A", "Gadget X",
                 "Widget B", "Widget A"],
    "qty":      [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
    "revenue":  [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                 14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
    "cost":     [2100.00, 2800.00, 14000.00, 1050.00, 6600.00,
                 10500.00, 700.00, 7700.00, 2200.00, 12600.00],
    "status":   ["shipped", "shipped", "open", "shipped", "open",
                 "shipped", "shipped", "open", "shipped", "open"],
})

trend_df = pd.DataFrame({
    "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "revenue": [28000, 31500, 29800, 34200, 38100, 39145],
    "orders":  [95, 108, 101, 119, 131, 138],
    "cost":    [19600, 22050, 20860, 23940, 26670, 27400],
})

customers_df = pd.DataFrame({
    "customer_id": [1, 2, 3, 4, 5],
    "name":        ["Acme Corp", "Globex", "Initech", "Umbrella", "Vandelay"],
    "region":      ["North East", "South East", "Midwest", "West", "North East"],
    "tier":        ["enterprise", "smb", "smb", "enterprise", "mid-market"],
})


# ── Connector + DataModel ─────────────────────────────────────────────────────

connector = MemoryConnector("demo", tables={
    "orders":    orders_df,
    "trend":     trend_df,
    "customers": customers_df,
})

model = DataModel("SalesModel")
model.add_connector(connector)
model.add_table("orders",    connector="demo", source="orders")
model.add_table("trend",     connector="demo", source="trend")
model.add_table("customers", connector="demo", source="customers")
model.connect()

registry.add_connector(connector)
registry.add_model(model)


# ── Report factories ──────────────────────────────────────────────────────────

@registry.report(
    "sales_summary",
    description="Shipped order revenue and margin breakdown by region and product.",
)
def sales_summary():
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
        description="Aggregate revenue and margin by region",
    )
    return (
        Report("Sales Summary")
        .author("TraceBi Demo")
        .description("Shipped order revenue and margin breakdown.")
        .parameter("status_filter", "shipped")
        .add(TextSection(
            title="Overview",
            content="Revenue and margin for all shipped orders, grouped by region.",
            style="heading1",
        ))
        .add(TableSection(
            title="Revenue by Region",
            dataset=by_region,
            columns=["region", "revenue", "margin", "orders"],
            column_labels={"revenue": "Revenue ($)", "margin": "Margin ($)"},
            number_formats={"Revenue ($)": "{:,.2f}", "Margin ($)": "{:,.2f}"},
            totals=["revenue", "margin", "orders"],
            style="striped",
        ))
        .add(ChartSection(
            title="Revenue by Region",
            dataset=by_region,
            chart_type="bar",
            x="region",
            y="revenue",
            ylabel="Revenue (USD)",
        ))
        .add(TableSection(
            title="Shipped Order Detail",
            dataset=with_margin,
            columns=["order_id", "region", "product", "qty", "revenue", "margin"],
            column_labels={"order_id": "Order #", "revenue": "Revenue ($)", "margin": "Margin ($)"},
            number_formats={"Revenue ($)": "{:,.2f}", "Margin ($)": "{:,.2f}"},
        ))
    )


@registry.report(
    "revenue_trend",
    description="Monthly revenue trend with cost overlay and growth analysis.",
)
def revenue_trend():
    ds = model.load("trend")
    with_growth = ds.transform(
        lambda df: df.assign(
            growth_pct=df["revenue"].pct_change().mul(100).round(1)
        ),
        description="Month-over-month revenue growth %",
    )
    return (
        Report("Revenue Trend")
        .author("TraceBi Demo")
        .description("Monthly revenue and cost trend with growth rate.")
        .add(TextSection(
            title="Revenue Trend",
            content="Month-over-month revenue performance with cost overlay.",
            style="heading1",
        ))
        .add(ChartSection(
            title="Revenue vs Cost",
            dataset=ds,
            chart_type="line",
            x="month",
            y=["revenue", "cost"],
            ylabel="USD",
        ))
        .add(TableSection(
            title="Monthly Detail",
            dataset=with_growth,
            columns=["month", "revenue", "cost", "orders", "growth_pct"],
            column_labels={
                "revenue": "Revenue ($)",
                "cost": "Cost ($)",
                "growth_pct": "MoM Growth %",
            },
            number_formats={
                "Revenue ($)": "{:,.0f}",
                "Cost ($)": "{:,.0f}",
            },
        ))
    )


@registry.report(
    "customer_overview",
    description="Customer list with region and tier breakdown.",
)
def customer_overview():
    ds = model.load("customers")
    by_tier = ds.transform(
        lambda df: df.groupby("tier", as_index=False).size().rename(
            columns={"size": "count"}
        ),
        description="Count customers by tier",
    )
    return (
        Report("Customer Overview")
        .author("TraceBi Demo")
        .description("Customer breakdown by region and tier.")
        .add(TextSection(
            title="Customers",
            content="All registered customers grouped by tier.",
            style="heading1",
        ))
        .add(ChartSection(
            title="Customers by Tier",
            dataset=by_tier,
            chart_type="pie",
            x="tier",
            y="count",
        ))
        .add(TableSection(
            title="Customer List",
            dataset=ds,
            columns=["customer_id", "name", "region", "tier"],
            column_labels={"customer_id": "ID"},
        ))
    )
