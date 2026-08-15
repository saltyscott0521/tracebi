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

TraceBi-specific: the test files are phase-scoped (`test_phase1.py`, `test_phase2.py`, `test_phase25.py`, `test_phase4.py`, `test_phase5.py`). Don't reorganize tests across files. Don't add shared fixtures that create cross-phase dependencies.

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
- **Web layer** (`web/`): FastAPI REST API + React UI exposing all of the above via a singleton registry.

All six development phases are complete and tested.

---

## The Three-Phase Workflow

This is the spine — the mental model to hold before anything else. TraceBi takes
data from messy to reportable in three project-root folders, each with its own
cadence, decoupled by **freeze points** (a materialized artifact handed from one
phase to the next):

1. **MANIPULATE** — `transforms/`. Ordinary, unconstrained pandas: pull the
   queries, do the real analysis (window functions, prose parsing, cleaning,
   dedupe), then **sink** clean star-schema tables into a file-backed DuckDB
   warehouse. The framework does not constrain this phase. The contract is not
   *how* you clean, it is *what lands* — the named tables at the end of the
   script. Reference: `transforms/holdings_transform.py` → `DuckDBConnector(...).write(df, "table")`.

   *— freeze: `data/warehouse.duckdb` (materialized tables) —*

2. **MODEL** — `models/`. A declarative `DataModel` (star schema) over the
   warehouse: grain, keys, measures, in a few dozen lines a reviewer reads
   without opening the pandas above it. It reads the sink; it never sees the
   transform. Reference: `models/portfolio_model.py`.

   *— freeze: the model (the semantic contract) —*

3. **DASHBOARD** — `reports/`. A `ReportSpec` (JSON) pointed at the model —
   KPI cards, charts, tables — where every figure is a live query. Because the
   model is materialized, the page re-renders in milliseconds with no pandas in
   the loop. Reference: `reports/portfolio_dashboard.json`; served on the
   Reports page of the web UI. `reports/` also holds template packages and
   `@register.report` factories — every report form lives in the one folder.

**Why the split:** the slow, unconstrained analysis (①) and the fast, iterated
reporting (③) never block each other, because the model (②) is a frozen contract
between them. Editing the dashboard never re-runs the pandas.

**Honest scope of lineage / trust.** Tracing lineage *through* the raw analysis
(phase ①) is intentionally not done — the line is drawn at the **sink**, where
the numbers become a contract you can report against. The trust machinery
(stamped queries with a resolved query + lineage + SHA-256 fingerprint;
validate-before-execute on specs; `tracebi verify`) applies **from the model
boundary onward** — phases ② and ③. `tracebi verify` re-runs a manifest's
recorded queries and compares fingerprints; it does not read a transform and
does not assert a number is correct. Never claim it verifies the phase-① analysis.

---

## Repository Layout

