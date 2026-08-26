---
slug: period-over-period
title: Year-over-year is a governed measure, not a self-join in report.py
when: comparing a measure to an earlier period — YoY, QoQ, MoM growth, or the prior period's value
---
**The pitfall.** "Revenue vs the same month last year" is the most-asked
analytic question and the one that most reliably drops into `report.py`: you
pull the series, shift it, join it back to itself, and divide — ungenerated,
ungoverned, `verifiable: false`. Done by hand it is also easy to get subtly
wrong (off-by-one on the shift, misaligned partitions).

**The correct pattern in TraceBi.** Declare period-over-period measures over a
base measure and a `(unit, n)` offset. `offset` gives the prior period's value;
`growth` gives `(current - prior) / prior`:

```python
model.add_time_grain("dim_date", "month", source="order_date", grain="month")
model.add_measure("revenue", column="rev", agg="sum")
model.add_measure("rev_ly",  offset=("revenue", "year", 1))                 # a year ago
model.add_measure("rev_yoy", growth=("revenue", "year", 1), format="percent")  # YoY %

model.query(fact="orders", measures=["revenue", "rev_ly", "rev_yoy"],
            dimensions=["dim_date.month"])       # a YoY column, governed
```

`unit` is a time grain (`year`, `quarter`, `month`, `week`, `day`); YoY is
`("revenue", "year", 1)`, QoQ is `("revenue", "quarter", 1)`, MoM is
`("revenue", "month", 1)`. It works alongside other dimensions — YoY *per
region* — by matching each row to the same region one year back.

**Two things to know.** The query must group by **exactly one declared time
grain** (the period axis). And the comparison is against periods **present in
the result** — so *include* the comparison period rather than filtering it out:
a `filters` (WHERE) restriction to 2024 removes 2023 and leaves nothing to
compare to. To show only the latest period, use `order_by` + `limit` (which run
*after* the shift), not a filter.

**The tell.** Shifting a series and joining it to itself in `report.py` to get
YoY or MoM? That's an `offset`/`growth` measure. (For a running total *to date*
— YTD/QTD — that's a time-ordered cumulative, a different shape: see
[[year-to-date]].)
