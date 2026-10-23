# portfolio_project

The reference TraceBi project — the three-phase workflow run on a synthetic
fund Schedule-of-Investments export, from messy raw pull to a verified,
served report. This directory has exactly the shape `tracebi init` scaffolds;
it is the worked version of that scaffold with real cleaning to do.

```
⓪  INPUT       inputs/holdings.csv               a messy raw pull (generated)
               connections/crm.yaml              the credit team's CRM (Postgres):
                                                 issuer ratings, read by `-- source:`
               connections/billing.yaml, bank.yaml  billing and core banking, SQLite
                                                 files that ship (inputs/*.sqlite)
①  TRANSFORM   transforms/holdings_transform.sql parse prose blobs, dedupe,
                                                 normalise → SINK star tables
                                                 (+ .contract.yaml beside it)
               transforms/saas_transform.sql     the SaaS model's (+ .contract.yaml)
               transforms/wealth_transform.sql   Wealth Management's (+ .contract.yaml)
               transforms/affordability_transform.py  housing's, the pandas
                                                 escape hatch (`with contract`)
                          ── freeze: data/warehouse.duckdb (tracebi.yaml) ──
②  MODEL       models/portfolio_model.yaml         grain, keys, measures — the contract
               models/saas_model.yaml, models/housing_model.yaml,
               models/wealth_model.yaml
                          ── freeze: the model ──
③  REPORT      reports/portfolio_model/portfolio_dashboard/       one-screen app, every figure a live query
               reports/portfolio_model/portfolio_desk/            an app people work in (app.jsx)
               reports/portfolio_model/portfolio_book/            an editorial report, its own CSS
               reports/portfolio_model/portfolio_overview/        an app with top tabs
               reports/portfolio_model/portfolio_concentration/   an app over governed window measures
               reports/portfolio_model/portfolio_showcase/        kitchen-sink demo, every figure kind
               reports/housing_model/affordability/               public data, a one-number answer
               reports/wealth_model/aum_by_branch/, aum_by_region/  a bank's book, by branch and region
               pipelines/<model>.yaml                             one per model: transform → build
```

## Run it

```bash
python run_workflow.py        # ① build the warehouse, ③ build every report into output/
tracebi verify output/portfolio_model/portfolio_dashboard.html.manifest.json   # REPRODUCES
tracebi serve                 # browse at http://127.0.0.1:8000 → Reports
tracebi run-pipeline portfolio_model   # or: a model's pipeline — rebuild its warehouse, then its reports
```

`run_workflow.py` generates the messy source into `inputs/` on first run
(`inputs/generate_raw.py`), so phase ① has real work: prose instrument blobs
to parse into issuers, trailing position counters to strip, sectors spelled
six ways, money stored as strings. `inputs/seed_crm.sql` (applied by
`inputs/seed_crm.py`) is the CRM's issuer ratings, and
`inputs/issuer_ratings.csv` the same rows as a snapshot; see "A source outside
the warehouse" below.

Phase ① is SQL: `transforms/holdings_transform.sql`, DuckDB statements run top
to bottom in one fresh connection by `tracebi run-transform holdings_transform`.
`transforms/holdings_transform_pandas.py` does the same work in pandas, the
escape hatch for cleaning that outgrows SQL; both sink identical tables.

Phase ① ends with a declared sink contract, beside the SQL in
`transforms/holdings_transform.contract.yaml` — `rows`, `unique`, `not_null`,
`foreign_key` checked as read-only SQL against the tables that just landed and
recorded in `data/warehouse.contracts.json`. Every transform here declares
one, so every warehouse table carries a status. A failed check raises at sink
time; a green one lets a report say *the sink satisfied its contract* — never
that the transform was verified.

## A source outside the warehouse

One star table, `dim_rating`, comes from a relational database rather than a
file: the credit team's CRM, a Postgres table `issuer_ratings` (each issuer's
rating, its date and whether it is on watch). `connections/crm.yaml` declares
it (`type: postgres`, `url: ${TRACEBI_CRM_URL}`), and the header of
`holdings_transform.sql` reads it with

```sql
-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv
```

so the runner loads the table through the connection before the first
statement and the SQL joins `crm.issuer_ratings` to the parsed issuers (an
issuer the CRM does not cover lands as `Unrated`). The pandas form does the
same with `tracebi.transforms.load_source`. The model declares `dim_rating`
like any other warehouse table; the showcase filters and charts by it.

Point it at any Postgres:

```bash
export TRACEBI_CRM_URL=postgresql+psycopg://user:password@host:5432/dbname   # or put it in .env
python inputs/seed_crm.py            # creates and fills issuer_ratings (inputs/seed_crm.sql)
tracebi run-pipeline portfolio_model # the transform now reads the CRM, then the reports build
tracebi verify output/portfolio_model/portfolio_showcase.html.manifest.json --contracts
```

The URL needs a driver (`postgresql+psycopg://`; `pip install
'tracebi[postgres]'`). With `docker compose up` the CRM is a standing mock
database, `crm` on the stack's Postgres, loaded once at first start from
`inputs/seed_crm.sql` (`docker/postgres-init.sql`) and never written again;
`TRACEBI_CRM_URL` points at it. The image bakes its warehouse at build time,
with no database to read, so that certificate says the snapshot stood in; the
`seed` service then re-runs each model's pipeline, and the portfolio transform
reads the CRM. **Refresh data** on the portfolio model (or `docker compose exec
app tracebi run-pipeline portfolio_model`) does the same later.

