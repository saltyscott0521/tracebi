# TraceBi — Project Notes & Design Decisions

A running log of key discussions, decisions, and concepts for the TraceBi project.

---

## Build Status

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Done | Connectors, DataModel, DataSet + lineage |
| Phase 2 | ✅ Done | Report Engine (Excel, HTML, manifest) |
| Phase 2.5 | ✅ Done | Medallion architecture, Star schema, Lineage diagram |
| Phase 3 | ✅ Done | Dashboard server (Dash-based, associative filters) |
| Phase 4 | ✅ Done | Pipeline runner (APScheduler, DB write-back, cross-layer lineage) |
| Phase 5 | ✅ Done | Web UI (FastAPI + React, Dash embedded, medallion-aware demo) |
| Phase 6 | ✅ Done | DuckDB engine, push-down filters, layer rename, CLI, auto-discovery, auth, docker-compose |
| Docs | ✅ Done | README rewritten, docs/overview.html added |

---

## 2026-05-06 — Report as Code Philosophy

### Context
Discussion about whether TraceBi's "report as a script" approach would work well
for ad hoc data requests, and whether it could be made obsolete by AI.

### Core Concept: Report as Code
Every report is a self-contained `.py` or `.ipynb` file that is the source of
truth for both the analysis logic and the formatted output. Key properties:

- **Rerunnable on demand** — reconnects to live data, reruns transforms, regenerates output
- **Auditable** — every report script committed to git with a lineage manifest
- **Self-documenting** — the code IS the documentation of how the number was calculated
- **Deliverable + traceable** — the business gets Excel/HTML, the team keeps the script

### Proposed Folder Convention
```
tracebi/
├── tracebi/          ← the library
├── requests/         ← one file per ad hoc request
│   ├── 2024_06_open_orders_by_region.py
│   ├── 2024_07_customer_churn_analysis.ipynb
│   └── 2024_08_product_margin_review.py
└── output/           ← generated reports land here
```

Each file in `requests/` is:
- Self-contained (defines its own model, transforms, and report)
- Rerunnable (same code = same logic, fresh data each run)
- Committed to git (permanent record of the analysis)

