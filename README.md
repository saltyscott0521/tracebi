# TraceBi

[![CI](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml/badge.svg)](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://github.com/saltyscott0521/tracebi)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**The trust layer for AI-generated analytics** — a code-first BI framework
for Python where **every number has a receipt**.

Governance tooling assumes a human wrote the transformation and is still
around to ask. TraceBi assumes a machine wrote it and is gone — so from the
model boundary onward, every figure carries its resolved query, lineage, and
SHA-256 fingerprint, and `tracebi verify` re-checks the receipt on demand.
The mechanism is a three-phase workflow that takes data from messy to
reportable. The full identity, vocabulary, and refusals live in
**[MANIFESTO.md](MANIFESTO.md)**.

---

## How it works — the three-phase workflow

TraceBi splits the work of turning raw data into a report into three phases,
each a project-root folder with its own cadence. The phases are decoupled by
**freeze points**: a materialized artifact handed from one to the next, so the
slow analysis and the fast reporting never block each other.

```
①  TRANSFORM    transforms/          slow, runs rarely — unconstrained pandas
      read messy sources → parse, clean, key, dedupe → WRITE star-schema tables
                                                        │
                                       freeze ▼  data/warehouse.duckdb
②  MODEL        models/              the contract, changes deliberately
      a declarative DataModel (star schema) over the warehouse — grain, keys,
      measures, in a few dozen lines a reviewer reads without opening the pandas
                                                        │
                                       freeze ▼  the model (the semantic contract)
③  REPORT       reports/             fast, iterate constantly
      a ReportSpec (JSON) pointed at the model — KPI cards, charts, tables,
      every figure a live query. Re-renders in milliseconds; nothing re-runs ①.
```

**Phase 1 (TRANSFORM)** is ordinary, unconstrained pandas — pull the queries
you need, do the real analysis (window functions, prose parsing, cleaning),
then *sink* clean star-schema tables into a file-backed DuckDB warehouse. The
framework does not constrain how you clean; the contract is *what lands* — the
named tables at the end of the script.

**Phase 2 (MODEL)** is a thin declarative star schema over the warehouse. It
reads the sink; it never sees the transform.

**Phase 3 (REPORT)** is a JSON `ReportSpec` pointed at the model. Because the
model is materialized, the page re-renders in milliseconds with no pandas in the
loop — editing the report never re-runs the analysis. (A dashboard is a style
of report, not a different thing.)

| Phase | Folder | Artifact | Discovered by the server as |
|---|---|---|---|
| ① Transform | `transforms/` | pandas → DuckDB tables | — (run explicitly) |
| ② Model | `models/` | `DataModel` (a `model` variable) | a model on the Models page |
| ③ Report | `reports/` | `ReportSpec` JSON (or a template package / factory) | a report on the Reports page |

```bash
cd examples/portfolio_project   # the reference project ships in the repo
python run_workflow.py          # ① build the warehouse, ③ render the report once
python -m tracebi.web.run       # serve it: http://127.0.0.1:8000 → Reports → portfolio_dashboard
```

The reference implementation ships in the repo at `examples/portfolio_project/`
— a complete project with the exact shape `tracebi init` scaffolds:
`transforms/holdings_transform.py`, `models/portfolio_model.py`,
`reports/portfolio_dashboard.json`, driven by `run_workflow.py`. Full
walkthrough: **[WORKFLOW.md](WORKFLOW.md)**.

Everything below hangs off this spine: the framework gives you the connectors
and lineage-tracked `DataSet` for phase 1, the `DataModel` for phase 2, the
report engine for phase 3, and — **from the model boundary onward (phases 2 and
3)** — the trust machinery that makes a published figure re-provable.

---

## Why TraceBi?

| Trust capability | Dash / Streamlit | dbt | Qlik / Tableau | **TraceBi** |
|---|---|---|---|---|
| Semantic contract agents query (facts, dims, named measures) | ✗ | ✓ (Semantic Layer, cloud) | partial (governed models, not agent-first) | ✓ |
| Every query stamped: resolved query + lineage + result fingerprint | ✗ | ✗ | ✗ | ✓ |
| Report specs validated *before* execution | ✗ | ✗ (compiles SQL, no report layer) | ✗ | ✓ |
| Re-provable artifacts (`tracebi verify` re-runs the receipts) | ✗ | ✗ | ✗ | ✓ |
| Self-contained HTML artifact + lineage manifest | ✗ (live app, no artifact) | ✗ (docs site, not reports) | partial (exports, no lineage) | ✓ |
| Code-first Python framework underneath | ✓ | ✗ (SQL + YAML) | ✗ | ✓ |

---

## What's built

These are the framework's build milestones (a different axis from the three
workflow phases above — a "Phase" here is a development stage, not a folder):

