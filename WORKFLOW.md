# The three-phase workflow

An agent (or an analyst) writes as much pandas as the data needs, sinks the
result into a warehouse, declares a thin model over it, and points a report
at the model. Each phase has its own folder and its own cadence.

```
⓪  INPUT                 a raw pull lands here
    inputs/holdings.csv         (an AltsVault API export, a CSV, a SQL dump)
                                                          │
①  TRANSFORM             slow, runs rarely, code is free
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
③  REPORT                fast, iterate constantly
    reports/portfolio_dashboard.json
      a ReportSpec (one of the report forms) — KPI cards, charts, a table —
      every figure a live query against ②. Edit it and re-render in
      milliseconds; nothing re-runs ①.
```

The point of the split is the **freeze points**. Phase ① can be thousands of
lines of arbitrary pandas; once it has run, the warehouse is a fixed input.
Phase ② is small enough to review as data. Phase ③ never touches pandas, so
reshaping the page is instant — the coupling that makes report iteration
painful is gone.

## Run it

```bash
cd examples/portfolio_project
python run_workflow.py          # ① build the warehouse, ③ render the report once
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
| ① Transform | `transforms/` | pandas → DuckDB tables | — (run explicitly) |
| ② Model | `models/` | `DataModel` (a `model` variable) | a model on the Models page |
| ③ Report | `reports/` | `ReportSpec` JSON, template package, or `@register.report` factory | a report on the Reports page |

The warehouse is `data/warehouse.duckdb` — one file phase ① writes and phase ②
reads. The model opens it read-through; the two phases can run in separate
processes because the sink is on disk. `inputs/` holds the raw material (the
demo's `holdings.csv` is tracked; a large or sensitive real pull can be
gitignored per-file). `data/` holds the warehouse and `run_workflow.py`'s
one-off render; `output/` holds `tracebi report build` renders (its default
target). Both dirs are gitignored except the `*.manifest.json` receipts inside
them — those stay tracked, as the audit trail behind every rendered number.

Phase ① and ② have a live surface of their own: `tracebi dev` with no name
opens the **discovery workbench** — any script run while it serves can
`tracebi.workbench.show(df, note=...)` an excerpt into the portal, the
warehouse panel lists tables and contract status as sinks land, and the
models panel shows the star schema taking shape. Same pins, same
steer-from-chat loop, before a single report exists. `tracebi session
export` saves the session to `explorations/` as a committed lab-notebook
record (`--format md` for the git-review twin) — exploration-stamped,
receipt-free, refused by `verify` by name.

A transform may end with a **sink contract** — a `with contract(...)` block
declaring what must be true of the tables it just sank (row counts, unique
keys, no NULLs, foreign keys, value domains, cross-table reconciliation). The
checks run as read-only SQL at sink time; a failure raises; success records a
certificate beside the warehouse (`data/warehouse.contracts.json`) that report
manifests join against (`satisfied` / `stale` / `no_contract`) and
`tracebi verify --contracts` re-runs. It certifies the **sink**, never the
pandas above it — see `transforms/holdings_transform.py` for the reference
declaration.

## Iterating on the report

Everything visible is a query. The report is an artifact package under
`reports/<name>/`: `tracebi new-report "My Report"` scaffolds one, `tracebi dev
<name>` live-previews it while you edit, and `tracebi report build <name>`
renders one self-contained HTML plus its manifest receipt. Nothing re-runs
phase ①.

The lighter alternative is to edit the JSON spec directly. To add a panel, add
a section to `reports/portfolio_dashboard.json` with a `data.query` naming a
`fact`, its `measures`, and `dimensions` — no code, no re-run of phase ①. A
`metrics` section can carry a `data` query too: a card whose `value` names a
measure reads it live, so the KPI strip never goes stale.
