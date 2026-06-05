from tracebi import FinalLayer
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.web import register
from web.demo_app.pipeline import pipeline_model


@register.report(
    "medallion_revenue",
    description="Revenue breakdown produced by the Landing → Manipulation → Final pipeline.",
)
def medallion_revenue():
    gold = FinalLayer(model=pipeline_model)

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
