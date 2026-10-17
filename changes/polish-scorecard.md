### Added — `--job scorecard`; acronyms in labels; bars inside the cell

- `tracebi new-dashboard --job scorecard`: every measure the fact runs (up
  to four) as a KPI, each with its trend when the model has a time
  dimension, then all of them by category.
- Derived labels spell business acronyms in capitals (`ending_mrr` →
  "Ending MRR", `ytd_revenue` → "YTD revenue"), the same in the build and
  the runtime; scaffold sentences keep them ("leads on ending MRR").
- A table's in-cell bar runs inside the cell's padding, so the longest bar
  ends where its number does.
