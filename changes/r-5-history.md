### Changed — History reads as sentences, and fits a phone

- Each row of History (`/runs`, `/runs?model=<m>`) says what ran in words:
  "Report build · Portfolio Dashboard" (the report's name; its identifier is
  the link's tooltip), then its verdict, when it started ("2 h ago", the date
  and time in a tooltip), how long it took and who ran it. Rows are grouped
  by day under a header that stays in view while you scroll.
- A column no row fills is not drawn: Model (also hidden under a model
  filter), Took (a build recorded by `tracebi report build` stores no finish
  time; background runs, schedules and pipeline runs do) and Who. A single
  empty cell reads "—".
- A failed or running run says so in a chip, and a failed row is tinted red
  with a red rule; a report build that succeeded shows only its verdict; any
  other run that finished says so quietly ("Succeeded"). Order stays
  newest first.
- A report's run links to the report's page; a pipeline run or step to the
  Transform stage of its model. The separate "Open" link is gone (the
  report's page has Open).
- Filters: a chip per model (by label), then Kind and "Report or pipeline"
  as selects (names, not identifiers), all kept in the URL as before
  (`?model=`, `?kind=`, `?target=`). Publish runs have their own kind.
- On a phone (640px and narrower) History is a list of cards, one per run:
  name, chip, then kind · time · how long · who.
- With nothing recorded: "Nothing has run yet. A build from the app,
  `tracebi report build`, or a schedule appears here.", with no filters.
- Checked at 390px, no change needed: the library's descriptions wrap to two
  lines, and the dashboard, concentration and book have nothing floating
  over their content, in the app's frame or on `/r/` (the receipt is the
  masthead's chip and link).
