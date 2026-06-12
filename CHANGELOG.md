# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added
- **Standalone model registry** (`tracebi/model_registry.py`) — define a
  `DataModel` once in `models/<name>.py` (expose it as a module-level `model`
  variable) and import it from any notebook or script without the web server:
  `from tracebi.model_registry import get_model, list_models`.
  `auto_discover()` lazily loads files on first access; the global registry
  auto-discovers `models/` in cwd on first use.
- **Standalone pipeline registry** (`tracebi/pipeline_registry.py`) — same
  pattern for `PipelineRunner` instances. Each `pipelines/<name>.py` exposes a
  `runner` variable; `from tracebi.pipeline_registry import get_runner` loads
  it on demand. No web server required.
- **`tracebi new-model` / `tracebi list-models`** CLI commands with a
  `--models-dir` global flag. `new-model` scaffolds a fully-commented
  `models/<slug>.py` template including connector, table, relationship,
  dimension, and fact stubs.
- **`tracebi new-pipeline` / `tracebi list-pipelines`** CLI commands with a
  `--pipelines-dir` global flag. `new-pipeline` scaffolds a
  `pipelines/<slug>.py` template with Bronze → Silver layer stubs and an
  optional `@register.pipeline()` block for web registration.
- **Project-root auto-discovery in the web server** — `web/api/main.py` now
  scans `models/`, `pipelines/`, and `reports/` at startup and registers
  anything it finds into the web registry. Override paths via
  `TRACEBI_MODELS_DIR`, `TRACEBI_PIPELINES_DIR`, `TRACEBI_REPORTS_DIR`.
  `TRACEBI_REPORTS_DIR` is also added to the existing requests/scheduled
  discovery loop.
- **`tracebi.web.register.get_runner(name)`** — returns the named pipeline
  runner from the web registry when available, falling back to
  `pipeline_registry` when the web layer is not running.
- **`tracebi.web.register.get_model()` / `get_default_model()` fallback** —
  these now fall back to the standalone `model_registry` when the web layer
  is not imported, so `from tracebi.web import register;
  register.get_default_model()` works in pure-library usage too.
- **35 new tests** covering model and pipeline registry discovery, lazy
  loading, default selection, explicit registration, and all new CLI commands.

### Changed
- **Demo models moved out of the web layer** — `SalesModel` and `WealthModel`
  now live at the project root in `models/sales_model.py` and
  `models/wealth_model.py` (replacing `web/demo_app/model.py` and
  `web/demo_app/banking.py`). The demo app's reports, dashboard, pipeline, and
  registry now pull them in via `get_model(...)`, demonstrating the intended
  pattern: models are declared once outside the web UI and the web layer runs
  on top of them.
- **`DataModel.connectors()`** — new public accessor returning the connector
  objects registered on a model, so app code can surface a model's connectors
  without reaching into private attributes.
- **`LineageNode` is now frozen** — attributes cannot be reassigned and
  `connector`/`metadata` are read-only mappings. The audit chain can no
  longer be rewritten after the fact. `to_dict()` still returns plain
  mutable dicts for serialization.
- **`DataSet.fingerprint()` is now SHA-256** over a canonical
  serialization (column names + dtypes + CSV content) instead of MD5 over
  `pd.util.hash_pandas_object`. Deterministic across sessions and pandas
  versions, so manifest fingerprints can be re-verified long after render.
  Fingerprints recorded by older versions will not match.
- **`DataModel.query()` validates every column reference** — unknown
  measure columns, filter columns, and dimension attributes now raise
  `ValueError` with did-you-mean suggestions. Previously the pandas engine
  silently skipped filters on missing columns (returning unfiltered data)
  and undeclared dimension attributes could slip through.

### Added
- **DataSet cleaning verbs** — `dropna()`, `fillna()`, `deduplicate()`,
  `cast()`, and `limit()` as first-class transforms with structured lineage
  (row counts, fill counts, type maps). Previously these required
  `.transform(lambda ...)`, which records only a freeform description.
  `ds.help()` lists them under a new "Cleaning" section.
- **`docs/analyst-guide.md`** — a single linear walkthrough of the analyst
  development flow: scaffold → discover data → transform → parameters →
  report → live preview (`tracebi dev`) → publish to the web UI. Linked
  from the README's "Choose your path" table.
- **`docs/notebook-guide.md`** — using TraceBi from Jupyter: rich DataSet/
  DataModel previews, `HTMLRenderer().preview()` inline rendering, and how
  `.ipynb` files in `requests/` execute as request scripts (cell
  concatenation, magic/shell-escape stripping, run-clean-top-to-bottom).
