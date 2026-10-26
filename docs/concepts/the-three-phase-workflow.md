# The three-phase workflow

A TraceBi project moves data through three folders: a transform cleans it, a
model defines it, and a report presents it. Each stage hands the next a fixed
artifact, called a [[freeze-points|freeze point]].

```
inputs/  →  transforms/  →  [ warehouse ]  →  models/  →  reports/
   ⓪            ①            freeze          ②            ③
```

| Stage | Folder | What you write | Where you see it |
|---|---|---|---|
| Input | `inputs/` | Raw files: a CSV, an API export, a SQL dump | Data → Sources |
| Transform | `transforms/` | DuckDB SQL (`.sql` with a `.contract.yaml` beside it), or pandas (`.py`, `.ipynb`) | Data → Transforms; run it with `tracebi run-transform` |
| Model | `models/` | A YAML file: tables, joins, measures (`.py` for anything YAML cannot say) | Data → Models → the model's page |
| Report | `reports/` | A package: `report.json` plus an `app.jsx` dashboard or a `template.html` page | Reports, under its model |

## Transform

A transform is a SQL file by default: `transforms/<name>.sql`, DuckDB
statements run top to bottom in one fresh connection. It reads the inputs,
does whatever cleaning the data needs (window functions, parsing, dedupe), and
ends by writing clean star-schema tables into the warehouse. When SQL is not
enough, write pandas or polars in a `.py` or `.ipynb`. `tracebi run-transform`
runs either form and prints which one ran.

TraceBi does not constrain how you clean. It cares about what lands: the named
tables at the end. A [[sink-contracts|sink contract]] in `<name>.contract.yaml`
checks those tables.

A transform can also read a database. Declare it once as a connection
(`connections/crm.yaml`, its URL kept in an environment variable), then add a
header line to the SQL:

```sql
-- source: crm.issuer_ratings
```

The table loads through the connection before the first statement, and the
SQL reads it as `crm.issuer_ratings`. The contract's certificate records each
load's fingerprint under `sources`, and `tracebi verify --contracts` reports
when a source has changed since. See [[transform-sql]].

**Freeze point:** the warehouse, `data/warehouse.duckdb` by default.

## Model

A model is a short YAML file over the warehouse: its grain, keys and
[[measures]]. It reads the warehouse tables and never sees the transform. See
[[model]].

**Freeze point:** the model itself, the definitions every report uses.

## Report

A report package where every figure is a query against the model. The model's
tables already exist, so the page rebuilds in milliseconds without running
the transform. See [[report]].

## One warehouse per project

`tracebi.yaml` declares the warehouse. Every transform writes to it and every
model reads it (`type: warehouse`), so transforms and reports can run in
separate processes. `output/` holds what `tracebi report build` writes. Both
`data/` and `output/` are gitignored, except the `*.manifest.json` traces,
which stay in git as the record behind every built number.

## Try it on the reference project

```bash
cd examples/portfolio_project
python run_workflow.py          # build the warehouse, then every report
tracebi serve                   # open portfolio_model, then portfolio_dashboard
```

The first run writes a messy Schedule of Investments into `inputs/`: position
descriptions to parse into issuers, sectors spelled six ways, money stored as
strings. The project has four models sharing one warehouse.
`holdings_transform.sql`, `saas_transform.sql` and `wealth_transform.sql` are
SQL with a `.contract.yaml` beside each; the last two read SQLite databases
in `inputs/` through `-- source:` lines. `affordability_transform.py` is
pandas and declares its contract in a `with contract(...)` block.

## In the app

The app has four places in its sidebar.

- **Reports** opens first. It is the library: a folder per model, each report
  with whether its numbers still reproduce. **Ask this model**, on a folder's
  or a model's page, puts a question to that model.
- **Data** (analysts and admins) opens on **Overview**, a board with these
  stages as lanes: sources, transforms, the warehouse, models, reports. Its
  four folders, nested under it in the sidebar, are **Sources**,
  **Transforms**, **Warehouse** and **Models**, and each thing in them has a
  page of its own: a connection, a table, a transform (the pipeline that
  rebuilds its data, where an admin clicks **Refresh data**), a model (its
  tables, joins and measures, and the line to its other stages).
- **Review** holds what needs attention, drafts, **History** (what ran) and
  **Verify** (check a report file from anywhere).
- **Docs** is this handbook.

## Before a report exists

`tracebi dev` with no report name opens the app's Data page with a project
feed. Any script can post a table or a note to it with
`tracebi.workbench.show(df, note=...)`. `tracebi dev --classic` lays the
warehouse, models and packages out beside the feed on one page. `tracebi
session export` saves the session to `explorations/` as a committed record
(`--format md` for a version that reads well in review). It carries no trace,
and `tracebi verify` refuses it.

## Where trust starts

Lineage is traced from the sink, not through the transform. The trust
features (stamped queries, [[lineage]], fingerprints and `tracebi verify`)
apply to the model and the report. `tracebi verify` re-runs a manifest's
recorded queries and compares fingerprints; it does not assert a number is
correct.

The transform is reviewed like any code in git. A sink contract adds
checks its tables must pass before the data counts. See [[trace]] for what a
trace proves and what it does not.

## Why it works this way

The slow analysis in the transform and the fast work on reports never block
each other, because the model sits between them as a fixed contract. Editing
a report never re-runs the transform.

## Next

- Run all three stages: [[quickstart]]
- Write a transform: [[transform]]
