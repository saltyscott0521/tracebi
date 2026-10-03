"""
Phase ② — MODEL. Sales pipeline template.

A star schema over the warehouse phase ① sank. Grain is one row per
opportunity. Stage, rep, and region are the cuts.

Open pipeline value is the sum of amounts still in an open stage. Won
and lost deals contribute zero, so the total is not a sum of every
deal's original amount. Win rate is won deals divided by closed deals
(won plus lost) — a ratio of those totals. It is not the mean of
per-rep win rates, which would weight a rep with one close the same as
a rep with many.

    from tracebi.model_registry import get_model
    model = get_model("sales_pipeline_model")

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
    DataModel("sales_pipeline_model")
    .add_connector(connector)
    .add_table("fact_opportunity", connector="warehouse",
               source="fact_opportunity")
    .add_table("dim_stage", connector="warehouse", source="dim_stage")
    .add_table("dim_rep", connector="warehouse", source="dim_rep")
    .add_table("dim_region", connector="warehouse", source="dim_region")
    .add_dimension("dim_stage", table_name="dim_stage", key_col="stage_id",
                   attributes=["stage"])
    .add_dimension("dim_rep", table_name="dim_rep", key_col="rep_id",
                   attributes=["rep"])
    .add_dimension("dim_region", table_name="dim_region", key_col="region_id",
                   attributes=["region"])
    .add_fact(
        "fact_opportunity",
        table_name="fact_opportunity",
        measures=["amount", "pipeline_amount", "won", "closed", "won_amount"],
        foreign_keys={
            "dim_stage": "stage_id",
            "dim_rep": "rep_id",
            "dim_region": "region_id",
        },
    )
    .add_measure(
        "pipeline_value",
        column="pipeline_amount",
        agg="sum",
        description="Open pipeline: sum of amounts on deals still open",
        format="currency0",
    )
    .add_measure(
        "won_deals",
        column="won",
        agg="sum",
        description="Deals with status won",
    )
    .add_measure(
        "closed_deals",
        column="closed",
        agg="sum",
        description="Deals closed won or lost; the win-rate denominator",
    )
    .add_measure(
        "won_value",
        column="won_amount",
        agg="sum",
        description="Amount on won deals",
        format="currency0",
    )
    .add_measure(
        "win_rate",
        ratio=("won_deals", "closed_deals"),
        description=(
            "Win rate: won deals / closed deals "
            "(ratio of totals, not a mean of per-rep rates)"
        ),
        format="percent",
    )
)
