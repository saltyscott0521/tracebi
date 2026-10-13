### Added — a measure can carry its own filter

- **`add_measure(..., filters={...})`** restricts a `simple` or `expression` measure to
  the rows its filter matches: `add_measure('purchases', column='amount', agg='sum',
  filters={'activity_type': 'purchase'})`. The filter uses the query vocabulary
  (equality, lists, operator dicts, `or` groups) over the fact's own columns. Other
  measures, including ratios and shares that name it, are unaffected by its filter.
- **Declarative models too.** A measure in `models/<name>.yaml` takes a `filters:`
  mapping, with the same schema check as the rest of the measure.
- **The receipt carries it.** The query's lineage records each filter and the resolved
  measure filters, and the semantic contract in a built page shows the measure's
  `filters`. `tracebi verify` re-runs the query, so changing the filter in the model
  shows as drift.
- **Refused by name, before any aggregation runs:** a filter on a column the fact does
  not have, a dimension reference inside a measure's filter (filter the query instead),
  an empty filter, a filter on a ratio or share (it filters through the base measures),
  and a filtered measure in a query with `aggregate=False`.
- The scaffolded `sample_model` declares `large_order_revenue` as an example.
