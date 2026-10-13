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

### Added — a report can calculate its own measures

- **`measures` in report.json.** A package's `report.json` may declare measures keyed by
  model: `"measures": {"wealth_model": {"net_new_assets": {"measure_expr": "purchases -
  sales"}}}`. Each takes the same keywords as `add_measure` (simple, expression, ratio,
  share, filters, and arithmetic over other measures), so the vocabulary is the model's.
- **Scoped to the report's bindings.** A binding that names one of them in its
  `measures` gets it for that query. The shared model is not changed, a query on the
  model cannot see the name, and a name the model already declares is refused.
- **Labelled, and re-checkable.** The receipt's semantic contract marks each one
  `scope: report` with the label "calculated in this report", and the stamped query
  carries its definition, so `tracebi verify` replays it. These are re-runnable, not
  governed definitions: promote a reused one into the model through review.
- **Arithmetic over measures.** `add_measure(..., measure_expr="purchases - sales")` is
  a new kind on the model too: arithmetic over other measures' totals (names and
  numbers, `+ - * /` and parentheses), computed after aggregation. A zero denominator
  gives NaN. Calls, columns and comparisons are refused at declaration.
- **Demonstrated.** The scaffold's sample dashboard carries a filtered split of revenue
  (`big_minus_small`). The demo's AUM by Branch report carries net new assets by branch:
  purchases less sales from `fact_activities`, fees left out.
