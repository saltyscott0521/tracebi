# TraceBi — CLAUDE.md

Codebase guide for AI assistants. Read this before touching any code.

---

## What This Project Is

**TraceBi** is a code-first, traceable BI and analytics framework for Python. It combines relational data modeling (Qlik-style associations), full data lineage tracking, multiple report output formats (Excel, HTML, PDF), live Dash dashboards, medallion-architecture ETL, and scheduled pipeline orchestration — all in a single pip-installable package.

There is also a **FastAPI web layer** (`web/`) that exposes the framework via a REST API with Jinja2-templated UI.

All four development phases are complete:
- Phase 1: Connectors, DataModel, DataSet with lineage
- Phase 2: Report engine (Excel + HTML renderers, lineage manifest)
- Phase 2.5: Medallion architecture, StarSchema, LineageDiagram
- Phase 3: Live Dash dashboard with associative filters
- Phase 4: Pipeline runner with SQLite persistence and cross-layer lineage

---

## Repository Layout

```
tracebi/               # Core Python package (~5200 LOC)
  connectors/          # Data source adapters (CSV, SQL, BigQuery, Snowflake, Memory)
  model/               # DataSet, DataModel, StarSchema abstractions
  etl/                 # BronzeLayer, SilverLayer, GoldLayer
  reports/             # Report engine + renderers (Excel, HTML, PDF)
  dashboard/           # Dash-based live dashboard components
  pipeline/            # PipelineRunner (scheduling + DB persistence)
  lineage/             # LineageDiagram (matplotlib / mermaid / HTML)
  __init__.py          # Public API re-exports
web/                   # FastAPI web application
  api/
    main.py            # FastAPI app, CORS, router mounts, WSGI middleware
    registry.py        # Singleton resource registry
    routers/           # Route handlers per domain
  templates/           # Jinja2 HTML templates
  run.py               # Dev server entry point (uvicorn wrapper)
  demo_app.py          # Sample registry setup used by default
examples/              # Phase 1–4 runnable demos
tests/                 # pytest suite (163 tests across 5 files)
seeds/                 # DB initialization + Bronze seeding
requests/              # Ad hoc report scripts; _template.py is the scaffold
data/                  # SQLite DB lives here (gitignored)
docs/                  # Static HTML docs
pyproject.toml         # Project metadata, dependencies, pytest config
README.md              # Full user-facing docs
NOTES.md               # Architecture decisions and open questions
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Build / packaging | Hatchling (`pyproject.toml`) |
| Core dependency | pandas ≥ 1.5 |
| Web API | FastAPI + uvicorn |
| Templates | Jinja2 |
| Dashboard | Dash + Plotly |
| Database | SQLite (via SQLAlchemy); BigQuery and Snowflake connectors also available |
| Scheduling | APScheduler |
| Reports | openpyxl (Excel), WeasyPrint (PDF), matplotlib (charts) |
| Lineage graphs | networkx + matplotlib |
| Tests | pytest + pytest-cov |

---

## Development Setup

```bash
# Install with all optional features
pip install -e ".[reports,dashboard,pipeline,lineage,sql]"

# For development (includes all extras + pytest)
pip install -e ".[dev]"
```

---

## Running the Project

### Web API (development server)
```bash
python web/run.py                          # http://127.0.0.1:8000
python web/run.py --port 9000 --host 0.0.0.0
```

### Web API (production)
```bash
uvicorn web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Custom app module
```bash
TRACEBI_APP=mymodule.config uvicorn web.api.main:app
```
`TRACEBI_APP` (default: `web.demo_app`) controls which module registers resources with the registry at startup.

### Database setup
```bash
python seeds/seed_db.py          # Creates data/tracebi.db, seeds raw tables, runs Bronze
```

### Phase examples
```bash
python examples/phase1_example.py   # Connectors + DataModel
python examples/phase2_example.py   # Reports (opens browser)
python examples/phase25_example.py  # Medallion + StarSchema
python examples/phase3_example.py   # Live Dash dashboard
python examples/phase4_example.py   # Full pipeline + scheduling
```

---

## Running Tests

```bash
pytest tests/               # All 163 tests
pytest tests/test_phase1.py # Single phase
pytest -v                   # Verbose output
pytest --cov                # With coverage
```

Test files map directly to phases:

| File | Coverage |
|---|---|
| `test_phase1.py` | Connectors, DataSet, DataModel, lineage |
| `test_phase2.py` | Report engine, renderers, manifest |
| `test_phase25.py` | Medallion layers, StarSchema, LineageDiagram |
| `test_phase3.py` | Dashboard, panels, callbacks, filters |
| `test_phase4.py` | PipelineRunner, scheduling, DB persistence |

---

## Core Design Patterns

### 1. Immutable DataSet + lineage chain

`DataSet` wraps a pandas DataFrame and a list of `LineageNode` objects. Every transformation returns a **new** `DataSet`; nothing is mutated in place. The lineage chain accumulates automatically.

