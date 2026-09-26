"""
Refresh inputs/housing_history.csv from the official series on FRED.

    python inputs/fetch_data.py

Pulls the 30-year mortgage rate (MORTGAGE30US, weekly), the median sales
price of houses sold (MSPUS, quarterly) and median household income
(MEHOINUSA646N, annual, from 1984), averages each to calendar years, and
rewrites the CSV. Years before 1984 keep the snapshot's income, because the
FRED income series starts in 1984 (the Census H-8 table goes back further).
Needs network access to fred.stlouisfed.org; nothing else in this project
does.
"""

from __future__ import annotations

import io
import os
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "housing_history.csv")
FIRST_YEAR = 1971

_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def _series(series_id: str) -> pd.Series:
    """Annual mean of one FRED series, indexed by year."""
    with urllib.request.urlopen(_FRED.format(series_id), timeout=60) as resp:
        frame = pd.read_csv(io.BytesIO(resp.read()))
    date_col, value_col = frame.columns[0], frame.columns[1]
    frame[value_col] = pd.to_numeric(frame[value_col], errors="coerce")
    frame["year"] = pd.to_datetime(frame[date_col]).dt.year
    return frame.dropna().groupby("year")[value_col].mean()


def main() -> None:
    old = pd.read_csv(CSV).set_index("year")
    rate = _series("MORTGAGE30US").round(2)
    price = _series("MSPUS").round(-2)
    income = _series("MEHOINUSA646N").round(0)

    # Complete calendar years only: the latest year is dropped until every
    # series has a full year of data.
    last = int(min(rate.index.max(), price.index.max(), income.index.max()))
    years = range(FIRST_YEAR, last + 1)
    out = pd.DataFrame({"year": list(years)}).set_index("year")
    out["mortgage_rate"] = rate.reindex(years)
    out["median_price"] = price.reindex(years)
    out["median_income"] = income.reindex(years)
    kept = out["median_income"].isna()
    out.loc[kept, "median_income"] = old["median_income"].reindex(out.index[kept])
    if kept.any():
        first, final = out.index[kept].min(), out.index[kept].max()
        print(f"kept snapshot income for {first}-{final} "
              "(FRED MEHOINUSA646N starts in 1984; source: Census table H-8)")
    missing = out[out.isna().any(axis=1)]
    if len(missing):
        raise SystemExit(f"no data for years {list(missing.index)} — not writing")
    out["median_price"] = out["median_price"].astype(int)
    out["median_income"] = out["median_income"].astype(int)
    out.reset_index().to_csv(CSV, index=False)
    print(f"wrote {CSV}: {len(out)} years, {out.index.min()}-{out.index.max()}")


if __name__ == "__main__":
    main()
