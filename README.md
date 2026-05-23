# TraceBi

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

## Installation

```bash
# Core
pip install pandas

# Reports (Excel + charts)
pip install -e ".[reports]"

# Dashboard
pip install -e ".[dashboard]"

# Pipelines (scheduling + DB write-back)
pip install -e ".[pipeline]"

# Lineage diagrams
pip install -e ".[lineage]"

# DuckDB connector + push-down engine
pip install -e ".[duckdb]"

# Everything
pip install -e ".[reports,dashboard,pipeline,lineage,sql,duckdb,web]"
```

### Docker

```bash
docker compose up --build      # web UI on http://localhost:8000
```

### CLI

```bash
tracebi new-request "Open orders by region"   # scaffold requests/open_orders_by_region.py
tracebi list-requests
tracebi run open_orders_by_region
```

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
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer

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
runner.register(bronze, name="orders_bronze",   schedule="0 * * * *")
runner.register(silver, name="orders_silver",   schedule="15 * * * *",
                depends_on="orders_bronze")
runner.register(gold,   name="revenue_by_region", schedule="30 6 * * *",
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

A browser interface over your TraceBi registry — connectors, models, reports, pipelines, and live dashboards all in one place.

```bash
# Install web dependencies
pip install -r web/requirements.txt

# Start the server (hot-reload on by default)
python web/run.py
# Open http://localhost:8000
```

The web UI auto-detects `data/tracebi.db`. If the Silver pipeline layer has been run, reports and dashboards read from real medallion data. Otherwise it falls back to in-memory demo data.

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
python examples/phase1_example.py    # connectors + DataModel + lineage
python examples/phase2_example.py    # report engine (opens browser)
python examples/phase25_example.py   # medallion + star schema + lineage diagram
python examples/phase3_example.py    # live Dash dashboard
python examples/phase4_example.py    # full pipeline (run seeds/seed_db.py first)
```

## Running tests

```bash
pytest tests/
# 163 passed
```

---

## Project structure

```
tracebi/
├── tracebi/
│   ├── connectors/       CSV, SQL, BigQuery, Snowflake, Memory
│   ├── model/            DataSet, DataModel (with star-schema query)
│   ├── etl/              BronzeLayer, SilverLayer, GoldLayer
│   ├── reports/          Report, ExcelRenderer, HTMLRenderer
│   ├── dashboard/        Dashboard, DashboardServer, panels
│   ├── pipeline/         PipelineRunner (APScheduler + DB)
│   └── lineage/          LineageDiagram
├── web/
│   ├── api/              FastAPI app, routers, registry
│   ├── templates/        Jinja2 HTML templates
│   ├── demo_app.py       Built-in demo (medallion + in-memory fallback)
│   ├── run.py            Dev server entrypoint
│   └── requirements.txt  Web-only dependencies
├── examples/             Runnable demos (phase1–4)
├── tests/                163 tests across all phases
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

```
requests/
├── _template.py
├── 2024_06_open_orders_by_region.py
└── 2024_07_customer_churn_analysis.py
```

---

## License

MIT
