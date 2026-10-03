### Added

- One run store. Pipeline runs, report builds, schedule ticks, and background report runs are rows in `tracebi_runs`. `GET /api/runs` lists them (`kind`, `target`, `limit`); a viewer may read it. The HTML stays a file; the row holds the path, so another worker sharing the database can poll a run and open the last build.
- Alembic migrates that store (`tracebi/migrations`). An existing SQLite file keeps its history. An existing `output/schedule_runs.jsonl` is imported once, and `tracebi schedule list` reads the last run from the store. On Postgres a schedule tick takes an advisory lock per report, so two workers do not send the same email.
