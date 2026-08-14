from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.web import register
from tracebi.model_registry import get_model

model = get_model("sales_model")


@register.report(
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