```
tracebi/               # Core Python package (~5200 LOC)
  connectors/          # BaseConnector + CSV, SQL, BigQuery, Snowflake, Memory, DuckDB
  model/               # DataSet, DataModel (with star-schema query)
  etl/                 # LandingLayer / BronzeLayer, ManipulationLayer / SilverLayer, FinalLayer / GoldLayer
  reports/             # Report, Section types, ExcelRenderer, HTMLRenderer
  pipeline/            # PipelineRunner + APScheduler integration
  lineage/             # LineageDiagram (matplotlib / mermaid / HTML export)
  web/                 # register facade + auto-discovery for request scripts (.py and .ipynb)
    api/
      main.py          # FastAPI app entry point — CORS, routers, auth
      auth.py          # Optional HTTP Basic / proxy-header middleware
      registry.py      # Back-compat re-export of tracebi.registry (the real seam)
      errors.py        # Structured error payload (message + traceback) for routers
      lineage_graph.py # LineageNode list → React Flow graph (shared by routers)
      routers/         # One file per domain (connectors, models, reports, pipelines, dev)
    demo_app/          # Default app module package — shows how to wire everything together
    run.py             # Dev server (uvicorn wrapper) — python -m tracebi.web.run
    ui/dist/           # Built React bundle, written here by `cd web/ui && npm run build`
                       # (gitignored; Docker, Vercel and the release workflow build it. A
                       # wheel built from a tree without it ships no UI — / says so.)
  cli.py               # tracebi init / new-request / list-requests / run / dev / validate
  _notebook.py         # notebook_to_source() — concatenates code cells for exec
  __init__.py          # Public API re-exports — check here before writing new code
web/
  ui/                  # React UI source — a Node workspace, NOT a Python package. Nothing
                       # importable lives under the top-level web/ any more: shipping a
                       # directory named `web` in the wheel collided with the unrelated
                       # `web.py` distribution, which owns that same path in site-packages.
                       # `npm run build` writes its output into tracebi/web/ui/dist.
examples/              # Phase 1–4 + 2.5 runnable demos — read these to understand data flow
tests/                 # pytest suite (700+ tests; run it for the current count), one file per area
seeds/                 # DB init + Bronze seeding
inputs/                # Phase ⓪ INPUT — raw pulls land here (API export / CSV / SQL dump).
                       #   Tracked: holdings.csv + generate_raw.py (the demo source).
transforms/            # Phase ① MANIPULATE — unconstrained pandas that reads inputs/ and
                       #   sinks clean star tables into the warehouse (holdings_transform.py)
models/                # Phase ② MODEL — DataModel definitions over the warehouse;
                       #   each .py exposes a `model` variable (portfolio_model.py)
pipelines/             # PipelineRunner definitions — each .py exposes a `runner` variable
reports/               # Phase ③ DASHBOARD — every report form in one folder: ReportSpec
                       #   JSON (portfolio_dashboard.json), template packages (<name>/), and
                       #   @register.report() factories. All discovered and served alike.
requests/              # Ad hoc report scripts (.py or .ipynb); _template.py is the scaffold
run_workflow.py        # Runs the three-phase workflow end to end (phase ① build + ③ render)
data/                  # Gitignored local data: the demo SQLite DB and the workflow's
                       #   warehouse.duckdb + rendered dashboard HTML (build artifacts)
.env.example           # Documented env vars (auth, connector URLs, dev mode)
.github/workflows/     # CI — pytest matrix + ruff lint
Dockerfile             # Multi-stage build (React UI + Python app)
docker-compose.yml     # Single-container getting-started story
vercel.json            # Vercel: UI build + /api rewrite to the Python function
api/                   # Vercel serverless entry (index.py) + trimmed requirements
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

# Three-phase workflow
python run_workflow.py                          # phase ① builds data/warehouse.duckdb,
                                                #   phase ③ renders the dashboard HTML once, offline
python -m tracebi.web.run                       # serves it; auto-discovers models/ + reports/
                                                #   → Reports page (TRACEBI_REPORTS_DIR, default reports)

# Run (dev)
python -m tracebi.web.run                              # http://127.0.0.1:8000
TRACEBI_APP=mymodule.config python -m tracebi.web.run  # Custom app module
TRACEBI_DEV_MODE=1 python -m tracebi.web.run           # Enables POST /api/_dev/reload

# Run (prod)
# Multiple workers requires Postgres — see the note below.
uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
docker compose up --build                      # Or the docker-compose path
vercel --prod                                  # Vercel + Supabase (see docs/deploy-vercel-supabase.md)

# Database
python seeds/seed_db.py                        # Create + seed data/tracebi.db

# Model and pipeline scaffolding
tracebi new-model "Sales Model"                # → models/sales_model.py
tracebi list-models
tracebi new-pipeline "Sales ETL"               # → pipelines/sales_etl.py
tracebi list-pipelines
tracebi run-pipeline sales_etl                 # run every layer, upstream first
tracebi run-pipeline sales_etl --layer orders_silver [--refresh]
tracebi run-pipeline sales_etl --status        # last run per layer, executes nothing

# Agent / tooling context
tracebi context                                # framework vocabulary as JSON
tracebi context --model sales_model            # plus that model's schema
tracebi spec schema                            # JSON Schema for a report spec
tracebi spec validate report.json              # check a spec without running it
tracebi spec render report.json                # build and render it
tracebi mcp                                    # agent gateway over MCP (stdio)
tracebi mcp --transport http --port 8765       # remote agent — needs TRACEBI_MCP_TOKEN (or --insecure)
tracebi verify output/report.manifest.json     # re-run recorded queries; classify drift
tracebi serve                                  # browse the project

# Tests
pytest tests/                                  # Full suite (run it for the current count)
pytest tests/test_phase1.py                    # Single phase
pytest --cov                                   # With coverage
```

---

## Reports as Data

