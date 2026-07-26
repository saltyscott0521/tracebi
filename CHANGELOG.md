# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### ⚠️ Breaking — queries now refuse to double-count

`DataModel.query()` **raises `ValueError` when a joined dimension's key is
not unique.** Previously the star-schema `LEFT JOIN` silently multiplied
fact rows and inflated every additive measure — returning a confident,
fully-lineaged, wrong number. In a two-order fixture whose true revenue was
$150, a single duplicated `customer_id` produced $250 with no warning.

**If this raises for you, your previous numbers were wrong.** Three ways
forward:

1. Deduplicate the dimension table (usually correct — the duplicate is an
   SCD-2 history row or an unfiltered snapshot).
2. Pick a key column that is genuinely unique.
3. Pass `query(..., allow_fanout=True)` if the multiplication is intended
   (legitimate for many-to-many). The opt-in is then recorded as a
   `warning` node in the lineage, so the audit trail shows it was
   deliberate.

The error names the dimension, the key, sample duplicate values, and the
exact row multiplication (e.g. `2 → 3 rows (x1.50)`).

This applies the principle already documented for column validation —
*"a typo must fail loudly, never return a silently wrong result"* — to join
cardinality.

### Added — a working path from install to running app

**`tracebi serve`** — the missing CLI step between an installed package and
a browsable UI. Run it from a project root; artifacts are discovered from
the working directory. Previously every documented route to the web app
started with `git clone` plus an editable install.

**`tracebi init` now scaffolds the layout the server actually reads** —
`models/`, `pipelines/`, `reports/`, `requests/`, `scheduled/`, plus
`data/` and `output/`. It used to create only `requests/`, so an init'd
project was structurally incompatible with the web app: there was no path
from `tracebi init` to a running UI at all. Discovery directories carry a
`.gitkeep` so the layout survives a clone.

**`TRACEBI_APP=""` now means "no app module".** Serving a user's project no
longer drags in the bundled demo app, which references demo data they do
not have and failed on import. An app module is only needed for connectors
and dashboards; the four artifact directories need none.

### Removed

- **`tracebi.yaml`.** It was scaffolded by `tracebi init` and checked by
  `tracebi validate`, but **parsed by no code** — there was no YAML reader
  and `pyyaml` was not a dependency. Its `connectors:` block invited users
  to configure a data source that would never be read. Connectors are
  declared in Python, in `models/`, where they are versioned and reviewable.

### Fixed

- **The Getting Started page could silently serve nothing.** The docs
  router hardcoded a repo-root-relative path (`parents[3]`), which does not
  exist in an installed layout, so `GET /api/docs` returned an empty list
  with no error. It now resolves at call time: `TRACEBI_DOCS_DIR`, then the
  working directory, then the package checkout.

### Added — named measures make the model a shared vocabulary

**`DataModel.add_measure()`** — define a calculation once, review it in a
pull request, version it in git, and reference it by name everywhere:

```python
model.add_measure("revenue", column="revenue", agg="sum",
                  description="Gross booked revenue")
model.add_measure("gross_margin", expr="revenue - cost", agg="sum")
model.add_measure("margin_pct", ratio=("gross_margin", "revenue"),
                  format="percent")

model.query(fact="fact_orders", measures=["revenue", "margin_pct"],
            dimensions=["dim_customer.region"])
```

Exactly three kinds — *simple*, *aggregate-of-row-expression*, and
*ratio-of-measures*. They cover the large majority of real usage, run on
both engines, and need **no expression parser**. Ratios divide the
aggregated totals, so `margin_pct` is `sum(margin)/sum(revenue)` rather than
the mean of per-row ratios, which is a different and usually wrong number.

Measures are **data, never callables** — a lambda cannot be serialized,
diffed, reviewed, or validated before it runs, and accepting one would
forfeit reproducibility at the root. Expressions are arithmetic over column
names only: function calls, quotes, and SQL fragments are rejected at
declaration, and every referenced column is checked against the fact table
before execution.

The ad-hoc `{column: agg}` form is unchanged and still works.

**`QuerySpec`** — a star-schema query as data, with `to_dict()`/`from_dict()`.
`DataModel.execute(spec)` is now the primitive and `query(...)` is sugar over
it. The resolved spec is stamped into the query's lineage, so the audit trail
records not merely *that* a query ran but exactly *which* one — with
`DataSet.fingerprint()`, that is end-to-end reproducibility.

**`info()` now describes the vocabulary** — declared measures with their
definitions, descriptions, and formats, plus the supported filter operators.
It answers what a number *means*, not just what it is called.

### Fixed — identical queries produced different fingerprints

Grouped query results had no deterministic row order. DuckDB returned groups
in hash-table order, which **varied between identical runs of the same
query**, while pandas' `groupby` sorts by default. Two consequences, both
undermining the audit story:

- `DataSet.fingerprint()` hashes row order, so re-running the same query
  against the same data produced a *different* fingerprint — manifest
  fingerprints were not reliably re-verifiable.
- The two engines returned different frames for the same query, so results
  depended on whether DuckDB happened to be installed.