### TODO
- [x] Add `requests/` folder to repo structure
- [x] Build a request template file (`requests/_template.py`)
- [x] Add `output/` to `.gitignore` (generated files shouldn't be committed)

---

## 2026-05-06 — AI + TraceBi: Complementary, Not Competing

### Context
Discussion on whether Claude or similar AI could make TraceBi obsolete by
managing report delivery and writing directly.

### What AI Could Replace
- Writing the report script itself (Claude Code can already do this)
- The "someone sits down and writes the pandas transforms" step
- Natural language → report script generation

### What AI Cannot Replace
- **Auditability** — a Claude chat answer is gone; a committed `.py` file
  with a lineage manifest is permanent and defensible
- **Reproducibility** — same code + same data = same output, rerunnable in
  6 months; chat conversations are stateless in the wrong way
- **Governance** — regulated industries (finance, healthcare, compliance)
  need to prove how a number was calculated; a git-committed script is
  evidence, an AI chat is not
- **Version control** — diff two versions of a report, roll back, branch;
  none of this is possible with chat-generated answers

### The Right Mental Model: AI + TraceBi Together
```
Business user: "Show me open orders by region for $50k+ accounts"
        ↓
Claude writes the report script
        ↓
TraceBi executes it against the DataModel
        ↓
Lineage manifest records everything
        ↓
Excel/HTML delivered + script committed to git
```

AI handles the **generation**, TraceBi handles the **execution, formatting,
and auditability**. The script exists whether Claude wrote it or a human did.

### Competitive Risk
The real risk is NOT AI replacing TraceBi — it's tools like Notion, Hex, or
Observable getting good enough at code-first + formatted output. But none
currently combine:
- Relational model (Qlik-style associations)
- Full lineage tracking per report
- Multiple output formats (Excel, HTML, PDF)
- Pure Python, no GUI required

That combination remains a genuine differentiator.

### TODO
- [ ] Design a `RequestTemplate` that Claude Code can use as a scaffold
      when generating new report scripts from natural language
- [ ] Consider a CLI command: `tracebi new-request "open orders by region"`
      that scaffolds a new request file from a template

---

## Architecture Reference

### Package Structure
```
tracebi/
  connectors/     Source adapters (CSV, SQL, BigQuery, Snowflake, Memory)
  model/          Core abstractions (DataSet, DataModel with star-schema query)
  etl/            Medallion layers (Bronze → Silver → Gold)
  reports/        Report engine + renderers (Excel, HTML)
  dashboard/      Dash-based live dashboard server
  lineage/        Lineage visualisation (LineageDiagram)
examples/         Runnable demos for each phase
tests/            Pytest suite (one file per phase)
requests/         Project-specific report scripts (copy _template.py)
output/           Generated files — gitignored
```

### Core Design Patterns

**Immutable DataSet** — every operation (filter/transform/sort/join) returns a new
DataSet with the original's lineage plus a new LineageNode appended. The underlying
DataFrame is never mutated in place.

**Why:** Lineage is append-only. You can always reconstruct exactly which operations
produced a result. No in-place mutation means no hidden state bugs.

**DataModel** — Qlik-style relational graph. Name your connectors, tables, and
relationships once; reports, dashboards, and pipelines all read from the same
definitions. `load()` always re-reads from source (no caching).

**Medallion layers as separate classes** — Bronze/Silver/Gold are distinct
_contracts_, not just naming conventions. BronzeLayer enforces "no transforms".
SilverLayer enforces "declarative pipeline". GoldLayer enforces "aggregated via
the DataModel star-schema query". The type boundary makes it impossible to
accidentally skip a layer.

**MemoryConnector** — tests and demos should not require external files or databases.
Drop-in connector backed by a Python dict, so tests run in pure memory with full lineage.

### Medallion Architecture

```python
# Bronze — raw ingest
orders_bronze = BronzeLayer(connector=connector, source="orders.csv").load()

# Silver — clean
orders_silver = (
    SilverLayer()
    .cast({"order_date": "datetime64[ns]", "qty": "int64"})
    .drop_nulls(subset=["order_id"])
    .deduplicate(subset=["order_id"])
).apply(orders_bronze, name="orders_silver")

# Gold — aggregated via the DataModel's star-schema query
gold = GoldLayer(model=model)
revenue_by_region = gold.query(
    fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.region"],
    filters={"status": "shipped"},
)
```

### Star Schema (on DataModel)

Tag tables on the DataModel with star-schema roles. Dimension references
use dot notation: `"dim_name.attribute"`. Measures are a dict:
`{"column": "agg_func"}`. Supported agg funcs: `sum`, `count`, `mean`,
`min`, `max`, `nunique`.

```python
model.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region", "segment"])
model.add_fact("fact_orders", table_name="orders",
               measures=["revenue", "qty"],
               foreign_keys={"dim_customer": "customer_id"})

ds = model.query(
    fact="fact_orders",
    measures={"revenue": "sum"},
    dimensions=["dim_customer.region"],
)
```

### Lineage Diagram

```python
diag = LineageDiagram(ds)       # or LineageDiagram(report)
diag.show()                     # matplotlib / Jupyter inline
diag.to_html("lineage.html")    # standalone HTML with embedded SVG
print(diag.to_mermaid())        # paste into GitHub markdown
```

Node colors by operation type:

| operation  | color   |
|-----------|---------|
| load      | navy    |
| bronze    | bronze  |
| silver    | silver  |
| gold      | gold    |
| filter    | green   |
| transform | amber   |
| join      | orange  |
| sort      | purple  |

### Install

```bash
pip install -e ".[reports,dashboard]"
pip install networkx matplotlib        # for LineageDiagram
```

### Running Examples

```bash
python examples/phase1_example.py    # connectors + DataModel
python examples/phase2_example.py    # reports (opens browser)
python examples/phase3_example.py    # live Dash dashboard
python examples/phase25_example.py   # medallion + star schema + lineage diagram
```

---

---

## 2026-05-13 — Web UI (Phase 5)

### What was built
A FastAPI + Jinja2 web server (`web/`) that provides a browser UI over any
TraceBi registry. Key pieces:

- **Registry** (`web/api/registry.py`) — central singleton; connectors, models,
  reports, pipelines, and dashboards are all registered here at startup
- **App module** (`web/demo_app.py`) — imported on startup; detects `data/tracebi.db`
  and adapts: full medallion setup when Silver tables are present, in-memory
  MemoryConnector fallback otherwise
- **Dash embedding** — each registered `DashboardServer` is mounted inside FastAPI
  at `/dashboards/<name>/` via Starlette's `WSGIMiddleware`. Single port, no second
  server. The standalone `DashboardServer.run()` path is unaffected.
- **Pipelines page** — lists Bronze/Silver/Gold layers with run history and a
  ▶ Run button backed by `POST /api/pipelines/{name}/layers/{layer}/run`

### TRACEBI_APP pattern
The web layer is decoupled from `demo_app.py` via an env var:

```bash
TRACEBI_APP=myproject.tracebi_config python web/run.py
```

`myproject/tracebi_config.py` defines its own connectors, models, reports, and
dashboards and registers them with the shared registry. `demo_app.py` is a
reference implementation, not a required file.

### Notebook → Web UI workflow (TODO)
Current gap: there is no smooth path from "I built something in a notebook"
to "it shows up in the web UI". The intended workflow is:
1. Explore and prototype in a notebook using the library
2. Move the stable definitions into a `tracebi_config.py` module
3. Register them and point `TRACEBI_APP` at the module

This is functional but manual. A future improvement could be a helper that
lets you register objects directly from a notebook into a running server
(e.g. via a hot-reload module or a dev-mode registry endpoint).

### TODO
- [ ] Design the notebook → web UI workflow more explicitly
- [ ] Consider a `tracebi.web.register()` helper usable from notebooks
- [ ] Add a `/dashboards/<name>/lineage` endpoint to expose dashboard dataset lineage

---

## 2026-05-22 — Architecture & Positioning Discussion

### Product Positioning

TraceBi is the **reporting and delivery layer** for data that has already been
engineered upstream. It is not a replacement for dbt, Airflow, or Spark. It assumes
a mature data warehouse or lake exists and picks up from there.

**Core value TraceBi adds:**
- Connectivity — talk to whatever warehouse or lake already exists
- Lineage — every report knows exactly what data produced it and when
- Structure — a consistent, code-first pattern for building and maintaining reports
- Delivery — scheduled outputs, web UI, Excel, HTML, dashboards for non-technical users
- Auditability — git as the permanent record of what was built and why

**TraceBi explicitly is not:**
- A data engineering tool
- Responsible for data quality upstream
- A replacement for full ETL pipelines
- An in-memory compute engine for large datasets

The expectation is that heavy data engineering — transformations, aggregations,
cleaning — happens upstream in the database or lake before TraceBi connects to it.

---

### Replacing Medallion Framing

The Bronze/Silver/Gold medallion naming implies TraceBi owns the full ETL pipeline,
which conflicts with the positioning above. The discussion landed on replacing
medallion terminology with a simpler three-step model:

**Level 1 — Landing**
Connect to whatever upstream table exists and load it into TraceBi's context.
No transforms. Entry point could be a dbt silver model, a Snowflake view, a
Postgres table, or anything else. TraceBi does not own what happens before this.

**Level 2 — Manipulation**
Optional light touches before serving. Joins, column casts, filters, renames —
the kind of thing an analyst would do in a notebook before analyzing. If upstream
data is already in the right shape, this step can be skipped entirely.

**Final Model / Star Schema**
The serving layer. Declare facts and dimensions, run the analytic query, get back
a clean dataset ready for a report or dashboard. Reports can be built off Level 2
data (detail/transaction level) or the Final Model (aggregated). Both are valid;
the framework should support either without prescribing which to use.

> **Open decision:** whether to rename Bronze/Silver/Gold to Landing/Manipulation/Final
> in the codebase, or keep the current names and adjust the framing in docs/UI only.

---

### Large Data / Memory Considerations

- The database or lake does the heavy compute — TraceBi receives only the result
- Push-down filters at the connector level (WHERE clauses before loading) are the
  right pattern for detail-level queries
- DataModel.query() should aggregate at the database level where possible —
  only the small result set comes back to Python
- Transaction-level detail reports are valid but should always filter at the SQL
  level first, not load everything and filter in pandas
- A lineage warning when a large unaggregated load occurs with no filters would
  be useful — visible in the lineage chain, not blocking

---

### Web UI — Auto-Discovery Direction

Current state: reports and pipelines are registered manually in `demo_app.py`.

Direction: move toward folder-based auto-discovery where the app scans designated
directories at startup. Reports follow a convention (decorated `run()` function or
entry point) so the registry builds itself. `demo_app.py` becomes minimal — just
path config and connector credentials.

Open decisions:
- Whether `requests/` (ad hoc) and `scheduled/` are separate folders or one folder
  where a decorator determines scheduling
- Connectors and models remain as Python declarations (not YAML)

---

### Deployment Model

- Docker is the right deployment target for the web UI mode
- Single `docker-compose.yml` with app + SQLite (or Postgres) + output volume
  is the right getting-started story
- Cloud VM (small EC2, DigitalOcean droplet) is where most real small-team
  deployments will land
- Serverless is a poor fit — the scheduler is stateful and long-running
- API layer should be designed to sit behind external auth (Authelia, Cloudflare
  Access) without requiring a rewrite

---

### Two Usage Modes

**Mode 1 — Pure library**
Install TraceBi, write Python scripts, render reports to files or inline in a
notebook. No web server, no UI. Target persona: data engineer or analyst comfortable
in code.

**Mode 2 — Installed package with web UI**
Configure connectors and models, write report scripts into designated folders, web
UI surfaces and delivers reports. Includes scheduling, run history, output downloads,
lineage visualization.

---

### User Personas

**Persona A — Data engineer / analyst**
Writes the Python, sets up connectors, builds the pipeline and reports. Comfortable
in code. Uses TraceBi as a library or as the code layer of Mode 2. Cares about
lineage, reproducibility, git as the audit trail.

**Persona B — Business stakeholder**
Wants to see the report, download the Excel, filter a dashboard. Never touches Python.
Needs the web UI to be self-service and reliable. Currently underserved by the
architecture — worth keeping in mind as the web UI develops.

---

### Architectural Risks

- **Dash embedded inside FastAPI** — known friction point for middleware, auth, and
  hot-reloading. May need to be a separate service as dashboards grow.
- **Pandas memory ceiling** — DataSet should be designed so it could wrap a lazy
  frame (Polars, DuckDB) in the future without deep rewrites.
- **`model.load()` pulling full tables** — push-down filter/column selection on
  load should be a first-class feature, not an afterthought.
- **Auth gap** — no user identity or permissions model exists yet. Minimum viable
  approach is HTTP basic auth or sitting behind a proxy. Design the API so auth
  can be added without a rewrite.

---

## Open Questions

- Should `requests/` files be standalone scripts or should they import a
  shared project-level `DataModel` defined once in a central file?
- Should the request template support both `.py` and `.ipynb` formats?

---

## 2026-05-23 — Recommendations Actioned

Built out the work described in the 2026-05-22 architecture discussion plus
the older Phase 5 and AI + TraceBi TODOs. Summary of what changed:

### DuckDB-backed engine, pandas-facing API
- New `DuckDBConnector` for in-memory analytics, persistent `.duckdb` files,
  and zero-config Parquet / CSV / JSON file access (`tracebi.[duckdb]` extra).
- `DataModel.query()` (the star-schema analytic surface) now executes joins,
  filters, and aggregations inside DuckDB (zero-copy view registration from
  pandas), then materialises the result back to a pandas DataFrame so the
  user-facing API is unchanged. Falls back to pandas when DuckDB isn't installed.
- The final lineage node records which engine ran the query
  (`metadata["engine"] = "duckdb" | "pandas"`).

### Push-down filter + column projection
- `BaseConnector.load(source, filter=None, columns=None)` is the new
  contract. Every connector implements it.
- `SQLConnector` / `BigQueryConnector` / `SnowflakeConnector` /
  `DuckDBConnector` push filters down via `WHERE` / parameter binding and
  project columns via `SELECT`. `MemoryConnector` and `CSVConnector` apply
  them in pandas after loading. `supports_pushdown()` exposes this.
- `DataModel.load(table_name, filter=..., columns=...)` threads the call
  through, and records which path was used in the load lineage node.

### Lineage warning on large unfiltered loads
- `DataModel.load()` appends an `operation="warning"` node when a load
  returns more than `LARGE_LOAD_WARN_ROWS` (default 100k) rows *and* no
  filter / column projection was passed. Non-blocking — visible in the
  lineage chain only.

### Landing / Manipulation / Final layer naming
- `LandingLayer`, `ManipulationLayer`, `FinalLayer` are the new canonical
  classes — direct subclasses of `BronzeLayer` / `SilverLayer` / `GoldLayer`
  with the only difference being the `operation` and `layer_label` they
  stamp into lineage.
- Existing `BronzeLayer` / `SilverLayer` / `GoldLayer` keep working
  unchanged (and existing tests assert on the old `"bronze"`/`"silver"`/
  `"gold"` lineage tags). All 163 prior tests still pass.

### CLI: `tracebi new-request`
- New `tracebi.cli` module wired as a `[project.scripts]` entry point.
- `tracebi new-request "Open orders by region"` → scaffolds
  `requests/open_orders_by_region.py` from a fresh template.
- Plus `tracebi list-requests` and `tracebi run <name>`.

### Folder-based auto-discovery
- `tracebi.web.discovery.auto_discover(path)` imports every `*.py` in a
  directory (skipping `_*`).  The web server calls this at startup against
  `TRACEBI_REQUESTS_DIR` (default `requests/`), so any
  `@registry.report(...)` decorators inside drop-in files fire automatically.

### Notebook helper: `tracebi.web.register`
- `from tracebi.web import register` exposes a small facade —
  `register.connector(...)`, `register.model(...)`, `register.pipeline(...)`,
  `register.dashboard(...)`, `@register.report(...)`,
  `register.auto_discover(...)`. All lazy-import the web registry singleton
  so the library still works in pure-library installs.

### Web layer additions
- `GET /api/dashboards/{name}/lineage` — returns a React Flow graph for the
  combined lineage of every panel in a dashboard.
- Optional `BasicAuthMiddleware` activates when `TRACEBI_AUTH_USER` and
  `TRACEBI_AUTH_PASS` are set; `/api/health` is always public.

### Deployment
- `docker-compose.yml` for the getting-started story — mounts `data/`,
  `output/`, and `requests/` and exposes the web UI on port 8000.
- Dockerfile picks up the new `[duckdb]` extra.

### Open decisions left as-is
- Layer renaming is additive only — no plan to delete the
  Bronze/Silver/Gold class names. CLAUDE.md still references both.

---

## 2026-05-23 — Follow-up: rename finalised across UI + remaining TODOs

A second pass actioned the items called out in NOTES.md follow-up.

### UI refresh
- `web/demo_app.py` migrated to `LandingLayer` / `ManipulationLayer`
  / `FinalLayer`. Pipeline runs now stamp `layer_type =
  "landing" | "manipulation" | "final"`.
- React UI updated: new badge variants in `Shared.jsx`, new
  `TYPE_BADGE` + `TYPE_LABEL` maps in `Pipelines.jsx` that handle both
  legacy ("bronze/silver/gold") and new vocabularies, copy refresh
  on `Home.jsx` (concept #3, feature grid, walkthrough step #3),
  and a "⊶ Lineage" modal on `Dashboards.jsx` consuming
  `/api/dashboards/{name}/lineage`.
- `useRunPipeline` hook + "Run all" button on each pipeline card.

### Pipeline-level run endpoint
- `POST /api/pipelines/{name}/run` — walks all leaves with their full
  upstream chain (deduplicated) by default, or fires every layer in
  registration order with `refresh=false`.

### Proxy header-trust auth
- `ProxyHeaderAuthMiddleware` reads identity from a configurable header
  (default `X-Forwarded-User`) and exposes it at `request.state.user`.
- `TRACEBI_AUTH_PROXY_HEADER` selects proxy mode; optional
  `TRACEBI_AUTH_PROXY_TRUSTED_IPS` restricts which client IPs may pass.
- Proxy mode wins when both Basic and Proxy env vars are set.
- Designed for Authelia / oauth2-proxy / Cloudflare Access deployments.

### Embedded Dash toggle
- `TRACEBI_EMBED_DASHBOARDS=0` skips the WSGI mount; dashboards then
  run standalone via `DashboardServer.run()`. Default remains embedded
  for the single-port demo flow.

### Folder & decorator
- `@registry.scheduled("name", cron="…")` decorator registers a report
  *and* tags it with a cron expression. `registry.list_scheduled()`
  exposes the cron-tagged factories for an external scheduler.
- Second auto-discovery directory: `TRACEBI_SCHEDULED_DIR`
  (default `scheduled/`). Same import semantics as `requests/`.

### Shared project model
- `Registry.add_model(model, default=True)` and
  `Registry.set_default_model(name)` track a project-level default.
- `tracebi.web.register.get_default_model()` returns it; the request
  template and notebook scaffold both call this so files don't each
  rebuild their own DataModel.

### CLI: notebook scaffold
- `tracebi new-request "…" --notebook` writes a valid `.ipynb` with
  starter cells. `tracebi list-requests` now lists both `.py` and
  `.ipynb`.

### Dev-mode reload
- `TRACEBI_DEV_MODE=1` mounts `POST /api/_dev/reload` and
  `GET /api/_dev/discovered`.
- `reload_modules()` invalidates the importlib caches, bumps mtime,
  and deletes stale `.pyc` before re-importing, so back-to-back edits
  within the same second are picked up.

### Tests
- 229 total (66 in `test_phase5.py`), covering proxy auth, dashboard
  lineage endpoint, pipeline-level run, shared model defaults,
  `@scheduled`, notebook scaffolding, dev-mode reload.
