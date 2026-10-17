# portfolio_project

The reference TraceBi project — the three-phase workflow run on a synthetic
fund Schedule-of-Investments export, from messy raw pull to a verified,
served report. This directory has exactly the shape `tracebi init` scaffolds;
it is the worked version of that scaffold with real cleaning to do.

```
⓪  INPUT       inputs/holdings.csv               a messy raw pull (generated)
①  TRANSFORM   transforms/holdings_transform.py  parse prose blobs, dedupe,
                                                 normalise → SINK star tables
                          ── freeze: data/warehouse.duckdb ──
②  MODEL       models/portfolio_model.yaml         grain, keys, measures — the contract
                          ── freeze: the model ──
③  REPORT      reports/portfolio_model/portfolio_dashboard/       one-screen app, every figure a live query
               reports/portfolio_model/portfolio_desk/            an app people work in (app.jsx)
               reports/portfolio_model/portfolio_book/            an editorial report, its own CSS
               reports/portfolio_model/portfolio_overview/        an app with top tabs
               reports/portfolio_model/portfolio_concentration/   an app over governed window measures
               reports/portfolio_model/portfolio_showcase/        kitchen-sink demo, every figure kind
               reports/housing_model/affordability/               public data, a one-number answer
               pipelines/<model>.py                               one per model: transform → build
```

## Run it

```bash
python run_workflow.py        # ① build the warehouse, ③ render the dashboard once
tracebi verify data/portfolio_dashboard.html.manifest.json   # every section: REPRODUCES
tracebi serve                 # browse at http://127.0.0.1:8000 → Reports
tracebi run-pipeline portfolio_model   # or: a model's pipeline — rebuild its warehouse, then its reports
```

`run_workflow.py` generates the messy source into `inputs/` on first run
(`inputs/generate_raw.py`), so phase ① has real work: prose instrument blobs
to parse into issuers, trailing position counters to strip, sectors spelled
six ways, money stored as strings.

Phase ① ends with a declared sink contract — `rows`, `unique`, `not_null`,
`foreign_key` checked as read-only SQL against the tables that just landed and
recorded in `data/warehouse.contracts.json`. A failed check raises at sink
time; a green one lets a report say *the sink satisfied its contract* — never
that the transform was verified.

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
  watch list of the lowest marks, and a holdings list with search, sector and
  fund filters and a CSV download. Every number is a kit figure the receipt names.
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
  sunk by `transforms/affordability_transform.py` to its own
  `data/housing.duckdb` and modelled by `models/housing_model.yaml`. Today's buyer
  is a labelled **scenario** (`data-tb-scenario`) whose assumptions the reader
  sets; it is computed in the browser and never part of the receipt.
  `python inputs/fetch_housing.py` refreshes the snapshot from the publishers
  (see `inputs/housing_sources.md`); it needs the network, so it is not part of
  the pipeline.

Back under `portfolio_model/`:

- `portfolio_model/portfolio_showcase/` — the maintained kitchen-sink demo: every
  figure kind, controls, layouts, and trust affordance the artifact offers,
  including a `report.py` escape hatch whose output stamps `verifiable: false`
  and never reads green.

The full tour of the workflow lives in `docs/concepts/the-three-phase-workflow.md` at the repo root.
