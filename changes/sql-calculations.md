### Added — SQL calculations

- **`sql_calculations` in report.json.** A package may declare named calculations keyed
  by model: `"sql_calculations": {"sample_model": {"running_revenue": "SELECT region_id,
  order_date, SUM(revenue) OVER (PARTITION BY region_id ORDER BY order_date) AS
  running_revenue FROM fact_orders"}}`. A data binding names one with
  `{"model": "sample_model", "sql": "running_revenue"}`, the way a model query is bound.
- **Read-only, and refused when it is written.** A calculation must be one `SELECT` (or
  `WITH`) statement; anything else (a write, `ATTACH`, `COPY`, `PRAGMA`, `SET`,
  `INSTALL`, `LOAD`, or a second statement) is refused when the report is discovered. It
  runs in DuckDB against the model's warehouse, attached read-only, with external access
  switched off and the configuration locked, so a `read_csv` or a glob reaches no file.
- **Model measures by name.** `{{ measure('revenue') }}` expands to the model's measure
  in SQL. Simple measures (sum, count, mean, min, max, nunique of one column) and
  filtered ones expand; a ratio, expression, share or other kind is refused by name.
- **Stamped and re-checkable.** The receipt records the SQL as written and the SQL that
  ran, a fingerprint of each warehouse table it reads, and the result fingerprint. The
  semantic contract labels each one "calculated in this report (SQL)". `tracebi verify`
  re-runs it and reports source drift when the warehouse changes.
- **Rows come back in a canonical order** (by columns, left to right), so the fingerprint
  does not depend on the engine's scan order. Put the grouping and date columns first.
- **Limits.** A selection or a filter cannot reach a SQL binding yet (the build refuses
  rather than ship an unfiltered page). Unqualified measure columns can be ambiguous in a
  join. The web UI does not render the label yet; the receipt carries it.
