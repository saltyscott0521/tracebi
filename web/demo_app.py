"""
TraceBi demo app — populates the registry with sample data.

This module is imported automatically by web/api/main.py on startup.
It serves as a working example of how to wire your own data sources into
the TraceBi web layer — replace (or extend) it with your real config.

To use your own module instead:
    TRACEBI_APP=mypackage.tracebi_config uvicorn web.api.main:app --reload
"""

import os

import pandas as pd
from sqlalchemy import create_engine

from tracebi import (
    DataModel, MemoryConnector, SQLConnector,
    LandingLayer, ManipulationLayer, FinalLayer, PipelineRunner,
)
from tracebi.reports import Report, TableSection, TextSection, ChartSection
from tracebi.dashboard import Dashboard, DashboardServer, FilterPanel, MetricPanel, ChartPanel, TablePanel
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
registry.add_model(model, default=True)


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


# ── Dashboard ─────────────────────────────────────────────────────────────────

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

registry.add_dashboard(
    "sales",
    DashboardServer(sales_dashboard, model=model),
    description="Live sales overview with associative region and product filters.",
)


# ── Medallion Pipeline ────────────────────────────────────────────────────────
#
# Extends the demo data with a customer_id FK so orders can be joined to
# customers through the DataModel's star-schema query. Runs Bronze → Silver → Gold
# at startup so the Pipeline page shows live run history immediately.

# Source data — orders extended with customer_id for the FK join
_orders_raw = orders_df.assign(
    customer_id=[1, 2, 3, 4, 1, 3, 2, 4, 1, 3]
)[["order_id", "customer_id", "product", "qty", "revenue", "cost", "status"]]

_customers_raw = customers_df.rename(columns={"tier": "segment"})

# SQLite DB for pipeline persistence
_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(_DB_DIR, exist_ok=True)
_DB_URL = f"sqlite:///{os.path.join(_DB_DIR, 'demo.db')}"

_orders_raw.to_sql("orders_raw",    con=create_engine(_DB_URL), if_exists="replace", index=False)
_customers_raw.to_sql("customers_raw", con=create_engine(_DB_URL), if_exists="replace", index=False)

_db = SQLConnector("demo_db", url=_DB_URL)

# Landing — raw ingest from upstream tables, no transforms
_orders_landing = LandingLayer(
    connector=_db, source="orders_raw", description="Raw orders",
    sink=_db, sink_table="orders_bronze",
)
_customers_landing = LandingLayer(
    connector=_db, source="customers_raw", description="Raw customers",
    sink=_db, sink_table="customers_bronze",
)

# Manipulation — optional light cleaning before serving
_orders_manip = (
    ManipulationLayer(source=_db, source_table="orders_bronze", sink=_db, sink_table="orders_silver")
    .drop_nulls(subset=["order_id", "customer_id"])
    .deduplicate(subset=["order_id"])
)
_customers_manip = (
    ManipulationLayer(source=_db, source_table="customers_bronze", sink=_db, sink_table="customers_silver")
    .drop_nulls()
    .deduplicate(subset=["customer_id"])
)

# DataModel with star-schema query surface (reads from silver tables)
_pipeline_model = DataModel("SalesPipelineModel")
_pipeline_model.add_connector(_db)
_pipeline_model.add_table("orders_silver",    connector="demo_db", source="orders_silver")
_pipeline_model.add_table("customers_silver", connector="demo_db", source="customers_silver")
_pipeline_model.add_dimension(
    name="dim_customer",
    table_name="customers_silver",
    key_col="customer_id",
    attributes=["region", "segment"],
)
_pipeline_model.add_fact(
    name="fact_orders",
    table_name="orders_silver",
    measures=["revenue", "qty", "cost"],
    foreign_keys={"dim_customer": "customer_id"},
)

# Final/serving layers — analytics-ready aggregations via the model's query()
_final_by_region = FinalLayer(
    model=_pipeline_model, fact="fact_orders",
    measures={"revenue": "sum", "qty": "sum", "cost": "sum"},
    dimensions=["dim_customer.region"],
    sink=_db, sink_table="gold_revenue_by_region",
)
_final_by_segment = FinalLayer(
    model=_pipeline_model, fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.segment"],
    filters={"status": "shipped"},
    sink=_db, sink_table="gold_revenue_by_segment",
)

