### Added — a Sales Overview report for the demo's SalesModel

- `SalesModel`, the demo's first model, had no report. `reports/sales_model/sales_overview.json`
  reads it: revenue, units and cost, revenue by region, and a by-tier table, every
  figure a live query.
- `scripts/ui_audit.py` flags any model with no report (`model-without-reports`).
