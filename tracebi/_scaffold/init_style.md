# House style

Your team's design rules for reports, read by every agent before it builds a
page (`tracebi context` and the MCP `get_context` return this file as
`house_style`). Write only what differs from TraceBi's defaults — they are
already in the agent's context, so repeating them changes nothing. Keep it
short.

## Rules

None yet: the defaults apply. Add one rule per line here.

## Examples — not rules until you move them up

- Theme: `tracebi theme use ocean` (the project default, `reports/_theme.css`).
- Dashboards are apps (`app.jsx`) with a left sidebar; briefs and anything
  emailed stay `template.html`.
- Titles name the decision, not the data: "Is churn under 3%?", not "Churn".
- Money in whole units (`currency0`) on KPI cards; cents only in tables.
- Every KPI states its period and comparison in its context line.
- Fiscal year starts in February: say "FY" in labels, never "year".
