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
| Phase 5 | ✅ Done | Web UI (FastAPI + Jinja2, Dash embedded, medallion-aware demo) |
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
  model/          Core abstractions (DataSet, DataModel, StarSchema)
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
StarSchema". The type boundary makes it impossible to accidentally skip a layer.

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

# Gold — aggregated via StarSchema
gold = GoldLayer(schema=schema)
revenue_by_region = gold.query(
    fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.region"],
    filters={"status": "shipped"},
)
```

### Star Schema

Dimension references use dot notation: `"dim_name.attribute"`.
Measures are a dict: `{"column": "agg_func"}`.
Supported agg funcs: `sum`, `count`, `mean`, `min`, `max`, `nunique`.

```python
schema = StarSchema("Sales", model=model)
schema.add_dimension("dim_customer", table_name="customers",
                     key_col="customer_id", attributes=["region", "segment"])
schema.add_fact("fact_orders", table_name="orders",
                measures=["revenue", "qty"],
                foreign_keys={"dim_customer": "customer_id"})
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

## Open Questions

- Should `requests/` files be standalone scripts or should they import a
  shared project-level `DataModel` defined once in a central file?
- Should the request template support both `.py` and `.ipynb` formats?
- For the CLI scaffolding idea — is `tracebi new-request` worth building now?
- What does the notebook → web UI registration workflow look like in practice?
  Should it be a live dev-mode endpoint, a module reload, or just "copy to config file"?
