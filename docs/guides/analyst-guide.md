# TraceBi Analyst Guide

Take a report from a blank folder to a built, checked file that the app
serves, then work with the model directly in Python.

## Before you begin

- A TraceBi project with a warehouse and a model. The reference project in
  `examples/portfolio_project/` has both, and so does a project from
  `tracebi init` ([[quickstart]]).
- If your analyst is an AI agent, give it `AGENTS.md` and the SOPs in
  `docs/agents/` instead ([[sop-authoring]]).

## Build a report

### 1. Build the reference project

```bash
cd examples/portfolio_project
python run_workflow.py       # runs the transforms, then builds every report
python -m tracebi.web.run    # serves it at http://127.0.0.1:8000
```

The transform `transforms/holdings_transform.sql` writes the warehouse,
`models/portfolio_model.yaml` defines it, and the packages under
`reports/portfolio_model/` read it. `portfolio_book/` is an editorial page and
`portfolio_dashboard/` is an app dashboard.

### 2. Create a report package

```bash
tracebi new-report "My Report"
```

This writes `reports/my_report/`: `report.json` with the data bindings (named
queries against a model) and `template.html`, the page. Every figure on the
page names a binding with `data-tb-figure` and `data-tb-binding`. A figure
with no binding must carry `data-tb-unverified`.

### 3. Open the live loop

```bash
tracebi dev my_report
```

Keep it running in its own terminal. It opens the app on the report in Build
mode. The page re-renders when you save the package, a model or a transform.
The panel beside it shows what changed on each save, the data each binding
reads, checks, and notes a reviewer left. Put scratch work in
`data-tb-stage="exploration"` blocks; they show here and are removed at build.

### 4. Read the pins

```bash
tracebi report status my_report
```

This prints what each figure has earned. Lines marked 📌 are a reviewer
pointing at a figure with a note. Handle those first.

### 5. Build

```bash
tracebi report build my_report
```

The build removes exploration blocks, checks every figure against its binding,
and writes `output/my_report.html` and `output/my_report.html.manifest.json`.
The app already lists the package under its model, so there is no separate
publish step.

### 6. Check it

```bash
tracebi verify output/my_report.html.manifest.json --strict --contracts
```

`--strict` fails unless every figure reproduces. `--contracts` also re-runs
the sink contracts, so the trace can say the sink satisfied its contract.
Contract status never changes a figure's status.

### 7. Send it

```bash
tracebi report send my_report --to team@example.com --subject "Q3 book"
```

This builds, verifies and emails the report with its manifest. It refuses to
send a report that does not verify. `--force` sends anyway, with the failing
verdict in the email. It needs `TRACEBI_SMTP_URL` and `TRACEBI_SMTP_FROM`;
`TRACEBI_SLACK_WEBHOOK` adds a Slack ping. To send on a timer, add a
`schedule` block to `report.json` and run `tracebi schedule run` from cron, or
`tracebi schedule serve` ([[report-json]]).

## What happened

- The report's numbers are queries against the model, run once at build and
  fingerprinted.
- The built page can filter: each filter re-runs every figure's own query over
  the slice the page carries, and the chip reads Local. A figure's number is
  only ever a query result. Search only narrows the rows shown.
- `report.py` beside `report.json` is the escape hatch for pandas the model
  cannot express. Its outputs are stamped `verifiable: false` and never read
  green.
- A JSON `ReportSpec` under `reports/` still builds. `tracebi migrate spec
  reports/<name>.json` compiles it into a package, which then takes its place.

## Explore before a report exists

```bash
tracebi dev
```

With no report name, the app opens on the Data page with the project feed.
Any script in the project can post to it with `tracebi.workbench.show(df,
note=...)`. The warehouse tables are on Data's Warehouse tab, and each model's
schema on its Model tab.

To keep a record of the session:

```bash
tracebi session export               # explorations/<name>.html
tracebi session export --format md   # the Markdown version
```

