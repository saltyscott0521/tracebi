# TraceBi — CLAUDE.md

Behavioral guidelines and codebase reference for AI assistants. Read before touching any code.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial one-liners, use judgment.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing anything:
- State your assumptions explicitly. If uncertain, ask.
- If a request is ambiguous, present the interpretations — don't pick one silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something about the codebase is unclear, stop and name what's confusing.

TraceBi-specific traps to surface first:
- "Add a transform" — does it belong in `DataSet`, a `SilverLayer` config, or a `GoldLayer`? These are different things with different lineage implications.
- "Add a connector" — is it a core connector (goes in `tracebi/connectors/`) or app-specific (stays in the app module, registered at startup)?
- "Update the report" — does the caller want the HTML renderer, the Excel renderer, the PDF renderer, or all three?

---

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

TraceBi-specific: the framework already provides DataSet chaining, lineage tracking, and layer composition. Don't re-implement plumbing that already exists. Check `tracebi/__init__.py` for what's already exported before writing anything new.

---

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

TraceBi-specific: the five test files are phase-scoped (`test_phase1.py` through `test_phase4.py`). Don't reorganize tests across files. Don't add shared fixtures that create cross-phase dependencies.

---

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add a transform" → "write a test that uses it, then make it pass"
- "Fix the lineage bug" → "write a test that reproduces it, then make it pass"
- "Add a new API route" → "hit the endpoint and verify the response shape"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Run `pytest tests/` before and after any change. A passing suite is the minimum bar.

---

## Project Overview

**TraceBi** is a code-first, traceable BI framework for Python. Core ideas:

- **DataSet**: immutable wrapper around a pandas DataFrame + lineage chain. Every operation returns a new DataSet; nothing mutates in place.
- **DataModel**: Qlik-style associative model linking multiple DataSets by key, with an analytic star-schema query surface (facts, dimensions, measures) on the same class.
- **Medallion ETL**: Landing (raw ingest) → Manipulation (declarative cleaning) → Final (DataModel star-schema aggregation). `BronzeLayer` / `SilverLayer` / `GoldLayer` remain as aliases.
- **PipelineRunner**: registers layers, schedules with APScheduler, persists run history to SQLite.
- **Report engine**: builds structured reports (text, tables, charts) and renders to Excel, HTML, or PDF.
- **Dashboard**: live Dash app with associative filter panels.
- **Web layer** (`web/`): FastAPI REST API + React UI exposing all of the above via a singleton registry.

All six development phases are complete and tested.

---

## Repository Layout

```
tracebi/               # Core Python package (~5200 LOC)
  connectors/          # BaseConnector + CSV, SQL, BigQuery, Snowflake, Memory, DuckDB
  model/               # DataSet, DataModel (with star-schema query)
  etl/                 # LandingLayer / BronzeLayer, ManipulationLayer / SilverLayer, FinalLayer / GoldLayer
  reports/             # Report, Section types, ExcelRenderer, HTMLRenderer
  dashboard/           # Dashboard, FilterPanel, MetricPanel, ChartPanel, TablePanel
  pipeline/            # PipelineRunner + APScheduler integration
  lineage/             # LineageDiagram (matplotlib / mermaid / HTML export)
  web/                 # register facade + auto-discovery for request scripts (.py and .ipynb)
  cli.py               # tracebi init / new-request / list-requests / run / dev / validate
  _notebook.py         # notebook_to_source() — concatenates code cells for exec
  __init__.py          # Public API re-exports — check here before writing new code
web/
  api/
    main.py            # FastAPI app entry point — CORS, routers, WSGI mounts, auth
    auth.py            # Optional HTTP Basic / proxy-header middleware
    registry.py        # Singleton resource store — the seam between framework and app
    errors.py          # Structured error payload (message + traceback) for routers
    lineage_graph.py   # LineageNode list → React Flow graph (shared by routers)
    routers/           # One file per domain (connectors, models, reports, pipelines, dashboards, dev)
  ui/                  # React UI (built into web/ui/dist/ at Docker build time)
  run.py               # Dev server (uvicorn wrapper)
  demo_app/            # Default app module package — shows how to wire everything together
examples/              # Phase 1–4 + 2.5 runnable demos — read these to understand data flow
tests/                 # 243 pytest tests, one file per phase
seeds/                 # DB init + Bronze seeding
requests/              # Ad hoc report scripts (.py or .ipynb); _template.py is the scaffold
data/                  # SQLite DB (gitignored)
.env.example           # Documented env vars (auth, connector URLs, dev mode)
.github/workflows/     # CI — pytest matrix + ruff lint
Dockerfile             # Multi-stage build (React UI + Python app)
docker-compose.yml     # Single-container getting-started story
pyproject.toml         # Single source of truth for deps, build, and pytest config
CHANGELOG.md           # Keep-a-changelog format
LICENSE                # MIT
README.md              # Full user-facing docs
NOTES.md               # Architecture decisions and open questions
```

