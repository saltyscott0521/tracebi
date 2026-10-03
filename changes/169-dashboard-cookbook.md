### Added — dashboard cookbook

- `tracebi new-report "Name" --layout brief|dashboard|tabbed` writes a named
  page structure. `brief` is one finding (answer sentence, KPIs, one chart).
  `dashboard` is that plus a chart beside a filterable table — still the
  default when the flag is omitted, and still what `tracebi init` writes.
  `tabbed` is the same header, then Overview and Detail tabs.
- `tracebi context` lists the three recipes under `presentation.layout`, and
  the `author_report` prompt names them so an agent picks the one that fits
  (`dashboard` by default) instead of designing one. Ask only when a person
  is in the loop and the choice is not obvious. With only the gateway, write
  `template.html` from that recipe's pieces.
