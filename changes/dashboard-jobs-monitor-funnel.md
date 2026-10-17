### Added — monitor and funnel dashboards

- `tracebi new-dashboard --job monitor`: the latest period of every measure
  (up to four) with its sparkline, the series, and a watch list, lowest first.
  Needs a time dimension; without one it starts as a scorecard.
- `tracebi new-dashboard --job funnel`: the fact's count measures as stages,
  widest first, each stage's share of the first declared as a report-level
  ratio in `report.json` `"measures"`, so the receipt names it.

### Fixed

- A report-level measure's `format` now reaches the page: a `"percent"`
  measure declared in `report.json` reads `69.2%`, not `0.69`.

### Added — an app prints every view

- The kit's `usePrinting()` is true while the page prints (Ctrl+P, and
  `tracebi report build --format pdf`, which now dispatches `beforeprint`).
  Scaffolded dashboards with tabs or a sidebar render all their views then, with
  the navigation hidden, so the PDF holds the whole report, not the open view.
