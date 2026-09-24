---
slug: design-kpis-with-context
title: A KPI without a comparison is a number, not a signal — show three to five, each with context
when: adding KPI / value cards to a report, or deciding how many headline numbers to show
---
**The pitfall.** A row of eight KPI cards: "Fair Value $1.7M", "Positions 214",
"Issuers 38"… Each is correct and none can be judged. Is $1.7M good? Up or
down? Against what? Eight of them also means none stands out — the reader's eye
has nowhere to land. This is the signature of generated dashboards: every
available aggregate becomes a card.

**The correct pattern in TraceBi.**

- **Three to five KPIs, chosen for the page's question** (see
  [[design-lead-with-the-answer]]). If it doesn't bear on the answer, it's not a
  headline.
- **Every KPI carries its comparison**, and the comparison is a governed measure,
  not a hand-computed delta:

```python
model.add_measure("fv_prior",  offset=("fair_value", "month", 1))
model.add_measure("fv_growth", growth=("fair_value", "month", 1), format="percent")
```

  Bind both in the card — the value, and "+6.2% vs last month" beneath it in a
  `.tb-kpi-context` line — so the change carries the same receipt as the value.
  Put `data-tb-direction="up-good"` (or `"down-good"` for costs and defaults) on
  the bound change. The runtime then draws an arrow and colors the change good
  or bad from its sign, while the text stays the number. The arrow means the
  reader never has to rely on color alone. Against a target, bind the
  target too; never type it in.
- **Put the unit and the period in the label**: "Fair value · end of Aug", not
  "Fair Value". A KPI whose period is ambiguous gets misquoted.
- **One number per card.** A card listing three figures is a small table — use a
  table figure.

**The tell.** Cover the numbers and read only the labels: if you can't say why
each one is on this page, cut it. If a card has no "vs", the reader can't act on
it. Period-over-period measures are covered in [[period-over-period]].
