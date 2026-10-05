### Added — Refresh shows a running log of every run

- **Run all** and each step's **Run** now start the run in the background and
  open a new **Log** tab that follows it: everything the steps print (a
  transform's own output, the runner's `[step] Running…` / `✓ 12 in → 11 out
  (0.4s)` lines, the report builds), each line stamped with the time since the
  run began. Past runs are in the picker; Copy takes the whole log.
- A pipeline that is already running is joined, not started twice.
- `POST /api/pipelines/{name}/runs`, `GET …/runs`, `GET …/runs/{id}`,
  `GET …/runs/{id}/log?after=` (analyst: a log is whatever the steps printed).
  Logs are files under `data/logs/pipelines/<name>/`, the newest 30 kept, 2 MB
  each. The Runs page lists them as **Pipeline run**.
- The step line `[step] ✓ …` now says how long the step took.

### Fixed — Refresh failed in the app once another model shared the warehouse

`portfolio_model` and `saas_model` write one `warehouse.duckdb`. Once the app had
listed the models, `saas_model` held that file open read-only and refreshing
`portfolio_model` failed with "another tracebi process holds the warehouse
open", from the app and from the old `POST …/run`. A pipeline now releases every
loaded model's handles before its transform writes, not only its own.
