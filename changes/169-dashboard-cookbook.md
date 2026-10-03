### Added — dashboard cookbook

- `tracebi new-report "Name" --layout brief|dashboard|tabbed` writes a named
  page structure. `brief` is one finding (answer sentence, KPIs, one chart).
  `dashboard` is that plus a chart beside a filterable table — still the
  default when the flag is omitted, and still what `tracebi init` writes.
  `tabbed` is the same header, then Overview and Detail tabs.
- `tracebi context` lists the three recipes under `presentation.layout`, and
  the `author_report` prompt offers them so an agent asks which structure
  instead of designing one.
