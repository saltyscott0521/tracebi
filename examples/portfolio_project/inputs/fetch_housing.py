"""
Refresh inputs/housing_history.csv from the publishers.

    python inputs/fetch_housing.py

One row per complete calendar year, 1979 on, current dollars:

* ``mortgage_rate``   Freddie Mac 30-year fixed, annual mean of the weekly
                      survey (FRED ``MORTGAGE30US``).
* ``existing_price``  An existing-home price level: the FHFA all-transactions
                      repeat-sales index (FRED ``USSTHPI``, quarterly, 1975 on),
                      scaled so its latest twelve months average the same as
                      NAR's median existing-home sales price over those months
                      (FRED ``HOSMEDUSM052N``, which FRED carries for the last
                      thirteen months only). Repeat sales track the same houses
                      over time, so the mix of what sold doesn't move it.
* ``new_home_price``  Census/HUD median sales price of houses sold (FRED
                      ``MSPUS``) — mostly NEW houses, kept to show the gap.
* ``median_income``   Census median household income, current dollars
                      (CPS ASEC table H-5, all races, 1967 on).
* ``earner_income``   Median usual weekly earnings of full-time wage and salary
                      workers × 52 (BLS via FRED ``LEU0252881500A``, 1979 on) —
                      one earner, where household income increasingly counts two.

Needs network access to fred.stlouisfed.org and www2.census.gov; nothing else
in this project does. Writes ``housing_anchor.txt`` beside the CSV recording
the scale that turned the index into dollars.
"""

from __future__ import annotations

import io
import os
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "housing_history.csv")
ANCHOR = os.path.join(HERE, "housing_anchor.txt")
FIRST_YEAR = 1979            # the per-earner series starts here

_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
_H5 = ("https://www2.census.gov/programs-surveys/cps/tables/time-series/"
       "historical-income-households/h05.xlsx")


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _fred(series_id: str) -> pd.Series:
    """One FRED series, indexed by observation date."""
    frame = pd.read_csv(io.BytesIO(_get(_FRED.format(series_id))))
    frame.columns = ["date", "value"]
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.dropna().set_index("date")["value"]


def _annual(series: pd.Series, *, whole_years: bool = True) -> pd.Series:
    """Calendar-year mean; with whole_years, only years with every period."""
    grouped = series.groupby(series.index.year)
    means = grouped.mean()
    if whole_years:
        per_year = grouped.size()
        means = means[per_year >= per_year.max() * 0.9]
    return means


def _household_income() -> pd.Series:
    """Census H-5, all races, median household income in current dollars.

    Some years appear twice (a methodology change); the first row listed is
    the newer method, which is the one kept.
    """
    raw = pd.read_excel(io.BytesIO(_get(_H5)), header=None)
    labels = raw[0].astype(str).str.strip()
    start = labels[labels == "All Races"].index[0] + 1
    out = {}
    for label, median in zip(labels[start:], raw[2][start:]):
        if not label[:4].isdigit():
            if out:                      # the first block (all races) is done
                break
            continue                     # its header rows
        out.setdefault(int(label[:4]), float(median))
    return pd.Series(out).sort_index()


def _existing_price(hpi: pd.Series, nar: pd.Series) -> tuple[pd.Series, str]:
    """Scale the repeat-sales index to NAR's latest twelve months of medians."""
    last12 = nar.sort_index().iloc[-12:]
    monthly_hpi = hpi.resample("MS").ffill().reindex(last12.index, method="ffill")
    scale = last12.mean() / monthly_hpi.mean()
    note = (f"existing_price = FHFA USSTHPI x {scale:.4f}: NAR HOSMEDUSM052N "
            f"averaged ${last12.mean():,.0f} over {last12.index[0]:%b %Y}-"
            f"{last12.index[-1]:%b %Y}; the index averaged {monthly_hpi.mean():.2f}.")
    return _annual(hpi) * scale, note


def main() -> None:
    rate = _annual(_fred("MORTGAGE30US")).round(2)
    existing, note = _existing_price(_fred("USSTHPI"), _fred("HOSMEDUSM052N"))
    new_home = _annual(_fred("MSPUS"))
    earner = _fred("LEU0252881500A") * 52
    earner.index = earner.index.year
    income = _household_income()

    series = {"mortgage_rate": rate, "existing_price": existing.round(-2),
              "new_home_price": new_home.round(-2), "median_income": income,
              "earner_income": earner}
    last = int(min(s.index.max() for s in series.values()))
    years = range(FIRST_YEAR, last + 1)
    out = pd.DataFrame({k: s.reindex(years) for k, s in series.items()})
    out.index.name = "year"
    missing = out[out.isna().any(axis=1)]
    if len(missing):
        raise SystemExit(f"no data for years {list(missing.index)} — not writing")
    for col in ("existing_price", "new_home_price", "median_income", "earner_income"):
        out[col] = out[col].astype(int)
    out.reset_index().to_csv(CSV, index=False)
    with open(ANCHOR, "w", encoding="utf-8") as fh:
        fh.write(note + "\n")
    print(f"wrote {CSV}: {len(out)} years, {out.index.min()}-{out.index.max()}")
    print(note)


if __name__ == "__main__":
    main()