The export carries no manifest, and `tracebi verify` refuses it.

## Work with a model in Python

### 1. Find the models

```bash
tracebi list-models
tracebi validate        # loads every model and checks dimension keys are unique
```

### 2. Load one

```python
from tracebi.model_registry import get_model, get_default_model, list_models

print(list_models())               # ["sales_model", "banking_model"]
model = get_model("sales_model")   # or get_default_model()

model.describe()        # tables, relationships, facts, dimensions
orders = model.load("orders")
orders                  # shape, columns, dtypes, sample rows
orders.help()           # every DataSet method
```

No web server is needed. If no model exists yet, `tracebi new-model "Sales
Model"` writes `models/sales_model.yaml`.

In the app, **Ask** puts a question to a model as a sentence built from its
own measures and dimensions ("Show *fair value* by *sector*, *largest first*,
*top 8*"). The answer is a fresh query, marked Not checked. **Keep this**
starts a draft report of that figure. **Advanced** opens the query builder,
and "The query as code" gives the Python and the `report.json` binding.

### 3. Transform the data

Every method returns a new `DataSet` and adds a step to its lineage:

```python
orders = (
    model.load("orders", filter={"status": "shipped"})   # filter at the source
    .deduplicate(subset="order_id")
    .dropna(subset="region")
    .fillna({"discount": 0})
    .cast({"qty": "int64"})
    .assign(margin=lambda df: df.revenue - df.cost)
    .filter("margin > 0", description="Profitable only")
    .sort("margin", ascending=False)
    .limit(100)
)
orders.print_lineage()   # one line per step
```

Use the named methods rather than `.transform(lambda ...)` where you can. They
record what they did (rows removed, columns cast, cells filled) in lineage.

```python
enriched = orders.join(customers, on="customer_id", how="left")
by_region = enriched.aggregate(
    by="region",
    revenue="sum",
    orders=("order_id", "nunique"),   # (column, func) names the output
)
```

A mistyped column names the closest match:
`dropna() column(s) not found: 'regin' (did you mean 'region'?)`.

### DataSet methods

| Method | Does | Lineage records |
|---|---|---|
| `.filter(expr)` | Pandas query string | expr, rows before and after |
| `.dropna(subset=)` | Drop rows with nulls | subset, rows removed |
| `.fillna(value)` | Fill nulls (scalar or `{col: val}`) | cells filled |
| `.deduplicate(subset=)` | Drop duplicate rows | subset, keep, rows removed |
| `.cast({col: dtype})` | Convert dtypes | type map |
| `.assign(col=...)` | Add or replace columns | columns added or replaced |
| `.join(other, on=)` | Join two DataSets | both sides' lineage, row counts |
| `.aggregate(by=, ...)` | Group and aggregate | group keys, agg map |
| `.sort(by)` | Sort rows | columns, direction |
| `.select(cols)` | Keep these columns | column list |
| `.rename({old: new})` | Rename columns | rename map |
| `.limit(n)` | First n rows | n, rows before |
| `.transform(func)` | Any DataFrame to DataFrame | rows and columns changed |

These add no lineage step: `.shape`, `.columns`, `len(ds)`, `.to_pandas()`,
`.print_lineage()`, `.fingerprint()`, `.help()`.

## Share a model and a pipeline with your team

```bash
tracebi new-model "Sales Model"       # models/sales_model.yaml
tracebi new-pipeline "Sales ETL"      # pipelines/sales_etl.yaml
```

Commit both. Anyone on the team can then load them:

```python
from tracebi.model_registry import get_model
from tracebi.pipeline_registry import get_runner

model = get_model("sales_model")
runner = get_runner("sales_etl")
runner.run("transform")               # a YAML pipeline has two steps: transform, build
```

The web server finds both folders at startup.

## Next

- Use a notebook for the transform: [[notebook-guide]]
- Style the page: [[styling-a-report]]
