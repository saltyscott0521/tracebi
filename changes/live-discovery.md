### Added — the server picks up new reports without a restart

- Live discovery: every `TRACEBI_DISCOVERY_INTERVAL` seconds (default 5)
  the web server rescans `reports/` and `models/`. A report package or spec
  added to a running server appears on the Reports page, a deleted one
  disappears, and a new model or pipeline file is registered. A broken package is
  retried when its files change. `0` turns it off. Python report modules
  are still found only at startup.