**Without a database** (a fresh clone, CI) the demo still builds: with
`TRACEBI_CRM_URL` unset, `inputs/issuer_ratings.csv`, a committed snapshot of
the same twelve rows, stands in. Only an unset variable does that; a URL that is
set but unreachable stops the transform. The certificate
(`data/warehouse.contracts.json`) records which fed the sink, under the
transform's `sources`:

- from the CRM: `{"connection": "crm", "table": "issuer_ratings", "rows": 12,
  "fingerprint": …, "loaded_at": …}`;
- from the snapshot: the same, plus `"source_fallback": "csv"`, `"fallback":
  "inputs/issuer_ratings.csv"` and the reason (the unset variable).

Every report's trace carries that record beside `dim_rating`'s contract status,
so a reader can see the CRM was not reached. `tracebi verify --contracts`
re-reads each source and reads `unchanged`, `CHANGED` (the CRM moved since the
sink was certified: re-run the transform) or `not checked` (it cannot be read
now).

## Databases that ship

Two models read a database that is committed with the project, so they build
anywhere with nothing to set up. `connections/bank.yaml` (the core-banking
system behind Wealth Management) and `connections/billing.yaml` (the billing
system behind SaaS Subscriptions) each give their URL a default:

```yaml
url: ${TRACEBI_BANK_URL:-sqlite:///inputs/bank.sqlite}
```

With the variable set nowhere, the connection is the SQLite file in
`inputs/`, a relative path resolved against the project root. A deployment
that keeps the bank in another database sets `TRACEBI_BANK_URL` and nothing
else changes. The files are small and generated: `python inputs/seed_bank.py`
writes the bank's six tables (branches, clients, products, accounts,
holdings, activities) from a fixed seed, and `python inputs/seed_billing.py`
loads `inputs/subscriptions.csv` into the billing system's `subscriptions`
and `plans`. Each keeps the mess its transform cleans (a client segment
spelled three ways, market values stored as text, an activity posted twice;
plans and statuses spelled several ways, a duplicated account-month).

`transforms/wealth_transform.sql` and `transforms/saas_transform.sql` read
the tables with `-- source: bank.<table>` and `-- source: billing.<table>`
lines, and each certificate records every load (`connection`, `rows`,
`fingerprint`), as it does the CRM's.

Reports are organised **by model**: the folder is the model's name, so a model,
the reports that read it and its pipeline sit together. A report in a folder is
named by its path: `tracebi report build portfolio_model/portfolio_book`.
`tracebi run-pipeline portfolio_model` rebuilds that model's warehouse, then
every report in its folder.

Under `reports/portfolio_model/`:

- `portfolio_dashboard/` — the whole book on one screen, an app (`app.jsx`):
  a KPI strip with a lead, sector and fund charts, and the holdings table with
  search, a sector filter, a CSV download and a stamped total row.
- `portfolio_model/portfolio_desk/` — the book as an app (`app.jsx`, the React
  lane): a sidebar with Overview, Holdings and Funds, a KPI strip with a lead, a
  watch list of the lowest marks, and a holdings list with search and a CSV
  download; the sector and fund filters and the spread range sit in the sidebar,
  so they cut every view. Every number is a kit figure the trace names.
- `portfolio_model/portfolio_book/` — an editorial report with its own house CSS:
  the headline is the finding ("marked at 97.9% of cost"), every number in the
  prose is a bound figure, and `script.js` draws the issuer table from the same
  fingerprinted rows. One self-contained file, checkable offline with
  `tracebi verify --file`.
- `portfolio_model/portfolio_overview/` — the book at a glance, an app with
  top tabs (Overview, Issuers, Funds): the third app shape beside
  `portfolio_dashboard` (one screen) and `portfolio_desk` (a sidebar).
- `portfolio_model/portfolio_concentration/` — rank, share of total and running share as
  governed window measures; the headline's "top five hold 55.6%" is the fifth
  issuer's row, picked by a `having` clause. It was once a `report.py` escape
  hatch and no longer needs to be.
Under `reports/housing_model/`:

- `affordability/` — a second domain on public data: what buying the median
  home took of ten years of income, for every buyer since 1979 (mortgage rate
  from Freddie Mac, existing-home price from NAR through HUD and FHFA, income
  from the Census, one earner's pay from BLS). `inputs/housing_history.csv` is
  sunk by `transforms/affordability_transform.py` into the project's one
  warehouse and modelled by `models/housing_model.yaml`. Today's buyer
  is a labelled **scenario** (`data-tb-scenario`) whose assumptions the reader
  sets; it is computed in the browser and never part of the trace.
  `python inputs/fetch_housing.py` refreshes the snapshot from the publishers
  (see `inputs/housing_sources.md`); it needs the network, so it is not part of
  the pipeline.

Under `reports/wealth_model/`:

- `aum_by_branch/` — assets under management by branch and asset class,
  with net new assets by branch (purchases less sales, the report's own
  measure); its own `style.css` and fonts.
- `aum_by_region/` — the same book by region, with a lede naming the
  region that manages the most.

Back under `portfolio_model/`:

- `portfolio_model/portfolio_showcase/` — the maintained kitchen-sink demo: every
  figure kind, controls, layouts, and trust affordance the artifact offers,
  including a `report.py` escape hatch whose output stamps `verifiable: false`
  and never reads green.

The full tour of the workflow lives in `docs/concepts/the-three-phase-workflow.md` at the repo root.
