# TraceBi Analyst Guide

The complete development flow for writing request scripts — from blank file to
a published, parameterized, fully-traceable report. One linear path; every
code block is runnable.

**Who this is for:** analysts writing reports against an existing TraceBi
project (a `DataModel` someone has already wired up). If you're setting up
connectors and models from scratch, start with the [README](../README.md)
Quick Start instead.

---

## The development loop at a glance

```
tracebi new-request "My Report"     # 1. scaffold
tracebi dev my_report               # 2. edit ↔ live preview loop
tracebi run my_report               # 3. render final outputs
git add requests/my_report.py      # 4. ship — the web UI picks it up
```

---

## 1. Scaffold a request

```bash
tracebi new-request "Open orders by region"
# → requests/open_orders_by_region.py

# Prefer notebooks? Same flow, .ipynb output:
tracebi new-request "Open orders by region" --notebook
```

Working in Jupyter? The [Notebook Guide](notebook-guide.md) covers rich
previews, inline report rendering, and shipping notebooks as request scripts.

The generated file has five numbered sections: parameters → model → datasets →
report → render. Fill them in top to bottom.

`tracebi validate` checks your project layout (tracebi.yaml, requests/, .env)
if something feels misconfigured.

## 2. Discover what data you have

Before writing transforms, see what's in the model. In a notebook or REPL:

```python
from tracebi.web import register
model = register.get_default_model()

model.describe()        # tables, relationships, facts, dimensions
model.info()            # same, as a dict

orders = model.load("orders")
orders                  # rich repr: shape, columns, dtypes, sample rows
orders.help()           # cheat sheet of every DataSet verb
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

## 4. Parameters

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

## 5. Build the report

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

## 6. The edit ↔ preview loop

```bash
tracebi dev my_report
```

Watches your script, re-runs it on save, and serves a live HTML preview in
your browser. This is the fastest way to iterate on layout and content.

When you're done, render the final artifacts:

```bash
tracebi run my_report          # writes output/*.xlsx and *.html
```

## 7. Publish to the web UI

The template's last section registers your report with the web server:

```python
from tracebi.web import register

@register.report("open_orders", description="Weekly open-order snapshot.")
def _factory():
    return report
```

Any script in `requests/` is auto-discovered on server start (and on
dev-mode reload). Your report appears on the **Requests** page with its
parameter form, run button, downloads, and per-section lineage graphs —
no extra wiring.

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

**Stuck?** `ds.help()` and `model.help()` print these cheat sheets in any
session. The [examples/](../examples/) directory has complete runnable
walkthroughs, and `web/demo_app/reports/` shows production-shaped report
factories.
