### Added — push from a laptop; code an admin approves

- `tracebi push <paths> --server <url> [--note "why"]`, after `tracebi login`:
  report packages and `models/<name>.yaml|.json` become your drafts; Python
  (`transforms/`, `pipelines/`, `models/<name>.py`, `connections/`, a package's
  `report.py`) becomes one code request. Data files are refused.
- Code requests (`/api/code-requests`, stored under `.tracebi/requests/<id>/`
  and in the new `tracebi_code_requests` table, Alembic 0006). An admin reviews
  each file's diff on the Drafts page and approves (the files go in, what they
  replace is kept under `.tracebi/history/code/`, and the pipelines they touch
  run once on the server) or declines with a reason.
- `POST /api/library/sync`: a git webhook (`TRACEBI_LIBRARY_SYNC_SECRET`,
  GitHub's `X-Hub-Signature-256` or `X-TraceBi-Sync-Token`) that fast-forwards
  each library checkout and picks up the change.
