### Fixed — a model's pages show everything that belongs to it

- `GET /api/reports` returns `models` for each report: the models its data
  bindings read, by the name the app lists. Reports, Runs and the attention
  strip use it, so a report filed in a folder named unlike its model (the
  demo app's are) still appears under that model.
- Live discovery forgot reports an app module registered from its own folder
  about five seconds after the server started (the demo app's vanished). It
  now forgets only what its own scan covers.
- Diagram, Refresh and search colours are theme tokens, readable in dark mode.
- `scripts/ui_audit.py` checks that each model's Reports and Sources list
  exactly what the API says it owns, that no report reads a model the
  switcher doesn't list, that nothing appears or vanishes mid-audit, and that
  the bundle and hard-coded colour count never grow.
