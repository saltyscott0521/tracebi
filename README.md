# TraceBi

[![CI](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml/badge.svg)](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://github.com/saltyscott0521/tracebi)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A **code-first, traceable BI and analytics framework** for Python.

Define your data model, transformations, and reports entirely in code.
Every dataset, report, and pipeline run is traceable back to the exact
connector, query, and transform steps that produced it.

---

## Why TraceBi?

| Feature | Dash / Streamlit | dbt | Qlik / Tableau | **TraceBi** |
|---|---|---|---|---|
| Code-defined reports | ✓ | ✗ | ✗ | ✓ |
| Relational data model | ✗ | ✓ | ✓ | ✓ |
| Full data lineage per report | ✗ | partial | ✗ | ✓ |
| Excel / HTML output | ✗ | ✗ | ✓ | ✓ |
| Medallion architecture | ✗ | ✓ | ✗ | ✓ |
| Scheduled pipelines | ✗ | ✓ | ✓ | ✓ |
| Live dashboard | ✓ | ✗ | ✓ | ✓ |

---

## What's built

- [x] **Phase 1** — Connectors (CSV, SQL, BigQuery, Snowflake, Memory, DuckDB) with push-down filter/columns, DataModel, DataSet with immutable lineage chain
- [x] **Phase 2** — Report engine (Excel + HTML renderers, lineage manifest per render)
- [x] **Phase 2.5** — Landing/Manipulation/Final layers (medallion-compatible), DuckDB-backed star-schema query on DataModel, LineageDiagram
- [x] **Phase 3** — Live Dash dashboard with associative filters
- [x] **Phase 4** — Pipeline runner with APScheduler, DB persistence, cross-layer lineage
- [x] **Phase 5** — Web UI (FastAPI + React, Dash embedded), folder-based auto-discovery, optional HTTP Basic auth, `tracebi` CLI, docker-compose deployment

---

## 30-second quick start

No database, no config — just pandas in memory:

```python
import pandas as pd
from tracebi import DataModel, MemoryConnector
from tracebi.reports import Report, TableSection, HTMLRenderer

orders = pd.DataFrame({
    "order_id": [1, 2, 3, 4],
    "region":   ["NE", "SE", "NE", "MW"],
    "revenue":  [100.0, 200.0, 150.0, 300.0],
})

model = DataModel("Demo").add_connector(MemoryConnector("mem", {"orders": orders}))
model.add_table("orders", connector="mem", source="orders")

ds = model.load("orders")
report = Report("Demo").add(TableSection(title="Orders", dataset=ds))
HTMLRenderer().serve(report, port=8080)   # opens in your browser
```

The same `DataSet` carries its lineage all the way through to the rendered
manifest — no separate audit step.

---

## Coming from pandas?

You already know 95% of this. A `DataSet` is a thin, **immutable** wrapper
around a `pandas.DataFrame` that records what happened to it:

```python
ds = model.load("orders")        # DataSet, not DataFrame

# The verbs you already use have first-class equivalents that record
# structured lineage (keys, measures, row counts in/out):
enriched = (
    ds
    .assign(margin=lambda df: df.revenue - df.cost)        # like df.assign
    .join(customers, on="customer_id", how="left")         # like df.merge
    .aggregate(by="region",                                # like groupby/agg
               revenue="sum", orders=("order_id", "nunique"))
)

# Anything else fits in .transform() — any DataFrame -> DataFrame function
# (pivot, resample, custom logic) works unchanged:
pivoted = ds.transform(lambda df: df.pivot_table(...), description="…")

df = ds.to_pandas()              # escape hatch: plain DataFrame copy, any time
ds.help()                        # cheat sheet of the fluent API
```

The differences that matter:

- **Nothing mutates.** Every method (`.filter()`, `.transform()`, `.sort()`, …)
  returns a *new* DataSet; the original is untouched. Branch freely.
- **Every step is recorded.** The description you pass becomes part of the
  audit trail — `ds.print_lineage()` shows the full chain with row counts.
- **`.filter()` takes a pandas query string** (`"status == 'shipped'"`), the
  same syntax as `DataFrame.query()`.
- **In Jupyter**, a `DataSet` at the end of a cell renders a rich preview —
  shape, lineage chain, and the first rows with dtypes.

---

## Choose your path

| I want to… | Start here |
|---|---|
| Work in a notebook with rich previews | `examples/analyst_quickstart.py` — run it cell-by-cell in Jupyter |
| Write a one-off report or query | Copy `requests/_template.py` and run it with `tracebi run` |
| Build a scheduled ETL pipeline | `examples/phase4_example.py` → then `web/demo_app/` as a wiring template |
| Expose everything in a web UI | `web/demo_app/` shows the full wiring; `TRACEBI_APP=mymodule python web/run.py` |
| Query facts/dimensions visually | Tag tables with `add_fact()` / `add_dimension()`, then open the **Explore** page |
| Understand data flow end-to-end | `examples/phase1_example.py` through `phase4_example.py` in order |
| Browse the API interactively | Start the server, then open `http://localhost:8000/docs` (Swagger UI) or `/redoc` |
| Add a chart or table to a report | [Build a report](#3-build-a-report) — `ChartSection`, `TableSection`, `TextSection` |

---

## Installation

TraceBi is not on PyPI yet — install from a clone (or straight from GitHub).
The fastest path for an analyst:

```bash
git clone https://github.com/saltyscott0521/tracebi
cd tracebi
pip install -e ".[analyst]"           # reports + sql + csv + lineage + duckdb + dotenv
```

Or without cloning:

```bash
pip install "tracebi[analyst] @ git+https://github.com/saltyscott0521/tracebi"
```

Pick the pieces you need (extras work the same with either install style):

```bash
pip install -e "."                    # core only (pandas)
pip install -e ".[reports]"           # Excel + HTML renderers
pip install -e ".[dashboard]"         # Dash dashboard
pip install -e ".[pipeline]"          # scheduling + DB write-back
pip install -e ".[lineage]"           # lineage diagrams
pip install -e ".[duckdb]"            # DuckDB connector + push-down engine
pip install -e ".[web]"               # FastAPI + uvicorn web UI
pip install -e ".[all]"               # everything
```

### Docker / deployment

The repo ships a multi-stage `Dockerfile` (builds the React UI, then the
Python app) and a `docker-compose.yml` that mounts `./data`, `./output`,
and `./requests` from the host so your pipeline DB and rendered reports
survive container restarts.

```bash
# Local: web UI on http://localhost:8000
docker compose up --build
```

Optional environment overrides (set in a `.env` beside `docker-compose.yml`):

| Variable | Purpose |
|---|---|
| `TRACEBI_APP` | Python module to import on startup (default `web.demo_app`) |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | Turn on HTTP Basic auth |
| `TRACEBI_AUTH_PROXY_HEADER` | Trust an upstream identity header (Authelia / oauth2-proxy / Cloudflare Access) |
| `TRACEBI_EMBED_DASHBOARDS=0` | Run dashboards as separate processes |
| `TRACEBI_DEV_MODE=1` | Mount `/api/_dev/reload` for hot iteration |

**Single-VM deployment** is the supported v1 story — one container behind
nginx or a reverse-proxy, SQLite volume mounted at `/app/data`. Cloud Run /
ECS / Fly.io all work the same way (the scheduler runs in-process; if the
container restarts, schedules resume from the persisted DB).

**Honest caveats:** the scheduler is single-process. It will not scale
horizontally across replicas, and a hard kill loses in-flight runs (the
`tracebi_runs` table still records that they started). For larger workloads
swap APScheduler for an external orchestrator (Airflow, Prefect, Dagster) and
keep the rest of TraceBi as the data layer.

### CLI

```bash
tracebi init my_project                              # scaffold tracebi.yaml + .env.example + requests/
tracebi new-request "Open orders by region"          # → requests/open_orders_by_region.py
tracebi new-request "Customer churn" --notebook      # → requests/customer_churn.ipynb
tracebi list-requests
tracebi run open_orders_by_region                    # works for .py and .ipynb
tracebi dev open_orders_by_region                    # live preview: re-runs + reloads on save
tracebi validate                                     # sanity-check the current project
```

`tracebi dev` serves the rendered report on http://127.0.0.1:8001 and reloads
the browser every time you save the script — keep it next to your editor for
a tight authoring loop. Script errors render as a traceback page that
recovers on the next good save.

---

## Quick Start

### 1. Connect to data

```python
from tracebi import DataModel, SQLConnector, MemoryConnector

# SQLite / Postgres / MySQL / BigQuery / Snowflake
db = SQLConnector("sales_db", url="sqlite:///data/sales.db")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_table("orders",    connector="sales_db", source="orders")
model.add_table("customers", connector="sales_db", source="customers")
model.add_relationship("orders_customers", "orders", "customers",
                        left_key="customer_id", how="left")
```

### 2. Load and transform (full lineage at every step)

```python
orders = (
    model.load("orders")
    .filter("status == 'shipped'", description="Shipped orders only")
    .transform(
        lambda df: df.assign(margin=df["revenue"] - df["cost"]),
        description="margin = revenue - cost",
    )
    .sort("margin", ascending=False)
)

orders.print_lineage()
# Step 1: [LOAD]       Loaded 'orders' from connector 'sales_db'
# Step 2: [FILTER]     Shipped orders only  (250 → 198 rows)
# Step 3: [TRANSFORM]  margin = revenue - cost
# Step 4: [SORT]       Sorted by margin (desc)
```

### 3. Build a report

```python
from tracebi.reports import (
    Report, TextSection, TableSection, ChartSection,
    ExcelRenderer, HTMLRenderer,
)

report = (
    Report("Q2 Sales Report")
    .author("Data Team")
    .parameter("period", "Q2 2024")
    .add(TextSection(title="Summary", content="Summary", style="heading1"))
    .add(TextSection(content="Revenue up 12% vs Q1.", style="normal"))
    .add(ChartSection(title="Revenue Trend", dataset=trend_ds,
                      chart_type="line", x="month", y="revenue"))
    .add(TableSection(title="Top Orders", dataset=orders,
                      columns=["region", "product", "revenue"],
                      totals=["revenue"]))
)

ExcelRenderer().render(report, "output/q2_sales.xlsx")  # + saves manifest.json
HTMLRenderer().render(report, "output/q2_sales.html")
HTMLRenderer().serve(report, port=8080)   # open in browser
HTMLRenderer().preview(report)            # inline in Jupyter
```

Layout and styling extras:

```python
from tracebi.reports import Metric, MetricSection, RowSection

report = (
    Report("Q2 Sales Report")
    # Row of KPI cards with green/red deltas
    .metrics([
        Metric("Total Revenue", 1_250_000, format="currency0", delta=0.12),
        Metric("Refund Rate", 0.034, format="percent", delta=-0.01, good_when_up=False),
    ])
    # Chart and table side by side (HTML; stacks vertically in Excel)
    .row(
        ChartSection(title="By Region", dataset=by_region, chart_type="bar",
                     x="region", y="revenue", show_values=True),
        TableSection(title="Detail", dataset=by_region,
                     number_formats={"revenue": "currency"},   # named shortcuts
                     highlight_negatives=["margin"],           # red negatives
                     color_scale={"revenue": "#2E74B5"}),      # heat map
    )
)
```

Named number formats (`currency`, `currency0`, `percent`, `comma`, `decimal`)
work in tables and metrics, in both HTML and Excel output.

**In notebooks**, `DataSet`, `DataModel`, and `Report` all render rich inline
previews — a `Report` at the end of a cell shows the fully rendered report.
Call `.help()` on any of them for an API cheat sheet.

### 4. Landing → Manipulation → Final (Medallion architecture)

The three-step layer model — TraceBi's positioning name and the legacy
medallion name resolve to the same classes:

| TraceBi name        | Medallion alias  | Role                                                |
|---------------------|------------------|-----------------------------------------------------|
| `LandingLayer`      | `BronzeLayer`    | Connect to upstream table, ingest as-is.            |
| `ManipulationLayer` | `SilverLayer`    | Optional light cleaning before serving.             |
| `FinalLayer`        | `GoldLayer`      | Serve via DataModel star-schema query — facts + dims. |

```python
from tracebi import LandingLayer, ManipulationLayer, FinalLayer  # or BronzeLayer / SilverLayer / GoldLayer

# Landing — raw ingest, zero transforms
landing = LandingLayer(connector=db, source="orders_raw",
                       sink=db, sink_table="orders_bronze")
ds_landing = landing.execute()   # loads + writes to DB

# Manipulation — declarative cleaning pipeline
manip = (
    ManipulationLayer(source=db, source_table="orders_bronze",
                      sink=db, sink_table="orders_silver")
    .cast({"qty": "int64", "order_date": "datetime64[ns]"})
    .drop_nulls(subset=["order_id"])
    .deduplicate(subset=["order_id"])
)
ds_manip = manip.execute()   # loads landing → cleans → writes manipulation

# Tag tables on the DataModel with star-schema roles
model.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region", "segment"])
model.add_fact("fact_orders", table_name="orders_silver",
               measures=["revenue", "qty"],
               foreign_keys={"dim_customer": "customer_id"})

# Final — aggregated via the model's star-schema query (DuckDB-backed)
final = FinalLayer(model=model, fact="fact_orders",
                   measures={"revenue": "sum", "qty": "sum"},
                   dimensions=["dim_customer.region"],
                   sink=db, sink_table="revenue_by_region_gold")
ds_final = final.execute()   # queries → aggregates → writes serving table
```

### 5. Schedule pipelines

```python
from tracebi.pipeline.runner import PipelineRunner

runner = PipelineRunner(db_url="sqlite:///data/tracebi.db")

# Each layer has its own independent schedule
# (landing / manip / final are the layers built in section 4 above)
runner.register(landing, name="orders_bronze",   schedule="0 * * * *")
runner.register(manip,   name="orders_silver",   schedule="15 * * * *",
                depends_on="orders_bronze")
runner.register(final,   name="revenue_by_region", schedule="30 6 * * *",
                depends_on="orders_silver")

# On-demand: run one layer
runner.run("orders_silver")

# On-demand: full refresh (bronze → silver → gold)
runner.run("revenue_by_region", refresh=True)

# View run history with cross-layer lineage
runner.lineage("revenue_by_region")

# Start the scheduler (blocking)
runner.start()
```

Every run is recorded in `tracebi_runs` with `rows_in`, `rows_out`, `status`,
and an `upstream_run_id` linking back to the previous layer's run.

### 6. Live dashboard

```python
from tracebi.dashboard import Dashboard, DashboardServer
from tracebi.dashboard import FilterPanel, MetricPanel, ChartPanel, TablePanel

dashboard = (
    Dashboard("Q2 Sales Dashboard")
    .columns(2)
    .add_filter(FilterPanel("region-filter", label="Region",
                            column="region", table_name="orders"))
    .add_panel(MetricPanel("total-revenue", title="Total Revenue",
                           table_name="orders", column="revenue",
                           aggregation="sum", prefix="$"))
    .add_panel(ChartPanel("by-region", title="Revenue by Region",
                          table_name="orders", chart_type="bar",
                          x="region", y="revenue"))
    .add_panel(TablePanel("orders-table", title="Orders",
                          table_name="orders",
                          columns=["order_id", "region", "revenue"]))
)

DashboardServer(dashboard, model=model).run(port=8050)
# Open http://localhost:8050/
```

Filters are **associative** — selecting a region automatically filters every
panel that shares that column.

### 7. Lineage diagrams

```python
from tracebi.lineage.diagram import LineageDiagram

diag = LineageDiagram(ds_gold)   # or LineageDiagram(report)
diag.show()                       # matplotlib / Jupyter inline
diag.to_html("lineage.html")      # standalone HTML with embedded SVG
print(diag.to_mermaid())          # paste into GitHub markdown
```

---

## Web UI

A browser interface over your TraceBi registry — connectors, models, reports, pipelines, and live dashboards all in one place. Highlights:

- **Explore** — a visual star-schema query builder: pick a fact, toggle
  measures and dimension attributes, add filters, and get results with a
  chart, CSV download, and the *lineage graph of the exact query that ran*.
- **Models** — table previews with column dtypes and full-table CSV export,
  plus an interactive ERD of your relationships.
- **Reports** — run in the browser (in the background, with run history and
  a toast when done), download as Excel or HTML, and inspect per-section
  lineage. Failures show the full Python traceback.
- **Requests** — browse the scripts in `requests/` and run them straight
  from the browser. Scripts execute fresh on every click, so edits on disk
  show up without registering anything or restarting the server. Scripts
  that declare `request_params(...)` get an automatic parameter form.
- **Pipelines** — the medallion chain as a live DAG with per-layer run
  buttons and run history.

```bash
# Install web dependencies
pip install -e ".[web]"

# Start the server (hot-reload on by default)
python web/run.py
# Open http://localhost:8000
```

The API is self-documenting: once the server is running, open
[`http://localhost:8000/docs`](http://localhost:8000/docs) for the Swagger UI
or [`http://localhost:8000/redoc`](http://localhost:8000/redoc) for ReDoc —
every endpoint, parameter, and response schema is listed there.

`web/demo_app/` is the default app module package. It wires an in-memory `MemoryConnector` for the main `SalesModel` and stands up a self-contained SQLite medallion pipeline (Landing → Manipulation → Final) at startup so the Pipelines page has live run history. Reports and dashboards read from those resources.

To point the UI at your own data module instead of the built-in demo:

```bash
TRACEBI_APP=mypackage.tracebi_config python web/run.py
```

Your module just needs to import `registry` and call `registry.add_connector()`, `registry.add_model()`, `@registry.report(...)`, and optionally `registry.add_pipeline()` / `registry.add_dashboard()`.

### 8. Adding reports and dashboards to the web UI

```python
from web.api.registry import registry
from tracebi.reports import Report, TableSection
from tracebi.dashboard import Dashboard, DashboardServer, ChartPanel

# Register a report
@registry.report("my_report", description="My custom report")
def my_report():
    ds = model.load("orders")
    return Report("My Report").add(TableSection(title="Orders", dataset=ds))

# Register a dashboard
dashboard = Dashboard("My Dashboard").add_panel(
    ChartPanel("rev", title="Revenue", dataset=ds, chart_type="bar", x="region", y="revenue")
)
registry.add_dashboard("my_dashboard", DashboardServer(dashboard, model=model))
```

---

## Local database setup (example)

```bash
# Create data/tracebi.db, seed source tables, run initial Bronze load
python seeds/seed_db.py

# Run Silver
python -c "from seeds.seed_db import runner; runner.run('orders_silver')"

# Full Gold refresh
python -c "from seeds.seed_db import runner; runner.run('revenue_by_region', refresh=True)"

# Start scheduler
python -c "from seeds.seed_db import runner; runner.start()"
```

---

## Running the examples

```bash
python examples/analyst_quickstart.py  # notebook-first tour: rich previews, report styling
python examples/phase1_example.py      # connectors + DataModel + lineage
python examples/phase2_example.py      # report engine (opens browser)
python examples/phase25_example.py     # medallion + star schema + lineage diagram
python examples/phase3_example.py      # live Dash dashboard
python examples/phase4_example.py      # full pipeline (run seeds/seed_db.py first)
```

## Running tests

```bash
pytest tests/
# 339 passed
```

---

## Project structure

```
tracebi/
├── tracebi/
│   ├── connectors/       CSV, SQL, BigQuery, Snowflake, Memory, DuckDB
│   ├── model/            DataSet, DataModel (with star-schema query)
│   ├── etl/              LandingLayer, ManipulationLayer, FinalLayer (Bronze/Silver/Gold aliases)
│   ├── reports/          Report, ExcelRenderer, HTMLRenderer (+ render_pdf via weasyprint)
│   ├── dashboard/        Dashboard, DashboardServer, panels
│   ├── pipeline/         PipelineRunner (APScheduler + DB)
│   └── lineage/          LineageDiagram
├── web/
│   ├── api/              FastAPI app, routers, registry
│   ├── ui/               React UI (Vite)
│   ├── demo_app/         Built-in demo (medallion + in-memory fallback)
│   ├── run.py            Dev server entrypoint
│   └── requirements.txt  Web-only dependencies
├── examples/             Runnable demos (phase1–4)
├── tests/                339 tests across all phases
├── seeds/                seed_db.py — one-command DB setup
├── requests/             _template.py — scaffold for ad hoc report scripts
├── data/                 SQLite DB lives here (gitignored)
└── NOTES.md              Design decisions and architecture reference
```

---

## Ad hoc reports

Copy `requests/_template.py`, rename it, fill in the four sections
(connect → build datasets → build report → render), and commit it to git.
The script is the permanent, auditable record of how the numbers were produced.

Declare parameters with defaults in one line — they're overridable from the
CLI and surface as a form on the web UI's Requests page:

```python
from tracebi import request_params

params = request_params(period="Q2 2024", top_n=10)
```

```bash
tracebi run my_report --param period="Q3 2024" --param top_n=25
```

Run standalone, the script just uses the defaults — no harness required.

```
requests/
├── _template.py
├── 2024_06_open_orders_by_region.py
└── 2024_07_customer_churn_analysis.py
```

---

## License

MIT
