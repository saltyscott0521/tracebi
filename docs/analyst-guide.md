# TraceBi Analyst Guide

The analyst path from messy data to a served report, plus the full
development flow for ad-hoc reports as **artifact packages** — from blank
scaffold to a built, verified, fully-traceable artifact. Every code block is
runnable.

> **Deprecated: the `requests/` script lane.** Earlier versions of this
> guide centered on request scripts. That lane is **deprecated and removed
> in 0.8** — `tracebi init` no longer scaffolds `requests/`, and
> `tracebi new-request` / `tracebi run` print a deprecation warning. The one
> report lane is the **artifact package** (`reports/<name>/`), covered
> below. The request-script walkthrough is kept for projects still on the
> lane through 0.7 and is clearly marked **legacy**.

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
route for reports you author as free HTML over the model — followed by the
**legacy request-script** walkthrough (deprecated, removed in 0.8). Both
share the same models, lineage, and manifests.

---

## The artifact-package loop at a glance

```
tracebi new-report "My Report"      # 1. scaffold reports/my_report/
tracebi dev my_report               # 2. live loop — workbench, pins, exploration
tracebi report build my_report      # 3. render → output/my_report.html + manifest
tracebi verify output/my_report.html.manifest.json --strict --contracts
                                    # 4. prove it before anyone reads it
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

---

## Legacy: the request-script lane (deprecated, removed in 0.8)

Everything below describes the old `requests/` script lane, kept for
projects still on it through 0.7. Do not start new work here — scaffold an
artifact package instead (`tracebi new-report`). Sections 2, 3, and 8
(model discovery and the DataSet verbs) apply to both lanes.

The legacy loop at a glance:

```
tracebi new-request "My Report"     # 1. scaffold (prints a deprecation warning)
tracebi dev my_report               # 2. edit ↔ live preview loop
tracebi run my_report               # 3. render final outputs
git add requests/my_report.py      # 4. ship — the web UI picks it up
```

## 1. Scaffold a request (legacy)

```bash
tracebi new-request "Open orders by region"   # DEPRECATED — use tracebi new-report
# → requests/open_orders_by_region.py

# Prefer notebooks? Same flow, .ipynb output:
tracebi new-request "Open orders by region" --notebook
```

Working in Jupyter? The [Notebook Guide](notebook-guide.md) covers rich
previews, inline report rendering, and shipping notebooks as request scripts.

The generated file has five numbered sections: parameters → model → datasets →
report → render. Fill them in top to bottom.

`tracebi validate` checks your project layout and then loads every model in
`models/`, verifying each dimension key is unique — a duplicate key silently
inflates every total it touches. Run it before you trust a number.

## 2. Discover what data you have

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

## 3. Load and transform

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

## 4. Parameters (legacy)

Declare defaults once; override from the CLI or the web UI without editing
code:

```python
from tracebi import request_params

params = request_params(period="Q2 2024", min_revenue=0)
```

```bash
tracebi run my_report --param period="Q3 2024" --param min_revenue=500
```

Overrides are coerced to the type of the default (`"500"` → `500` because the
default is an int); unknown parameter names fail loudly. The web UI's
**Requests** page renders a form from these defaults automatically.

## 5. Build the report (legacy)

```python
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection

report = (
    Report("Open Orders by Region")
    .author("Your Name")
    .description("Weekly open-order snapshot.")
    .parameter("period", params["period"])

    .add(TextSection(title="Summary", content="Summary", style="heading1"))
    .add(ChartSection(title="Revenue by Region", dataset=by_region,
                      chart_type="bar", x="region", y="revenue"))
    .add(TableSection(title="Detail", dataset=by_region, totals=["revenue"]))
)
```

Pass DataSets straight into sections — each section's full lineage is embedded
in the report manifest automatically. That manifest *is* the audit trail: when
someone asks "where did this number come from?", it's already answered.

## 6. The edit ↔ preview loop (legacy)

```bash
tracebi dev my_report
```

Watches your script, re-runs it on save, and serves a live HTML preview in
your browser. (Pointed at a request *script*, `tracebi dev` keeps this
legacy single-file loop; pointed at an artifact *package* it opens the
current loop with the workbench.)

When you're done, render the final artifacts:

```bash
tracebi run my_report          # writes output/*.xlsx and *.html + *.manifest.json
```

The `.manifest.json` beside each output is the **receipt**: the recorded
queries, lineage, input fingerprints, and git SHA behind every section.
Rendered HTML is disposable; the manifest is not — retain it. Later,
`tracebi verify output/my_report.html.manifest.json` re-proves it by re-running
each section's recorded model query and reporting whether the numbers still
reproduce, whether the source data drifted, or whether the model itself
changed. (Sections built from hand-transformed DataSets carry no recorded
query and are reported as `unverifiable` rather than guessed at. A report
whose sections are *all* unverifiable still exits 0, but the verdict reads
`NOTHING VERIFIED` — nothing in it was checked. A manifest with no
data-bearing section at all exits 1: there was nothing to check, so there is
nothing to pass.)

## 7. Publish to the web UI (legacy)

The template's last section registers your report with the web server:

```python
from tracebi.web import register

@register.report("open_orders", description="Weekly open-order snapshot.")
def _factory():
    return report
```

Any script in `requests/` is still auto-discovered on server start (and on
dev-mode reload) through 0.7, with a deprecation notice — the lane is
removed in 0.8. Your report appears on the **Requests** page with its
parameter form, run button, downloads, and per-section lineage graphs —
no extra wiring. (Artifact packages need none of this: `reports/<name>/`
is served on the **Reports** page as soon as it exists.)

## 8. Verbs cheat sheet

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
