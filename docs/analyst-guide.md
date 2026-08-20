# TraceBi Analyst Guide

The analyst path from messy data to a served report, plus the full
development flow for ad-hoc reports as **artifact packages** — from blank
scaffold to a built, verified, fully-traceable artifact. Every code block is
runnable.

> **The `requests/` script lane was removed (0.8, breaking).** Earlier
> versions of this guide centered on request scripts; that lane — with no
> receipt and no way to earn one — is gone. The one report lane is the
> **artifact package** (`reports/<name>/`), covered below. A JSON spec
> migrates with `tracebi migrate spec reports/<name>.json`.

**Who this is for:** analysts writing against an existing TraceBi project (a
warehouse and `DataModel` someone has already wired up, or one you build with
the workflow below). If you're setting up connectors from scratch, the
[README](../README.md) Quick Start and [WORKFLOW.md](../WORKFLOW.md) are the
starting points. If your "analyst" is an AI agent, the playbook is
[AGENTS.md](../AGENTS.md) — the two planes, the assurance ladder, and the
MCP gateway tools — with step-by-step SOPs in [docs/agents/](agents/);
agents work through the gateway against the same models this guide uses.

---

## The three-phase workflow

The primary analyst path is three project-root folders, each with its own
cadence, decoupled by **freeze points** — a materialized artifact handed from
one phase to the next. [WORKFLOW.md](../WORKFLOW.md) is the full account; the
shape:

```
①  TRANSFORM    transforms/       ordinary, unconstrained pandas
     read a messy source → parse, clean, key, dedupe → WRITE star-schema tables
                                                        │
                                                        ▼  freeze: data/warehouse.duckdb
②  MODEL        models/           a thin DataModel over the warehouse
     grain, keys, measures in a few dozen lines a reviewer reads without the pandas
                                                        │
                                                        ▼  freeze: the model (the semantic contract)
③  REPORT       reports/          an artifact package (or JSON ReportSpec) over the model
     KPI cards, charts, tables — every figure a live query; served on the Reports page
```

**Phase ①** is the real analysis: pull the queries you need and do whatever the
data demands — window functions, prose parsing, cleaning — then *sink* clean,
named star-schema tables into a file-backed DuckDB warehouse with
`DuckDBConnector(...).write(df, "table")`. The framework does not constrain how
you clean; the contract is *what lands*. Reference impl:
[transforms/holdings_transform.py](../examples/portfolio_project/transforms/holdings_transform.py).

**Phase ②** declares a star schema over the warehouse — it reads the sink and
never sees the transform above it. Reference impl:
[models/portfolio_model.py](../examples/portfolio_project/models/portfolio_model.py).

**Phase ③** is an **artifact package** (`reports/<name>/`) — or a JSON
`ReportSpec`, a serialization of the same thing — whose every figure is a
live query against the model. Because the model is materialized, the page
re-renders in milliseconds with no pandas in the loop — editing the report
never re-runs phase ①. Reference impls:
[reports/portfolio_book/](../examples/portfolio_project/reports/portfolio_book/) (package) and
[reports/portfolio_dashboard.json](../examples/portfolio_project/reports/portfolio_dashboard.json) (spec).

```bash
cd examples/portfolio_project   # the reference project ships in the repo
python run_workflow.py       # ① builds data/warehouse.duckdb, ③ renders once
python -m tracebi.web.run    # serve it: Reports → portfolio_dashboard
```

**Honest scope of the trust machinery.** Lineage is *not* traced through the
phase-① pandas — the framework draws the line at the sink, where the numbers
become a contract you can report against. Stamped queries, validate-before-
execute on specs, and `tracebi verify` apply from the **model boundary onward**
(phases ② and ③). `tracebi verify` re-runs a manifest's recorded queries and
compares fingerprints; it does not read a transform and does not assert a
number is correct.

The rest of this guide covers the **artifact-package** path — the ad-hoc
route for reports you author as free HTML over the model — then the model and
`DataSet` verbs both the package and any factory report are built on.

---

## The artifact-package loop at a glance

```
tracebi new-report "My Report"      # 1. scaffold reports/my_report/
tracebi dev my_report               # 2. live loop — workbench, pins, exploration
tracebi report build my_report      # 3. render → output/my_report.html + manifest
tracebi verify output/my_report.html.manifest.json --strict --contracts
                                    # 4. re-run its receipt before anyone reads it
```

