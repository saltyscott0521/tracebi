"""
Client Activity & Flows — wealth-management report.

Monthly net flows (purchases minus sales), activity by client segment,
and top-10 clients by gross activity.
"""

from tracebi.reports.report import (
    Report, TextSection, TableSection, ChartSection,
)
from tracebi.web import register
from web.demo_app.banking import banking_model


@register.report(
    "client_activity",
    description="Monthly net flows, activity by segment, and top-10 clients by gross activity.",
)
def client_activity():
    # ── Load and join ──────────────────────────────────────────────────────────
    activities_ds = banking_model.load("activities")
    accounts_ds   = banking_model.load("accounts")
    clients_ds    = banking_model.load("clients")

    with_accounts = activities_ds.join(
        accounts_ds, left_on="account_id", right_on="account_id",
        description="activities + accounts",
    )
    enriched = with_accounts.join(
        clients_ds, left_on="client_id", right_on="client_id",
        description="+ clients",
    )

    # ── Signed amount: purchases positive, sales negative, fees excluded ──────
    with_signed = enriched.assign(
        signed_amount=lambda df: df.apply(
            lambda r: r["amount"] if r["activity_type"] == "purchase"
                      else -r["amount"] if r["activity_type"] == "sale"
                      else 0.0,
            axis=1,
        ),
        description="signed_amount: purchase=+, sale=−, fee=0",
    )

    # ── Monthly net flows ─────────────────────────────────────────────────────
    monthly_flows = (
        with_signed
        .aggregate(
            by="trade_date",
            net_flow=("signed_amount", "sum"),
            gross_activity=("amount", "sum"),
            description="Monthly net flows and gross activity",
        )
        .sort("trade_date")
    )

    # ── Activity by segment ───────────────────────────────────────────────────
    by_segment = (
        with_signed
        .aggregate(
            by="segment",
            net_flow=("signed_amount", "sum"),
            gross_activity=("amount", "sum"),
            transactions=("activity_id", "count"),
            description="Activity totals by client segment",
        )
        .sort("gross_activity", ascending=False)
    )

    # ── Top-10 clients by gross activity ──────────────────────────────────────
    top_clients = (
        with_signed
        .aggregate(
            by=["client_id", "name", "segment"],
            gross_activity=("amount", "sum"),
            net_flow=("signed_amount", "sum"),
            transactions=("activity_id", "count"),
            description="Gross activity per client",
        )
        .sort("gross_activity", ascending=False)
        .transform(lambda df: df.head(10), description="Top 10 clients")
    )

    # ── Report ────────────────────────────────────────────────────────────────
    return (
        Report("Client Activity & Flows")
        .author("TraceBi Demo")
        .description("Monthly net flows, activity by client segment, and top-10 clients.")

        .add(TextSection(
            title="Monthly Net Flows",
            content="Net flows = purchases minus sales per month (fees excluded).",
            style="heading2",
        ))
        .add(ChartSection(
            title="Monthly Net Flows",
            dataset=monthly_flows,
            chart_type="bar",
            x="trade_date",
            y="net_flow",
            ylabel="Net Flow (USD)",
            figsize=(10, 4),
        ))
        .add(TableSection(
            title="Monthly Flow Detail",
            dataset=monthly_flows,
            columns=["trade_date", "net_flow", "gross_activity"],
            column_labels={
                "trade_date":      "Month",
                "net_flow":        "Net Flow ($)",
                "gross_activity":  "Gross Activity ($)",
            },
            number_formats={"net_flow": "currency0", "gross_activity": "currency0"},
            totals=["net_flow", "gross_activity"],
            highlight_negatives=["net_flow"],
            style="striped",
        ))
        .spacer()

        .add(TextSection(title="Activity by Segment", content="Activity by Segment", style="heading2"))
        .add(TableSection(
            title="Segment Summary",
            dataset=by_segment,
            columns=["segment", "net_flow", "gross_activity", "transactions"],
            column_labels={
                "net_flow":       "Net Flow ($)",
                "gross_activity": "Gross Activity ($)",
            },
            number_formats={"net_flow": "currency0", "gross_activity": "currency0"},
            totals=["net_flow", "gross_activity", "transactions"],
            style="striped",
        ))
        .spacer()

        .add(TextSection(title="Top 10 Clients by Gross Activity", content="Top 10 Clients", style="heading2"))
        .add(TableSection(
            title="Top 10 Clients",
            dataset=top_clients,
            columns=["name", "segment", "gross_activity", "net_flow", "transactions"],
            column_labels={
                "gross_activity": "Gross Activity ($)",
                "net_flow":       "Net Flow ($)",
            },
            number_formats={"gross_activity": "currency0", "net_flow": "currency0"},
            highlight_negatives=["net_flow"],
        ))
    )
