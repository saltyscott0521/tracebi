---
slug: group-by-band
title: Group by a value band with declared bins, not report.py
when: bucketing a numeric attribute into ranges — score bands, age brackets, size tiers, vintage decades
---
**The pitfall.** You want balances *by credit-score band*, but the model groups
by raw columns only — grouping by `credit_score` gives one row per distinct
score, useless. So the band gets pre-baked as a column in the transform (a
maintenance burden, and every new cut is a schema change) or computed in
`report.py` (ungoverned, `verifiable: false`), out of the receipted lane.

**The correct pattern in TraceBi.** Declare **value bins** on the dimension — a
governed CASE over ranges, referenced like any attribute:

```python
model.add_dimension("dim_customer", table_name="customers", key_col="id",
                    attributes=["credit_score"])
model.add_value_bins("dim_customer", "score_band",
                     source="credit_score", edges=[600, 700, 800])

model.query(fact="loans", measures=["balance"],
            dimensions=["dim_customer.score_band"])   # by band, with a receipt
```

`N` edges make `N+1` bands — below the first, between each pair, and at/above
the last: `[600, 700, 800]` gives `< 600`, `600–700`, `700–800`, `≥ 800`. Pass
`labels=[...]` (one per band) for your own names. A NULL source groups as NULL,
never the top band, and because a CASE is deterministic the result is
reproducible.

Two things to know: bands sort **lexicographically by label**, so pick labels
that sort if magnitude order matters (or order by a measure). And bins are
**groupable, not filterable** — filter on the source column, group by the band.

**The tell.** Adding a `_band` / `_bracket` / `_tier` column to the transform,
or a CASE in `report.py`, just to bucket a number for a group-by? Declare value
bins instead. (Bucketing a *date* is a time grain — see [[group-by-time]].)
