### Fixed — provenance badges on inline values no longer stack in the page corner

- A number bound inside a sentence (a `value` figure, a span) has no positioned
  box, so its absolute `REPRODUCIBLE` badge escaped to the page's top-right
  corner. Every inline value's badge landed on the same spot and they overlapped
  each other there. Inline value badges now sit beside the number they mark.
- Block figures (KPI cards, charts, tables) keep their corner and table-row
  placement. The badge text, its colour and when it appears are unchanged.