An artifact package is a directory `reports/<name>/`: `report.json` (the
data bindings — named queries against a model) plus `template.html` /
`style.css` / `script.js` — free HTML where every **figure claims a
binding** (`data-tb-figure` + `data-tb-binding`). A figure with no binding
carries `data-tb-unverified`; there is no third state.

The dev loop, step by step:

- **`tracebi dev <name>` blocks** — keep it open in its own terminal. It
  serves the report at the root and the **workbench** at `/__workbench`
  (figures, binding coverage, and the pins a reviewer left), re-rendering
  on every save to the package, `models/`, or `transforms/`.
- **Explore inside the artifact.** Blocks marked
  `data-tb-stage="exploration"` render under `tracebi dev` and die at
  build — scratch work never ships.
- **Read the pins before every pass.** `tracebi report status <name>`
  prints the earned state in the terminal; 📌 lines are a reviewer pointing
  at a figure with a note. Address those first.
- **Drafts are snapshots.** `tracebi report snapshot <name>` writes one
  HTML with exploration kept and a review banner; it carries no manifest
  and `verify` refuses it by name — a draft cannot impersonate a final.
- **Publishing is build + verify.** `tracebi report build <name>` strips
  exploration, validates every figure claim against its binding, and writes
  `output/<name>.html` plus the `.manifest.json` receipt. The package is
  already served on the **Reports** page — there is no separate publish
  step. `--contracts` also re-runs the sink contracts, so the receipt can
  say **the sink satisfied its contract** (never "the transform was
  verified" — contract status certifies what landed, not the pandas above
  it, and never colors a figure status).

`report.py` beside `report.json` is the escape hatch for pandas the model
can't express; its output stamps `verifiable: false` and never reads green
under `verify`. A JSON `ReportSpec` under `reports/` still renders — it is
a serialization, not a lane — and `tracebi migrate spec reports/<name>.json`
compiles it into a package, which shadows the same-named spec at discovery.

### Discovery mode — the workbench before a report exists

Run `tracebi dev` with **no argument** to open discovery mode: the same
workbench, anchored to nothing, over the project as a whole — warehouse tables,
sink contracts, models, and packages. It is the live surface for phases ① and
② before any report package exists. `tracebi dev <name>` anchors the workbench
to one package; `tracebi dev` alone is where you look while you are still
building the model underneath.

### Interactive controls subset — they never compute

A built artifact can carry `data-tb-filter` dropdowns, `data-tb-search`, and
`data-tb-rows` (scrollable tables). The honesty rule is locked in the runtime:
**controls subset which stamped rows a figure displays; they never compute a
new number.** So a value figure never reacts to a control, and a filtered KPI
needs its **own binding** rather than a client-side recomputation. This is what
keeps an interactive page as trustworthy as a static one — every number on
screen is still a stamped number, never one the browser invented.

### Capturing the exploration record

A discovery session is a lab notebook, not a report. `tracebi session export`
writes `explorations/<name>.html` (or `--format md` for the markdown twin) —
the committed record of the frames, charts, and notes you pushed to the
workbench. It carries **no manifest**, and `tracebi verify` refuses the file by
name: a lab notebook must not read as a receipt. It is the honest home for the
narrative a governed report deliberately does not carry.

### Delivering the report

`tracebi report send` builds the report, verifies it, and emails it with the
receipt — and **refuses to send an unverified receipt**:

```bash
tracebi report send my_report --to team@example.com --subject "Q3 book"
```

`--force` sends anyway, but the failing verdict travels with the report rather
than being hidden. Delivery reads `TRACEBI_SMTP_URL` / `TRACEBI_SMTP_FROM` for
email and `TRACEBI_SLACK_WEBHOOK` for Slack; point cron or CI at the same
command to schedule it. The refusal is the point: a receipt that does not
reproduce should never leave the building looking clean.

---

## Working with a model in code

The package's figures — and any `@register.report` factory — are built on the
same model surface and immutable `DataSet` verbs. This section is the shared
reference for both.

`tracebi validate` checks your project layout and then loads every model in
`models/`, verifying each dimension key is unique — a duplicate key silently
inflates every total it touches. Run it before you trust a number.

### Discover what data you have

First, see what shared models the project has defined:

```bash
tracebi list-models            # lists files in models/
```

Then load the one you need — this works whether or not the web server is running:

