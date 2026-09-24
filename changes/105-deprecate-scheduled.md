### Deprecated — registry.scheduled() never ran reports

- `@registry.scheduled` and `@register.scheduled` warn and still register
  the report. `tracebi init` no longer creates `scheduled/`. An existing
  `scheduled/` folder is still imported, and a script in it logs one
  deprecation line. Schedules belong in a package's `report.json`
  `"schedule"` block (`tracebi schedule`).
