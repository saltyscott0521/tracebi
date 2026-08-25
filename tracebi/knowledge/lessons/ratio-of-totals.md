---
slug: ratio-of-totals
title: A rate is a ratio of totals, never a mean of ratios
when: computing any rate, percentage, margin, yield, conversion, or per-unit metric
---
**The pitfall.** You want an overall margin, so you average the per-row margins.
That silently overweights small rows: a store with $10 revenue at 90% margin and
a store with $10,000 at 10% margin do **not** average to 50% — the real blended
margin is ~10.1%. `mean` of a ratio is almost always the wrong number, and it
looks completely plausible.

**The correct pattern in TraceBi.** Declare a **ratio measure**. It divides the
*sums* after aggregation — a true ratio of totals — never the mean of per-row
ratios:

```python
model.add_measure("gross_margin", column="gross_margin", agg="sum")
model.add_measure("revenue", column="revenue", agg="sum")
model.add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")
```

`margin_pct` is `sum(gross_margin) / sum(revenue)` at whatever grain you query —
correct at the company level, per region, per month, everywhere.

**The tell.** If you're reaching for `agg="mean"` — or `agg="sum"` — on
something that is itself a rate, %, or "per" quantity, stop. You do not add
rates (summing percentages is meaningless) and you do not average them (it
overweights small rows); you want a ratio of their numerator and denominator.
The framework refuses both by default and points you here; `min`/`max` of a
rate (the widest spread, the lowest yield) stay fine. A `mean` is only right for
a genuinely additive quantity whose typical value you want.

The refusal is not only spelled on the name. A column named nothing like a rate
— `mark_cost`, a fair-value-over-cost ratio sitting near 1.0 — is caught at
query time by its *values*: an additive aggregation of a floating column centred
near 1.0 is refused even when the name matches no rate token. If the column
genuinely is additive, `allow_rate_agg=True` on the measure or the query says so.

**Weighted averages are a ratio too** — see [[weighted-vs-plain-mean]].
