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
- [x] Design a `RequestTemplate` that Claude Code can use as a scaffold
      when generating new report scripts from natural language —
      `tracebi/cli.py:_template_text()` is the canonical scaffold.
- [x] Add a CLI command `tracebi new-request "open orders by region"` —
      shipped, plus `--notebook` flag for `.ipynb` scaffolding.

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

### Notebook → Web UI workflow (DONE)
Three pieces shipped on this thread:

1. **`tracebi.web.register`** — thin facade (`register.connector()`, `register.model()`,
   `@register.report()`, `register.get_default_model()`, …) that lazy-imports the registry
   so notebooks don't need to know FastAPI's layout.
2. **`tracebi.web.discovery.auto_discover()`** — folder scanner that imports
   every `*.py` and `*.ipynb` (skipping `_*`) under `TRACEBI_REQUESTS_DIR`
   (default `./requests`). Notebook code cells are concatenated; line magics
   (`%matplotlib`) and shell escapes (`!pip install`) are dropped silently.
3. **`POST /api/_dev/reload`** — opt-in dev-mode endpoint
   (`TRACEBI_DEV_MODE=1`) that re-imports every previously-discovered module.

### TODO
- [x] Design the notebook → web UI workflow more explicitly — see above.
- [x] Add a `tracebi.web.register()` helper usable from notebooks — shipped.
- [x] Add a `/dashboards/<name>/lineage` endpoint to expose dashboard dataset lineage — shipped.

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

All four questions in this section have been resolved:

- **Shared vs standalone request files** — resolved: shared. `requests/_template.py`
  and the CLI scaffold both call `register.get_default_model()` and fall back to
  building a local model only when no project default has been registered.
- **`.py` and `.ipynb` request formats** — resolved: both. `tracebi new-request
  --notebook` scaffolds an `.ipynb`; `tracebi run` and `auto_discover` execute
  either format.
- **`tracebi new-request` worth building** — resolved: yes, shipped. Plus
  `tracebi init`, `list-requests`, `run`, and `validate`.
- **Notebook → web UI registration workflow** — resolved: folder-based
  auto-discovery on startup, plus the optional dev-mode reload endpoint for
  iterative editing without restarting the server.

---

## 2026-05-22 — Architecture Review & Action Plan

> Comprehensive review of the codebase against the vision. Captured here as a
> working document for the next agent to pick up and execute against.
> Findings cite specific files; recommendations are prioritized.

### Concept Assessment

The genuinely differentiated idea is **"Report as Code + lineage manifest as
audit artifact."** Not the medallion layers, not the dashboard, not the
connectors. The thing nothing else in the comp set does well is:

> Business asks for a number. Analyst commits a `.py` file. The file is
> rerunnable, the output is Excel/HTML the business actually opens, and the
> manifest is courtroom-defensible six months later.

**Unique value proposition (one sentence):** The only Python framework where
every Excel/HTML/PDF deliverable carries an immutable, machine-readable
lineage manifest, and the script that produced it is the auditable source of
truth.

**Comp set summary:**

| Tool | Better than us | Worse than us |
|---|---|---|
| dbt | Warehouse SQL transforms, mature model lineage, community | Per-report manifests; Excel/HTML; analyst ad-hoc; non-SQL transforms |
| Dagster | Real DAG orchestration, asset materialization | Lower ceremony; report-shaped artifacts |
| Great Expectations | Data quality testing | Nothing — integrate, don't compete |
| Evidence.dev | Static-site BI from SQL+markdown | Python ecosystem; Excel; programmatic transforms |
| Hex / Deepnote | Notebook UX, collab, secrets, SSO | Git as source of truth; no vendor lock-in; runs anywhere |
| Streamlit / Dash | Live interactivity | Lineage; reports-as-files; medallion structure |
| Power BI / Tableau | Polish, ubiquity | Auditability; diffable reports; code review for analytics |

The 2026-05-22 positioning entry (above) arrived at the right framing —
delivery and auditability layer, not ETL platform. Need to commit to it in
README, UI copy, and public API.

---

### Architecture Findings

