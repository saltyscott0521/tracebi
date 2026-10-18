### Changed — words a reader meets (A2-1)

- Every shipped `report.json` `description` (the reference project, both
  `init --template` bundles, the demo app and the init sample) is one sentence
  a reader would use: what the page shows, never how it is built ("Ending MRR,
  customers and logo churn, month by month and by plan."). What was worth
  keeping for authors moved to a new optional `notes` key, which nothing
  renders. `tracebi new-report` / `new-dashboard` write a reader sentence from
  the query with a bracket to fill: "Revenue by region, over [the period these
  numbers cover]."
- The masthead's kicker is the model's label. A template whose masthead has no
  `.tb-kicker` gets `<p class="tb-kicker">` before its `<h1>` at build (and in
  the dev preview); the kit's `<Masthead>` with no `kicker` prop shows it (the
  build writes it on the app's mount point; `kicker={null}` shows none). An
  explicit kicker still wins. The shipped reports drop their own kickers
  ("DIRECT LENDING · PORTFOLIO OVERVIEW" and the like), so every page reads the
  same; the h1 is the report's name or its finding. `portfolio_dashboard`'s
  masthead said "Portfolio book"; it says "Portfolio Dashboard".
- The footer's visible line is "Built 18 Oct 2026 · Direct Lending Portfolio.
  The receipt does not claim the numbers are right.": the model by its label,
  the date in words, no author or tooling. Who built the file stays in the
  manifest (`rendered_by`) and the receipt's About this build ("built by …").
- `tracebi context`, `AGENTS.md` and the scaffolded guide teach "description
  is for the reader" and the kicker default; `tests/test_agent_guides.py`
  refuses a shipped description that talks about `app.jsx`, the kit,
  `template.html`, bound figures, model identifiers and the like.
