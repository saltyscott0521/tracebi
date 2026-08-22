---
slug: weighted-vs-plain-mean
title: A weighted average needs a weight — a plain mean is not one
when: averaging a rate/price/spread across rows of different size (par-weighted spread, VWAP, blended yield)
---
**The pitfall.** You label a measure "weighted average spread" and declare it
`agg="mean"`. A plain mean weights every row equally — a $1M position and a
$1,000 position count the same. That is not a weighted average, and calling it
one is a silent-wrong number with a confident label. (The reference model once
shipped exactly this mistake.)

**The correct pattern in TraceBi.** A weighted average *is* a ratio of totals:
`sum(value × weight) / sum(weight)`. Express the weighted numerator once, then
take a ratio against the total weight:

```python
# par-weighted spread = Σ(spread × par) / Σ(par)
model.add_measure("spread_x_par", expr="spread_bps * par_value", agg="sum")
model.add_measure("par_value", column="par_value", agg="sum")
model.add_measure("wtd_spread_bps", ratio=("spread_x_par", "par_value"))
```

Now `wtd_spread_bps` is correct at every grain, and its name matches its math.

**The tell.** The word "weighted" in a measure's name or description with
`agg="mean"` underneath is always wrong. If it's weighted, there is a weight
column — put it in the math. This is the same shape as [[ratio-of-totals]]; a
weighted mean is just a ratio whose numerator carries the weight.
