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

**The tell.** If you're reaching for `agg="mean"` on something that is itself a
rate, %, or "per" quantity, stop — you almost certainly want a ratio of its
numerator and denominator instead. A mean is only right for a genuinely additive
quantity you want the typical value of.

**Weighted averages are a ratio too** — see [[weighted-vs-plain-mean]].
