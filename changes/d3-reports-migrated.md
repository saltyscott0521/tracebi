### Changed — every reference report draws with D3

- `portfolio_book`, `portfolio_concentration`, `affordability` and the demo
  app's `aum_by_branch` no longer list ECharts. Their `configureChart` and
  raw `echarts.init` code is replaced by chart attributes: stack, palette,
  marks, axis titles. Nothing in the repo uses ECharts now; it stays
  available to a report that lists `"libs": ["echarts"]`.
- `portfolio_book`'s `by_sector` query orders by fair value (descending), so
  the largest sector draws first. The ordering is in the stamped query, not
  in script.js.

### Added — `data-tb-unit`, and short currency ticks

- `data-tb-unit="%"` puts a suffix after every value, tick and mark of a
  chart. It is text only and never rescales the number. Use it for a rate
  stored as 6.81 meaning 6.81%; the `percent` format would multiply by 100.
- Axis ticks for `currency` / `currency0` charts are compact with the sign
  (`$20M`). Tooltips and marks keep the full format.
