---
slug: design-show-the-difference
title: When the question is "how far off?", show the difference itself, not two things to subtract
when: comparing actual to budget, target, forecast or a prior period — in a KPI or a chart
---
**The pitfall.** Two lines — actual and budget — on one chart, or two cards
reading "$76,934" and "$85,000". The reader's real question is *how far off are
we*, and the page makes them do the subtraction in their head, week by week.
Small gaps vanish between two close lines; large ones are hard to size. This is
one of the classic dashboard mistakes: expressing a measure *indirectly*.

**The correct pattern in TraceBi.** Make the difference the thing you plot or
bind, as a governed measure — never a number computed in `script.js`:

- **Against a prior period:** `growth=("revenue", "month", 1)` gives
  (current − prior) / prior directly; `offset` gives the prior value when you
  also need it. See [[period-over-period]].
- **Against a budget or target in the data:** declare the variance as a ratio
  of totals so it stays correct at every grain:

```python
model.add_measure("variance",     expr="actual - budget", agg="sum")
model.add_measure("variance_pct", ratio=("variance", "budget"), format="percent")
```

- **Chart the variance, around zero.** A bar or line of `variance_pct`, one
  point per period or per unit, reads instantly: above zero is ahead, below is
  behind. Bars also compare fairly across units of different size — a small
  team 20% over budget stands out even when a large one is further over in
  dollars.
- **Percent for comparing across different sizes, amount for sizing the
  impact.** Show the percent on the chart; put the amount in the table beneath
  or in the tooltip.

**The tell.** If the page shows two numbers and the reader's first move would be
to subtract them, bind the difference instead. Headline KPIs work the same way —
see [[design-kpis-with-context]].
