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
- **Data** (analysts and admins) is a console. Its home is a status board:
  a card each for Sources, Transforms, Warehouse, Models and Reports with
  one health pill, **Needs attention** (a source not reachable here, a file
  nobody reads, a transform no pipeline runs, a table no model reads, each
  with its action), what agents may read, recent activity and schedules.
  Its four lists, nested under it in the sidebar, are **Sources**,
  **Transforms**, **Warehouse** and **Models**, one shape for all: search,
  filter chips, a Status column in the app's words (Connected, Unreachable,
  Checks passed, Changed since checked, Nobody reads it…) and a row menu.
  Every thing in them has a page of the same shape: its name, type and
  status, its actions top right (Test and Setup for a source, Refresh data
  for a transform, Copy SQL and Export for a table, Ask this model for a
  model), then tabs: **Overview** (its facts, among them From, Read by,
  Last moved, Trust and Agents), its own (a source's **Tables**, where you
  tick what agents may read; a table's **Data** and **Columns**; a
  transform's **Steps** and **Code**; a model's **Schema** and
  **Measures**), **Lineage**, **Activity**, **Agents** and **Settings**.
  **View lineage**, on the home and every page, opens the map of the
  project: these stages as lanes, wired by what reads what, read through a
  lens (**Coverage**, **Flow**, **Freshness**, **Trust**, **What agents
  see**).
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

The numbers' lineage is traced from the sink, not through the transform. The trust
features (stamped queries, [[lineage]], fingerprints and `tracebi verify`)
apply to the model and the report. `tracebi verify` re-runs a manifest's
recorded queries and compares fingerprints; it does not assert a number is
correct.

The transform is reviewed like any code in git. A sink contract adds
checks its tables must pass before the data counts. See [[trace]] for what a
trace proves and what it does not.

## Where each column comes from

A SQL transform also records where each column of its tables comes from.
While it runs, DuckDB parses every statement, and the certificate keeps, per
column, the source columns it is computed from: `fact_holdings.par` from
`inputs/holdings.csv.par`, `dim_rating.rating` from
`crm.issuer_ratings.rating`. Where the parse cannot be followed, the column
says `null` and why; nothing is guessed. A pandas or notebook transform
records nothing. It is a record of what the SQL reads, not a check that a
number is right. The map's Flow lens and a table's Columns tab show it; see
[[transform-sql]].

## Watching a refresh, and what depends on a piece

While a refresh runs, the map and every **Lineage** tab show it moving: the
transform pulses while its step runs, then its warehouse tables and the models
that read them light, and each report lights as the run rebuilds it. A step
that fails stops there: its piece turns red and its **Trust** row says why
(`1 check failed`). The map only watches. An edge says what depends on what,
never what should run; a refresh is started by a person or a pipeline's
schedule.

Select a warehouse table or a source table, or a model and then one of its
measures, and **Depends on this** lists every report figure downstream of it,
by report: its label, the number the built page prints and the report's
verdict, each a link to that figure's trace. It is read from the last builds'
manifests (a figure counts only when its query read that table or measure), so
a report never built here is named apart. It changes nothing.

## Why it works this way

The slow analysis in the transform and the fast work on reports never block
each other, because the model sits between them as a fixed contract. Editing
a report never re-runs the transform.

## Next

- Run all three stages: [[quickstart]]
- Write a transform: [[transform]]
