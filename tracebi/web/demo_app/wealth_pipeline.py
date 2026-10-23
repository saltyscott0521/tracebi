"""Medallion pipeline for the demo app's ``wealth_model``.

Landing → Manipulation → Final over the same demo database as the sales
pipeline: raw holdings and branches land, get cleaned, and the final layer
aggregates assets under management by branch into ``gold_aum_by_branch``.

Its seed step writes the bank (``sample_data.py``) into that database: the
six tables ``wealth_model`` reads (clients, branches, products, accounts,
holdings, activities) and the raw tables the Landing layers read. Definition
and execution are separate exactly as in ``pipeline.py``: with a durable
``TRACEBI_DEMO_DB_URL`` importing this only defines layers; without one it
seeds and runs itself, because nothing else can have.
"""
from sqlalchemy import create_engine

from tracebi import DataModel, FinalLayer, LandingLayer, ManipulationLayer, PipelineRunner
from tracebi.state import state_url
from tracebi.web.demo_app import sample_data
from tracebi.web.demo_app.pipeline import _DB_URL, DURABLE_DB, db

# The tables wealth_model reads, by name in the demo database.
BANK_TABLES = {
    "clients": sample_data.clients_df, "branches": sample_data.branches_df,
    "products": sample_data.products_df, "accounts": sample_data.accounts_df,
    "holdings": sample_data.holdings_df, "activities": sample_data.activities_df,
}


def seed_source_tables() -> None:
    """Write the bank wealth_model reads, and the raw tables the Landing
    layers read. Execution, not definition."""
    engine = create_engine(_DB_URL)
    for name, frame in BANK_TABLES.items():
        frame.to_sql(name, con=engine, if_exists="replace", index=False)
    sample_data.holdings_df.to_sql("holdings_raw", con=engine, if_exists="replace", index=False)
    sample_data.branches_df.to_sql("branches_raw", con=engine, if_exists="replace", index=False)


_holdings_landing = LandingLayer(
    connector=db, source="holdings_raw", description="Raw holdings",
    sink=db, sink_table="holdings_bronze")
_branches_landing = LandingLayer(
    connector=db, source="branches_raw", description="Raw branches",
    sink=db, sink_table="branches_bronze")
_holdings_manip = (
    ManipulationLayer(source=db, source_table="holdings_bronze", sink=db, sink_table="holdings_silver")
    .drop_nulls(subset=["holding_id", "branch_id"]).deduplicate(subset=["holding_id"]))
_branches_manip = (
    ManipulationLayer(source=db, source_table="branches_bronze", sink=db, sink_table="branches_silver")
    .drop_nulls().deduplicate(subset=["branch_id"]))

# What the Final layer reads: the cleaned tables, joined the star-schema way.
wealth_pipeline_model = DataModel("wealth_pipeline_model", label="Wealth Holdings (pipeline)")
wealth_pipeline_model.add_connector(db)
wealth_pipeline_model.add_table("holdings_silver", connector="demo_db", source="holdings_silver")
wealth_pipeline_model.add_table("branches_silver", connector="demo_db", source="branches_silver")
wealth_pipeline_model.add_dimension(
    name="dim_branch", table_name="branches_silver", key_col="branch_id", attributes=["branch", "region"])
wealth_pipeline_model.add_fact(
    name="fact_holdings", table_name="holdings_silver",
    measures=["market_value", "cost_basis", "units"], foreign_keys={"dim_branch": "branch_id"})

_final = FinalLayer(
    model=wealth_pipeline_model, fact="fact_holdings",
    measures={"market_value": "sum", "cost_basis": "sum"}, dimensions=["dim_branch.branch"],
    sink=db, sink_table="gold_aum_by_branch")

# Run history in the state store, as the sales pipeline's (pipeline.py).
runner = PipelineRunner(db_url=state_url())
runner.register(_holdings_landing, name="holdings_bronze", schedule="0 * * * *")
runner.register(_branches_landing, name="branches_bronze", schedule="0 * * * *")
runner.register(_holdings_manip, name="holdings_silver", schedule="15 * * * *", depends_on="holdings_bronze")
runner.register(_branches_manip, name="branches_silver", schedule="15 * * * *", depends_on="branches_bronze")
runner.register(_final, name="aum_by_branch", schedule="30 6 * * *", depends_on="holdings_silver")

# The model this pipeline is about, so the app shows it on that model's Data page: it seeds
# the tables wealth_model reads, lands raw copies of two and aggregates them by branch.
runner.model = "wealth_model"

LAYERS = ["holdings_bronze", "branches_bronze", "holdings_silver", "branches_silver", "aum_by_branch"]


def seed_and_run() -> None:
    """Seed the raw tables and run every layer, upstream first."""
    seed_source_tables()
    for layer in LAYERS:
        runner.run(layer)


if not DURABLE_DB:
    seed_and_run()
