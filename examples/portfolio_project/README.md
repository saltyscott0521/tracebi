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
③  REPORT      reports/portfolio_model/portfolio_dashboard.json   every figure a live query
               reports/portfolio_model/portfolio_book/            freeform template package
               reports/portfolio_model/portfolio_overview/        default-component runtime package
               reports/portfolio_model/portfolio_concentration/   governed window measures
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

- `portfolio_dashboard.json` — a governed `ReportSpec`;
  validate it without running (`tracebi spec validate`), every figure
  reproducible.
- `portfolio_model/portfolio_book/` — a freeform template package: your own
  HTML/CSS/JS around fingerprinted data, built into one self-contained file
  checkable offline with `tracebi verify --file`.
- `portfolio_model/portfolio_overview/` — a default-component package: KPI, chart,
  and table figures hydrated by the shipped runtime from the stamped bytes, no
  author CSS or JS at all.
- `portfolio_model/portfolio_concentration/` — rank, share of total and running share as
  governed window measures. It was once a `report.py` escape hatch and no
  longer needs to be.
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
