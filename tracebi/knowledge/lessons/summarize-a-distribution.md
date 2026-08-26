---
slug: summarize-a-distribution
title: A mean hides skew and tails — use median and stddev
when: reporting the "average" of returns, P&L, position size, spread, latency, or anything with outliers
---
**The pitfall.** You report the *average* P&L per desk. One desk has a single
$500 outlier among values around $11 — its "average" comes out $133, a number
that describes none of its days. The mean is dragged by outliers and skew, and
most real financial and operational data (returns, position sizes, spreads,
latencies) is skewed. A mean of a skewed distribution is a confident, misleading
summary.

**The correct pattern in TraceBi.** Summarize the *shape*, not just the centre:

```python
model.add_measure("median_pnl", column="pnl", agg="median")   # the honest centre
model.add_measure("stddev_pnl", column="pnl", agg="stddev")   # the dispersion
model.add_measure("mean_pnl",   column="pnl", agg="mean")      # keep it, but read it with the others
```

`median` is robust to the outlier the mean chases; `stddev` tells you how spread
out the values are. Report them together — a mean beside a median that's far
below it is itself the signal that the distribution is skewed.

**When the tail is the point, report the tail.** Risk lives in the worst marks,
the largest drawdowns, the slowest requests — which a mean *and* a median both
hide. Percentile aggregations spell it `p<N>` (`p50` is the median):

```python
model.add_measure("p90_mark", column="mark", agg="p90")   # 90th percentile
model.add_measure("p99_mark", column="mark", agg="p99")   # the deep tail
```

Any `p0`–`p100`, interpolated and deterministic. `p95`/`p99` are the fund-ops
tail-risk view; `p90`/`p95` the latency SLO view.

**The tell.** If you're about to report "average X" for anything that can have a
few large values — trade sizes, returns, balances, response times — pause. The
mean alone is almost never the honest summary of a skewed quantity; lead with the
median, show the spread, and report a `p95`/`p99` when the tail is what matters.

Not to be confused with a *rate* — a mean of a per-row rate is a different
mistake; see [[ratio-of-totals]].
