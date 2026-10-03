"""
Phase ② — MODEL. SaaS metrics template.

A star schema over the warehouse phase ① sank. Grain is one row per
account per month, including the churn month and the inactive months
after it, so every account is still present at the latest snapshot.

Ending MRR and customer count are period-end balances: summed across
plans and cohorts, taken at the latest month in the query. They are not
summed across months. Logo churn is logos lost divided by logos at the
start of that same month — a ratio of totals, not a mean of per-account
rates. The cohort dimension is the signup month, so a report can cut
those balances by cohort without treating cohort as the time axis.

    from tracebi.model_registry import get_model
    model = get_model("saas_model")

Next step on your own warehouse: ``tracebi connect <name> --kind ...``,
then re-point the connector and the ``source=`` names below (or draft a
new model with ``tracebi new-model --from``).

Construction is declarative and lazy — importing this file does not
touch the warehouse. Never call model.connect() at import time.
"""

from __future__ import annotations

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")

connector = DuckDBConnector("warehouse", database=WAREHOUSE)

model = (
    DataModel("saas_model")
    .add_connector(connector)
    .add_table("fact_account_month", connector="warehouse",
               source="fact_account_month")
    .add_table("dim_month", connector="warehouse", source="dim_month")
    .add_table("dim_plan", connector="warehouse", source="dim_plan")
    .add_table("dim_cohort", connector="warehouse", source="dim_cohort")
    .add_dimension("dim_month", table_name="dim_month", key_col="month_id",
                   attributes=["month"])
    .add_dimension("dim_plan", table_name="dim_plan", key_col="plan_id",
                   attributes=["plan"])
    .add_dimension("dim_cohort", table_name="dim_cohort", key_col="cohort_id",
                   attributes=["cohort"])
    .add_fact(
        "fact_account_month",
        table_name="fact_account_month",
        measures=["mrr", "active", "churned", "starting"],
        foreign_keys={
            "dim_month": "month_id",
            "dim_plan": "plan_id",
            "dim_cohort": "cohort_id",
        },
    )
    .add_measure(
        "ending_mrr",
        period_end=("mrr", "dim_month.month"),
        description="Ending MRR at the latest month in the query",
        format="currency0",
    )
    .add_measure(
        "customers",
        period_end=("active", "dim_month.month"),
        description="Logos active at the latest month in the query",
        format="comma",
    )
    .add_measure(
        "churned_logos",
        period_end=("churned", "dim_month.month"),
        description="Logos that churned in the latest month of the query",
    )
    .add_measure(
        "starting_logos",
        period_end=("starting", "dim_month.month"),
        description="Logos that were customers at the start of that month",
    )
    .add_measure(
        "logo_churn",
        ratio=("churned_logos", "starting_logos"),
        description=(
            "Logo churn: logos lost / logos at the start of the month "
            "(ratio of totals)"
        ),
        format="percent",
    )
)
