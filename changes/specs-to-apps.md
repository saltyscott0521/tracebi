### Changed — no shipped report is a JSON spec any more

- `portfolio_model/portfolio_dashboard` is a report package with an `app.jsx`
  dashboard: the whole book on one screen, with a KPI strip, sector and fund
  charts, and the holdings table with search, a sector filter, a CSV download
  and a stamped total row. `run_workflow.py` builds it with the package
  renderer.
- The demo app's `sales_overview`, `medallion_revenue` (two views: all orders,
  shipped orders) and `aum_by_region` are app dashboards too.
- A JSON `ReportSpec` still works and compiles with `tracebi migrate spec`.
