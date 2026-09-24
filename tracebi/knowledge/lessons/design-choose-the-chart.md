---
slug: design-choose-the-chart
title: Pick the chart for the question, and sort it so the answer is visible
when: choosing a chart_type / data-tb-type for a figure
---
**The pitfall.** Chart type chosen for variety — a pie here, a donut there, an
area chart because the last one was a bar. Readers then decode each chart
differently, and the comparison the page is about is hard to see. Pies with
nine slices, bars in alphabetical order, and a line through categories that
have no order are the usual results.

**The correct pattern in TraceBi.** Choose from the question, not the menu
(`bar`, `barh`, `line`, `area`, `pie`, `scatter`):

| The question | Chart | Setting in TraceBi |
| --- | --- | --- |
| Which is biggest? Compare categories | `barh` (long labels) or `bar` | sort in the query: `"order_by": ["-fair_value"]` |
| How did it change over time? | `line` | group by a time grain (`add_time_grain`), order ascending |
| What's the mix of a whole? | `bar` sorted; `pie` only with ≤ 5 parts | a `share` measure gives the % |
| Do two measures move together? | `scatter` | x and y are both measures |
| Top N | `barh`, sorted, limited | `order_by` + `limit` in the query |

- **Sort in the query, never in the chart or script.js.** An unsorted bar chart
  hides its own answer, and sorting in the browser moves ordering out of the
  receipt.
- **One measure per axis.** No dual axes: two scales on one chart invite the
  reader to compare heights that aren't comparable. Use two charts side by side
  (`.tb-cols-2`).
- **Pie is for 2–5 parts of a positive whole.** TraceBi refuses negative values
  in a pie; past five slices, use sorted bars.
- **Lines need an ordered axis** — time, or an ordered band. Categories without
  an order are bars.
- **Many series? Small multiples, not spaghetti.** Past about five lines on one
  chart, nobody can follow any of them. Show one small chart per group, side by
  side on the same measure (`.tb-cols-3`), or show only the series that matter
  in color and the rest in grey ([[design-color-with-meaning]]).

**The tell.** If the reader has to hover to learn which bar is largest, the chart
isn't sorted. If the legend has more than five entries, it's the wrong chart.
See [[design-color-with-meaning]] for highlighting the bar that matters.
