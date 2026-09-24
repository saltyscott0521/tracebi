### Added — report-design lessons and the `tracebi-designer` skill

- Thirteen `design-` lessons in the knowledge base, delivered the same way as the
  analyst lessons (`tracebi knowledge`, `tracebi context`, MCP): lead with the
  answer, KPIs with context, choose the chart for the question, color with
  meaning, format for reading, fewer columns with search first, plan every
  state, cut the chrome, show the difference, honest axes, layout by
  importance, consistency over variety, and accessible by default — grounded
  in Stephen Few's dashboard pitfalls, Tufte's graphical integrity, the IBCS
  standard and WCAG contrast, and checked against what TraceBi actually does.
- `skills/tracebi-designer/SKILL.md`, the design counterpart to
  `tracebi-analyst`: an eight-step review pass for any report page, and the rule
  that presentation never changes a number.
- Spec validation checks design. `ReportSpec.validate()` (so `tracebi spec
  validate`, the MCP `validate_report_spec` tool and `POST /api/spec/validate`)
  now warns, with a path and the lesson to read, on unsorted bar charts, pies
  not limited to five parts, more than five lines on a chart, more than five
  KPI cards, tables wider than six columns with no `columns` list, palettes
  over six colors, and emoji in titles or text. Warnings only — a valid spec
  is never refused for design. The reference `portfolio_dashboard.json` now
  names its table's five columns, the one check it tripped.
- The showcase report is rebuilt through the new review: a headline that
  states the finding, KPIs with context, and the decorative chrome removed.