---

## Commands

```bash
# Install
pip install -e ".[dev]"                        # Everything the test suite needs (incl. web)

# Run (dev)
python web/run.py                              # http://127.0.0.1:8000
TRACEBI_APP=mymodule.config python web/run.py  # Custom app module
TRACEBI_DEV_MODE=1 python web/run.py           # Enables POST /api/_dev/reload

# Run (prod)
uvicorn web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
docker compose up --build                      # Or the docker-compose path

# Database
python seeds/seed_db.py                        # Create + seed data/tracebi.db

# Tests
pytest tests/                                  # Full suite (243 tests)
pytest tests/test_phase1.py                    # Single phase
pytest --cov                                   # With coverage
```

---

## Core Invariants — Never Violate These

**1. DataSet is immutable.**
Every transform method must return a new `DataSet`. Never mutate `.df` or `.lineage` in place. If you add a new method to `DataSet`, it returns a new instance with the new `LineageNode` appended.

**2. Every data operation produces a LineageNode.**
Lineage is non-optional. If your new transform skips the lineage step, the audit chain breaks silently. Look at existing methods in `tracebi/model/dataset.py` for the pattern.

**3. Registry is populated at startup, read at request time.**
`web/api/registry.py` is a singleton. Register all connectors, models, reports, and dashboards in your app module (e.g. `web/demo_app/`) during import. Never mutate the registry inside a FastAPI route handler.

**4. Optional dependencies must fail loudly.**
Each feature group (reports, dashboard, pipeline, lineage, sql) has optional deps. Wrap their imports in `try/except ImportError` and raise a clear `ImportError` telling the user which extras key to install. Don't let a missing dep produce a confusing `AttributeError` later.

**5. pyproject.toml is the only place for deps and config.**
Do not add `setup.py`, `requirements.txt`, `tox.ini`, or `setup.cfg`. The framework does not auto-load `.env` — `python-dotenv` is shipped via the `analyst`/`all` extras, but request scripts must call `load_dotenv()` themselves. Framework-read env vars: `TRACEBI_APP`, `TRACEBI_REQUESTS_DIR`, `TRACEBI_DEV_MODE`, `TRACEBI_EMBED_DASHBOARDS`, `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` / `TRACEBI_AUTH_PROXY_HEADER` / `TRACEBI_AUTH_PROXY_TRUSTED_IPS` / `TRACEBI_AUTH_REALM`.

---

## Anti-Patterns

| Don't | Do instead |
|---|---|
| Mutate `dataset.df` directly | Return `DataSet(new_df, dataset.lineage + [new_node])` |
| Import from `web/demo_app/` in tests | Use `MemoryConnector` or fixture data |
| Add cross-phase imports in test files | Keep tests isolated to their phase module |
| Make the framework read connector URLs from env vars implicitly | Construct connectors in app module code; pass credential-bearing URLs via `os.environ[...]` explicitly (see `.env.example`) |
| Add a new route without touching the registry | Wire it through `registry.py` so it's discoverable |
| Reach into `_private` attrs of framework objects from routers | Use the public surfaces: `runner.layers()`/`run_history()`, `model.info()`, `connector.describe()`, `registry.dashboards()` |
| Modify `tracebi_*` SQLite tables manually | Use `PipelineRunner` API |
| Add a new medallion layer without registering it | Call `runner.register(layer)` |