- **`docs/web-customization.md`** — pointing the web server at your own
  app module (`TRACEBI_APP`), the registry seam, adding resources and API
  routes, React UI theming via the CSS token system, auth modes, and
  deployment, with an environment-variable reference table.
- **`request_params` in scaffolds** — `tracebi new-request` (both `.py`
  and `--notebook`) now includes a parameters section, so the CLI
  `--param` flag and the web UI's parameter form work out of the box on
  newly scaffolded requests.
- **`git_sha` in every `ReportManifest`** — the HEAD commit of the repo at
  render time (`"unknown"` outside a git checkout). Closes the gap between
  "I can prove what happened" and "I can prove what happened *and
  reproduce it*."
- **Per-layer run locks in `PipelineRunner`** — a layer can only execute
  once at a time per process; a second concurrent run raises
  `RuntimeError("Layer '…' is already running")` instead of corrupting
  run history.
- **Thread-safe web `Registry`** — all mutators and compound reads are
  guarded by an `RLock`, making registration safe under threaded servers
  and dev-mode reloads.
- **Second demo data model: `WealthModel`** — a wealth-management star
  schema (clients, branches, products, accounts dimensions; holdings and
  activities facts) registered alongside `SalesModel` to showcase serving
  multiple data models from one TraceBi app. Ships with two reports built
  on the new join/aggregate/assign verbs (`aum_by_branch`,
  `client_activity`), works in the Explore query builder across all four
  dimensions, and `seeds/seed_db.py` now persists the banking tables to
  SQLite as well.
- **First-class `DataSet.join()` / `.aggregate()` / `.assign()`** — the
  pandas verbs analysts reach for, recording *structured* lineage instead of
  freeform descriptions: join keys, join type, and left/right/after row
  counts; group-by columns and per-measure aggregation functions; columns
  added/replaced. Missing columns raise with did-you-mean suggestions.
  `.transform()` remains the escape hatch for everything else.
- **Lineage graphs now branch at joins** — join steps record which lineage
  nodes belong to the right side (`right_chain_len`), so the React Flow
  graph renders both parent chains flowing into the join node instead of a
  misleading straight line. Older lineage still renders linearly.
- **Background report runs in the web UI** — `POST /api/reports/{name}/runs`
  starts a run and returns a `run_id` (202); the UI polls, shows recent run
  history with durations, and toasts on completion instead of blocking.
- **Request parameters** — declare defaults in one line
  (`params = request_params(period="Q2 2024", top_n=10)`); override via
  `tracebi run x --param period=Q3` or the automatic parameter form on the
  web UI's Requests page. Defaults are discovered statically (AST), so the
  form renders without executing the script; overrides are coerced to the
  default's type and unknown names fail loudly.
- **Report layout & styling** — `MetricSection`/`Metric` KPI cards with
  green/red delta indicators, `RowSection` side-by-side layout (HTML;
  stacks in Excel), table `highlight_negatives`, per-column `color_scale`
  heat maps, `column_widths`, named number-format shortcuts (`currency`,
  `currency0`, `percent`, `comma`, `decimal`), `area` charts, and
  `show_values` data labels. Fluent shortcuts: `Report.metrics()` / `.row()`.
- **Notebook ergonomics** — rich `_repr_html_` on `DataSet` (preview table +
  lineage-chain badges), `DataModel` (structure at a glance), and `Report`
  (full inline preview); `.help()` cheat sheets on all three.
- **Live dev loop** — `tracebi dev <request>` watches a request script,
  re-runs it on save, and serves the report with browser auto-reload;
  script errors render as a traceback page that reloads once fixed.
- **Requests page** — browse the scripts in `requests/` from the web UI and
  run them fresh per click (no registration or server restart needed), with
  output, lineage, and manifest tabs. Backed by `GET/POST /api/requests…`.
- **Row counts in every lineage step** — transforms, sorts, selects,
  renames, and joins now record row counts (joins: left/right/after);
  lineage graph nodes display them for every operation.
- **Explore page** — visual star-schema query builder in the web UI: pick a
  fact, measures (with per-measure agg functions), dimension attributes, and
  filters; results render with a bar chart, CSV download, and the lineage
  graph of the exact query that ran. Backed by `POST /api/models/{name}/query`.
- **Pipeline Flow view** — the medallion chain rendered as a live DAG with
  status-colored layer nodes, animated dependency edges, and per-node run
  buttons.
- **Lineage inspector** — click any step in a lineage graph to see its full
  metadata (connector, source, join keys, engine, row counts, timestamp).
