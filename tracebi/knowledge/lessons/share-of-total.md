---
slug: share-of-total
title: "% of total" is a governed measure, not a report.py computation
when: showing each row's share of the whole — concentration, contribution, weight, mix
---
**The pitfall.** You want "each region's % of total revenue," or "the top 10
positions' share of the book." The share depends on the *query's* result (the
filtered, aggregated rows), so it can't be pre-computed in the transform — and
the model didn't used to express it, so it fell to `report.py`. That stamps the
number `verifiable: false`: it leaves the governed lane and can never read green
under `verify`. A concentration figure with no receipt is the opposite of what
you want.

**The correct pattern in TraceBi.** Declare a **share measure** — it divides each
value by the total of its base measure across the whole result, computed at query
time, governed:

```python
model.add_measure("revenue", column="revenue", agg="sum")
model.add_measure("revenue_share", share="revenue", format="percent")

model.query(fact="sales", measures=["revenue", "revenue_share"],
            dimensions=["dim_region.region"])
# each region's revenue, and its share of TOTAL revenue — with a receipt
```

The share is taken over the **whole** result *before* any `limit`, so "top 10 by
revenue, each showing its share of the grand total" is genuine concentration —
the shown rows' shares sum to less than 100%, and that is correct.

**The tell.** If you're about to compute a percent-of-total, a contribution, or a
concentration in `report.py`, stop — that's a `share` measure. Reach for
`report.py` only when the number genuinely cannot come from a query; a
share-of-total can. `rank` and running/cumulative are governed measures too —
see [[rank-and-cumulative]] for the full concentration table.

The escape hatch is the *transform* for missing structure, or a governed measure
for missing computation — see [[ratio-of-totals]] for the sibling discipline.
