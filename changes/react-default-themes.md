### Changed — a dashboard is an app; themes and a house style

- `tracebi new-report` writes a dashboard as `app.jsx` (the React lane): the
  title, a KPI strip with a lead, a chart beside its ranking, a filterable
  detail, and top tabs or a sidebar when asked. `--html` keeps the
  `template.html` dashboard; `brief` and `tabbed` stay template pages.
- `report.json` `"look"` sets an app's mode and density; `"theme"` names a
  shipped theme (graphite, indigo, midnight, ocean, plum, sand).
  `tracebi theme list` / `tracebi theme use <name>` (writes
  `reports/_theme.css`, the project default).
- `reports/_style.md` is the team's house style: `tracebi init` writes a
  starter, and `tracebi context` / MCP `get_context` return it as
  `house_style` for agents to follow.
- App pages layer `tracebi.css` under Tailwind's utilities, so a utility class
  wins; the kit gains `<Built>`. New lesson `design-app-dashboards`.
