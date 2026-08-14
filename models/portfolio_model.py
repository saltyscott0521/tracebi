"""
Phase ② — MODEL.

A star schema over the warehouse phase ① sank into. This file is the
*contract*: it names the grain, the keys, and the measures, in a few dozen
declarative lines a reviewer can read without ever opening the pandas that
produced the tables. It reads the warehouse; it does not build it.

    from tracebi.model_registry import get_model
    model = get_model("portfolio_model")

The web server auto-discovers this file. Construction is declarative and lazy —
importing it does not touch the warehouse, so it loads fine before phase ① has
ever run; a query is what reads the file.
"""

from __future__ import annotations

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")

# The connector points at the file phase ① wrote. Exposed at module scope so the
# web app can surface it on the Connectors page.
connector = DuckDBConnector("warehouse", database=WAREHOUSE)

model = (
    DataModel("portfolio_model")
    .add_connector(connector)
    # tables ← the exact names phase ① sank
    .add_table("fact_holdings", connector="warehouse", source="fact_holdings")
    .add_table("dim_fund", connector="warehouse", source="dim_fund")
    .add_table("dim_issuer", connector="warehouse", source="dim_issuer")
    # dimensions
    .add_dimension("dim_fund", table_name="dim_fund", key_col="fund_id",
                   attributes=["fund"])
    .add_dimension("dim_issuer", table_name="dim_issuer", key_col="issuer_id",
                   attributes=["issuer", "sector"])
    # fact ← keyed to both dimensions
    .add_fact("fact_holdings", table_name="fact_holdings",
              measures=["par", "cost", "fair_value", "spread_bps"],
              foreign_keys={"dim_fund": "fund_id", "dim_issuer": "issuer_id"})
    # measures ← the vocabulary a dashboard queries by name
    .add_measure("fair_value", column="fair_value", agg="sum",
                 description="Total fair value", format="currency0")
    .add_measure("cost_basis", column="cost", agg="sum",
                 description="Total cost basis", format="currency0")
    .add_measure("par_amount", column="par", agg="sum",
                 description="Total par", format="currency0")
    .add_measure("positions", column="holding_id", agg="count",
                 description="Position count")
    .add_measure("unrealized", expr="fair_value - cost", agg="sum",
                 description="Unrealized gain / loss", format="currency0")
    .add_measure("avg_spread_bps", column="spread_bps", agg="mean",
                 description="Weighted avg spread (bps)")
    .add_measure("mark", ratio=("fair_value", "cost_basis"),
                 description="Fair value / cost", format="percent")
)
