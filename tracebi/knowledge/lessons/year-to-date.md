---
slug: year-to-date
title: Year-to-date is a governed cumulative, not a hand-rolled running sum
when: reporting a running total within a period — YTD, QTD, or MTD revenue / units / P&L
---
**The pitfall.** YTD revenue — the total from January through the current month,
resetting each year — is a running sum that has to reset on a period boundary
and stay within each group. Hand-rolled it lands in `report.py` (ungoverned,
`verifiable: false`), and the reset is easy to get wrong: forget the partition
and the total runs across years; forget the ordering and the cumulative is
scrambled.

**The correct pattern in TraceBi.** Declare a `to_date` measure over a base
measure and a reset period:

```python
model.add_time_grain("dim_date", "month", source="order_date", grain="month")
model.add_measure("revenue", column="rev", agg="sum")
model.add_measure("rev_ytd", to_date=("revenue", "year"))     # resets each Jan
model.add_measure("rev_qtd", to_date=("revenue", "quarter"))  # resets each quarter

model.query(fact="orders", measures=["revenue", "rev_ytd"],
            dimensions=["dim_date.month"])   # a YTD column, governed
```

It accumulates the base over the query's time grain, ordered by time, resetting
at the start of each period — so YTD revenue in March is Jan + Feb + March, and
in the next January it starts over. It works alongside other dimensions (YTD
*per region*) by accumulating within each group, and it is deterministic.

The query must group by **exactly one declared time grain**, and that grain must
be **finer than the reset period** — YTD/QTD over a monthly grain is fine; a
month-to-date needs a daily or weekly grain (a month-to-date over monthly data
is just the month's value).

**The tell.** Writing a `groupby(...).cumsum()` with a year partition in
`report.py` for a YTD column? That's a `to_date` measure. (Comparing to an
earlier period instead of accumulating within one — YoY, MoM — is
[[period-over-period]].)
