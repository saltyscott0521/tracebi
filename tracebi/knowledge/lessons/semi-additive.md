---
slug: semi-additive
title: Sum a balance across funds, not across time — declare a period_end measure
when: reporting a point-in-time balance — AUM, NAV, headcount, inventory, shares outstanding — over time
---
**The pitfall.** AUM (assets under management) is a *stock*: a level measured at
a point in time, not a flow that accumulates. Declare it as a plain sum —
`add_measure("aum", column="balance", agg="sum")` — and "AUM by month" returns
January's balance **plus** February's balance **plus** March's. That is not
assets under management; it is a triple-count of the same money. The number is
confidently wrong, fully lineaged, and reads green. This is the classic
semi-additive trap, and it is the reason a real fund-ops book so often spills
into an ungoverned `report.py`.

A balance is **additive across ordinary dimensions** — total AUM across funds is
the sum of each fund's AUM — but **not additive across time**: over time you take
the *latest* snapshot, never the sum.

**The correct pattern in TraceBi.** Declare a **semi-additive** measure with
`period_end=(value_column, "dim_date.date_attr")`:

```python
model.add_measure("aum", period_end=("balance", "dim_date.as_of_date"))

model.query(fact="snapshots", measures=["aum"],
            dimensions=["dim_fund.fund"])          # each fund's latest balance
model.query(fact="snapshots", measures=["aum"],
            dimensions=["dim_date.month"])         # month-end AUM, a real series
model.query(fact="snapshots", measures=["aum"])    # total AUM at the latest snapshot
```

Within each group the measure sums the balance at the group's **latest snapshot
date** and never across snapshots — so it is summed across funds and taken at
period-end over time, in one governed query with a receipt. Pair it with a
[[group-by-time]] grain to get the period-end series.

It assumes entities snapshot on common dates (the month-end convention). Where
funds carry different latest dates, a per-entity variant is future work.

**The guardrail.** Because summing a stock is a silent-wrong number, declaring a
plain `agg="sum"` on a stock-named measure (`aum`, `nav`, `balance`,
`headcount`, `inventory`) is **refused** at definition time — it points you at
`period_end`. If the column is genuinely a flow (a *change* in balance, a
deposit, a trade), pass `allow_additive=True` to say so. Summing across
dimensions is never the problem; summing across time is. See also
[[grain-and-fanout]] for the other silent-inflation trap.

**The tell.** A measure named like a balance, aggregated with `sum`, reported
over a time axis? It is almost certainly a double-count. Declare it `period_end`.