```python
ds = connector.load("orders")          # LineageNode: source
ds2 = ds.filter(lambda df: df[df.status == "paid"])  # + filter node
ds3 = ds2.rename({"amt": "amount"})    # + rename node
```

This is the **central invariant** of the codebase. Never mutate a DataSet's underlying DataFrame or lineage list directly.

### 2. Registry pattern (web layer)

`web/api/registry.py` holds a module-level singleton that stores all connectors, models, report factories, and dashboards. Routers never import app-specific objects directly — they ask the registry. Custom app modules call `registry.add_connector()`, `@registry.report()`, etc. during import.

### 3. Medallion architecture

ETL follows Bronze → Silver → Gold:
- **Bronze**: raw ingest with timestamps, zero transforms
- **Silver**: declarative cleaning (cast types, deduplicate, drop nulls) via `SilverLayer`
- **Gold**: aggregated via `StarSchema` (fact + dimension tables)

Each layer is independent and can be run or re-run individually.

### 4. PipelineRunner system tables

`PipelineRunner` auto-creates SQLite tables on first use:
- `tracebi_layers` — registered layer definitions and cron schedules
- `tracebi_runs` — run history (status, row counts, upstream_run_id)
- `tracebi_schemas`, `tracebi_dimensions`, `tracebi_facts` — StarSchema metadata

Never modify these tables manually; use PipelineRunner API.

### 5. Ad hoc reports scaffold

Reports in `requests/` follow a strict 4-section pattern from `_template.py`:
1. Connectors
2. Transforms
3. Report assembly
4. Render + save

When adding a new report script, copy `_template.py` and fill in each section.

---

## API Routes

All API routes are mounted under `/api/`.

```
GET  /api/health
GET  /api/connectors
GET  /api/models
GET  /api/reports
POST /api/reports/{name}/run        # Returns HTML + lineage manifest JSON
GET  /api/pipelines
POST /api/pipelines/{name}/run
GET  /api/pipelines/{name}/lineage
GET  /                              # Index page
GET  /dashboards/{name}/            # Dash app mounted via WSGIMiddleware
```

Dash dashboards are mounted as WSGI sub-applications; routes under `/dashboards/` are handled entirely by Dash, not FastAPI.

---

## Adding New Features

### New connector
1. Subclass `tracebi.connectors.BaseConnector`
2. Implement `load(name) -> DataSet` (must produce a lineage node)
3. Register via `registry.add_connector(instance)` in your app module

### New report
1. Build a `Report` object with `TextSection`, `TableSection`, `ChartSection`
2. Render with `ExcelRenderer`, `HTMLRenderer`, or both
3. For web exposure: decorate a factory function with `@registry.report("name")`

### New medallion layer
1. Instantiate `BronzeLayer`, `SilverLayer`, or `GoldLayer` with source connector + transform config
2. Register with `runner.register(layer)`
3. Set a cron schedule if recurring: `runner.schedule(layer_name, "0 * * * *")`

### New dashboard panel
Subclass one of: `FilterPanel`, `MetricPanel`, `ChartPanel`, `TablePanel`. Pass instances to `Dashboard`.

---

## Key Conventions

- **No in-place DataFrame mutations.** Always return a new DataSet.
- **Lineage is non-optional.** Every data operation must produce a LineageNode. If you add a new transform method to DataSet, add the corresponding node.
- **Optional dependencies.** Each feature group (reports, dashboard, pipeline, etc.) has optional deps. Guard imports with try/except ImportError and raise a clear message pointing to the relevant extras key.
- **No environment-specific config files.** Connector URLs and app configuration live in Python code, not `.env` files. The only env var the framework reads is `TRACEBI_APP`.
- **Registry is read-only at request time.** Register all resources during app module import (startup). Never add to or remove from the registry inside a request handler.
- **Tests are phase-scoped.** Keep new tests in the file that matches the phase/module being tested. Do not add cross-phase test dependencies.
- **pyproject.toml is the single source of truth** for dependencies, test config, and build metadata. Do not add `setup.py`, `requirements.txt`, or `tox.ini`.

---

## What Does Not Exist Yet

- No CI/CD (no GitHub Actions, Dockerfile, or Makefile)
- No `.env` file support
- No database migrations (layers are idempotent and self-creating)
- No authentication on the web API
- No pre-commit hooks

---

## Useful Entry Points for Orientation

| Goal | File |
|---|---|
| Understand the whole framework | `README.md` |
| Understand architecture decisions | `NOTES.md` |
| See how everything wires together | `web/demo_app.py` |
| Add a resource to the web API | `web/api/registry.py` |
| Understand how data flows | `examples/phase4_example.py` |
| Write a new ad hoc report | `requests/_template.py` |
| Understand lineage chain | `tracebi/model/dataset.py` |