`reports/` accepts `*.json` alongside `*.py` and `*.ipynb`. A JSON file is a
`ReportSpec`: sections, and for each data-bearing one a `data` reference naming
a model and a query. Discovery validates it structurally and registers a
factory; everything downstream treats it as any other report, because a report
has only ever been *a name and a zero-arg callable*.

Two properties to preserve:

1. **The factory resolves models at call time, not at discovery time.** Doing
   query work during startup is the mistake `tracebi/web/demo_app` made, and a model
   the spec names may be registered after the file is scanned.
2. **Discovery-time validation is structural only.** Checking a spec against
   its models needs the models; that belongs to `tracebi spec validate` and to
   the first run, which reports a real error instead of failing startup.

Python and JSON are two serializations of one object graph — `from_report()`
exports, `build()` imports — so a notebook analyst can prototype interactively
and export to a governed artifact without a rewrite. **Python stays strictly
more powerful**: a spec cannot express arbitrary computation, which is exactly
why it is safe to generate and checkable without executing.

## Derived Presentation Defaults

`HTMLRenderer(derive_defaults=True)` (the default) fills in labels and number
formats the author left unset, from what the query already knows —
`tracebi/reports/derive.py`. `dim_branch.region` renders as `Region`;
`1705495.2200000002` renders as `1,705,495.22`.

Anything explicit wins outright. Order of preference for a format: the author's
`number_formats`, then a format the model declares on that measure, then a
column-name suffix hint (`_pct`), then shape — whole numbers get separators,
fractional ones two decimals. Columns named like `year`, `id` or `*_key` get no
format at all: a separator would render 2024 as `2,024`.

**The suffix hint is unit-aware, and only that rung is.** `percent` multiplies
by 100, and both conventions for a `_pct` column exist — a declared ratio
measure holds `0.069`, a hand-computed `pct_change().mul(100)` holds `12.5` —
so the hint applies only when every non-null value is fraction-shaped
(`|v| <= 1.5`, `_FRACTION_BOUND`). Otherwise the column falls through to the
shape default and keeps its own magnitude with no `%`. A declared measure
format still wins over this guard, because the model saying `format="percent"`
is a statement, not a guess. **A presentation default must never change the
number it presents.**

The guard is shape-based, so it cannot see a pre-scaled column whose values
happen to be small — a fund fee of `0.0945` meaning 0.0945% is indistinguishable
from a fraction. Store such a column in a unit its name states;
`models/wealth_model.py` uses `expense_ratio_bps`.

`ExcelRenderer` derives nothing — it applies only `section.number_formats`. So
a stored convention chosen to please the HTML renderer's derivation lands
unformatted in the spreadsheet: check both renderers before changing data.

Pass `derive_defaults=False` for the previous raw output verbatim.

This exists because raw defaults are a trap that scales badly: a human
authoring one report sees `DIM_BRANCH.REGION` and fixes it; an agent composing
at volume, with nobody reading the output, does not.

## Authorization

Authentication (`tracebi/web/api/auth.py`) says who a caller is; the `_Authorizer` in
the same module says what they may do. Roles are ordered and split by **side
effect**, which is the question a security review actually asks:

| Role | May |
|---|---|
| `viewer` | Read models, reports, lineage. Run Explore queries and spec validation — they compute but persist nothing. |
| `analyst` | viewer + execute report and request code. |
| `admin` | analyst + run pipeline layers, which write to the warehouse, and `/api/_dev/reload`. |

Three things to preserve when touching this:

1. **Enforcement is opt-in.** With no *usable* role source — no
   `TRACEBI_AUTH_ROLE_MAP`, and no `TRACEBI_AUTH_ROLE_HEADER` at all — every
   principal resolves to `admin`, so adding authorization could not lock a
   running deployment out of its own pipelines. Do not make it default-deny
   without a migration path. `TRACEBI_AUTH_DEFAULT_ROLE` is **not** a role
   source on its own: set by itself it names the fallback role but leaves
   enforcement off, and every principal is still `admin`. It switches
   enforcement on only alongside `TRACEBI_AUTH_ROLE_HEADER` (see invariant 2).
2. **The role header is only read when an upstream set it.** `_Authorizer`
   takes a required `trust_role_header`: proxy mode passes `True`, Basic auth
   passes `False`, because with no proxy in front the header is written by the
   principal it would promote. Proxy mode reads the *last* occurrence, so an
   appending proxy's own claim beats a client-supplied copy; a proxy should
   still replace the header. An untrusted header is not a role source on its
   own, but it does not cancel one either — an operator who also set
   `TRACEBI_AUTH_DEFAULT_ROLE` named the role everyone gets, and that is
   enforced (see 1).
