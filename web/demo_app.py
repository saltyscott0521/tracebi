"""
TraceBi demo app — populates the registry with sample data.

This module is imported automatically by web/api/main.py on startup.
It serves as a working example of how to wire your own data sources into
the TraceBi web layer — replace (or extend) it with your real config.

To use your own module instead:
    TRACEBI_APP=mypackage.tracebi_config uvicorn web.api.main:app --reload

Startup behaviour
-----------------
* If data/tracebi.db exists (created by ``python seeds/seed_db.py``):
  Uses the real SQLite-backed medallion pipeline — Bronze/Silver/Gold layers,
  StarSchema, and PipelineRunner are all registered and visible in the UI.
* Otherwise: falls back to an in-memory MemoryConnector dataset so the UI
  starts without any prerequisites.
"""

from __future__ import annotations

import os
import sys
import warnings

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_ROOT, "data", "tracebi.db")

from tracebi.reports import Report, TableSection, TextSection, ChartSection
from tracebi.dashboard import (
    Dashboard, DashboardServer,
    FilterPanel, MetricPanel, ChartPanel, TablePanel,
)
from web.api.registry import registry


# ── Try SQLite-backed medallion setup ─────────────────────────────────────────

_db_ready = False

if os.path.exists(_DB_PATH):
    try:
        sys.path.insert(0, _ROOT)
        from seeds.seed_db import build_pipeline, DB_URL

        runner, schema, model = build_pipeline(DB_URL)

        # Discover which tables exist in the DB
        try:
            from sqlalchemy import inspect as _sa_inspect
            _existing = _sa_inspect(runner._engine_()).get_table_names()
        except Exception:
            _existing = []

        # Silver tables must exist to use real data (created by running Silver layer)
        _silver_ready = (
            "orders_silver" in _existing and "customers_silver" in _existing
        )

        # Add silver + gold tables to the model if present
        for _tbl in ("orders_silver", "customers_silver",
                     "revenue_by_region_gold", "revenue_by_segment_gold"):
            if _tbl in _existing and _tbl not in model._tables:
                model.add_table(_tbl, connector="tracebi_db", source=_tbl)

        model.connect()

        registry.add_connector(list(model._connectors.values())[0])
        registry.add_model(model)
        registry.add_pipeline("sales", runner)  # always register pipeline if DB exists

        _db_ready = _silver_ready  # reports/dashboard use real data only when silver is ready

        if not _silver_ready and _existing:
            warnings.warn(
                "TraceBi demo: orders_silver not found — pipeline registered but "
                "reports/dashboard will use in-memory fallback. "
                "Run the Silver pipeline layer to activate real data."
            )
        elif not _existing:
            warnings.warn(
                "TraceBi demo: DB is empty — pipeline registered but reports/dashboard "
                "will use in-memory fallback. Run `python seeds/seed_db.py` first."
            )

    except Exception as _exc:
        warnings.warn(
            f"TraceBi demo: could not load SQLite pipeline ({_exc}). "
            "Falling back to in-memory data. Run `python seeds/seed_db.py` to enable "
            "the full medallion demo."
        )


# ── In-memory fallback ────────────────────────────────────────────────────────

if not _db_ready:
    import pandas as pd
    from tracebi import DataModel, MemoryConnector

    # Schema mirrors orders_silver / customers_silver so _enriched_orders() works
    # identically in both the in-memory and DB-backed paths.
    _orders_df = pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "customer_id": [1, 2, 3, 1, 3, 2, 1, 3, 2, 3],
        "product":     ["Widget A", "Widget B", "Gadget X", "Widget A",
                        "Gadget X", "Widget B", "Widget A", "Gadget X",
                        "Widget B", "Widget A"],
        "qty":         [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
        "revenue":     [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                        14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
        "status":      ["shipped", "shipped", "open", "shipped", "open",
                        "shipped", "shipped", "open", "shipped", "open"],
    })
    _customers_df = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "name":        ["Alice Corp", "Bob Industries", "Carol LLC"],
        "region":      ["North East", "Midwest", "South East"],
        "segment":     ["Enterprise", "SMB", "SMB"],
    })

    _connector = MemoryConnector("demo", tables={
        "orders":    _orders_df,
        "customers": _customers_df,
    })
    model = DataModel("SalesModel")
    model.add_connector(_connector)
    model.add_table("orders",    connector="demo", source="orders")
    model.add_table("customers", connector="demo", source="customers")
    model.connect()

    registry.add_connector(_connector)
    registry.add_model(model)


# ── Helper: enrich orders with customer region/segment ────────────────────────
# Used by both reports and the dashboard. Called fresh each time so lineage
# is always up-to-date with the current DB state.

