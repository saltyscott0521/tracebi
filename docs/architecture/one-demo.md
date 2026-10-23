# One demo: what tracebi.com serves, and the conventions every model follows

*Plan, 2026-10-23. Package `U-D` of the 2026-10-23 UI round.*

## What is served today, and why it reads as several products

The public demo (`docker-compose.yml`, and tracebi.com) serves **two
projects at once**: the reference project
(`examples/portfolio_project`) and the bundled demo app
(`TRACEBI_APP=tracebi.web.demo_app`). A visitor opening Data sees five
models that follow four different sets of rules:

| Model | Where | Model form | Warehouse | Transform | Pipeline | Reports |
|---|---|---|---|---|---|---|
| Direct Lending Portfolio | reference project | YAML | `type: warehouse` (`data/warehouse.duckdb`) + CRM Postgres by `-- source:` | SQL + `.contract.yaml` | YAML | `reports/portfolio_model/` (6) |
| SaaS Subscriptions | reference project | YAML | `type: warehouse` (same file) | Python, no contract | YAML | `reports/saas_model/` (2) |
| Housing Affordability | reference project | YAML | its own `data/housing.duckdb` (`type: duckdb`) | Python, no contract | YAML | `reports/housing_model/` (1) |
| Sales Orders | demo app | Python | `demo_db` (SQLite locally, Postgres on tracebi.com) holding `orders_raw/bronze/silver` **and the runner's own tables** | medallion layers in code | Python runner | `demo_app/reports/sales_model/` (2) |
| Wealth Management | demo app | Python | an in-memory `banking` connector; `holdings_raw/_silver` land in `demo_db` | medallion layers in code | Python runner | `demo_app/reports/wealth_model/` (2) |

So the Sources tab lists `crm`, `warehouse`, `housing_warehouse`, `demo_db`
and `banking`: three kinds of thing under one heading. The Warehouse tab
shows two DuckDB files plus a Postgres that also holds `tracebi_runs` and
`tracebi_sessions`. The reference project has **no `tracebi.yaml`**, so its
"warehouse" is the default path by accident rather than declaration. Two
of three reference transforms are Python with no sink contract, so their
tables read "No checks" beside the holdings tables' "Checks passed".

## The rule

**tracebi.com serves one project, and every model in it follows the same
conventions.** The conventions are the ones `tracebi init` scaffolds and
`CLAUDE.md` documents; the reference project is the proof that they hold
for more than one model.

1. **One project.** `docker-compose.yml` and the Dockerfile serve
   `examples/portfolio_project` only. `TRACEBI_APP` is unset there. The
   bundled demo app stays in the package as *the* example of wiring an app
   module in Python (medallion layers, `register`), opt-in as it is
   documented to be, and is never served beside a project.
2. **One warehouse per project**, declared. `examples/portfolio_project/tracebi.yaml`
   names `data/warehouse.duckdb` (file tier) and the engine limits.
   Housing moves into it: `housing_model.yaml` says `type: warehouse`, its
   transform sinks there, `data/housing.duckdb` goes away. The Warehouse tab
   then shows one warehouse with every model's tables, each with who wrote
   it.
3. **Every transform is SQL with a sink contract**, or is a Python escape
   hatch that still declares one. `saas_transform.py` and
   `affordability_transform.py` each gain a `.contract.yaml` (rows,
   unique, not_null, foreign_key) so every table on the Warehouse tab reads
   "Checks passed" or an honest failure, never "No checks". Where the Python
   is plain cleaning, rewrite it as SQL (`saas_transform.sql`); housing's
   prose parsing stays Python.
4. **Every model is YAML with a label, a grain and declared measures**, one
   file per model, reports in `reports/<model>/`, one pipeline YAML per
   model. Already true for the three; the rule is written so the next model
   follows it.
5. **Sources are real sources.** The Sources tab lists connections
   (`connections/*.yaml`) and `inputs/`. `crm` (Postgres) and `inputs/`
   (CSV, public data) are the two kinds of source the demo should show;
   the warehouse is not a source and the in-memory `banking` connector is
   not shown anywhere a visitor looks.
6. **The state store is never a data database.** `TRACEBI_STATE_URL` is
   its own database (compose: a second Postgres database, `tracebi_state`,
   on the same server); the demo app's runner, when someone does run it,
   uses `tracebi.state.state_url()` rather than its data URL; every
   explorer hides `tracebi_*` and `alembic_version` regardless
   (U-0 of the audit).

## What the visitor sees afterwards

- **Models**: three chains, each `inputs/… → <transform>.sql → N tables →
  N measures → N reports`, the portfolio one also showing `crm`.
- **Sources**: `crm` (Postgres, read by `holdings_transform`, tables
  listed when connected), `inputs/` (its files, each read by one
  transform). Nothing else.
- **Warehouse**: `warehouse` · `data/warehouse.duckdb` · one list of tables
  grouped by the transform that wrote them, every row "Checks passed".
- **Reports**: nine reports in three folders named for their models.

## What goes

- `data/housing.duckdb` and the `housing_warehouse` connector.
- The demo app from the served stack (not from the package). Its two
  reports per model, `sample_data.py`, and `wealth_model.py` are untouched
  in this round; whether to retire `wealth_model` is a separate call.
- `examples/seeds/seed_db.py`'s habit of seeding `data/tracebi.db`: it
  seeds `data/demo.db`, the demo app's own file.

## Acceptance

`tests/e2e/test_reference_project.py`: `tracebi.yaml` is read; `GET
/api/warehouse` lists exactly one warehouse holding housing's, saas's and
portfolio's tables, each with `contract.status == "satisfied"`; `GET
/api/connectors` lists `crm` and no `housing_warehouse`; `GET /api/models`
lists three models, every one `type: warehouse`. The UI smoke journey's
Sources step sees `crm` and `inputs/` only. `docker compose config` shows
`TRACEBI_APP` unset for `app` and `seed`, and `TRACEBI_STATE_URL` pointing
at a database other than `TRACEBI_CRM_URL`'s.
