### Changed — reports look like dashboards by default

- `tracebi.css`: refined neutrals and a 12px radius; a `.tb-grid` of
  `.tb-kpi` cells is one KPI strip with hairlines; sentence-case KPI labels;
  panel subtitles (a `.tb-note` after a card's `<h2>`); a table that ends a
  card runs edge to edge; controls sit in one toolbar row; the methodology
  block is a quiet footer; a sidebar (`data-tb-nav="side"`) is a fixed,
  full-height app rail; dark mode uses zinc surfaces and a chart palette
  stepped and validated for the dark ground.
- New: `.tb-kpi--lead` (the strip's main number, twice as wide),
  `.tb-cols-2-1` / `.tb-cols-1-2` (a wide panel beside a narrow one), and
  `.tb-spark` (a line or area chart in a KPI drawn as a zero-based
  sparkline).
- The `dashboard` scaffold, `tracebi init`'s sample and the `--template`
  starters use them; striped tables are no longer the starter default.