def _orders_table() -> str:
    """Return the correct orders table name for the active model."""
    return "orders_silver" if _db_ready else "orders"


def _customers_table() -> str:
    return "customers_silver" if _db_ready else "customers"


def _enriched_orders():
    """Load orders joined with customer region/segment."""
    orders_ds = model.load(_orders_table())
    customers_ds = model.load(_customers_table())
    return orders_ds.transform(
        lambda df: df.merge(
            customers_ds.to_pandas()[["customer_id", "region", "segment"]],
            on="customer_id",
            how="left",
        ),
        description="Enrich orders with customer region and segment",
    )


# ── Reports ───────────────────────────────────────────────────────────────────

@registry.report(
    "sales_summary",
    description="Shipped order revenue by region — sourced from the Silver layer.",
)
def sales_summary():
    enriched = _enriched_orders()
    shipped = enriched.filter("status == 'shipped'", description="Shipped orders only")
    by_region = shipped.transform(
        lambda df: df.groupby("region", as_index=False).agg(
            revenue=("revenue", "sum"),
            qty=("qty", "sum"),
            orders=("order_id", "count"),
        ).sort_values("revenue", ascending=False),
        description="Aggregate revenue and order count by region",
    )
    layer_note = "Silver layer (orders_silver ⋈ customers_silver)" if _db_ready else "In-memory demo data"
    return (
        Report("Sales Summary")
        .author("TraceBi Demo")
        .description("Shipped order revenue breakdown by region.")
        .parameter("source", layer_note)
        .add(TextSection(
            title="Overview",
            content=f"Revenue for all shipped orders, grouped by customer region. Source: {layer_note}.",
            style="heading1",
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
            title="Revenue by Region",
            dataset=by_region,
            columns=["region", "revenue", "qty", "orders"],
            column_labels={"revenue": "Revenue ($)", "qty": "Units Sold"},
            number_formats={"Revenue ($)": "{:,.2f}"},
            totals=["revenue", "qty", "orders"],
            style="striped",
        ))
        .add(TableSection(
            title="Order Detail",
            dataset=shipped,
            columns=["order_id", "region", "product", "qty", "revenue", "status"],
            column_labels={"order_id": "Order #", "revenue": "Revenue ($)"},
            number_formats={"Revenue ($)": "{:,.2f}"},
        ))
    )


@registry.report(
    "revenue_by_segment",
    description="Shipped revenue aggregated by customer segment — Gold layer if available.",
)
def revenue_by_segment():
    if _db_ready and "revenue_by_segment_gold" in model._tables:
        ds = model.load("revenue_by_segment_gold")
        source_note = "Gold layer (revenue_by_segment_gold)"
        x_col, y_col = "segment", "revenue"
    else:
        enriched = _enriched_orders()
        shipped = enriched.filter("status == 'shipped'", description="Shipped only")
        ds = shipped.transform(
            lambda df: df.groupby("segment", as_index=False).agg(
                revenue=("revenue", "sum"),
                orders=("order_id", "count"),
            ).sort_values("revenue", ascending=False),
            description="Aggregate by customer segment",
        )
        source_note = "Silver layer (computed)" if _db_ready else "In-memory demo data"
        x_col, y_col = "segment", "revenue"

    return (
        Report("Revenue by Segment")
        .author("TraceBi Demo")
        .description("Shipped revenue broken down by customer segment.")
        .parameter("source", source_note)
        .add(TextSection(
            title="Revenue by Customer Segment",
            content=f"Aggregated shipped revenue per customer segment. Source: {source_note}.",
            style="heading1",
        ))
        .add(ChartSection(
            title="Revenue by Segment",
            dataset=ds,
            chart_type="pie",
            x=x_col,
            y=y_col,
        ))
        .add(TableSection(
            title="Segment Detail",
            dataset=ds,
            column_labels={"revenue": "Revenue ($)"},
            number_formats={"Revenue ($)": "{:,.2f}"},
        ))
    )


@registry.report(
    "customer_overview",
    description="Customer list with region and segment breakdown.",
)
def customer_overview():
    ds = model.load(_customers_table())
    by_segment = ds.transform(
        lambda df: df.groupby("segment", as_index=False).size().rename(
            columns={"size": "count"}
        ),
        description="Count customers by segment",
    )
    return (
        Report("Customer Overview")
        .author("TraceBi Demo")
        .description("Customer breakdown by region and segment.")
        .add(TextSection(
            title="Customers",
            content="All registered customers grouped by segment.",
            style="heading1",
        ))
        .add(ChartSection(
            title="Customers by Segment",
            dataset=by_segment,
            chart_type="pie",
            x="segment",
            y="count",
        ))
        .add(TableSection(
            title="Customer List",
            dataset=ds,
            columns=["customer_id", "name", "region", "segment"],
            column_labels={"customer_id": "ID"},
        ))
    )