# PipelineRunner — register layers with schedules and dependencies
_runner = PipelineRunner(db_url=_DB_URL)
_runner.register(_orders_landing,    name="orders_bronze",    schedule="0 * * * *")
_runner.register(_customers_landing, name="customers_bronze", schedule="0 * * * *")
_runner.register(_orders_manip,      name="orders_silver",    schedule="15 * * * *",
                 depends_on="orders_bronze")
_runner.register(_customers_manip,   name="customers_silver", schedule="15 * * * *",
                 depends_on="customers_bronze")
_runner.register(_final_by_region,   name="revenue_by_region",  schedule="30 6 * * *",
                 depends_on="orders_silver")
_runner.register(_final_by_segment,  name="revenue_by_segment", schedule="30 6 * * *",
                 depends_on="orders_silver")

# Run full pipeline once at startup so the UI has live data immediately
_runner.run("orders_bronze")
_runner.run("customers_bronze")
_runner.run("orders_silver")
_runner.run("customers_silver")
_runner.run("revenue_by_region")
_runner.run("revenue_by_segment")

registry.add_pipeline("sales", _runner)


# ── Medallion report (reads from gold layer via the model's star-schema query) ──

@registry.report(
    "medallion_revenue",
    description="Revenue breakdown produced by the Landing → Manipulation → Final pipeline.",
)
def medallion_revenue():
    gold = FinalLayer(model=_pipeline_model)

    by_region = gold.query(
        fact="fact_orders",
        measures={"revenue": "sum", "qty": "sum", "cost": "sum"},
        dimensions=["dim_customer.region"],
        name="revenue_by_region",
    )
    by_segment = gold.query(
        fact="fact_orders",
        measures={"revenue": "sum", "order_id": "count"},
        dimensions=["dim_customer.segment"],
        filters={"status": "shipped"},
        name="revenue_by_segment_shipped",
    )

    total_rev = by_region.to_pandas()["revenue"].sum()

    return (
        Report("Medallion Revenue Report")
        .author("TraceBi Demo")
        .description("Revenue derived from Bronze → Silver → Gold pipeline via the model's star-schema query.")
        .parameter("pipeline", "orders (landing) → orders (manipulation) → revenue_by_region (final)")

        .add(TextSection(
            title="Pipeline Overview",
            content="Pipeline Overview",
            style="heading1",
        ))
        .add(TextSection(
            content=(
                f"Total revenue across all regions: ${total_rev:,.2f}. "
                "Data flows through Landing (raw ingest) → Manipulation (deduplication) "
                "→ Final (star-schema dimensional aggregation)."
            ),
            style="normal",
        ))
        .spacer()

        .add(TextSection(title="Revenue by Region", content="Revenue by Region", style="heading2"))
        .add(ChartSection(
            title="Revenue by Region",
            dataset=by_region,
            chart_type="bar",
            x="dim_customer.region",
            y="revenue",
            ylabel="Revenue (USD)",
        ))
        .add(TableSection(
            title="Region Summary",
            dataset=by_region,
            columns=["dim_customer.region", "revenue", "qty", "cost"],
            column_labels={
                "dim_customer.region": "Region",
                "revenue": "Revenue ($)",
                "qty": "Units",
                "cost": "Cost ($)",
            },
            totals=["Revenue ($)", "Units", "Cost ($)"],
            number_formats={"revenue": "{:,.2f}", "cost": "{:,.2f}"},
        ))
        .spacer()

        .add(TextSection(title="Revenue by Segment (Shipped)", content="Revenue by Segment (Shipped)", style="heading2"))
        .add(ChartSection(
            title="Revenue by Segment — Shipped Orders",
            dataset=by_segment,
            chart_type="bar",
            x="dim_customer.segment",
            y="revenue",
            ylabel="Revenue (USD)",
        ))
        .add(TableSection(
            title="Segment Breakdown",
            dataset=by_segment,
            columns=["dim_customer.segment", "revenue", "order_id"],
            column_labels={
                "dim_customer.segment": "Segment",
                "revenue": "Revenue ($)",
                "order_id": "Order Count",
            },
            totals=["Revenue ($)", "Order Count"],
            number_formats={"revenue": "{:,.2f}"},
        ))
    )