3. **Unlisted writes require `analyst`.** `_required_role` falls through to
   `analyst` for any non-GET it does not recognise, so a route added later is
   guarded by default rather than open by default. Add an explicit rule when a
   new route needs `admin`.

Enforcement lives in the middleware, not in the routers — one place, and it
avoids touching the router imports that tests rebind for isolation.

---

## Audit Attribution

`tracebi_runs` records an `actor` and `actor_role` alongside what happened.
Identity lives in the web layer and the writer lives in the library, so it
crosses that boundary on a **ContextVar** (`tracebi/audit.py`) rather than the
library importing `web/` — the same mechanism works for the CLI, notebooks and
scheduled jobs, none of which have an HTTP request.

```python
from tracebi.audit import actor
with actor("alice", role="admin"):
    runner.run("orders_bronze")     # recorded against alice
```

Set by `BasicAuthMiddleware` / `ProxyHeaderAuthMiddleware` around `call_next`,
and by `tracebi run-pipeline` from the OS user. Attribution is optional
throughout: an unattributed run records `None` and behaves exactly as before.

A ContextVar, **not a module global** — a global would let concurrent requests
in one process read each other's actor.

New columns on an existing table are reconciled at startup by
`_add_missing_run_columns` (`CREATE TABLE IF NOT EXISTS` is a no-op against a
table that already exists). There is no migration framework here by design; if
you add a column to `tracebi_runs`, add it to `_RUNS_ADDED_COLUMNS` in the same
change or upgrades will break.

---

## Running More Than One Worker

`--workers 4`, or several container replicas, means several processes sharing
one database. `PipelineRunner`'s per-layer `threading.Lock` only guards its own
process, so the lock that actually matters is the database one:

| Backend | Concurrent layer execution |
|---|---|
| **Postgres** | Safe. A `pg_try_advisory_lock` per layer means a second process is refused with a clear error instead of interleaving writes. |
| **SQLite** | **Single process only.** The cross-process lock is a no-op, so two workers will both execute the same layer, interleave writes to the sink, and leave two "running" rows in the run history. |

SQLite is the development and demo fallback. Anything running more than one
process needs `PipelineRunner(db_url=<postgres url>)`.

---

## Core Invariants — Never Violate These

**1. DataSet is immutable.**
Every transform method must return a new `DataSet`. Never mutate `.df` or `.lineage` in place. If you add a new method to `DataSet`, it returns a new instance with the new `LineageNode` appended.

**2. Every data operation produces a LineageNode.**
Lineage is non-optional. If your new transform skips the lineage step, the audit chain breaks silently. Look at existing methods in `tracebi/model/dataset.py` for the pattern. `LineageNode` is frozen — pass all fields (including `metadata`) at construction; you cannot edit a node afterwards, by design.

**3. Registry is populated at startup, read at request time.**
`tracebi/registry.py` holds the singleton (`from tracebi.registry import registry`). It lives in the library, not the web layer — the FastAPI app is one consumer, but so are the CLI, request scripts, and notebooks. Register all connectors, models, and reports in your app module (e.g. `tracebi/web/demo_app/`) during import. Never mutate the registry inside a FastAPI route handler.

`tracebi/web/api/registry.py` is a backward-compatible re-export of the same object. **Do not repoint the routers at `tracebi.registry` directly** — `tests/test_phase5.py::TestPipelineRunEndpoint::test_run_all_layers` isolates state by rebinding `tracebi.web.api.registry.registry` before the router under test is first imported, and routers bind at import time, so changing the import path silently breaks that isolation. If you ever do repoint them, convert that test in the same change — and check it fails when you break the rebind, because a suite that passes because isolation became a no-op looks exactly like a suite that passes.

**4. Optional dependencies must fail loudly.**
Each feature group (reports, pipeline, lineage, sql) has optional deps. Wrap their imports in `try/except ImportError` and raise a clear `ImportError` telling the user which extras key to install. Don't let a missing dep produce a confusing `AttributeError` later.

