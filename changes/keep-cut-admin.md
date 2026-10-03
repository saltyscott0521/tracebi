### Changed — Keeping a selection cut requires admin

- `POST /api/reports/{name}/selection/keep` requires the `admin` role when
  role enforcement is on, including reports in a folder
  (`/api/reports/finance/close/selection/keep`). It rewrites the published
  `report.json`. Recomputing a cut (`POST .../selection`) stays available to
  an `analyst`. With no role source configured, every principal is still
  admin.
