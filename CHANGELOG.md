# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

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
