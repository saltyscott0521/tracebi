Copy `deploy/.env.example` to `deploy/.env` and set `TRACEBI_PROJECT_DIR` to the folder `tracebi init` created.

```
docker compose -f deploy/compose.yml up -d
```

Open http://localhost:8000. Add `--profile postgres` for Postgres.
Backups are copying `TRACEBI_PROJECT_DIR` (and `TRACEBI_PGDATA_DIR` when using Postgres).
In-server schedules are a separate issue in #80.
