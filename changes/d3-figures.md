### Added — figures drawn in code with D3

- `report.json` `"libs": ["d3"]` inlines a D3 7.9.0 subset (153 KB; no
  `d3-dsv` or `d3-fetch`, so nothing needs `eval` or the network). Built from
  `web/ui/d3-bundle.js` (`npm run build:d3`); attribution in `NOTICE`.
- `tracebi.draw(figureId, fn)` draws a `data-tb-figure="custom"` element:
  `fn(surface, rows, theme)` runs once the data is loaded and again whenever
  the figure's rows change (a filter, the search, a selection) or its width
  does. `rows` are copies of the binding's stamped rows as the page's filters
  leave them, so a drawn figure follows the page's controls and can never add
  a number. A figure in a hidden tab draws when the tab is shown.
- `tracebi.theme()` returns the page's resolved tokens (ink, muted, rule, bg,
  surface, accent, good, bad, font, mono, palette), so a drawn figure matches
  the theme.
- The portfolio showcase's Detail tab has a D3 treemap of holdings by sector;
  click a sector to filter the page.
