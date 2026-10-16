### Added — the React lane: `app.jsx` for app-like dashboards

- A report package may hold `app.jsx` in place of `template.html`: a React
  component built into the same single offline file with the same receipt.
  The page carries React 18, Sucrase (compiles the JSX in the page; the CSP
  still refuses `eval`), Tailwind's browser build, and — when imported —
  Recharts and only the lucide icons the app names.
- The `tracebi` kit: `Kpi`, `Value`, `Chart`, `Spark`, `Table`, `Filter`,
  `Search`, `Download`, `useBinding`, `fmt`. Kit figures render the same
  `data-tb-*` elements a template holds; the build reads their literal props
  as claims and refuses a binding or column that does not exist. Numbers the
  app computes itself are labelled as its own presentation.
- Imports outside the kit, dynamic imports, and non-literal figure bindings
  fail the build with the fix in the message.
- `tracebi.refresh()` hydrates figures mounted after load (a view switch).
- Discovery, drafts, the report source view and `report build` accept
  `app.jsx`. Docs: `docs/reference/app-jsx.md`.
