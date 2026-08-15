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
②  MODEL       models/portfolio_model.py         grain, keys, measures — the contract
                          ── freeze: the model ──
③  REPORT      reports/portfolio_dashboard.json  every figure a live query
               reports/portfolio_book/           freeform template package
               reports/portfolio_concentration/  the report.py escape hatch
```

## Run it

```bash
python run_workflow.py        # ① build the warehouse, ③ render the dashboard once
tracebi verify data/portfolio_dashboard.html.manifest.json   # every section: REPRODUCES
tracebi serve                 # browse at http://127.0.0.1:8000 → Reports
```

`run_workflow.py` generates the messy source into `inputs/` on first run
(`inputs/generate_raw.py`), so phase ① has real work: prose instrument blobs
to parse into issuers, trailing position counters to strip, sectors spelled
six ways, money stored as strings.

The three report forms in `reports/` are the three authoring lanes:

- `portfolio_dashboard.json` — a governed `ReportSpec`; validate it without
  running (`tracebi spec validate`), every figure re-provable.
- `portfolio_book/` — a freeform template package (`tracebi report build
  portfolio_book`): your own HTML/CSS/JS around fingerprinted data, built
  into one self-contained file checkable offline with `tracebi verify --file`.
- `portfolio_concentration/` — a package with a `report.py` escape hatch:
  pandas the model can't express. Its output stamps `verifiable: false` and
  never reads green — the honest lane for hand-derived numbers.

The full tour of the workflow lives at the repo root: `WORKFLOW.md`.
