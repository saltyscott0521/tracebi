"""
Phase ② — MODEL: housing affordability, one row per year.

The grain is a calendar year. Each measure is that year's figure; across
several years the plain measures (rate, price, income, payment) are simple
means, and the two shares are ratios of totals.

    from tracebi.model_registry import get_model
    model = get_model("housing_model")
"""

from __future__ import annotations

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")

connector = DuckDBConnector("warehouse", database=WAREHOUSE)

model = (
    DataModel("housing_model")
    .add_connector(connector)
    .add_table("fact_housing", connector="warehouse", source="fact_housing")
    .add_table("dim_year", connector="warehouse", source="dim_year")
    .add_dimension("dim_year", table_name="dim_year", key_col="year_id",
                   attributes=["year", "decade"])
    .add_fact("fact_housing", table_name="fact_housing",
              measures=["mortgage_rate", "median_price", "median_income",
                        "monthly_payment", "annual_payment"],
              foreign_keys={"dim_year": "year_id"})
    # One row per year, so per year this is that year's published average.
    # Across years it is a plain mean of annual averages, which is what a
    # "rate over the decade" line should show: there is no loan volume here
    # to weight by. Hence allow_rate_agg.
    .add_measure("mortgage_rate", column="mortgage_rate", agg="mean",
                 description="30-year fixed rate, annual average, in percent",
                 format="decimal", allow_rate_agg=True)
    .add_measure("median_price", column="median_price", agg="mean",
                 description="Median sales price of houses sold",
                 format="currency0")
    .add_measure("median_income", column="median_income", agg="mean",
                 description="Median household income", format="currency0")
    .add_measure("monthly_payment", column="monthly_payment", agg="mean",
                 description="Monthly principal and interest on the median "
                             "home: 20% down, 30 years, that year's average rate",
                 format="currency0")
    .add_measure("annual_payment_total", column="annual_payment", agg="sum",
                 description="Twelve monthly payments")
    .add_measure("income_total", column="median_income", agg="sum",
                 description="Median household income, summed")
    .add_measure("price_total", column="median_price", agg="sum",
                 description="Median price, summed")
    .add_measure("payment_share", ratio=("annual_payment_total", "income_total"),
                 description="A year of payments as a share of median "
                             "household income", format="percent")
    .add_measure("price_to_income", ratio=("price_total", "income_total"),
                 description="Median price as a multiple of median household "
                             "income", format="decimal")
)