**DataSet + LineageNode (`tracebi/model/dataset.py`)** — strong.
Immutability is real. Three gaps:
- `LineageNode` is a regular `@dataclass`, not frozen. `ds.lineage[0].metadata['rows'] = 999` mutates the audit chain in place.
- `fingerprint()` uses `pd.util.hash_pandas_object()` — non-cryptographic, non-deterministic across pandas versions, sensitive to column order.
- Every constructor does `df.copy()`. Lethal for large data; fine for small aggregates.

**DataModel (`tracebi/model/data_model.py`)** — `load()` always issues
`SELECT *`. No pushdown. `resolve()` does merges in pandas memory even when
both sides come from the same SQL connector.

**Medallion (Bronze/Silver/Gold)** — kill the framing. NOTES.md 2026-05-22
already arrived at Landing/Manipulation/Final. Three reasons:
1. It overpromises (implies we own ingest).
2. It collides with dbt.
3. `GoldLayer` adds nothing — 30-line wrapper around `StarSchema.query()` that stamps a lineage node.

Keep old class names as deprecated aliases for one version, then remove.

**Report engine (`tracebi/reports/`)** — sections + manifest + multi-renderer
is solid. Manifest persisting per-section dataset lineage + fingerprint is
the genuinely novel piece — make it prominent in docs. Renderers need fuzz
testing with NaN, long text, mixed dtypes, unicode.

**Pipeline runner (`tracebi/pipeline/runner.py`)** — functional but rough:
- No locking. Two workers can both `run("layer")` concurrently; run history becomes ambiguous.
- SQL injection: `f"WHERE layer_name = '{layer_name}'"` with `layer_name` from a FastAPI path parameter.
- `runner.run()` returns synchronously from the web endpoint but the UI gets `"status": "triggered"` while the job may still be running.

**Web UI / Registry** — confirms risks already named in NOTES.md:
- Dash inside FastAPI via WSGI middleware won't scale.
- Registry is module-level singleton populated at import time; fragile under hot-reload or multi-worker uvicorn.
- No auth (known). Design assuming reverse-proxy enforces identity.

---

### Lineage & Traceability — Three Real Gaps

**Gap 1 — Lineage of the *code that produced the lineage*.** Manifest
records transforms but not the git SHA of the repo at render time. Add
`git_sha` to `ReportManifest`. Difference between "I can prove what
happened" and "I can prove what happened *and reproduce it.*"

**Gap 2 — Cross-pipeline lineage.** A report consuming a gold table doesn't
carry the upstream `run_id` of the pipeline run that produced it. Can't
answer: "this Excel file's `revenue_by_region` came from which pipeline
run?" Stamp the most recent successful `run_id` of any sink table the
report reads onto its manifest.

**Gap 3 — Dashboards have no lineage export.** Already a TODO in NOTES.md.
Should be P1, not P3. A dashboard without lineage breaks the whole
framework's promise.

**What it gets right:** lineage captured *at operation time*, not
reconstructed from a parsed DAG. dbt builds lineage from SQL parsing; that
breaks on dynamic SQL. We build from runtime ops — more accurate (if less
analyzable statically).

---

### Action Plan (Prioritized)

#### P0 — Before anyone runs this on real data

| # | Item | File(s) |
|---|---|---|
| 1 | Parameterize all SQL in pipeline history queries | `tracebi/pipeline/runner.py` |
| 2 | Remove plaintext credential storage; accept callables/env vars | `tracebi/connectors/snowflake_connector.py`, `sql_connector.py` |
| 3 | `threading.RLock` around Registry mutators and compound reads | `web/api/registry.py` |
| 4 | File lock or DB advisory lock per layer in PipelineRunner | `tracebi/pipeline/runner.py` |
| 5 | `@dataclass(frozen=True)` on `LineageNode`, immutable metadata mapping | `tracebi/model/dataset.py` |

#### P1 — Quick wins (≤1 day each, high impact)

