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
   documented to be, and is never served beside a project. **Wealth
   Management is served**, so it moves into the reference project as its
   fourth model, rebuilt to the conventions below (next section).
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

## Wealth Management moves into the reference project

The demo app's `wealth_model` is the one visitors recognise (a bank's
clients, branches, products, accounts, holdings, activities; AUM by branch
and region), so it stays on the site, as a model of the reference project
built the way the other three are:

- **Source**: a core-banking database that ships, `connections/bank.yaml`
  (`url: ${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}`), with the six
  raw tables the demo app generates today (the frames in `wealth_model.py`,
  written by `inputs/seed_bank.py`, committed). The raw
  tables keep a little mess worth cleaning (segment spelled three ways,
  market values as strings, a duplicated activity), so the transform has
  work to do.
- **Transform**: `transforms/wealth_transform.sql` + `.contract.yaml`,
  `-- source: bank.clients`, `bank.branches`, `bank.products`,
  `bank.accounts`, `bank.holdings`, `bank.activities`; sinks `dim_client`,
  `dim_branch`, `dim_product`, `dim_account`, `fact_holdings_wealth` (or a
  `wealth_` prefix throughout, since `fact_holdings` is the portfolio's)
  and `fact_activities` into the one warehouse.
- **Model**: `models/wealth_model.yaml`, label `Wealth Management`, the
  demo app's measures (AUM, cost basis, unrealised gain, client count,
  activity volume) and dimensions (branch, region, segment, risk profile,
  product class) declared.
- **Pipeline**: `pipelines/wealth_model.yaml`, transform → build.
- **Reports**: `reports/wealth_model/aum_by_branch` and `aum_by_region`
  moved over as they are (`app.jsx` dashboards), bindings re-pointed at the
  YAML model's names, plus whatever the showcase lacks that these had.

The demo app keeps its own `wealth_model.py` and medallion
`wealth_pipeline.py` as the Python example; the two are no longer the same
thing served twice. `sales_model` stays in the demo app only.

## Sources: one of each kind, on purpose

The four models show the four ways a project gets its data, so a visitor
sees the range without reading a doc:

| Model | Source kind | How |
|---|---|---|
| Direct Lending Portfolio | **CSV + a live Postgres**, combined | `inputs/holdings.csv` plus the CRM: `connections/crm.yaml` → `${TRACEBI_CRM_URL}`, a database in the box's Postgres seeded by the `seed` service. Off the box the `-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv` snapshot stands in and the certificate says so. This is the only model that needs a credential, which is what makes it the credentials demo too. |
| Wealth Management | **A database file that ships** | `connections/bank.yaml` → `${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}`: a core-banking SQLite with the six raw tables, written by `inputs/seed_bank.py`, committed, read by `-- source: bank.<table>` lines. Always connects, on the box too. |
| SaaS Subscriptions | **A database file that ships** | `connections/billing.yaml` → `${TRACEBI_BILLING_URL:-sqlite:///inputs/billing.sqlite}`: the billing system's `subscriptions` and `plans` tables (today's `subscriptions.csv`, loaded into SQLite by `inputs/seed_billing.py`). |
| Housing Affordability | **CSV only**, public data | `inputs/housing_history.csv`, the NAR series, fetched by `inputs/fetch_housing.py`; no connection file, read by `read_csv` in the transform. |

Rules the table rests on:

- A source that is "a database" is a database: a Postgres on the box or a
  SQLite that ships, never an in-memory connector. In-memory stays a unit
  test tool.
- The shipped files are small, generated by a committed script in
  `inputs/`, and regenerated by it; the CSV a script started from stays as
  the script's input, not as a second source.
- A connection value may carry a **default**, shell-style:
  `url: ${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}`. The default is
  used when the name resolves nowhere (environment, `.env`, store); it must
  pass the same no-credential check as a literal (a SQLite path does, a
  Postgres URL with a password does not), so a secret can never hide in a
  default. `validate_connection_doc` enforces it; the Sources panel shows
  "Set · default" as the source; a deployment that wants `bank` on a real
  Postgres sets the variable and nothing else changes.
- The `-- source: … fallback:` directive stays for what it is for: a
  declared connection that is unreachable right now. Only the live-Postgres
  model uses it.

The demo app follows the same rule where it keeps mock data: `banking`
stops being a `MemoryConnector` and becomes tables in `data/demo.db`
(SQLite, written by `sample_data.py`) or in `TRACEBI_DEMO_DB_URL`'s
Postgres, like `sales_model`'s already are.

## What the visitor sees afterwards

- **Models**: four chains, each `inputs/… → <transform>.sql → N tables →
  N measures → N reports`, the portfolio one showing `crm` + CSV, the
  wealth one `bank`, the SaaS one `billing`, the housing one CSV.
- **Sources**: `crm` (Postgres on the box, "not connected · snapshot"
  elsewhere), `bank` and `billing` (SQLite files that ship, always
  connected, tables listed), and `inputs/` (CSV and the shipped files, each
  read by one transform). Nothing else.
- **Warehouse**: `warehouse` · `data/warehouse.duckdb` · one list of tables
  grouped by the transform that wrote them, every row "Checks passed".
- **Reports**: eleven reports in four folders named for their models.

## What goes

- `data/housing.duckdb` and the `housing_warehouse` connector.
- The demo app from the served stack (not from the package). Its files
  are untouched in this round except that `banking` becomes a real
  database (above).
- `examples/seeds/seed_db.py`'s habit of seeding `data/tracebi.db`: it
  seeds `data/demo.db`, the demo app's own file.

## Acceptance

`tests/e2e/test_reference_project.py`: `tracebi.yaml` is read; `GET
/api/warehouse` lists exactly one warehouse holding housing's, saas's and
portfolio's tables, each with `contract.status == "satisfied"`; `GET
/api/connectors` lists `crm`, `bank`, `billing` and no `housing_warehouse`; `GET /api/models`
lists four models, every one `type: warehouse`, `wealth_model` among them
with its two reports built. The UI smoke journey's
Sources step sees `crm`, `bank`, `billing` and `inputs/` only. `docker compose config` shows
`TRACEBI_APP` unset for `app` and `seed`, and `TRACEBI_STATE_URL` pointing
at a database other than `TRACEBI_CRM_URL`'s.
