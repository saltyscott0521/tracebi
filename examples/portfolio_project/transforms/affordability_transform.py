# %% [markdown]
# # Phase ① — TRANSFORM: what a median home cost to finance, year by year
#
# Reads the annual series in `inputs/housing_history.csv` (rate, median
# price, median income) and works out, for each year, the monthly payment on
# the median home and how much of the median household's income it took.
# Then it SINKS a small star schema into the warehouse.
#
# Assumptions, stated once and carried into the report's methodology:
# 20% down, a 30-year fixed loan at that year's average rate, principal and
# interest only (no taxes, insurance or PMI).
#
#     python transforms/affordability_transform.py
#
# Idempotent: rerun any time; it replaces the warehouse tables.

# %%
from __future__ import annotations

import os

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.contracts import contract

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "inputs", "housing_history.csv")
# Its own warehouse file: the housing tables stay out of the portfolio
# warehouse and its contract.
WAREHOUSE = os.path.join(ROOT, "data", "housing.duckdb")

DOWN_PAYMENT = 0.20
TERM_YEARS = 30


# %%
def monthly_payment(rate_pct: pd.Series, loan: pd.Series, years: int) -> pd.Series:
    """Level monthly payment on a fully amortizing loan (principal + interest)."""
    r = rate_pct / 100 / 12
    n = years * 12
    return loan * r / (1 - (1 + r) ** -n)


# %%
def run() -> dict:
    raw = pd.read_csv(RAW)
    df = raw.sort_values("year").drop_duplicates("year").reset_index(drop=True)

    df["loan_amount"] = df["median_price"] * (1 - DOWN_PAYMENT)
    df["monthly_payment"] = monthly_payment(df["mortgage_rate"], df["loan_amount"],
                                            TERM_YEARS).round(2)
    df["annual_payment"] = df["monthly_payment"] * 12

    dim_year = pd.DataFrame({
        "year_id": df["year"],
        "year": df["year"],
        "decade": (df["year"] // 10 * 10).astype(str) + "s",
    })
    fact = df[["year", "mortgage_rate", "median_price", "median_income",
               "loan_amount", "monthly_payment", "annual_payment"]].rename(
        columns={"year": "year_id"})

    os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
    wh = DuckDBConnector("housing_warehouse", database=WAREHOUSE)
    wh.write(dim_year, "dim_year")
    wh.write(fact, "fact_housing")

    with contract(
        "affordability", warehouse=WAREHOUSE,
        note="one row per year from inputs/housing_history.csv (Freddie Mac "
             "30-year average rate, Census/HUD median sales price, Census "
             "median household income, current dollars); monthly payment is "
             "principal and interest on the median price with 20% down over "
             "30 years at that year's average rate — no taxes, insurance or PMI",
    ) as c:
        c.rows("fact_housing", at_least=40,
               note="the series starts in 1971; fewer rows means a truncated pull")
        c.unique("dim_year", ["year_id"])
        c.not_null("fact_housing", ["year_id", "mortgage_rate", "median_price",
                                    "median_income", "monthly_payment"])
        c.foreign_key("fact_housing", "year_id", refers_to=("dim_year", "year_id"))

    return {"years": len(fact), "first": int(df["year"].min()),
            "last": int(df["year"].max())}


# %%
if __name__ == "__main__":
    print(run())