- Add `git_sha` to `ReportManifest` (~15 lines). Falls back to `unknown` if not in a repo.
- `tracebi[all]` extras_require (one line in `pyproject.toml`).
- Lead the README with the 10-line Excel report path; medallion as optional section.
- SHA-256 of canonical Parquet bytes as fingerprint (~10 lines). Turns "fingerprint" into a real audit primitive.
- Extract `BaseRenderer` and document the renderer extension point.
- `tests/test_web_api.py` covering every router with FastAPI `TestClient` (~300 lines). Currently zero web-layer tests.
- Add `/dashboards/<name>/lineage` endpoint (already TODO'd).
- `StarSchema.query()` — raise on missing declared dimension attributes (currently silent skip; "silent wrong answer" bug class).

#### P2 — Medium-term (1–2 weeks each)

- Pushdown filters on `model.load(where=…, columns=…)` and `BaseConnector.load(…)`. SQL/BigQuery/Snowflake implement; CSV/Memory filter in memory.
- Per-request memoization (`RunContext` scoped per HTTP request or pipeline run). Reuse loads within a context; never across. Marketed "freshness" doesn't survive dashboard interactivity.
- Rename medallion → Landing/Manipulation/Final. Old names as aliases.
- Make `runner.run()` async-capable for web endpoint. Return `run_id`; expose `GET /api/runs/{id}` for polling.
- `tracebi new-request "open orders by region"` CLI scaffolding.
- Connector-aware `repr` that masks credentials.
- Cross-pipeline lineage stamping (Gap 2 above).

#### P3 — Big architectural moves

- **`DataSet` over a query graph, not a DataFrame.** Biggest leverage move. `DataSet` becomes a thin handle to a lazy graph; `.to_pandas()` is the only materialization point. Unlocks pushdown joins, DuckDB execution, Polars backend, lineage-aware query optimization. NOTES.md already flags the direction — start the abstraction work while it's cheap.
- **DuckDB as default execution engine** for in-process work; pandas as fallback. DuckDB does pushdown to Parquet/SQL natively, handles 10× more data than pandas, and the lineage layer doesn't care which engine ran the op.
- **Native Great Expectations integration.** Every `SilverLayer` step can carry an optional GE expectation suite; failures become lineage nodes. Don't build a DQ engine; integrate one.
- **Notebook hot-reload registry.** `from tracebi.web import dev_register; dev_register(report)` POSTs to a dev endpoint and report appears without restart. Killer DX for Persona A.

#### Killer features (where TraceBi could actually stand out)

- **Diffable reports.** `tracebi diff requests/q2_report.py @ main..feature-branch` runs both versions against the same data snapshot and produces a structural diff of the resulting reports (table values, chart shapes). Nothing in BI does this. Analytics equivalent of `git diff` for code review of *numbers*.
- **Replayable lineage.** Given a saved manifest JSON, regenerate the report against historical data using warehouse time-travel (Snowflake `AT(TIMESTAMP …)`, BigQuery snapshots, Iceberg). "Reproduce the Q1 board deck's revenue number with today's connectors" becomes a one-liner.
- **Email/Slack delivery as first-class.** `report.deliver(to="finance@…", channel="#weekly-reports")` with Excel attached and a link to the manifest. The "delivery" half of "code-first analytics + delivery" is currently missing.
- **`tracebi lint`** that statically checks `requests/*.py` for anti-patterns: unfiltered loads of large tables, missing report descriptions, charts without titles, deprecated APIs.

---

### Specific Code Anti-Patterns

1. `pipeline/runner.py` `_engine_()` method — rename to `@property`. Trailing underscore is uncomfortable Python.
2. `pipeline/runner.py` raw-string SQL — parameterize (also covered in P0).
3. `GoldLayer` (`etl/gold.py`) is a 30-line wrapper. Delete or make it earn its keep with incremental refresh / sink materialization.
4. `StarSchema.query()` silently skips dimension attributes that don't exist on the dim table — covered in P1.
5. Connectors store plaintext credentials as instance attributes — covered in P0; also affects `repr` and pickle.
6. `DataModel.resolve()` does merges in pandas memory even when both sides share a SQL connector. Add TODO for connector-aware planner.
7. `web/api/registry.py` mutated at import time — under uvicorn `--reload` can produce duplicate registrations. Guard with `is_registered` check, or `Registry.from_module(name)` factory that wipes state first.
8. `web/api/routers/*` endpoints are sync, calling blocking pandas. Single-worker uvicorn serializes all requests. Convert to `async def` + `await asyncio.to_thread(...)` or document multi-worker as required.
9. No timeout on `model.load()` in preview endpoint — a 100M-row table hangs the request indefinitely. Add row-limit + timeout.
10. `requests/_template.py` could enforce structure via a `@tracebi.request(name, schedule=None)` decorator that the auto-discovery scanner picks up. Unifies ad-hoc and scheduled flows.

---

### What's NOT Tested (test coverage gaps)

- **Web API routers**: zero tests for FastAPI endpoints.
- **Concurrency**: no concurrent-access tests for Registry, DataModel, PipelineRunner.
- **Credential handling**: Snowflake and BigQuery connectors never tested.
- **Large data**: no tests with DataFrames > 100K rows.
- **Renderer output bytes**: no tests against actual Excel/HTML/PDF output, only that they don't crash. Use `hypothesis` with constrained DataFrames.
- **Dash dashboard**: panels tested structurally; no integration tests with the server.
- **Edge cases**: no tests for division by zero in aggregations, NaN handling, special characters in column names.

---

### The Two Bets

1. **Commit to the "code-first analytics delivery + auditability" positioning** and trim everything that contradicts it (medallion framing, implication of ETL ownership). NOTES.md already arrived here — execute on it.
2. **Make the lineage truly bulletproof** (frozen nodes, cryptographic fingerprints, git SHA in manifests, cross-pipeline lineage) before adding more surface area. The promise of "defensible audit trail" is the only thing we can offer that dbt + Hex + Streamlit cannot, and it has to actually hold.

The pandas-memory ceiling is the eventual scaling wall, but doesn't have to be solved on day one — make the abstraction lazy-friendly now so it can be swapped later.


---

## 2026-06-05 — demo_app.py → Folder-Based App Structure

### Decision

`web/demo_app.py` is a monolithic file (~460 LOC) mixing data setup, reports,
dashboard, and pipeline. Goal: split it into a folder where each concern lives
in its own file and a single `registry.py` is the explicit wiring manifest.

### Chosen approach: Option A — Explicit registry

Each resource is defined in its own file as a plain function or object (no
decorators). One central `registry.py` imports them all and makes every
`registry.add_*()` / `registry.add_report()` call. Reading `registry.py`
top-to-bottom shows the complete app manifest.

Auto-discovery (`@registry.report` decorators spread across files) was
considered but rejected for the structured app layer — auto-discovery stays
for ad-hoc `requests/` scripts.

### Target layout

```
web/
  demo_app/                    ← replaces demo_app.py; TRACEBI_APP=web.demo_app
    __init__.py                ← from web.demo_app import registry  (triggers wiring)
    model.py                   ← DataModel, MemoryConnector, relationships
    pipeline.py                ← PipelineRunner + Landing/Manipulation/Final layers
    dashboard.py               ← Dashboard + DashboardServer
    reports/
      __init__.py              ← empty
      sales_summary.py         ← def sales_summary() -> Report
      revenue_trend.py         ← def revenue_trend() -> Report
      customer_overview.py     ← def customer_overview() -> Report
      medallion_revenue.py     ← def medallion_revenue() -> Report
    registry.py                ← imports all of the above; all registry.add_*() calls live here
```

### Key invariants to preserve

- `TRACEBI_APP=web.demo_app` must keep working (no change to the env var).
- `model` object from `model.py` is the shared default — `pipeline.py`,
  `dashboard.py`, and reports all import from `model.py`, never redefine it.
- `registry.py` is the only file that imports from `web.api.registry` —
  individual report files stay pure Python (importable without the web stack).
- `pipeline.py` creates `_runner` and runs the startup sequence; `registry.py`
  calls `registry.add_pipeline("sales", _runner)`.

### TODO (pick up next session)

- [ ] Create `web/demo_app/` folder with the layout above
- [ ] Migrate each report function to its own file under `reports/`
- [ ] Pull connector + DataModel into `model.py`
- [ ] Pull pipeline layers + PipelineRunner into `pipeline.py`
- [ ] Pull Dashboard + DashboardServer into `dashboard.py`
- [ ] Write `registry.py` that imports + wires everything
- [ ] Write `__init__.py` that imports registry (side-effect import)
- [ ] Delete `web/demo_app.py`
- [ ] Verify `TRACEBI_APP=web.demo_app` still works (resolves to `__init__.py`)
- [ ] Run full test suite (243 tests) — no regressions expected since web layer
      imports demo_app lazily via `TRACEBI_APP` string, not direct import
