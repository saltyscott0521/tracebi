# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added
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

### Security
- Proxy-header auth warns loudly when `TRACEBI_AUTH_PROXY_TRUSTED_IPS` is
  unset (header spoofing risk); the server prints a banner at startup when
  no auth is configured at all.
- BigQuery push-down filters now use real query parameters instead of
  interpolated literals; Snowflake identifiers are validated before quoting.

### Fixed
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