---

## How to Add Things

### New connector
1. Subclass `tracebi.connectors.BaseConnector`
2. Implement `load(name) -> DataSet` — must append a `LineageNode`
3. Register: `registry.add_connector(instance)` in your app module

### New report (ad hoc)
Copy `requests/_template.py`. Fill in the four sections: connectors → transforms → report assembly → render + save.

### New report (web-exposed)
Decorate a factory function with `@registry.report("name")`. The function receives no args and returns a rendered `Report`.

### New medallion layer
```python
# ManipulationLayer is the canonical name; SilverLayer remains as an alias.
layer = ManipulationLayer(source=bronze_connector, source_table="orders_bronze",
                          sink=db, sink_table="orders_silver").deduplicate(subset=["order_id"])
runner.register(layer, name="orders_silver", schedule="0 * * * *",
                depends_on="orders_bronze")
```

### New dashboard panel
Subclass `FilterPanel`, `MetricPanel`, `ChartPanel`, or `TablePanel`. Pass to `Dashboard(panels=[...])`.

### New FastAPI route
Add a file under `web/api/routers/`, include it in `web/api/main.py`, and read resources only from the registry — never import app-specific objects directly.

---

## API Routes

```
GET  /api/health
GET  /api/connectors
GET  /api/connectors/{name}
GET  /api/models
GET  /api/models/{name}                              → tables, relationships, facts, dimensions
GET  /api/models/{name}/tables/{t}/preview           → first N rows + dtypes + total_rows
GET  /api/models/{name}/tables/{t}/export.csv        → full table as CSV attachment
POST /api/models/{name}/query                        → star-schema query + lineage graph
GET  /api/reports
POST /api/reports/{name}/run                         → HTML + lineage manifest JSON
GET  /api/reports/{name}/download?format=xlsx|html   → rendered file attachment
GET  /api/reports/{name}/lineage                     → React Flow graph per section
GET  /api/reports/{name}/mermaid
GET  /api/requests                                   → scripts in requests/ (name, type, modified)
POST /api/requests/{name}/run                        → execute script fresh; HTML + manifest
GET  /api/requests/{name}/lineage                    → React Flow graph per section
GET  /api/pipelines
POST /api/pipelines/{name}/run
POST /api/pipelines/{name}/layers/{layer}/run
GET  /api/pipelines/{name}/layers/{layer}/history
GET  /api/dashboards
GET  /api/dashboards/{name}/lineage
GET  /dashboards/{name}/                             → Dash WSGI sub-app (not FastAPI)
GET  /                                               → React SPA (web/ui/dist, when built)
```

Failed report/query runs return a structured ``detail``:
``{message, exception_type, traceback}`` — keep that shape; the UI renders it.

---

## What Doesn't Exist Yet

- No Makefile (commands documented in README + this file)
- No database migrations (layers are idempotent)
- No pre-commit hooks
- No PyPI release (install is `pip install -e .` or from git)
- No PDF renderer implementation (the `[pdf]` extras key exists but `PDFRenderer` does not)

Don't add these unless asked.

---

## Orientation Map

| Goal | Start here |
|---|---|
| Understand the whole framework | `README.md` |
| Understand architecture decisions | `NOTES.md` |
| See a complete working wiring | `web/demo_app/` |
| Understand data flow end-to-end | `examples/phase4_example.py` |
| Add something to the web API | `web/api/registry.py` |
| Write an ad hoc report | `requests/_template.py` |
| Understand the lineage chain | `tracebi/model/dataset.py` |
| Add a new connector | `tracebi/connectors/` (pick any existing one as a model) |

---

**These guidelines are working if:** diffs are minimal and focused, tests pass before and after, and questions surface before implementation rather than after mistakes.
