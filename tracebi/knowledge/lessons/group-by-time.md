---
slug: group-by-time
title: Group by month with a declared time grain, not report.py
when: reporting a trend or breakdown over time — by day, week, month, quarter, or year
---
**The pitfall.** You want revenue *by month*, but the model groups by raw
columns only — a timestamp groups by the exact instant, one row each, useless.
So the month rollup gets pre-baked as a column in the transform (a maintenance
burden, one column per grain) or computed in `report.py` (ungoverned,
`verifiable: false`).

**The correct pattern in TraceBi.** Declare a **time grain** on the date
dimension — a governed `date_trunc` referenced like any attribute:

```python
model.add_dimension("dim_date", table_name="dates", key_col="d",
                    attributes=["order_date"])
model.add_time_grain("dim_date", "order_month", source="order_date", grain="month")

model.query(fact="orders", measures=["revenue"],
            dimensions=["dim_date.order_month"])   # revenue by month, with a receipt
```

Grains: `day`, `week`, `month`, `quarter`, `year`. Declare the grains you report
on once; every report groups by them by name, and because `date_trunc` is
deterministic the result is reproducible. A model's declared grains appear under
its dimensions' `derived` in `tracebi context --model`.

**The tell.** Reaching for `report.py`, or adding a `_month`/`_quarter` column to
the transform, just to group by a period? Declare a time grain instead. (A date
grain is also the foundation for period-over-period and cumulative-to-date work.)