- [x] **Phase 1** — Connectors (CSV, SQL, BigQuery, Snowflake, Memory, DuckDB) with push-down filter/columns, DataModel, DataSet with immutable lineage chain
- [x] **Phase 2** — Report engine (Excel + HTML renderers, lineage manifest per render)
- [x] **Phase 2.5** — Landing/Manipulation/Final layers (medallion-compatible), DuckDB-backed star-schema query on DataModel, LineageDiagram
- [x] **Phase 4** — Pipeline runner with APScheduler, DB persistence, cross-layer lineage
- [x] **Phase 5** — Web UI (FastAPI + React), folder-based auto-discovery, optional HTTP Basic / proxy-header auth with roles, `tracebi` CLI, docker-compose deployment
- [x] **Agent gateway** — the kernel over MCP (`tracebi mcp`): an agent queries the semantic model and authors validated report specs; every response is stamped with the resolved query, lineage, and a fingerprint of the full result
- [x] **Verify loop** — every render records input fingerprints in the manifest; `tracebi verify` (and the gateway's `verify_manifest` tool) re-runs the recorded queries and classifies each as reproduces / source drift / model changed / unexplained / unverifiable, then gives the receipt one verdict — a manifest where nothing could be checked is never reported as a pass. This operates on phase-2/3 queries against the model; it re-runs recorded queries and compares fingerprints — it does **not** read a phase-1 transform or assert a number is correct.

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
| Understand the three-phase workflow (transform → model → report) | [WORKFLOW.md](WORKFLOW.md) — the spine, with the reference implementation |
| Follow the full analyst flow start-to-finish | [docs/analyst-guide.md](docs/analyst-guide.md) — scaffold → transform → report → publish |
| Work in a notebook with rich previews | [docs/notebook-guide.md](docs/notebook-guide.md) + `examples/analyst_quickstart.py` |
| Write a one-off report or query | Copy `requests/_template.py` and run it with `tracebi run` |
| Define a reusable model for notebooks and scripts | `tracebi new-model "My Model"` → edit `models/<name>.py` → `from tracebi.model_registry import get_model` |
| Define a scheduled ETL pipeline | `tracebi new-pipeline "My ETL"` → edit `pipelines/<name>.py` → `from tracebi.pipeline_registry import get_runner` |
| Point the web app at my own data / restyle the UI | [docs/web-customization.md](docs/web-customization.md) — app modules, registry, theming, auth, deploy |
| Query facts/dimensions visually | Tag tables with `add_fact()` / `add_dimension()`, then open the **Explore** page |
| Understand data flow end-to-end | `examples/phase1_example.py` through `phase4_example.py` in order |
| Browse the API interactively | Start the server, then open `http://localhost:8000/docs` (Swagger UI) or `/redoc` |
| Add a chart or table to a report | [Build a report](#3-build-a-report) — `ChartSection`, `TableSection`, `TextSection` |
| Let an AI agent query models and author reports | `pip install 'tracebi[mcp]'`, then register `tracebi mcp` with your agent — see [Agent gateway](#agent-gateway-mcp) |
| Re-prove a rendered report's numbers | `tracebi verify output/report.manifest.json` — re-runs every recorded query and classifies drift |
| Point an agent at the rules of the road | [AGENTS.md](AGENTS.md) — the agent knowledge base; SOPs in [docs/agents/](docs/agents) |

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

That install builds from the repo tree, where the React bundle
(`tracebi/web/ui/dist`) is gitignored — so it carries the library and the API but
**no web UI**. `tracebi serve` will start and `/` will tell you so. For the
browser interface, clone and build it (see [Web UI](#web-ui)), or install a
wheel built by `.github/workflows/release.yml`, which runs the UI build first.

Pick the pieces you need (extras work the same with either install style):

```bash
pip install -e "."                    # core only (pandas)
pip install -e ".[reports]"           # Excel + HTML renderers
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

The stack is three services, one per deployment plane:

| Service | Plane | Does |
|---|---|---|
| `db` | state | Postgres. Medallion tables **and** pipeline run history, surviving restarts. |
| `seed` | execution | Runs the pipeline once, then exits. The only service that writes. |
| `app` | serving | FastAPI + React on `:8000`. Reads. |

Because `TRACEBI_DEMO_DB_URL` points at Postgres, importing the app module in
`app` *defines* layers without executing any — starting a web process does no
batch work. Re-run the pipeline without restarting the API:

```bash
docker compose run --rm seed
```

Postgres is published on `:5432`, so the execution plane can equally be driven
from the host by cron, CI, or `tracebi run-pipeline`. That is the shape a real
deployment takes, and it is why the compose file is worth reading even if you
deploy elsewhere. See NOTES.md, "Deployment planes".

Optional environment overrides (set in a `.env` beside `docker-compose.yml`):

| Variable | Purpose |
|---|---|
| `TRACEBI_APP` | Python module to import on startup (default `tracebi.web.demo_app`) |
| `TRACEBI_DEMO_DB_URL` | Any SQLAlchemy URL. Set → definitions only, no execution at import. Unset → ephemeral SQLite that seeds itself. |
| `POSTGRES_PASSWORD` | Local compose Postgres password (default `tracebi`) |
| `POSTGRES_PORT` | Host port for the compose Postgres (default `5432`). Set it if you already run Postgres locally: `POSTGRES_PORT=55432 docker compose up`. |
| `TRACEBI_MODELS_DIR` | Folder scanned for model definitions (default `models`) |
| `TRACEBI_PIPELINES_DIR` | Folder scanned for pipeline definitions (default `pipelines`) |
| `TRACEBI_REPORTS_DIR` | Folder scanned for named report factories (default `reports`) |
| `TRACEBI_REQUESTS_DIR` | Folder scanned for ad-hoc request scripts (default `requests`) |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | Turn on HTTP Basic auth |
| `TRACEBI_AUTH_PROXY_HEADER` | Trust an upstream identity header (Authelia / oauth2-proxy / Cloudflare Access) |
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
tracebi init my_project                              # scaffold models/ pipelines/ reports/ requests/
tracebi new-request "Open orders by region"          # → requests/open_orders_by_region.py
tracebi new-request "Customer churn" --notebook      # → requests/customer_churn.ipynb
tracebi list-requests
tracebi run open_orders_by_region                    # works for .py and .ipynb
tracebi dev open_orders_by_region                    # live preview: re-runs + reloads on save
tracebi validate                                     # load every model; check dimension keys are unique
tracebi serve                                        # browse the project at http://127.0.0.1:8000
tracebi new-model "Sales Model"                      # → models/sales_model.py
tracebi list-models
tracebi new-pipeline "Sales ETL"                     # → pipelines/sales_etl.py
tracebi list-pipelines
tracebi run-pipeline sales_etl                       # run every layer, upstream first
tracebi run-pipeline sales_etl --status              # last run per layer, executes nothing
tracebi context [--model NAME]                       # framework vocabulary as JSON (for agents and tooling)
tracebi spec schema                                  # JSON Schema for a report spec
tracebi spec validate report.json                    # check a spec without executing it
tracebi spec render report.json                      # build a spec and render HTML + manifest
tracebi new-report "Portfolio Book"                  # → reports/portfolio_book/ (template package scaffold)
tracebi report build portfolio_dashboard             # render a report (spec or package) → self-contained HTML + manifest
tracebi report preview portfolio_dashboard           # build and open it in a browser
tracebi mcp                                          # agent gateway over MCP (stdio)
tracebi verify output/report.manifest.json           # re-run recorded queries; classify drift
tracebi verify --file output/report.html             # offline: does the shipped file's data still match its manifest?
```

`run-pipeline` executes layers without a web server, which is what lets the
batch work run somewhere other than the API process — a cron entry, a
Kubernetes CronJob, an Airflow task, a CI job. It exits non-zero if any layer
fails, so whatever invoked it can act on that. TraceBi does not need to own
the schedule.

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
    .deduplicate(subset="order_id")
    .dropna(subset="region")
    .assign(margin=lambda df: df["revenue"] - df["cost"])
    .sort("margin", ascending=False)
)

orders.print_lineage()
# Step 1: [LOAD]         Loaded 'orders' from connector 'sales_db'
# Step 2: [FILTER]       Shipped orders only  (250 → 198 rows)
# Step 3: [DEDUPLICATE]  Removed 3 duplicate rows by ['order_id']
# Step 4: [DROPNA]       Dropped 2 rows with nulls in ['region']
# Step 5: [ASSIGN]       Assigned columns: margin
# Step 6: [SORT]         Sorted by margin (desc)
```

Cleaning verbs (`dropna`, `fillna`, `deduplicate`, `cast`, `limit`) record
structured lineage — row counts, fill counts, type maps — automatically.
`.transform(lambda df: ...)` remains the escape hatch for anything else.
Run `ds.help()` for the full cheat sheet.

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

### 6. Lineage diagrams

```python
from tracebi.lineage.diagram import LineageDiagram

diag = LineageDiagram(ds_gold)   # or LineageDiagram(report)
diag.show()                       # matplotlib / Jupyter inline
diag.to_html("lineage.html")      # standalone HTML with embedded SVG
print(diag.to_mermaid())          # paste into GitHub markdown
```

---

## Agent gateway (MCP)

An AI agent should work against your **semantic contract**, not your
warehouse. `tracebi mcp` serves the kernel over the
[Model Context Protocol](https://modelcontextprotocol.io): the agent reads
the vocabulary with `get_context` (models, facts, dimensions, named
measures, report sections — nothing outside it will validate), queries with
`query_model`, and authors reports as specs it can check *before* executing
with `validate_report_spec`.

Every query response is **stamped** — the resolved query, the full lineage
chain, and a SHA-256 fingerprint of the complete result travel with the
rows. Rows are a capped preview; the fingerprint always covers the full
result, so any number the agent quotes is verifiable afterwards by
re-running the recorded query and comparing hashes. `render_report_spec`
produces the governed HTML artifact plus its lineage manifest, and refuses
a spec that fails validation. `verify_manifest` closes the loop: it re-runs
every query recorded in a manifest and classifies the outcome (reproduces,
source drift, model changed, unexplained), so an agent can check its own
receipt before a human sees the number.

The full playbook — the two planes, the L0–L3 assurance ladder, all eight
tools, and the canonical discover → explore → author → validate → render → verify → cite
loop — is in [AGENTS.md](AGENTS.md).

```bash
pip install 'tracebi[mcp]'

# Local agent (e.g. Claude Code), from your project directory:
claude mcp add tracebi -- tracebi mcp

# Remote agent: the HTTP transport requires a token —
# every client must send "Authorization: Bearer $TRACEBI_MCP_TOKEN".
export TRACEBI_MCP_TOKEN=$(openssl rand -hex 32)
tracebi mcp --transport http --port 8765

# Without a token the server refuses to start; serving an
# unauthenticated gateway is an explicit opt-out:
tracebi mcp --transport http --port 8765 --insecure
```

The HTTP transport binds `127.0.0.1` and enables DNS-rebinding protection,
so a genuinely remote agent should reach it through a reverse proxy (TLS
termination there; the bearer token still applies end to end).

Read-and-compute only: queries, validation, rendering, and verification.
Pipeline execution (which writes to the warehouse) is deliberately not exposed.
Attribution is recorded as `mcp:<TRACEBI_MCP_ACTOR>` (default `mcp:agent`)
in the same audit trail as web and CLI actors.

### Retaining receipts

Every render writes a `<output>.manifest.json` next to the artifact —
`render_report_spec` lands both in `output/` by default. The
manifest is the audit trail: the recorded queries, lineage, input
fingerprints, and git SHA that let a reviewer check a number months later.
`tracebi verify <manifest>` is that check — it re-runs every recorded query
and reports whether each still reproduces, whether the inputs drifted, or
whether the model itself changed. It exits 0 only when something was
actually checked and nothing failed: 2 for diagnosed source drift, 1 for an
undiagnosed mismatch *or* for a manifest with no data-bearing section, which
verifies nothing and so cannot pass. A receipt whose every section is
hand-transformed still exits 0, but says `NOTHING VERIFIED` rather than
`REPRODUCES`.

`tracebi verify <manifest>` re-proves the numbers against the model; it does
not read the file you actually shipped. `tracebi verify --file <report.html>`
is the offline complement: it re-hashes the data blocks embedded in a
self-contained report and checks each against the manifest, so an edited total
in a file mailed around a company is caught (`FILE ALTERED`) even with no
database in reach. One asks *do these numbers still reproduce*; the other asks
*is this the file we rendered*.

Rendered HTML is disposable; manifests are not. Retain them — commit them, or
archive whatever lands in `output/` — because a receipt you discarded proves
nothing.

---

## Web UI

A browser interface over your TraceBi registry — connectors, models, reports, and pipelines all in one place. Highlights:

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

# Build the React UI — tracebi/web/ui/dist is gitignored, so a fresh clone has none,
# and neither does a `pip install ... @ git+https://...`. Without it the API
# still runs; / serves a page saying so. This step needs a clone.
cd web/ui && npm ci && npm run build && cd ../..

# Start the server (hot-reload on by default)
python -m tracebi.web.run
# Open http://localhost:8000
```

The API is self-documenting: once the server is running, open
[`http://localhost:8000/docs`](http://localhost:8000/docs) for the Swagger UI
or [`http://localhost:8000/redoc`](http://localhost:8000/redoc) for ReDoc —
every endpoint, parameter, and response schema is listed there.

`tracebi/web/demo_app/` is the default app module package. The DataModels themselves live at the project root in `models/` (`sales_model.py`, `wealth_model.py`) and are shared with notebooks and scripts via `get_model(...)`; the demo app pulls them in and stands up a self-contained SQLite medallion pipeline (Landing → Manipulation → Final) at startup so the Pipelines page has live run history. Reports read from those resources.

The second model — `WealthModel` (`models/wealth_model.py`) — is a wealth-management star schema with four dimensions (clients, branches, products, accounts) and two facts (holdings, activities), showing that a TraceBi app can serve multiple data models side by side. The `aum_by_branch` and `client_activity` reports are built on it, and it's fully queryable from the Explore page (e.g. AUM by region × asset class, or net flows by client segment).

To point the UI at your own data module instead of the built-in demo:

```bash
TRACEBI_APP=mypackage.tracebi_config python -m tracebi.web.run
```

Your module just needs to import `registry` and call `registry.add_connector()`, `registry.add_model()`, `@registry.report(...)`, and optionally `registry.add_pipeline()`.

**Project-root directories are auto-discovered** — you don't have to put everything in the app module. The server scans these folders at startup and registers whatever it finds:

| Directory | Convention | Env var override |
|---|---|---|
| `models/` | each `.py` exposes a `model` variable (a `DataModel`) | `TRACEBI_MODELS_DIR` |
| `pipelines/` | each `.py` exposes a `runner` variable (a `PipelineRunner`) | `TRACEBI_PIPELINES_DIR` |
| `reports/` | a `.py` factory (`@register.report(...)`), a `.json` `ReportSpec` (workflow phase ③), or a `<name>/` template package — all served as reports | `TRACEBI_REPORTS_DIR` |
| `requests/` | ad-hoc scripts with `request_params()` and `run()` | `TRACEBI_REQUESTS_DIR` |

Use `tracebi new-model` / `tracebi new-pipeline` to scaffold the files. See [docs/web-customization.md](docs/web-customization.md) for the full wiring guide.

### Shared models and pipelines (no web server required)

Define a model once in `models/` and import it anywhere — notebooks, scripts, or the web server:

```bash
tracebi new-model "Sales Model"          # scaffold models/sales_model.py
# edit models/sales_model.py — wire connectors, tables, relationships
```

```python
from tracebi.model_registry import get_model, list_models

print(list_models())                     # ["sales_model"]
model = get_model("sales_model")
ds = model.load("orders")
```

Same pattern for pipelines:

```bash
tracebi new-pipeline "Sales ETL"         # scaffold pipelines/sales_etl.py
```

```python
from tracebi.pipeline_registry import get_runner

runner = get_runner("sales_etl")
runner.run("orders_silver")
runner.status()
```

The web server auto-discovers both directories at startup and registers them into the registry automatically.

### Adding reports to the web UI

Drop a file in `reports/` and decorate a factory function — the server picks it up on startup with no extra wiring:

```python
# reports/weekly_summary.py
from tracebi.model_registry import get_model
from tracebi.reports import Report, TableSection

try:
    from tracebi.web import register

    @register.report("weekly_summary", description="Weekly order summary")
    def _factory():
        model = get_model("sales_model")
        ds = model.load("orders")
        return Report("Weekly Summary").add(TableSection(title="Orders", dataset=ds))
except ImportError:
    pass
```

---

## Local database setup (example)

```bash
# Create data/tracebi.db, seed source tables, run initial Bronze load
python examples/seeds/seed_db.py

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
python examples/phase4_example.py      # full pipeline (run examples/seeds/seed_db.py first)
```

## Running tests

```bash
pytest tests/
# 777 passed
```

---

## Project structure

The repo root is the framework; the working project lives in `examples/`.
Your own project (from `tracebi init`) has the same shape as
`examples/portfolio_project/`.

```
tracebi/                        ← the framework repo
├── tracebi/                    The Python package — everything the wheel ships
│   ├── connectors/             CSV, SQL, BigQuery, Snowflake, Memory, DuckDB
│   ├── model/                  DataSet, DataModel (with star-schema query)
│   ├── etl/                    LandingLayer, ManipulationLayer, FinalLayer (Bronze/Silver/Gold aliases)
│   ├── reports/                Report, ExcelRenderer, HTMLRenderer (+ render_pdf via weasyprint)
│   ├── pipeline/               PipelineRunner (APScheduler + DB)
│   ├── lineage/                LineageDiagram
│   ├── mcp_server.py           Agent gateway — 8 MCP tools over the kernel
│   └── web/
│       ├── api/                FastAPI app, routers, registry
│       ├── demo_app/           Bundled demo app — self-contained (its own models/ + reports/)
│       ├── run.py              Dev server — python -m tracebi.web.run
│       └── ui/dist/            Built React bundle (gitignored; npm run build writes here)
├── web/ui/                     React UI source (Vite) — a Node workspace, not a Python
│                               package; `npm run build` writes into tracebi/web/ui/dist
├── tests/                      843 tests across all phases
├── examples/
│   ├── portfolio_project/      THE reference project — the three-phase workflow
│   │   ├── inputs/             ⓪ raw pulls (holdings.csv + its generator)
│   │   ├── transforms/         ① pandas → sink star tables to DuckDB
│   │   ├── models/             ② the star-schema contract (portfolio_model.py)
│   │   ├── reports/            ③ spec + template packages + escape hatch
│   │   ├── requests/           the human scratchpad (unverified lane)
│   │   └── run_workflow.py     drives ①→③ (see WORKFLOW.md)
│   ├── seeds/                  Medallion demo DB seeding + Supabase companions
│   └── phase*.py               Small runnable feature demos
├── docs/                       Guides, ROADMAP, report-generator architecture
├── MANIFESTO.md                What TraceBi is, and what it refuses to build
└── NOTES.md                    Design decisions and architecture reference
```

---

## Ad hoc reports

Copy `requests/sample_report.py` (scaffolded by `tracebi init`; the fuller
`_template.py` ships in the reference project), rename it, fill in the numbered sections
(parameters → model → datasets → report → render), and commit it to git.
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