- Report downloads: `GET /api/reports/{name}/download?format=xlsx|html` plus
  download buttons in the UI.
- Full-table CSV export (`GET /api/models/{m}/tables/{t}/export.csv`) and
  richer previews (column dtypes, true total row count).
- Structured API errors: report/query failures return
  `{message, exception_type, traceback}`; the UI shows an expandable
  Python traceback.
- Public inspection surfaces: `PipelineRunner.layers()` / `run_history()` /
  `last_run()` / `execute_layer()` / `execution_order()`, `DataModel.info()`,
  `BaseConnector.describe()` (with credential-redacted URLs on
  `SQLConnector`), `Registry.dashboards()`, `HTMLRenderer.to_html()`.
- The demo model now ships `fact_orders` / `dim_customer` so Explore works
  out of the box.
- `.dockerignore` — `.env`, databases, `.git`, and local state no longer
  reach Docker image layers.
- `BigQueryConnector` and `SnowflakeConnector` are now importable from the
  top level (`from tracebi import BigQueryConnector`) like every other
  connector; their optional dependencies still load lazily.
- README "Coming from pandas?" section — how `DataSet` maps onto DataFrame
  habits (`.transform()` accepts any DataFrame→DataFrame function,
  `.to_pandas()` escape hatch, immutability); install instructions now show
  working from-clone / from-git commands (TraceBi is not on PyPI yet).

### Security
- Proxy-header auth warns loudly when `TRACEBI_AUTH_PROXY_TRUSTED_IPS` is
  unset (header spoofing risk); the server prints a banner at startup when
  no auth is configured at all.
- BigQuery push-down filters now use real query parameters instead of
  interpolated literals; Snowflake identifiers are validated before quoting.

### Fixed
- `tracebi run --help` / `tracebi dev --help` said they only accept `.py`
  scripts; both have always accepted `.ipynb` too and the help text now
  says so.
- Lint: removed two unused imports in `web/demo_app/reports/analyst_demo.py`
  that were failing `ruff check` in CI.
- Excel rendering crashed on reports containing pie charts (`PieChart` has
  no x/y axes).
- Renderer failures that change report output (totals, number formats) are
  now logged instead of silently swallowed.
- `pip install -e ".[dev]"` now installs the web dependencies the test
  suite needs; DuckDB tests skip instead of failing when duckdb is absent.

### Removed
- Legacy server-rendered Jinja UI (`web/api/routers/ui.py`,
  `web/templates/`) — unused since the React UI landed.

### Changed
- **Merged `StarSchema` into `DataModel`.** Facts, dimensions, and the
  analytic `query()` surface (DuckDB engine with pandas fallback) now live on
  `DataModel` itself. The standalone `StarSchema` class is gone.
- `GoldLayer` / `FinalLayer` now takes `model=` instead of `schema=`.
- `PipelineRunner.register_schema()` folded into `register_model()` — a single
  call persists relationships + facts + dimensions.

### Added
- `LICENSE` (MIT) and `CHANGELOG.md`.
- `analyst` and `all` convenience extras for one-line installs.
- Expanded PyPI metadata: authors, keywords, classifiers, project URLs.
- `tracebi --version` and `tracebi init <project>` scaffolding command.
- `tracebi run --refresh` flag for pipeline-style full-chain runs.
- `.env.example` plus optional `python-dotenv` support via the `analyst`/`all`
  extras.
- GitHub Actions CI: pytest on Python 3.10–3.12 with a ruff lint step.
- README badges (CI status, license, Python versions).

### Fixed
- README test count corrected to reflect the current suite size.
- Removed the lingering `postgresql://user:pass@host/db` example from
  `SQLConnector`'s docstring.

## [0.5.2] — 2026-05-23

Initial public surface. Five phases complete:

1. **Phase 1** — Connectors (CSV, SQL, BigQuery, Snowflake, Memory, DuckDB)
   with push-down filter/columns; `DataModel`; `DataSet` with immutable
   lineage chain.
2. **Phase 2** — Report engine (Excel + HTML renderers, lineage manifest per
   render).
3. **Phase 2.5** — Landing/Manipulation/Final layers (medallion-compatible),
   DuckDB-backed star-schema query, `LineageDiagram`.
4. **Phase 3** — Live Dash dashboard with associative filters.
5. **Phase 4** — Pipeline runner with APScheduler, DB persistence,
   cross-layer lineage.
6. **Phase 5** — Web UI (FastAPI + React, Dash embedded), folder-based
   auto-discovery, optional HTTP Basic auth, `tracebi` CLI, docker-compose
   deployment.
