### Added — the Map page

- `web/ui/src/pages/Map.jsx` draws the project as one picture: a band per model
  (transform → warehouse → model → reports), and zoomed into one model, its
  tables, a pill per measure, and the reports that use them. Picking a measure
  or a report lights its whole path and says it in words. Failed, changed and
  never-built states carry a glyph and words, never colour alone. The page is
  not routed yet.
- `GET /api/reports` items carry `measures`: the sorted measure names the
  report's data bindings ask for, read from `report.json` or the spec (no
  warehouse read).
- `GET /api/pipelines` items carry `transform`: the transform a model pipeline
  runs (`null` for a hand-built runner).