```python
from tracebi.model_registry import get_model, get_default_model, list_models

print(list_models())           # ["sales_model", "banking_model"]
model = get_model("sales_model")   # load a specific model by name
# or: model = get_default_model()  # load the first / default model

model.describe()        # tables, relationships, facts, dimensions
model.info()            # same, as a dict

orders = model.load("orders")
orders                  # rich repr: shape, columns, dtypes, sample rows
orders.help()           # cheat sheet of every DataSet verb
```

If no shared model exists yet, create one:

```bash
tracebi new-model "Sales Model"   # scaffolds models/sales_model.py
# edit it, then import with get_model("sales_model")
```

Or browse the web UI: **Models** shows every table with previews and the ER
diagram; **Explore** lets you prototype aggregations visually before
committing them to code.

### Load and transform

Every verb returns a **new immutable DataSet** and appends a step to its
lineage chain. Nothing mutates in place.

```python
orders = (
    model.load("orders", filter={"status": "shipped"})   # filter pushed to source
    .deduplicate(subset="order_id")                      # structured cleaning verbs
    .dropna(subset="region")
    .fillna({"discount": 0})
    .cast({"qty": "int64"})
    .assign(margin=lambda df: df.revenue - df.cost)      # add columns
    .filter("margin > 0", description="Profitable only") # pandas query syntax
    .sort("margin", ascending=False)
    .limit(100)                                          # top-N after sort
)

orders.print_lineage()   # the full audit chain, one line per step
```

**Prefer the named verbs over `.transform(lambda ...)`.** Both work, but named
verbs record structured lineage (rows removed, columns cast, fill counts) that
shows up in report manifests and the web UI's lineage graphs. `.transform()`
is the escape hatch when no verb fits.

Joining and aggregating:

```python
enriched = orders.join(customers, on="customer_id", how="left")

by_region = enriched.aggregate(
    by="region",
    revenue="sum",
    orders=("order_id", "nunique"),   # (column, func) names the output
)
```

Mistyped a column? Errors tell you what's available and suggest the closest
match: `dropna() column(s) not found: 'regin' (did you mean 'region'?)`.

## Verbs cheat sheet

| Verb | What it does | Lineage records |
|---|---|---|
| `.filter(expr)` | Pandas query string | expr, rows before/after |
| `.dropna(subset=)` | Drop rows with nulls | subset, rows removed |
| `.fillna(value)` | Fill nulls (scalar or `{col: val}`) | cells filled |
| `.deduplicate(subset=)` | Drop duplicate rows | subset, keep, rows removed |
| `.cast({col: dtype})` | Convert dtypes | type map |
| `.assign(col=...)` | Add/replace columns | columns added/replaced |
| `.join(other, on=)` | Join two DataSets | both sides' lineage, row counts |
| `.aggregate(by=, ...)` | Group + aggregate | group keys, agg map |
| `.sort(by)` | Sort rows | columns, direction |
| `.select(cols)` | Keep only these columns | column list |
| `.rename({old: new})` | Rename columns | rename map |
| `.limit(n)` | First n rows | n, rows before |
| `.transform(func)` | Escape hatch — any DataFrame → DataFrame | rows/columns delta |

Inspection (no lineage step): `.shape`, `.columns`, `len(ds)`, `.to_pandas()`,
`.print_lineage()`, `.fingerprint()`, `.help()`.

---

## Shared models and pipelines

If multiple people are writing reports against the same data, define the
model once in `models/` so nobody has to repeat the connector and table
setup:

```bash
tracebi new-model "Sales Model"       # creates models/sales_model.py — edit and commit it
tracebi new-pipeline "Sales ETL"      # creates pipelines/sales_etl.py — edit and commit it
```

Anyone on the team then gets:

```python
from tracebi.model_registry import get_model
from tracebi.pipeline_registry import get_runner

model = get_model("sales_model")      # loads models/sales_model.py on first access
runner = get_runner("sales_etl")      # loads pipelines/sales_etl.py on first access
runner.run("orders_silver")           # run a layer on demand
```

The web server auto-discovers both directories at startup — no extra
registration needed.

---

**Stuck?** `ds.help()` and `model.help()` print these cheat sheets in any
session. The [examples/](../examples/) directory has complete runnable
walkthroughs, and `tracebi/web/demo_app/reports/` shows production-shaped report
factories.
