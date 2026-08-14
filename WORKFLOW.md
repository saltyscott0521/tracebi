# The three-phase workflow

An agent (or an analyst) writes as much pandas as the data needs, sinks the
result into a warehouse, declares a thin model over it, and points a dashboard
at the model. Each phase has its own folder and its own cadence.

```
⓪  INPUT                 a raw pull lands here
    inputs/holdings.csv         (an AltsVault API export, a CSV, a SQL dump)
                                                          │
①  MANIPULATE            slow, runs rarely, code is free
    transforms/holdings_transform.py
      read inputs/ → parse, clean, key, dedupe → WRITE star-schema tables
                                                          │
                                                          ▼  data/warehouse.duckdb
②  MODEL                 the contract, changes deliberately
    models/portfolio_model.py
      a star schema over the warehouse — grain, keys, measures, in ~50 lines
      a reviewer reads without ever opening the pandas
                                                          │
                                                          ▼
③  DASHBOARD             fast, iterate constantly
    dashboards/portfolio_dashboard.json
      a ReportSpec — KPI cards, charts, a table — every figure a live query
      against ②. Edit the JSON and re-render in milliseconds; nothing re-runs ①.
```

The point of the split is the **freeze points**. Phase ① can be thousands of
lines of arbitrary pandas; once it has run, the warehouse is a fixed input.
Phase ② is small enough to review as data. Phase ③ never touches pandas, so
reshaping the page is instant — the coupling that makes report iteration
painful is gone.

## Run it

```bash
python run_workflow.py          # ① build the warehouse, ③ render the dashboard once
python -m tracebi.web.run       # serve it: http://127.0.0.1:8000 → Reports → portfolio_dashboard
```

`run_workflow.py` generates a synthetic messy Schedule-of-Investments file into
`inputs/` the first time (`inputs/generate_raw.py`), so there is real work for
phase ① to do: prose instrument blobs to parse into issuers, trailing `(2)`
position counters to strip, sectors spelled six ways, money stored as strings.

## Where each phase lives

| Stage | Folder | Artifact | Discovered by the server as |
|---|---|---|---|
| ⓪ Input | `inputs/` | a raw pull (CSV / API export / SQL dump) | — (you put it there) |
| ① Manipulate | `transforms/` | pandas → DuckDB tables | — (run explicitly) |
| ② Model | `models/` | `DataModel` (a `model` variable) | a model on the Models page |
| ③ Dashboard | `dashboards/` | `ReportSpec` JSON | a report on the Reports page |

The warehouse is `data/warehouse.duckdb` — one file phase ① writes and phase ②
reads. The model opens it read-through; the two phases can run in separate
processes because the sink is on disk. `inputs/` holds the raw material (the
demo's `holdings.csv` is tracked; a large or sensitive real pull can be
gitignored per-file); `data/` holds the build artifacts and is gitignored.

## Iterating on the dashboard

Everything visible is a query. To add a panel, add a section to
`dashboards/portfolio_dashboard.json` with a `data.query` naming a `fact`, its
`measures`, and `dimensions` — no code, no re-run of phase ①. A `metrics`
section can carry a `data` query too: a card whose `value` names a measure reads
it live, so the KPI strip never goes stale.
