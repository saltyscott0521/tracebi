### Changed — a KPI is a number with a signal

- The lead KPI is larger, not wider: `.tb-kpi--lead` sets its value at
  `--tb-text-3xl` (the others `--tb-text-2xl`) and no longer spans two cells.
  On a phone the strip stacks to one column.
- A KPI's change is a stamped figure of its own. In a template, put
  `<span class="tb-kpi-delta" data-tb-figure="value" … data-tb-direction="up-good">`
  first in the `.tb-kpi-context` line; in an app, `<Kpi … deltaBinding
  deltaCell deltaFormat deltaGood="up|down">`. It shows an arrow, the sign of
  a rise and `--tb-good` / `--tb-bad` from the stamped value; zero is
  neutral. The build records it as a claim (`fig-delta-<binding>-<cell>` in
  an app), refuses a column its binding does not return, and the no-JS view
  shows the same arrow and colour. No comparison measure, no delta.
- A `<Spark>` inside a `<Kpi>` (or a `.tb-spark` in a `.tb-kpi`) sits on the
  card's bottom edge, 32px tall.
- The init sample's fourth card is large orders with the report's own
  large-less-small measure as its delta; `portfolio_overview` shows fair value
  with unrealized (fair value less cost) as its delta, and cost beside it.