**5. pyproject.toml is the only place for deps and config.**
Do not add `setup.py`, `requirements.txt`, `tox.ini`, or `setup.cfg`. The framework does not auto-load `.env` — `python-dotenv` is shipped via the `analyst`/`all` extras, but request scripts must call `load_dotenv()` themselves. Framework-read env vars: `TRACEBI_APP`, `TRACEBI_MODELS_DIR`, `TRACEBI_PIPELINES_DIR`, `TRACEBI_REPORTS_DIR` (phase ③ — specs, packages, and factories, default `reports`), `TRACEBI_REQUESTS_DIR`, `TRACEBI_SCHEDULED_DIR`, `TRACEBI_DEV_MODE`, `TRACEBI_DOCS_DIR`, `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` / `TRACEBI_AUTH_PROXY_HEADER` / `TRACEBI_AUTH_PROXY_TRUSTED_IPS` / `TRACEBI_AUTH_REALM`, `TRACEBI_MCP_TOKEN` (bearer auth for `tracebi mcp --transport http`) / `TRACEBI_MCP_ACTOR` (audit attribution for gateway work, default `agent`).

---

## Anti-Patterns

| Don't | Do instead |
|---|---|
| Mutate `dataset.df` directly | Return `DataSet(new_df, dataset.lineage + [new_node])` |
| Import from `tracebi/web/demo_app/` in tests | Use `MemoryConnector` or fixture data |
| Add cross-phase imports in test files | Keep tests isolated to their phase module |
| Make the framework read connector URLs from env vars implicitly | Construct connectors in app module code; pass credential-bearing URLs via `os.environ[...]` explicitly (see `.env.example`) |
| Add a new route without touching the registry | Wire it through `registry.py` so it's discoverable |
| Reach into `_private` attrs of framework objects from routers | Use the public surfaces: `runner.layers()`/`run_history()`, `model.info()`, `connector.describe()`, `runner.layers()` |
| Modify `tracebi_*` SQLite tables manually | Use `PipelineRunner` API |
| Add a new medallion layer without registering it | Call `runner.register(layer)` |

---

## How to Add Things

### New transform (phase ①)
1. Add a `.py` under `transforms/`. Write whatever pandas the data needs — the
   framework does not constrain this phase.
2. End by sinking clean star-schema tables into the warehouse:
   `DuckDBConnector("warehouse", database=WAREHOUSE).write(df, "table")`. The
   contract is the named tables that land, not how you produced them.
3. Model this on `transforms/holdings_transform.py`. Keep it idempotent (a rerun
   replaces the warehouse tables). Nothing downstream imports this file.

### New connector
1. Subclass `tracebi.connectors.BaseConnector`
2. Implement `load(name) -> DataSet` — must append a `LineageNode`
3. Register: `registry.add_connector(instance)` in your app module

### New model definition (project-scope, no web server required)
1. `tracebi new-model "My Model"` — creates `models/my_model.py`
2. Edit the file: wire connectors, tables, relationships, facts, dimensions. The variable **must** be named `model`.
3. Import anywhere: `from tracebi.model_registry import get_model; model = get_model("my_model")`
4. The web server auto-discovers `models/` at startup (`TRACEBI_MODELS_DIR` to override).

### New pipeline definition (project-scope, no web server required)
1. `tracebi new-pipeline "My ETL"` — creates `pipelines/my_etl.py`
2. Edit the file: wire connectors, layers, and `runner.register(...)`. The variable **must** be named `runner`.
3. Import anywhere: `from tracebi.pipeline_registry import get_runner; runner = get_runner("my_etl")`
4. The web server auto-discovers `pipelines/` at startup (`TRACEBI_PIPELINES_DIR` to override).

### New report (ad hoc)
Copy `requests/_template.py`. Fill in the four sections: connectors → transforms → report assembly → render + save.

### New report (web-exposed)
Put a `.py` file in `reports/` (or use `requests/`). Decorate a factory function with `@register.report("name")`. The file is auto-discovered at startup; the function receives no args and returns a `Report`.

### New dashboard (phase ③)
1. Add a `ReportSpec` `.json` under `reports/`, pointed at a model (grain +
   measures it declares). Model this on `reports/portfolio_dashboard.json`.
2. Every figure is a live query against the model — KPI cards, charts, tables. A
   `metrics` section may carry a `data` query; a card whose `value` names a
   measure reads it live from the one-row result rather than hard-coding it.
3. Validate before running: `tracebi spec validate reports/<name>.json`. The
   folder is auto-discovered and served on the Reports page.

