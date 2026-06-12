from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.web import register
from tracebi.model_registry import get_model

model = get_model("sales_model")


@register.report(
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
