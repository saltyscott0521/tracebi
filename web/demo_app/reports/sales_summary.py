from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.web import register
from tracebi.model_registry import get_model

model = get_model("sales_model")


@register.report(
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