### New report as a template package (freeform HTML)
When the spec's section vocabulary is too rigid — a bespoke layout, your own
CSS — scaffold a package instead: `tracebi new-report "My Report"` creates
`reports/my_report/` (`report.json` data bindings + `template.html` / `style.css`
/ `script.js`). `tracebi report build my_report` renders ONE self-contained HTML
(CSS, JS, and fingerprinted data inlined; strict CSP; ECharts vendored, no CDN)
plus a manifest. `report.py` beside `report.json` is the escape hatch for pandas
the model can't express — its output stamps `verifiable: false` and never reads
green under `verify`. Charts render with ECharts in the browser; the SVG path is
kept only for the (unshipped) PDF renderer.

### New medallion layer
```python
# ManipulationLayer is the canonical name; SilverLayer remains as an alias.
layer = ManipulationLayer(source=bronze_connector, source_table="orders_bronze",
                          sink=db, sink_table="orders_silver").deduplicate(subset=["order_id"])
runner.register(layer, name="orders_silver", schedule="0 * * * *",
                depends_on="orders_bronze")
```

### New FastAPI route
Add a file under `tracebi/web/api/routers/`, include it in `tracebi/web/api/main.py`, and read resources only from the registry — never import app-specific objects directly.

---

## API Routes

```
GET  /api/health
GET  /api/schema                                     → machine-readable vocabulary (generated)
GET  /api/discovery                                  → per-file registered/skipped/failed + reason
GET  /api/spec/schema                                → JSON Schema for a report spec
POST /api/spec/validate                              → check a spec without executing it
POST /api/spec/render                                → build a spec and render HTML + manifest
GET  /api/connectors
GET  /api/connectors/{name}
GET  /api/models
GET  /api/models/{name}                              → tables, relationships, facts, dimensions
GET  /api/models/{name}/tables/{t}/preview           → first N rows + dtypes + total_rows
GET  /api/models/{name}/tables/{t}/export.csv        → full table as CSV attachment
POST /api/models/{name}/query                        → star-schema query + lineage graph
GET  /api/reports
POST /api/reports/{name}/run                         → HTML + lineage manifest JSON (sync)
POST /api/reports/{name}/runs                        → start background run; returns run_id (202)
GET  /api/reports/{name}/runs                        → recent background runs (no payloads)
GET  /api/reports/{name}/runs/{run_id}               → poll status; result/error when settled
GET  /api/reports/{name}/download?format=xlsx|html   → rendered file attachment
GET  /api/reports/{name}/lineage                     → React Flow graph per section
GET  /api/reports/{name}/mermaid
GET  /api/requests                                   → scripts in requests/ (name, type, modified)
GET  /api/requests/{name}/params                     → declared request_params() defaults (static)
POST /api/requests/{name}/run                        → execute script fresh; body {"params": {…}}
GET  /api/requests/{name}/lineage?params_json={…}    → React Flow graph per section
GET  /api/pipelines
POST /api/pipelines/{name}/run
POST /api/pipelines/{name}/layers/{layer}/run
GET  /api/pipelines/{name}/layers/{layer}/history
GET  /                                               → React SPA (tracebi/web/ui/dist); when it has not
                                                       been built, a page naming the build command
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
| Understand the three-phase workflow | `WORKFLOW.md` + `run_workflow.py` |
| Author a phase-① transform | `transforms/holdings_transform.py` |
| Define the model over the warehouse | `models/portfolio_model.py` |
| Build a dashboard | `reports/portfolio_dashboard.json` |
| Build a freeform report package | `tracebi new-report` → `reports/portfolio_book/` + `docs/report-generator-architecture.md` |
| Understand architecture decisions | `NOTES.md` |
| See a complete working wiring | `tracebi/web/demo_app/` |
| Understand data flow end-to-end | `examples/phase4_example.py` |
| Add something to the web API | `tracebi/registry.py` (singleton) + `tracebi/web/api/routers/` |
| Write an ad hoc report | `requests/_template.py` |
| Define a reusable DataModel | `tracebi new-model` → `models/` → `tracebi/model_registry.py` |
| Define a reusable pipeline | `tracebi new-pipeline` → `pipelines/` → `tracebi/pipeline_registry.py` |
| Understand the lineage chain | `tracebi/model/dataset.py` |
| Add a new connector | `tracebi/connectors/` (pick any existing one as a model) |

---

**These guidelines are working if:** diffs are minimal and focused, tests pass before and after, and questions surface before implementation rather than after mistakes.
