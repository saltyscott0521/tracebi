"""Escape hatch (architecture §8-M3): a windowed concentration metric.

The declarative query surface produces per-issuer fair value, but not a rank,
a share of total, or a *running cumulative* share — a window over the sorted
result. That is exactly the kind of thing report.py exists for.

``build`` receives the stamped inputs as ``{name: DataFrame}`` (here just
``by_issuer``, a query-reproducible model result) and returns the drawn data
as ``{name: DataFrame}``. The output is python-derived: fingerprinted and
file-checkable, but not reproducible by replaying a query.
"""

from __future__ import annotations

import pandas as pd


def build(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    df = inputs["by_issuer"].copy()
    df = df.rename(columns={
        "dim_issuer.issuer": "issuer",
        "dim_issuer.sector": "sector",
    })
    df = df.sort_values("fair_value", ascending=False).reset_index(drop=True)

    total = df["fair_value"].sum()
    df["rank"] = range(1, len(df) + 1)
    df["pct_of_total"] = (df["fair_value"] / total * 100).round(2)
    # The window the query surface cannot express: a running cumulative share.
    df["cumulative_pct"] = df["pct_of_total"].cumsum().round(2)

    return {"concentration": df[["rank", "issuer", "sector",
                                 "fair_value", "pct_of_total", "cumulative_pct"]]}