Grouped results are now ordered by their dimension columns, making runs
reproducible and the engines byte-identical. The engine-parity test now
compares whole frames rather than just totals.

### Added — the semantic model can express real questions

**Filters now work on dimension attributes.** `query()` accepted filters only
on fact columns and raised `ValueError` for anything else, so *"revenue by
product, for customers in the West region"* — the most common analytic
gesture there is — was unexpressible. A dimension referenced only by a
filter is now joined for that purpose.

**Filters are no longer equality-only.** A closed operator set, implemented
in both engines and parameterised in the DuckDB path:
`eq, ne, in, not_in, gt, gte, lt, lte, between, is_null, not_null, contains`.
Deliberately not free-form SQL — that cannot be validated, cannot be
executed by the pandas fallback, and is an injection surface.

Three spellings, all backward compatible with the existing `{col: value}`:

```python
model.query(fact="fact_orders", measures={"revenue": "sum"},
            dimensions=["dim_product.category"],
            filters={
                "status": "shipped",                    # equality
                "region": ["NE", "SE"],                 # IN
                "revenue": {"gte": 1000},               # operator
                "dim_customer.tier": "enterprise",      # dimension attribute
            })
```

Every predicate is recorded as its own lineage node with `target`,
`operator`, `value`, whether it hit the fact or a dimension, and whether it
was pushed down to the connector. Errors name the problem precisely — asking
for a bare `region` when it lives on a dimension tells you to write
`dim_customer.region`.

The pandas engine and the DuckDB engine are covered by a parity test: a
query returning different numbers depending on what happens to be installed
would make the lineage meaningless.

### ⚠️ Breaking — the report layer now fails loudly

Renderers used to substitute a default for anything unrecognised, so a typo
produced a plausible-looking wrong report and exit code 0. Sections now
validate at construction, with did-you-mean suggestions:

- Unknown `ChartSection.chart_type` raised nothing and drew a bar chart.
- Unknown `TextSection.style` / `TableSection.style` silently fell back.
- A chart that failed to plot had its **exception text drawn into the PNG** —
  a finished-looking deliverable containing a picture of an error message,
  invisible to the caller and absent from the manifest. It now raises.

`TextSection(style="heading1"|"heading2")` **no longer discards `content`.**
It rendered `title or content`, so a section with both lost the body text
entirely — this was silently dropping real narrative in five of the seven
demo reports. Content now renders beneath the heading when it differs from
the title; the widespread `title="X", content="X"` workaround still renders
once.

### Fixed

- **Nested `RowSection` no longer breaks the audit trail.**
  `Report.data_sections()` descended only one level while rendering and
  `to_manifest_dict()` recursed fully, so a row inside a row rendered
  correctly but vanished from the lineage graph, the manifest, and every
  `/lineage` endpoint. Recursion is now unbounded.
- **`tracebi validate` actually validates.** It performed three filesystem
  `stat` calls and imported nothing. It now loads every model in `models/`
  and runs `DataModel.validate()` on each, so a non-unique dimension key is
  caught before it can inflate a number. Exits non-zero on problems.

### Added

- **Section `id`** — optional stable identifier carried into the manifest,
  so a section can be referenced across renders (diffing two versions of a
  report, or tooling that edits structurally rather than by line number).
- **Manifest completeness.** `TextSection` records `content_sha256` (length
  alone cannot prove prose was not altered); `ChartSection` records `color`,
  `xlabel`, `ylabel`, `figsize`, `style`, `palette`, and `show_values`, so a
  chart is re-renderable from its own receipt.
- `ChartSection` normalises `figsize` to a tuple and `y` to a list at
  construction, so a section round-trips through JSON losslessly.
- **`DataModel.validate()`** — checks every declared dimension's key for
  uniqueness and nulls, loading only the key column. Returns structured
  data (`{ok, model, dimensions, errors, warnings}`) rather than printing,
  so the CLI, the web API, and agent tooling can all consume it. Run it
  before querying.
- **Null dimension keys** now emit a non-blocking `warning` lineage node —
  those rows cannot be matched by the join.
- **`tracebi/_version.py`** — single source of truth for the version. The
  package, the CLI, and the FastAPI app all resolve through it; the API had
  drifted to a hard-coded `0.1.0` against the package's `0.5.2`.

### Fixed

- **`import tracebi` no longer requires networkx.** The only declared
  runtime dependency is pandas, but `__init__` eagerly imported
  `LineageDiagram`, whose module scope did `import networkx as nx` — so a
  clean `pip install tracebi` produced an unimportable package. networkx is
  now imported on demand with an `ImportError` naming the `[lineage]`
  extra, and `LineageDiagram.to_mermaid()` (pure string building) works on
  the base install.
- **CI now has a base-install job.** The test job installs `.[dev,web]`, so
  it structurally cannot catch a module-level import of an optional
  dependency — which is how the above regressed unnoticed. The new job
  installs the bare distribution, imports the public modules, runs the
  console script, and asserts no optional dependency leaked in.

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
