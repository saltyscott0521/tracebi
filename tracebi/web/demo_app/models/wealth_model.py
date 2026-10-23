"""
wealth_model — banking / wealth-management demo DataModel.

A six-table star schema (clients, branches, products, accounts, holdings,
activities) in the demo database: ``data/demo.db`` (SQLite), or the
database ``TRACEBI_DEMO_DB_URL`` names. The wealth pipeline's seed step
(``wealth_pipeline.py``) writes the six tables there from the frames in
``sample_data.py``; this model reads them through the ``demo_db`` connector,
the same one ``sales_model`` reads. Lives at the project root so notebooks,
scripts, and the web server share one definition::

    from tracebi.model_registry import get_model
    model = get_model("wealth_model")

Exposes a module-level ``model`` (the convention the registry looks for) plus
``connector`` so the web app can surface it in the Sources list.
"""

from tracebi import DataModel
from tracebi.web.demo_app.pipeline import db as connector

# ── DataModel ──────────────────────────────────────────────────────────────────

model = DataModel("wealth_model", label="Wealth Management")
model.add_connector(connector)

model.add_table("clients",    connector="demo_db", source="clients")
model.add_table("branches",   connector="demo_db", source="branches")
model.add_table("products",   connector="demo_db", source="products")
model.add_table("accounts",   connector="demo_db", source="accounts")
model.add_table("holdings",   connector="demo_db", source="holdings")
model.add_table("activities", connector="demo_db", source="activities")

model.add_relationship(
    "accounts_to_clients",
    left_table="accounts",
    right_table="clients",
    left_key="client_id",
)
model.add_relationship(
    "clients_to_branches",
    left_table="clients",
    right_table="branches",
    left_key="branch_id",
)
model.add_relationship(
    "holdings_to_accounts",
    left_table="holdings",
    right_table="accounts",
    left_key="account_id",
)
model.add_relationship(
    "holdings_to_products",
    left_table="holdings",
    right_table="products",
    left_key="product_id",
)
model.add_relationship(
    "activities_to_accounts",
    left_table="activities",
    right_table="accounts",
    left_key="account_id",
)
model.add_relationship(
    "activities_to_products",
    left_table="activities",
    right_table="products",
    left_key="product_id",
)

# ── Star-schema tags ───────────────────────────────────────────────────────────

model.add_dimension(
    "dim_client",
    table_name="clients",
    key_col="client_id",
    attributes=["name", "segment", "risk_profile", "advisor"],
)
model.add_dimension(
    "dim_branch",
    table_name="branches",
    key_col="branch_id",
    attributes=["branch", "region", "manager"],
)
model.add_dimension(
    "dim_product",
    table_name="products",
    key_col="product_id",
    attributes=["ticker", "product_name", "asset_class", "risk_rating"],
)
model.add_dimension(
    "dim_account",
    table_name="accounts",
    key_col="account_id",
    attributes=["account_type", "opened"],
)
model.add_fact(
    "fact_holdings",
    table_name="holdings",
    measures=["units", "market_value", "cost_basis"],
    foreign_keys={"dim_account": "account_id", "dim_client": "client_id",
                  "dim_branch": "branch_id", "dim_product": "product_id"},
)
model.add_fact(
    "fact_activities",
    table_name="activities",
    measures=["units", "amount"],
    foreign_keys={"dim_account": "account_id", "dim_client": "client_id",
                  "dim_branch": "branch_id", "dim_product": "product_id"},
)

# Named measures — the shared definitions every report and agent agrees on.
# "Unrealized gain" is defined here, once, rather than re-derived (perhaps
# differently) by each consumer. The declared format also becomes the
# renderer's default for the column.
model.add_measure(
    "market_value", column="market_value", agg="sum", format="currency0",
    description="Sum of position market values.",
)
model.add_measure(
    "cost_basis", column="cost_basis", agg="sum", format="currency0",
    description="Sum of position cost bases.",
)
model.add_measure(
    "unrealized_gain", expr="market_value - cost_basis", agg="sum",
    format="currency0",
    description="Market value less cost basis, summed per group.",
)
model.add_measure(
    "gain_pct", ratio=("unrealized_gain", "cost_basis"), format="percent",
    description="Unrealized gain as a share of cost basis (ratio of totals).",
)

model.connect()
