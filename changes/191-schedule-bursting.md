### Added — A schedule can burst: one build per filter value

- A `report.json` `schedule.burst` block builds the report once per value
  of one dimension filter, and emails that copy to `burst.to[value]`.
  The filter is applied at build on every binding whose model has the
  dimension, through the same path as a selection filter.
- A value with no entry in `burst.to` is skipped and recorded. It is not
  sent to the top-level `to`. `burst` without `to` is refused when the
  package loads.
- Each slice is verified on its own. A refused, empty, or failed slice is
  not sent; the others still are. One parent run records every slice
  (value, status, recipients, output path). If any slice failed, came
  back empty, or was refused, one owner alert names those slices.
