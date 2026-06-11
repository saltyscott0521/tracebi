"""
AUM by Branch & Asset Class — wealth-management report.

Shows total AUM and unrealized gain broken out by branch/region and
by asset class, using the WealthModel holdings fact.
"""

from tracebi.reports.report import (
    Report, TextSection, TableSection, ChartSection,
    Metric, MetricSection,
)
from tracebi.web import register
from web.demo_app.banking import banking_model


@register.report(
    "aum_by_branch",
    description="AUM and unrealized gain by branch, region, and asset class.",
)
def aum_by_branch():
    # ── Load and join ──────────────────────────────────────────────────────────
    holdings_ds   = banking_model.load("holdings")
    accounts_ds   = banking_model.load("accounts")
    clients_ds    = banking_model.load("clients")
    branches_ds   = banking_model.load("branches")
    products_ds   = banking_model.load("products")

    # holdings → accounts → clients → branches
    with_accounts = holdings_ds.join(
        accounts_ds, left_on="account_id", right_on="account_id",
        description="holdings + accounts",
    )
    with_clients = with_accounts.join(
        clients_ds, left_on="client_id", right_on="client_id",
        description="+ clients",
    )
    with_branches = with_clients.join(
        branches_ds, left_on="branch_id", right_on="branch_id",
        description="+ branches",
    )

    # add unrealized gain
    enriched = with_branches.assign(
        unrealized_gain=lambda df: df["market_value"] - df["cost_basis"],
        description="unrealized_gain = market_value - cost_basis",
    )

    # ── Aggregations ──────────────────────────────────────────────────────────
    by_branch = (
        enriched
        .aggregate(
            by=["branch", "region"],
            market_value="sum",
            unrealized_gain="sum",
            description="AUM and gain by branch",
        )
        .sort("market_value", ascending=False)
    )

    # holdings → products for asset-class breakdown
    with_products = holdings_ds.join(
        products_ds, left_on="product_id", right_on="product_id",
        description="holdings + products",
    ).assign(
        unrealized_gain=lambda df: df["market_value"] - df["cost_basis"],
        description="unrealized_gain = market_value - cost_basis",
    )

    by_asset_class = (
        with_products
        .aggregate(
            by="asset_class",
            market_value="sum",
            unrealized_gain="sum",
            description="AUM and gain by asset class",
        )
        .sort("market_value", ascending=False)
    )

    # ── KPIs ──────────────────────────────────────────────────────────────────
    h = enriched.to_pandas()
    total_aum        = h["market_value"].sum()
    total_gain       = h["unrealized_gain"].sum()
    account_count    = h["account_id"].nunique()

    # ── Report ────────────────────────────────────────────────────────────────
    return (
        Report("AUM by Branch & Asset Class")
        .author("TraceBi Demo")
        .description("Total assets under management and unrealized gain by branch and asset class.")

        .add(MetricSection(
            title="Portfolio Overview",
            metrics=[
                Metric("Total AUM",          total_aum,     format="currency0"),
                Metric("Unrealized Gain",     total_gain,    format="currency0"),
                Metric("Accounts",            account_count, format="comma"),
            ],
        ))
        .spacer()

        .add(TextSection(title="AUM by Branch", content="AUM by Branch", style="heading2"))
        .add(ChartSection(
            title="AUM by Branch",
            dataset=by_branch,
            chart_type="bar",
            x="branch",
            y="market_value",
            ylabel="AUM (USD)",
            figsize=(9, 4),
            show_values=True,
        ))
        .add(TableSection(
            title="Branch Summary",
            dataset=by_branch,
            columns=["branch", "region", "market_value", "unrealized_gain"],
            column_labels={"market_value": "AUM ($)", "unrealized_gain": "Unreal. Gain ($)"},
            number_formats={"market_value": "currency0", "unrealized_gain": "currency0"},
            totals=["market_value", "unrealized_gain"],
            style="striped",
        ))
        .spacer()

        .add(TextSection(title="AUM by Asset Class", content="AUM by Asset Class", style="heading2"))
        .add(TableSection(
            title="Asset Class Breakdown",
            dataset=by_asset_class,
            columns=["asset_class", "market_value", "unrealized_gain"],
            column_labels={"market_value": "AUM ($)", "unrealized_gain": "Unreal. Gain ($)"},
            number_formats={"market_value": "currency0", "unrealized_gain": "currency0"},
            totals=["market_value", "unrealized_gain"],
            color_scale={"market_value": "#1d4ed8"},
            style="striped",
        ))
    )
