"""
Phase ② — MODEL: housing affordability, the two-part test.

Two facts over one year dimension:

* ``fact_housing`` — one row per year: rate, prices, incomes, and what the
  median existing home took to get into (``entry_cost``) and to carry
  (``payment``: principal, interest, property tax, insurance).
* ``fact_cohort_path`` — one row per buyer per year owned (up to ten): what
  that year's buyer was paying, after any refinance, against that later
  year's income. ``dim_cohort.bought`` is the purchase year and
  ``dim_held.years_owned`` how long they had owned it.

Across several years the plain measures are simple means; every share is a
ratio of totals, so a multi-year share is never a mean of shares.

    from tracebi.model_registry import get_model
    model = get_model("housing_model")
"""

from __future__ import annotations

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "housing.duckdb")

connector = DuckDBConnector("housing_warehouse", database=WAREHOUSE)

model = (
    DataModel("housing_model")
    .add_connector(connector)
    .add_table("fact_housing", connector="housing_warehouse", source="fact_housing")
    .add_table("fact_cohort_path", connector="housing_warehouse", source="fact_cohort_path")
    .add_table("dim_year", connector="housing_warehouse", source="dim_year")
    .add_table("dim_cohort", connector="housing_warehouse", source="dim_cohort")
    .add_table("dim_held", connector="housing_warehouse", source="dim_held")
    .add_dimension("dim_year", table_name="dim_year", key_col="year_id",
                   attributes=["year", "decade"])
    .add_dimension("dim_cohort", table_name="dim_cohort", key_col="cohort_id",
                   attributes=["bought"])
    .add_dimension("dim_held", table_name="dim_held", key_col="held_id",
                   attributes=["years_owned"])
    .add_fact("fact_housing", table_name="fact_housing",
              measures=["mortgage_rate", "existing_price", "new_home_price",
                        "median_income", "earner_income", "payment", "entry_cost"],
              foreign_keys={"dim_year": "year_id"})
    .add_fact("fact_cohort_path", table_name="fact_cohort_path",
              measures=["annual_payment", "median_income", "rate_held"],
              foreign_keys={"dim_year": "year_id", "dim_cohort": "cohort_id",
                            "dim_held": "held_id"})
    # One row per year, so per year this is that year's published average.
    # Across years it is a plain mean of annual averages: there is no loan
    # volume here to weight by. Hence allow_rate_agg.
    .add_measure("mortgage_rate", column="mortgage_rate", agg="mean",
                 description="30-year fixed rate, annual average, in percent",
                 format="decimal", allow_rate_agg=True)
    .add_measure("existing_price", column="existing_price", agg="mean",
                 description="Median existing-home price (FHFA repeat-sales "
                             "index scaled to NAR's median)", format="currency0")
    .add_measure("new_home_price", column="new_home_price", agg="mean",
                 description="Census/HUD median price of houses sold, mostly new",
                 format="currency0")
    .add_measure("median_income", column="median_income", agg="mean",
                 description="Median household income", format="currency0")
    .add_measure("earner_income", column="earner_income", agg="mean",
                 description="Median full-time earner's pay (weekly x 52)",
                 format="currency0")
    .add_measure("payment", column="payment", agg="mean",
                 description="Monthly principal, interest, property tax and "
                             "insurance on the median existing home, 20% down",
                 format="currency0")
    .add_measure("entry_cost", column="entry_cost", agg="mean",
                 description="Cash to close: 20% down plus 3% closing costs",
                 format="currency0")
    .add_measure("annual_payment_total", column="annual_payment", agg="sum",
                 description="Twelve monthly payments")
    .add_measure("annual_pi_total", column="annual_pi", agg="sum",
                 description="Twelve months of principal and interest only")
    .add_measure("entry_total", column="entry_cost", agg="sum",
                 description="Cash to close, summed")
    .add_measure("income_total", column="median_income", agg="sum",
                 description="Median household income, summed")
    .add_measure("earner_total", column="earner_income", agg="sum",
                 description="Full-time earner's pay, summed")
    .add_measure("price_total", column="existing_price", agg="sum",
                 description="Existing-home price, summed")
    .add_measure("payment_share", ratio=("annual_payment_total", "income_total"),
                 description="A year of full payments as a share of median "
                             "household income", format="percent")
    .add_measure("pi_share", ratio=("annual_pi_total", "income_total"),
                 description="Principal and interest only, as a share of "
                             "income: the narrow measure", format="percent")
    .add_measure("earner_share", ratio=("annual_payment_total", "earner_total"),
                 description="A year of full payments as a share of one "
                             "full-time earner's pay", format="percent")
    .add_measure("entry_share", ratio=("entry_total", "income_total"),
                 description="Cash to close as a share of a year's median "
                             "household income", format="percent")
    .add_measure("price_to_income", ratio=("price_total", "income_total"),
                 description="Existing-home price as a multiple of median "
                             "household income", format="decimal")
    # On fact_cohort_path the same payment_share reads a buyer's payment in a
    # later year against THAT year's income, so rising incomes and refinances
    # both show.
    .add_measure("rate_held", column="rate_held", agg="mean",
                 description="The rate the buyer holds that year, after any "
                             "refinance", format="decimal", allow_rate_agg=True)
)
