### Changed — every chart is drawn with D3

- The build inlines D3 (not ECharts) for any page with a chart figure, and
  `tracebi.js` draws all six types (bar, barh, line, area, pie, scatter) as
  SVG from the same `data-tb-*` grammar. No markup changes for authors.
- Each chart has a legend that toggles series (never the last one), a tooltip
  on every mark (a crosshair on line and area) showing the row's own value in
  the table's format, arrow-key reading announced to screen readers, animated
  updates when a filter changes (off for reduced motion and print), and a
  click on a bar or slice that sets the page's filter control for that column.
- A chart draws only its rows' own values: no totals, shares or averages.
  Series colours come from the unfiltered rows, so a filter never repaints the
  series that remain.
- A report that lists `"libs": ["echarts"]` keeps the ECharts engine;
  `tracebi.configureChart` applies only there. The `new-report` scaffold and
  compiled specs no longer pin ECharts.
- `tracebi init` scaffolds and both templates no longer pin ECharts.
- Moved to D3: the showcase (its fund palette is now the figure's `palette`),
  `portfolio_overview`, `mrr_dashboard` and `cohort_brief`. `portfolio_book`,
  `portfolio_concentration`, `affordability` and the demo's `aum_by_branch`
  still list ECharts and move next.
- Browser tests: `tests/test_d3_charts.py` (CI `ui-smoke` job).