if _db_ready and "revenue_by_region_gold" in model._tables:
    @registry.report(
        "gold_revenue_by_region",
        description="Gold-layer pre-aggregated revenue by region.",
    )
    def gold_revenue_by_region():
        ds = model.load("revenue_by_region_gold")
        return (
            Report("Gold — Revenue by Region")
            .author("TraceBi Demo")
            .description("Pre-aggregated Gold layer: revenue and units by customer region.")
            .parameter("source", "Gold layer (revenue_by_region_gold)")
            .add(TextSection(
                title="Gold Layer — Revenue by Region",
                content=(
                    "This report reads directly from the revenue_by_region_gold table, "
                    "produced by the GoldLayer via StarSchema aggregation over the "
                    "orders_silver fact table and customers_silver dimension."
                ),
                style="heading1",
            ))
            .add(ChartSection(
                title="Revenue by Region (Gold)",
                dataset=ds,
                chart_type="bar",
                x="region",
                y="revenue",
                ylabel="Revenue (USD)",
            ))
            .add(TableSection(
                title="Gold Table",
                dataset=ds,
                column_labels={"revenue": "Revenue ($)", "qty": "Units"},
                number_formats={"Revenue ($)": "{:,.2f}"},
                totals=["revenue", "qty"],
                style="striped",
            ))
        )


# ── Dashboard ─────────────────────────────────────────────────────────────────

# Pre-build enriched orders dataset for dashboard panels.
# Uses model.load() so lineage is tracked; rebuilt on server restart.
try:
    _dash_orders = _enriched_orders()
    _dash_customers = model.load(_customers_table())

    _by_region_ds = _dash_orders.transform(
        lambda df: df.groupby("region", as_index=False).agg(
            revenue=("revenue", "sum"), orders=("order_id", "count")
        ).sort_values("revenue", ascending=False),
        description="Revenue by region",
    )
    _by_segment_ds = _dash_orders.filter(
        "status == 'shipped'", description="Shipped only"
    ).transform(
        lambda df: df.groupby("segment", as_index=False).agg(
            revenue=("revenue", "sum")
        ),
        description="Revenue by segment",
    )

    _dash_title = "Sales Dashboard — Medallion" if _db_ready else "Sales Dashboard"
    _dash_desc = (
        "Live view over Silver/Gold layers with associative region filter."
        if _db_ready
        else "Live in-memory sales overview. Run seeds/seed_db.py for medallion data."
    )

    sales_dashboard = (
        Dashboard(_dash_title)
        .description(_dash_desc)
        .columns(2)
        .add_filter(FilterPanel(
            "region-filter", label="Region", column="region",
            dataset=_dash_orders,
        ))
        .add_filter(FilterPanel(
            "segment-filter", label="Segment", column="segment",
            dataset=_dash_orders,
        ))
        .add_panel(MetricPanel(
            "total-revenue", title="Total Revenue",
            dataset=_dash_orders, column="revenue",
            aggregation="sum", prefix="$", number_format="{:,.0f}",
        ))
        .add_panel(MetricPanel(
            "total-orders", title="Total Orders",
            dataset=_dash_orders, column="order_id",
            aggregation="count", number_format="{:,.0f}",
        ))
        .add_panel(ChartPanel(
            "revenue-by-region", title="Revenue by Region",
            dataset=_by_region_ds, chart_type="bar",
            x="region", y="revenue", ylabel="Revenue (USD)",
        ))
        .add_panel(ChartPanel(
            "revenue-by-segment", title="Revenue by Segment (Shipped)",
            dataset=_by_segment_ds, chart_type="pie",
            x="segment", y="revenue",
        ))
        .add_panel(TablePanel(
            "orders-table", title="Order Detail",
            dataset=_dash_orders,
            columns=["order_id", "region", "segment", "product", "qty", "revenue", "status"],
            column_labels={"order_id": "Order #", "revenue": "Revenue ($)"},
        ))
        .add_panel(TablePanel(
            "customers-table", title="Customers",
            dataset=_dash_customers,
            columns=["customer_id", "name", "region", "segment"],
            column_labels={"customer_id": "ID"},
        ))
    )

    registry.add_dashboard(
        "sales",
        DashboardServer(sales_dashboard, model=model),
        description=_dash_desc,
    )

except Exception as _dash_exc:
    warnings.warn(f"TraceBi demo: could not build dashboard ({_dash_exc}).")
