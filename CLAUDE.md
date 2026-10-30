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

TraceBi-specific: the test files are phase-scoped (`test_phase1.py`, `test_phase2.py`, `test_phase25.py`, `test_phase4.py`, `test_phase5.py`). Don't reorganize tests across files. Don't add shared fixtures that create cross-phase dependencies. End-to-end journeys live in `tests/e2e/` (their own `conftest.py` gives each journey a fresh workspace and registries) — see the testing rule below.

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

**Prefer end-to-end tests.** A new feature first gets a step in the journey
that uses it (`tests/e2e/`: the analyst, reference-project, web, agent,
schedule, pipeline, author, folder-permissions, push, sign-in and publishing
journeys drive the real CLI, web app and MCP tools in-process, so coverage
sees them). Add a unit test only for what a journey can't pin precisely: query
semantics, number-formatting parity (the page engine: `test_calc_parity.py`), fingerprints and verify verdicts,
contracts, security, the honesty rules. Since the 2026-10-18 cull the unit
suite holds those six, plus a test where a module no journey reaches would
otherwise go uncovered.
Don't add look-alikes, tests of private fields, "it didn't raise" or
"the string appears" checks. Before adding any test, answer *what bug would
this catch?* — `design/test-suite-review.md`.

---

## Project Overview

**TraceBi** is a code-first, traceable BI framework for Python. Core ideas:

- **DataSet**: immutable wrapper around a pandas DataFrame + lineage chain. Every operation returns a new DataSet; nothing mutates in place.
- **DataModel**: the semantic layer: the star-schema contract (tables, relationships, facts, dimensions, named measures) with a query surface on the same class, and the words people and agents use for it: descriptions, synonyms, example questions. The model page's Semantic layer shows the same text an agent receives (`capabilities.describe_model`).
- **Medallion ETL**: Landing (raw ingest) → Manipulation (declarative cleaning, compiled to DuckDB SQL; `transform(func)` is the marked pandas escape hatch) → Final (DataModel star-schema aggregation). `BronzeLayer` / `SilverLayer` / `GoldLayer` remain as aliases.
- **PipelineRunner**: registers layers, schedules with APScheduler, persists run history to SQLite.
- **Report engine**: builds structured reports (text, tables, charts) and renders to Excel, HTML, or PDF.
- **Web layer** (`web/`): FastAPI REST API + React UI exposing all of the above via a singleton registry.

All six development phases are complete and tested.

---

## Workspace and Projects

The words people and agents read (2026-10-28; nothing moved on disk):

- **Workspace**: what one `tracebi.yaml` covers: one warehouse, its sources,
  transforms and models, the brand and the default house theme. One per
  company. (It was called the "project" before; identifiers such as
  `project_config.py`, `describe_project`, `TRACEBI_PROJECT_DIR` keep their names.)
- **Project**: one area's reports, a top-level library folder named for the
  model(s) it reads (`reports/saas_model/` is the SaaS project). Models stay
  shared at the workspace; a project keeps its permissions in `_folder.yaml`.
  Folders inside a project stay folders; `my-published/<name>` is "My
  published", never a project. The API, files and addresses still say folder
  (`/api/folders`, `?folder=`, `folder` fields); `?project=` redirects to
  `?folder=` (`movedTo`). `folders.js` `isProject` / `folderWord` decide the word.
- **Themes** are set on a report (`report.json` `"theme"`) or the workspace
  (`tracebi.yaml` `brand: {theme}`), never a project.
- The gateway's `describe_workspace` is `describe_project` under the new word.
  `docs/concepts/workspace-and-projects.md` is the page.

## The Three-Phase Workflow

This is the spine — the mental model to hold before anything else. TraceBi takes
data from messy to reportable in three workspace-root folders, each with its own
cadence, decoupled by **freeze points** (a materialized artifact handed from one
phase to the next):

1. **TRANSFORM** — `transforms/`. SQL by default, with pandas or polars as the
   escape hatch: pull the queries (a table of a declared connection is a header
   line `-- source: crm.issuer_ratings [fallback: inputs/x.csv]`, loaded through
   the connector before the first statement and read as `crm.issuer_ratings`;
   the certificate records each load under `sources`, and a SQL transform's certificate also records `lineage`, each sink column's bases as DuckDB's parse proves them; read in place through DuckDB's
   scanner for Postgres, MySQL and SQLite (`method: scanner`), else as Arrow (Snowflake,
   BigQuery, ADBC; `arrow`), else through the connector (`pandas`), the fingerprint the
   same whichever way; `-- sink: <connection> [only]` just above a `CREATE OR REPLACE
   TABLE` sends that table through the connector's `write` after the run, `only` dropping
   the warehouse copy), do the real analysis (window functions,
   prose parsing, cleaning, dedupe), then **sink** clean star-schema tables
   into the warehouse. A `transforms/<name>.sql` runs top to bottom in one
   fresh warehouse connection (`tracebi/transforms.py`; placeholders
   `{{ sink }}` and `{{ root }}` only; `-- source:` lines attach declared
   connections' tables in memory, never sunk; a created non-TEMP table is a sink
   table on every tier; a created view over warehouse tables, or over a `-- source:`
   table its connection's allowlist (`agents:`) admits, is a sink view on the file and
   remote tiers, recorded with its bases (certificate `views: [{name, definition_sha256,
   bases}]`), refused over any other source, a file or a TEMP object, and on the object
   tier); a `.py` / `.ipynb` ends with
   `DuckDBConnector("warehouse", database=sink_target(ROOT)).write(df, "table")`.
   `tracebi run-transform` reports `form: sql | python | notebook`. The
   framework does not constrain this phase. The contract is not
   *how* you clean, it is *what lands* — the named tables at the end of the
   script. Reference: `examples/portfolio_project/transforms/holdings_transform.sql`
   (the same tables in pandas: `holdings_transform_pandas.py`).
   A transform may carry a **sink contract** (`tracebi/contracts.py`):
   `<name>.contract.yaml` beside it, or a
   `with contract(...)` block, of closed, declarative checks (`rows`, `unique`,
   `not_null`, `foreign_key`, `values`, `reconcile`) run as read-only SQL
   against the tables just sunk. A failed check raises at sink time; success
   records `data/warehouse.contracts.json` with connector-load-path
   fingerprints. Report manifests join against it (`transform_contracts`:
   `satisfied` / `stale` / `no_contract` — stale never reads green; each
   entry also carries `writer`, the transform file, and `read`, what that run
   read as every trace words it: `crm.issuer_ratings — snapshot
   inputs/issuer_ratings.csv`, then the input files; `sources.run_reads`) and
   `tracebi verify --contracts` re-runs it. Locked language: **"the sink
   satisfied its contract"** — never "the transform was verified"; contract
   status never colors figure statuses.

   *— freeze: the warehouse (`tracebi.yaml`: a DuckDB file, Parquet on object storage, or a remote engine) —*

2. **MODEL** — `models/`. A declarative `DataModel` (star schema) over the
   warehouse: grain, keys, measures, in a few dozen lines a reviewer reads
   without opening the pandas above it. It reads the sink; it never sees the
   transform. A model query runs in the sink: one locked, read-only DuckDB
   connection per query attaches the warehouse and reads the model's tables
   as views (`tracebi/model/engine.py`; nothing loaded into pandas, no file,
   URL, extension, ATTACH or COPY reachable, limits and the statement timeout
   in `tracebi.yaml`). A model table on a declared SQL connection (`connectors: - {name:
   crm, connection: crm}`) is read live: the query connection attaches that connection's
   allowlisted tables READ_ONLY before the lock (through the scanner, else loaded), a table
   not on the allowlist is refused by name, and a warehouse sink view over an allowlisted
   source brings its connection in the same way (`tracebi/connectors/scan.py`).
   Reference: `examples/portfolio_project/models/portfolio_model.yaml`.

   *— freeze: the model (the semantic contract) —*

3. **REPORT** — `reports/`. A report package pointed at the model (`report.json`
   bindings plus an `app.jsx` dashboard or a `template.html` page) — KPI cards,
   charts, tables — where every figure is a live query. Because the model is
   materialized, the page re-renders in milliseconds with no pandas in the
   loop. Reference:
   `examples/portfolio_project/reports/portfolio_model/portfolio_dashboard/`;
   served in the web UI, in the library (Reports) under its model. `reports/` also holds template
   packages and
   `@register.report` factories — every report form lives in the one folder.

**Why the split:** the slow, unconstrained analysis (①) and the fast, iterated
reporting (③) never block each other, because the model (②) is a frozen contract
between them. Editing a report never re-runs the pandas.

**Honest scope of lineage / trust.** Tracing lineage *through* free-form phase-①
code (pandas, a notebook) is intentionally not done — the line is drawn at the
**sink**, where the numbers become a contract you can report against. A SQL
transform is the exception only as far as DuckDB's parser goes: `tracebi/lineage_sql.py`
reads `json_serialize_sql` of every statement while it runs, and the certificate
records, per sink column, the columns it is computed from (`lineage`, with `form:
sql`; bases `conn.table.col`, `inputs/<path>.col`, `<table>.col`), with `from: null`
and a reason wherever the tree cannot be followed — never inferred from names. It is
a record of what the SQL reads, not a verdict, and never colors a status. The trust machinery
(stamped queries with a resolved query + lineage + SHA-256 fingerprint;
validate-before-execute on specs; `tracebi verify`) applies **from the model
boundary onward** — phases ② and ③. `tracebi verify` re-runs a manifest's
recorded queries and compares fingerprints; it does not read a transform and
does not assert a number is correct. Never claim it verifies the phase-① analysis.

---

## Repository Layout

```
tracebi/               # Core Python package (~24,000 LOC)
  connectors/          # BaseConnector + CSV, SQL, BigQuery, Snowflake, Memory, DuckDB; scan.py (DuckDB's
                       #   scanners, Arrow, LiveSource: how a source is read in place and attached live)
  model/               # DataSet, DataModel (with star-schema query), engine.py (the
                       #   locked read-only query connection + statement timeout)
  etl/                 # LandingLayer / BronzeLayer, ManipulationLayer / SilverLayer, FinalLayer / GoldLayer;
                       #   _sql.py compiles the steps to DuckDB SQL
  reports/             # Report, Section types, ExcelRenderer, HTMLRenderer; the artifact
                       #   lane: template_package, figures, stack, compile_spec, derive,
                       #   slice (what a page carries to recompute), calc_plan (each binding's
                       #   query as a closed plan; execute_plan is the oracle; parity fixtures
                       #   in tests/fixtures/calc_parity/ from scripts/gen_calc_parity.py),
                       #   assets/ (tracebi.js + tracebi.css + tracebi-calc.js, the page
                       #   engine: pure JS, _calc_src/, CALC_NOTICE.md; tracebi.js "The chart engine":
                       #   ONE ECharts option builder (optionFor) + theme (chartTheme) for every chart,
                       #   template figures and the kit's <Chart>/<Spark>/<EChart> alike; the one ECharts
                       #   build echarts-kit.min.js (root.__tbECharts, inlined on any page with a chart;
                       #   tree-shaken to the builder's series, heatmap, sankey and the components the guides
                       #   name, _react_src/echarts-entry.js); d3.min.js only for tracebi.draw ("libs": ["d3"]);
                       #   the React lane's react.min.js (TanStack Redact, the one runtime, with the kit; no
                       #   compiler), recharts.min.js (Recharts 2), _react_src/, REACT_NOTICE.md; app.jsx is
                       #   compiled at build (app_lane.compile_app: sucrase.min.js + tailwind-compiler.min.js
                       #   run in mini-racer's V8, no Node; the page carries the JS and the Tailwind CSS;
                       #   manifest app_compile at build|page; without mini-racer the page inlines
                       #   sucrase.min.js + tailwind.min.js and compiles itself); the house chart look: --tb-chart-* tokens in
                       #   tracebi.css, read at draw time from the figure (chartTokens), SVG by default,
                       #   canvas per figure (data-tb-renderer) or report.json "charts"
                       #   (docs/reference/chart-style.md); house.py (the three house themes:
                       #   ledger, the default, is tracebi.css itself; nightdesk, signal; report.json
                       #   "theme" over tracebi.yaml brand.theme; stacked after tracebi.css, before the
                       #   brand; the six accent presets in themes/ are deprecated, still built);
                       #   brand.py (tracebi.yaml brand: → tokens after the house theme, before
                       #   reports/_theme.css, its dark lift against the theme's dark card); the
                       #   interaction grammar in tracebi.js: mark/row/range clicks, the selection
                       #   bar, cross-highlighting, tracebi.onSelection/result; the host bridge's `figure`
                       #   message: a clicked figure's id, which the app's trace follows); cover.py (a
                       #   build's cover: first screen at 1200×750 via the pdf extra's Chromium,
                       #   beside the HTML; manifest "cover"; never fingerprinted)
  pipeline/            # PipelineRunner + APScheduler integration; run_record (a recorded run: row + log)
  lineage/             # LineageDiagram (matplotlib / mermaid / HTML export)
  web/                 # register facade + auto-discovery for discovered modules (.py and .ipynb)
    api/
      main.py          # FastAPI app entry point — CORS, routers, auth
      auth.py          # Optional HTTP Basic / proxy-header middleware
      registry.py      # Back-compat re-export of tracebi.registry (the real seam)
      errors.py        # Structured error payload (message + traceback) for routers
      lineage_graph.py # LineageNode list → React Flow graph (shared by routers)
      routers/         # One file per domain (connectors, models, reports, pipelines, dev, tables, credentials)
    demo_app/          # Bundled demo app — SELF-CONTAINED (its own models/ subdir +
                       #   reports/). Opt-in via TRACEBI_APP=tracebi.web.demo_app; the
                       #   default is no app module.
    run.py             # Dev server (uvicorn wrapper) — python -m tracebi.web.run
    ui/dist/           # Built React bundle, written here by `cd web/ui && npm run build`
                       # (gitignored; Docker and the release workflow build it. A
                       # wheel built from a tree without it ships no UI — / says so.)
  cli.py               # tracebi init / new-model / new-transform / new-report / dev / report
                       #   / schedule / verify / migrate / serve / mcp / session (see `tracebi --help`)
  permissions.py       # the one check: may this person do this to this report path? (_folder.yaml)
  schedule.py          # report.json "schedule" block: build → verify → email → record
  code_requests.py     # Python pushed from a laptop: stored, reviewed (diff), approved by an admin, run once;
                       #   approval also runs, once, each transform no declarative pipeline runs (an agent's propose_transform lands here);
                       #   a request whose dry run failed is never approved; approval in a git work tree commits exactly its files
                       #   (author the requester, committer the approver, TraceBi-Request trailer, never pushed; else commit_note says why)
  dryrun.py            # an agent's proposed SQL transform run once against a throwaway copy: scratch DuckDB under .tracebi/dryrun/<id>/,
                       #   warehouse READ_ONLY, -- source: via the real loader, external access locked, ATTACH/LOAD/scanner fns refused,
                       #   -- sink: and COPY not run, statement timeout; tables (each new | changed | unchanged against the warehouse; first 20 rows only for new and changed), checks (contracts.observe), lineage, error
  _push.py             # `tracebi push` — packages/models → drafts, code → a code request
  transforms.py        # phase ① transforms: find one, its form (sql/python/notebook), run it + its .contract.yaml
  contracts.py         # sink contracts: closed checks + certificate + manifest join
  lineage_sql.py       # SQL column lineage from DuckDB's parse (Tracer; column_lineage): the certificate's lineage,
                       #   columns_from, the graph's edge_facts
  project_config.py    # tracebi.yaml reader (one reader, cached per path): engine limits + the warehouse block
  project_credentials.py # ${NAME} / ${NAME:-default}: one resolver (environment → .env → encrypted store .tracebi/secrets.yml.enc);
                       #   required/status for the Sources page and `tracebi secret`
  sources.py           # what feeds the warehouse (read from transform text) and what it holds: the app's Sources and Warehouse pages;
                       #   the row-count rule (sql_row_estimates) and is_framework_table
  warehouse.py         # the warehouse's three tiers (tracebi.yaml warehouse:): Warehouse, SinkTarget; project_config.sink_target()
  verify.py            # re-run recorded queries, compare fingerprints, classify drift
  mcp_server.py        # agent gateway over MCP — 32 tools + 3 prompts (author_report, answer_question, address_pins),
                       #   + 2 for the workbench panel (workbench_view, workbench_pin: visibility app, listed only to an MCP Apps client);
                       #   the source tools read only a connection's agents: allowlist; describe_project = graph.py less the map-only node fields (lane, chip, sub, open)
  graph.py             # the workspace as one graph ({summary, nodes, edges}; summary counts every node, gaps beside): every source, transform, warehouse
                       #   group/table, model, report, the board's four facts as edges, a passport per node, gaps;
                       #   GET /api/graph and the gateway's describe_project serve it (design/control-tower.md);
                       #   never re-runs a verdict (desk.cached_verdict); edge_facts: the parser-proven column lineage
                       #   edges (source table / file / table → table); downstream(registry, node): every report figure that
                       #   depends on a table, source table or measure, from the builds' manifests (GET /api/graph/downstream, and the gateway's downstream tool; read-only)
  exports.py           # the gateway's export_table: a thin call over warehouse.export_table (the one implementation)
  _gateway_log.py      # opt-in gateway call log (TRACEBI_MCP_LOG=1) + the `tracebi agent log` summary
  workbench.py         # the live authoring surface (tracebi dev / report status)
  workbench_app.py     # the workbench inside the agent: MCP Apps ui://tracebi/workbench (workbench_app.html, one file, no network);
                       #   preview_draft / workbench_state / build_report open it; it polls workbench_view, pins via workbench_pin
                       #   (a draft's pins: the report path's workbench; workbench_state / resolve_pin draft=true)
  _dev_server.py       # the classic stdlib preview server (loopback), `tracebi dev --classic`; `tracebi dev` itself opens the app in dev mode (`/reports/<name>` with Build on; `/data` with no name)
  _delivery.py         # `tracebi report send` — SMTP / Slack delivery of a built artifact
  _session_export.py   # session export — the committed lab-notebook record (HTML or md twin)
  _notebook.py         # notebook_to_source() — concatenates code cells for exec
  __init__.py          # Public API re-exports — check here before writing new code
web/
  ui/                  # React UI source — a Node workspace, NOT a Python package. Nothing
                       # importable lives under the top-level web/ any more: shipping a
                       # directory named `web` in the wheel collided with the unrelated
                       # `web.py` distribution, which owns that same path in site-packages.
                       # `npm run build` writes its output into tracebi/web/ui/dist.
    src/when.js        # stamp / ago / day / isoTitle: every date in the app; format.js: count / plural
    src/words.js       # the words for facts Data repeats: refreshWords / pipelineRefresh, movedWords, checksWords (the CONTRACT chip),
                       #   tierWords, reachWords, FORM_LABEL, statusWords (a graph node → {text, tone}: every Status column and pill)
                       #   — every page that says one calls these
    src/components/ResourceTable.jsx  # Data's one list shape (search ?q=, chips ?filter=, sort ?sort=, StatusPill, TypeChip, DropMenu row menu)
    src/components/ResourcePage.jsx   # Data's one page shape (title, type, status, actions top right, tabs at ?tab=; Details, ActivityList)
    src/components/AnswerChart.jsx    # the app's own bar chart (Ask's answer, Explore's result): SVG by React, d3 for scales
                       #   only, the report engine's bar; no chart library in the app (Recharts is only the app.jsx kit's)
    src/styles/global.css      # tokens: Geist / Geist Mono (--font-sans, --font-mono); --font-display is the sans,
                       #   tight (--weight-display 600, --tracking-display); --hue-1..6 folder hues, a label
                       #   never a state; --shadow / --shadow-lg only on the library's tiles, covers, pills and hero
    src/components/Shared.jsx  # the parts: Segmented, Chip (states) vs Badge (labels), Btn/BtnLink,
                       #   ExportCsv, Empty (title, body, command | action), CopyCommand, Time;
                       #   .tb-list (global.css) for lists of things
tests/                 # pytest suite (run `pytest tests/` for the current count), one file per area;
                       #   tests/e2e/ holds the end-to-end journeys (preferred for new coverage)
examples/
  portfolio_project/   # THE reference working workspace — a complete three-phase workspace
                       #   with the same shape `tracebi init` scaffolds; every model follows it:
    tracebi.yaml       #   the ONE warehouse (data/warehouse.duckdb, file tier) + engine limits
    inputs/            #   ⓪ raw pulls (holdings.csv + generate_raw.py, the demo source)
    connections/       #   ⓪ crm.yaml: a Postgres CRM (TRACEBI_CRM_URL) the transform reads by
                       #     `-- source:`; inputs/seed_crm.sql (compose loads it once into its `crm`
                       #     database; seed_crm.py elsewhere), issuer_ratings.csv is the snapshot;
                       #     bank.yaml / billing.yaml: SQLite files that ship (inputs/*.sqlite, written by
                       #     inputs/seed_bank.py / seed_billing.py), url ${VAR:-sqlite:///inputs/x.sqlite}
    transforms/        #   ① SQL → sink star tables, each with a .contract.yaml (holdings_, saas_,
                       #     wealth_transform.sql; holdings_transform_pandas.py is the pandas escape hatch;
                       #     affordability_transform.py, housing's, declares `with contract`)
    models/            #   ② the star-schema contracts (portfolio_model, saas_model, housing_model,
                       #     wealth_model .yaml), every one `type: warehouse`
    reports/           #   ③ organised BY MODEL — the folder is the model's name:
                       #     portfolio_model/ (portfolio_dashboard (app.jsx),
                       #     portfolio_desk (app.jsx), portfolio_book (editorial),
                       #     portfolio_overview, portfolio_concentration,
                       #     portfolio_showcase (app.jsx, the app lane's kitchen sink)),
                       #     saas_model/ (mrr_dashboard, cohort_brief), housing_model/
                       #     (affordability, the editorial showcase), wealth_model/ (aum_by_branch, aum_by_region)
    pipelines/         #   one per model (YAML): transform → build that model's reports
    run_workflow.py    #   drives ①→③; data/ inside the workspace is gitignored
  seeds/               # Medallion demo DB seeding + Supabase deploy companions
  phase*.py            # Phase 1–4 + 2.5 runnable demos — read these to understand data flow
MANIFESTO.md           # What TraceBi is, the vocabulary canon, and what it refuses to build
.env.example           # Documented env vars (auth, connector URLs, dev mode)
.github/workflows/     # CI — pytest matrix + ruff lint
Dockerfile             # Multi-stage build (React UI + Python app); installs DuckDB's postgres, mysql, sqlite and httpfs extensions
docker-compose.yml     # Serves examples/portfolio_project only (TRACEBI_APP unset); Postgres holds
                       #   the standing mock CRM (`crm`) and `tracebi_state` (docker/postgres-init.sql)
pyproject.toml         # Single source of truth for deps, build, and pytest config
CHANGELOG.md           # Keep-a-changelog format
LICENSE                # MIT
README.md              # The front door: what it is, install, the reference workspace, the app, deploy, agents
NOTES.md               # The decision journal (dated entries), build status, open questions
docs/                  # The handbook (Obsidian vault): start/, concepts/, guides/, reference/, agents/ (sop-onboarding:
                       #   describe_project first, then connection → transform → model → report; sop-authoring; sop-model-changes).
                       #   docs/toc.yaml is the one order (sections, pages, blurbs, moved: old → new
                       #   address); /api/docs and site/build_docs.py read it. build_docs.py generates
                       #   docs/index.md and site/docs (commit both; test_docs_site guards them).
design/                # Internal, never published or served: design notes (one decision each), strategy/
                       #   (intent), pitfalls.md, the ui-audit baselines. Decisions are dated in NOTES.md.
```

---

## Commands

```bash
# Install
pip install -e ".[dev]"                        # Everything the test suite needs (incl. web)

# Three-phase workflow
cd examples/portfolio_project && python run_workflow.py
                                                # phase ① builds data/warehouse.duckdb,
                                                #   phase ③ builds every model's reports (tracebi report build → output/)
python -m tracebi.web.run                       # serves it; auto-discovers models/ + reports/
                                                #   → the library at / (TRACEBI_REPORTS_DIR, default reports)

# Run (dev)
python -m tracebi.web.run                              # http://127.0.0.1:8000 (gzip; hashed /assets/* cached immutable)
TRACEBI_APP=mymodule.config python -m tracebi.web.run  # Custom app module
TRACEBI_DEV_MODE=1 python -m tracebi.web.run           # Enables POST /api/_dev/reload

# Run (prod)
# Multiple workers requires Postgres — see the note below.
uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
docker compose up --build                      # Or the docker-compose path

# Database
python examples/seeds/seed_db.py               # Create + seed data/seed.db (connector seed_db; runs go to the state store)

# Model and pipeline scaffolding
tracebi new-model "Sales Model"                # → models/sales_model.yaml (--from <conn> --tables a,b: drafted; type: warehouse from the warehouse)
tracebi new-transform "Holdings"               # → transforms/holdings.sql + .contract.yaml (--python: .py)
tracebi run-transform holdings                 # run a .sql, .py or .ipynb transform, top-to-bottom fresh; prints its form
tracebi list-models
tracebi new-pipeline "Sales ETL"               # → pipelines/sales_etl.yaml (--python: .py)
tracebi list-pipelines
tracebi run-pipeline sales_etl                 # run every layer, upstream first
tracebi run-pipeline sales_etl --layer orders_silver [--refresh]
tracebi run-pipeline sales_etl --status        # last run per layer, executes nothing

# Workspace settings
# tracebi.yaml at the workspace root (tracebi init writes a commented one):
#   engine: {memory_limit: 1GB, threads: min(4,CPUs), temp_directory: data/.duckdb-tmp, query_timeout_s: 30}

# Agent / tooling context
tracebi context                                # framework vocabulary as JSON
tracebi context --brief                        # the token-lean tier (≤45% of the payload; brief.omitted names the topics)
tracebi context --topic presentation           # one section alone (the page grammar); get_context(topic=) over MCP
tracebi session export [--format md]           # save the discovery notebook → explorations/
tracebi session clear                          # reset a session feed (refused while dev serves)
tracebi context --model sales_model            # plus that model's schema
tracebi spec schema                            # JSON Schema for a report spec
tracebi spec validate report.json              # check a spec without running it
tracebi spec render report.json                # build and render it
tracebi migrate spec reports/<name>.json       # compile a spec → reports/<name>/ (artifact package)
tracebi mcp                                    # agent gateway over MCP (stdio)
tracebi mcp --transport http --port 8765       # remote agent — needs TRACEBI_MCP_TOKEN (or --insecure)
tracebi agent log [--since 7d]                 # summarize the opt-in gateway call log (TRACEBI_MCP_LOG=1)
tracebi verify output/report.manifest.json     # re-run recorded queries; classify drift
tracebi verify output/report.manifest.json --contracts  # + re-run the sink contracts
tracebi verify output/report.manifest.json --local     # replay every calc plan by the page engine and by the server
tracebi schedule list                          # packages with a report.json "schedule" block
tracebi schedule run <name> [--no-send]        # build → verify → email → record, now
tracebi schedule serve                         # run every schedule (needs [pipeline])
tracebi serve                                  # browse the workspace
tracebi login --server <url>                   # sign in (browser, OAuth + PKCE); ~/.config/tracebi/credentials.json
tracebi push <paths> --server <url> --note why  # packages/models → your drafts; Python → a code request an admin approves
tracebi logout --server <url>                  # revoke and forget
tracebi update [--check] [--yes]               # newer release? what's new + the command for this install
tracebi secret set NAME [--from-stdin]          # a credential into the workspace store (encrypted); list | unset NAME
tracebi export <table> --to <connection|prefix>  # a warehouse table or view out to a connection, or as Parquet under a prefix
tracebi connect <name> --kind postgres --store secret   # write the secret to the store instead of .env
tracebi connect <name> --kind postgres --host H --database D --user U --password-stdin   # the fields form
tracebi connect <name> --test                   # test an existing connection

# Tests
python -m pytest tests/                        # Full suite (run it for the current count); tests/conftest.py puts this tree first
                                               #   on PYTHONPATH so subprocesses import it, not the editable install's checkout
pytest tests/test_phase1.py                    # Single phase
pytest --cov                                   # With coverage
TRACEBI_TEST_POSTGRES_URL=postgresql+psycopg://… pytest tests/e2e/test_reference_project.py
                                               # the CRM step on a given Postgres (else a throwaway one, else skip)
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
`tracebi/web/demo_app/models/wealth_model.py` uses `expense_ratio_bps`.

`ExcelRenderer` derives nothing — it applies only `section.number_formats`. So
a stored convention chosen to please the HTML renderer's derivation lands
unformatted in the spreadsheet: check both renderers before changing data.

A text column whose every value is `YYYY-MM` reads "Jan 2024" (derive.month_label /
derive_text_formats; tracebi.js monthLabel), tables, axes and range pickers alike.

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
| `admin` | analyst + run pipeline layers, which write to the warehouse, `/api/_dev/reload`, keeping a selection cut (it writes the published `report.json`), approving code requests (pushed Python runs with the server's secrets), and `export_table` over the gateway. |

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

4. **OIDC sign-in is a third role source, and it switches enforcement on by
   design.** Setting `TRACEBI_OIDC_ISSUER` turns on the app's own sign-in
   (`tracebi/web/api/sso.py`): the provider's groups, mapped by
   `TRACEBI_OIDC_ROLE_MAP` (else `TRACEBI_OIDC_DEFAULT_ROLE`, `viewer`), give
   the role, and `SessionAuthMiddleware` passes it to `_Authorizer.check(...,
   role=)`. That is an explicit operator choice, so it does not breach
   invariant 1's no-lockout rule. It is mutually exclusive with Basic and proxy
   auth (`install_if_configured` raises). Sessions are server-side
   (`tracebi_sessions`, SHA-256 of the id only; 12h idle / 7d absolute); a
   `Bearer tbat_...` TraceBi access token (what `tracebi login` stores) is also
   accepted on `/api/`, `/dashboards/`, `/r/`. The static shell stays public;
   navigations without a session redirect to `/login`, API calls get 401.

5. **Folder permissions are a fourth, narrowing layer.** A `_folder.yaml` in a
   library folder grants view / build / publish / manage to groups or names
   (`tracebi/permissions.py`, `docs/reference/folder-yaml.md`). It can only
   narrow what a role allows, never widen it; with no file anywhere, roles
   decide and no one is locked out. The `admin` role and any actor with no
   sign-in role (the CLI, the scheduler, the unauthenticated app) always hold
   Manage, so a typo cannot lock out the people who fix it; a malformed file
   grants everyone else nothing. Groups come from the OIDC groups claim (stored
   with the session and the access token), `TRACEBI_AUTH_GROUPS_HEADER` in
   proxy mode, and `TRACEBI_LOCAL_USERS=name:role@group+group:password`; they
   cross into the library on a ContextVar beside the actor
   (`audit.get_groups()`).

5. **Folder levels decide publish vs. request, and are re-checked at decision
   time.** A draft publish into a folder (`tracebi/drafts.py`) is direct with
   Publish there, a stored request (`drafts/_requests/`) with only Build, and a
   403 below that. Approving or rejecting needs Publish on the destination at
   the moment of the decision, so a Build-only requester cannot approve their
   own. `accepts: checkable` in `_folder.yaml` binds everyone, admins included.
   No `_folder.yaml` anywhere means no requests: roles decide, as before.

6. **`my-published/<sign-in name>` is a person's own folder** (`permissions.personal_folder`,
   `_personal_level`). Its owner holds Publish there; anyone else holds only what
   a `_folder.yaml` *inside it* grants (a library-wide file never reaches in).
   Only a person with both a sign-in name and a sign-in role has one; the shared
   token, the CLI, the scheduler and an app without sign-in act as no one, hold
   Manage everywhere and get `personal: null` from `/api/folders`. Not offered
   under `TRACEBI_LIBRARY_MOUNTS`. Permissions are displayed in the app, never
   edited there: they live in the file.

7. **Credential writes need an identified admin.** `PUT`/`DELETE /api/credentials/{name}`
   require `admin` (`_required_role`) AND a role that sign-in or a configured role
   source gave (`request.state.identified`). With no role source the no-lockout rule
   makes everyone admin, so these two writes are refused (403 naming
   `tracebi secret set NAME`); `CredentialWriteGuard` does it when no auth middleware
   is installed. The connection writes (`POST/PUT/DELETE /api/connections…`, `POST /api/inputs`;
   `auth._credential_write`) follow the same rule; their 403 names `tracebi connect`. This is the one place invariant 1 is narrowed, because an open
   demo would otherwise let anyone repoint the server's connections.

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

Set by `BasicAuthMiddleware` / `ProxyHeaderAuthMiddleware` / `SessionAuthMiddleware` around `call_next`,
and by `tracebi run-pipeline` from the OS user. Attribution is optional
throughout: an unattributed run records `None` and behaves exactly as before.

A ContextVar, **not a module global** — a global would let concurrent requests
in one process read each other's actor.

The state store (`tracebi_runs` and the other runner tables) is migrated by
Alembic (`tracebi/migrations`). `upgrade` runs at startup. The baseline matches
the schema today's code leaves after startup; later revisions add columns.
`_add_missing_run_columns` still reconciles `tracebi_runs`: `CREATE TABLE IF
NOT EXISTS` is a no-op against a table that already exists, and a baseline
stamped onto a database that predates a column does not add it. If you add a
column to `tracebi_runs`, add the Alembic revision and the entry in
`_RUNS_ADDED_COLUMNS` in the same change, or an upgrade of an old file breaks.
Warehouse layers stay idempotent; they are not migrated.

---

## Running More Than One Worker

`--workers 4`, or several container replicas, means several processes sharing
one database. `PipelineRunner`'s per-layer `threading.Lock` only guards its own
process, so the lock that actually matters is the database one:

| Backend | Concurrent layer execution |
|---|---|
| **Postgres** | Safe. A `pg_try_advisory_lock` per layer, and one per scheduled report, means a second process is refused instead of interleaving writes or sending the same email twice. |
| **SQLite** | **Single process only.** The cross-process lock is a no-op, so two workers will both execute the same layer and both send a scheduled email. |

SQLite is the development and demo fallback. Anything running more than one
process needs Postgres: `TRACEBI_STATE_URL` for the shared run store, and
`PipelineRunner(db_url=<postgres url>)` when a runner keeps its own database.
Background report runs and the last-build path live in that store. The HTML
stays a file; the row holds the path, so a second worker can poll a run the
first started and open its last build.

---

## Core Invariants — Never Violate These

**1. DataSet is immutable.**
Every transform method must return a new `DataSet`. Never mutate `.df` or `.lineage` in place. If you add a new method to `DataSet`, it returns a new instance with the new `LineageNode` appended.

**2. Every data operation produces a LineageNode.**
Lineage is non-optional. If your new transform skips the lineage step, the audit chain breaks silently. Look at existing methods in `tracebi/model/dataset.py` for the pattern. `LineageNode` is frozen — pass all fields (including `metadata`) at construction; you cannot edit a node afterwards, by design.

**3. Registry is populated by discovery, read at request time.**
`tracebi/registry.py` holds the singleton (`from tracebi.registry import registry`). It lives in the library, not the web layer — the FastAPI app is one consumer, but so are the CLI, request scripts, and notebooks. Register all connectors, models, and reports in your app module (e.g. `tracebi/web/demo_app/`) during import. Never mutate the registry inside a FastAPI route handler. The one writer after startup is **live discovery** (`tracebi/web/discovery.py` `rescan` / `start_watcher`): a background thread started in the app lifespan that registers report packages, specs, model files and pipeline files added while the server runs, and forgets deleted reports, every `TRACEBI_DISCOVERY_INTERVAL` seconds. Python report modules in `reports/` stay startup-only (re-importing code on a timer re-runs its side effects); one that registers a report with no package is flagged in `/api/discovery` and `tracebi validate`, because it cannot render.

`tracebi/web/api/registry.py` is a backward-compatible re-export of the same object. Routers bind the registry at import time. `tests/test_phase5.py::TestPipelineRunEndpoint::test_run_all_layers` isolates state by swapping the pipelines router's own `registry` binding, so it holds whatever the import order (the web journeys import the app first). It used to rebind `tracebi.web.api.registry.registry` before the router's first import, which silently became a no-op once anything imported the app earlier. If you repoint the routers, keep that swap pointed at the binding the router actually reads — and check the test fails when you remove the swap, because a suite that passes because isolation became a no-op looks exactly like a suite that passes.

**4. Optional dependencies must fail loudly.**
Each feature group (reports, pipeline, lineage, sql) has optional deps. Wrap their imports in `try/except ImportError` and raise a clear `ImportError` telling the user which extras key to install. Don't let a missing dep produce a confusing `AttributeError` later.

**5. One permission check.**
`tracebi.permissions.granted_level` decides what a person may do to a report path, and
`report_paths.open_report` is where every named-report read asks it: a person without View
gets the answer for a name that does not exist (hidden is never "forbidden"), one with View but
without the purpose's level gets `NotPermitted` (HTTP 403). Do not decide folder access in a
router, tool or command; read a report through `open_report`, filter lists with
`permissions.can("view", name)`, and guard a write to a path with `permissions.require`.
A new surface that lists reports, reads their builds (including by file path) or records
their runs must filter the same way, and the e2e journey
`tests/e2e/test_folder_permissions_journey.py` is where to prove it.

**6. TraceBi's own tables are never data.**
`tracebi.sources.is_framework_table` (`tracebi_*`, `alembic_version`): every listing of a source's, warehouse's or model's tables leaves them out and returns `hidden_framework_tables`; the model routes 404 them. `TRACEBI_STATE_URL` is its own database, never a connection; a runner writes its history to `tracebi.state.state_url()`, not to the data URL (the demo app's runners do; `examples/seeds/seed_db.py` seeds `data/seed.db`).

**7. pyproject.toml is the only place for deps and config.**
Do not add `setup.py`, `requirements.txt`, `tox.ini`, or `setup.cfg`. A *workspace's* own settings (not secrets) live in `tracebi.yaml` at its root, read only through `tracebi/project_config.py` (`docs/reference/tracebi-yaml.md`): `engine: {memory_limit, threads, temp_directory, query_timeout_s}`, `warehouse: {tier: file|object|remote, location, endpoint, region, key_id, secret, url_style}` and `brand: {theme, name, logo, accent, palette, font, mode}` (every report page's look, charts included; `theme` is the house theme, `ledger` | `nightdesk` | `signal`, `tracebi/reports/house.py`; the rest compiled by `tracebi/reports/brand.py`; a missing file, non-hex colour, accent below 3:1 on the card or file over 400 KB fails the build). Object-tier `key_id`/`secret` MUST be `${VAR}` (environment, then workspace `.env`, resolved when a connection is made, never copied into `os.environ`); the conventional names are `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` and `TRACEBI_S3_ENDPOINT`, and the framework reads no fixed name. The framework does not auto-load `.env` — `python-dotenv` is shipped via the `analyst`/`all` extras, but transform scripts must call `load_dotenv()` themselves. The one exception: a `${VAR}` in `connections/<name>.yaml` (and the warehouse block's `key_id`/`secret`) is looked up when the connection is used, in order: the environment, the workspace `.env`, the workspace credential store (`.tracebi/secrets.yml.enc`: Fernet ciphertext of a `NAME: value` YAML document; `tracebi secret set NAME`, `tracebi secret edit` or the Sources page), then a `${NAME:-default}` default, which must pass the same no-credential check as a literal — only that name, never copied into `os.environ` (`tracebi/project_credentials.py`). A relative `sqlite:///` url in a connection resolves against the workspace root, and a literal one stays inside the workspace. Framework-read env vars: `TRACEBI_SECRET_KEY` (the Fernet key for the workspace credential store; unset, `.tracebi/secret.key` is generated 0600; several workers must share one), `TRACEBI_STATE_URL` (the shared run store; default `sqlite:///data/tracebi.db`), `TRACEBI_APP`, `TRACEBI_MODELS_DIR`, `TRACEBI_PIPELINES_DIR`, `TRACEBI_CONNECTIONS_DIR` (declarative sources, default `connections`), `TRACEBI_TRANSFORMS_DIR` (phase ① scaffolds, default `transforms`), `TRACEBI_DRAFTS_DIR` (remote drafts, default `drafts`), `TRACEBI_REPORTS_DIR` (phase ③ — specs, packages, and factories, default `reports`; ignored when `TRACEBI_LIBRARY_MOUNTS` is set), `TRACEBI_LIBRARY_MOUNTS` (`label:/abs/path,…` — several library roots; identity is `label/relative_path`), `TRACEBI_SCHEDULED_DIR` (deprecated: still imported if the folder exists, never ran reports; use a `report.json` `"schedule"` block), `TRACEBI_SCHEDULES_IN_SERVER` (`1` runs report schedules inside the web server; off by default; Postgres takes one advisory lock per report, SQLite is one process only), `TRACEBI_DISCOVERY_INTERVAL` (seconds between live-discovery scans of `reports/`, `models/` and `pipelines/`; default 5; `0` turns it off), `TRACEBI_COVERS` (`0` takes no cover at build — the gallery draws one; the test suite sets it), `TRACEBI_DEV_MODE`, `TRACEBI_DOCS_DIR`, `TRACEBI_WORKBENCH_DIR`, `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` / `TRACEBI_AUTH_PROXY_HEADER` / `TRACEBI_AUTH_PROXY_TRUSTED_IPS` / `TRACEBI_AUTH_GROUPS_HEADER` (proxy mode: the person's groups, for `_folder.yaml`) / `TRACEBI_AUTH_REALM`, `TRACEBI_MCP_TOKEN` (bearer auth for `tracebi mcp --transport http`; set on the web app, it also serves the gateway at `/mcp`) / `TRACEBI_MCP_ACTOR` (audit attribution for gateway work, default `agent`) / `TRACEBI_OIDC_ISSUER` (turns on per-person OAuth sign-in for `/mcp`) / `TRACEBI_OIDC_CLIENT_ID` / `TRACEBI_OIDC_CLIENT_SECRET` / `TRACEBI_OIDC_SCOPES` / `TRACEBI_OIDC_GROUPS_CLAIM` / `TRACEBI_OIDC_ROLE_MAP` (`group:role,…`) / `TRACEBI_OIDC_DEFAULT_ROLE` (default `viewer`) / `TRACEBI_DEMO_LOGIN` (a role: a one-click demo user on the gateway's own sign-in page; no identity provider, `/mcp` only) / `TRACEBI_LOCAL_USERS` (`name:role:password,…`, the same built-in sign-in) / `TRACEBI_OAUTH_SECRET` (signs it in flight; required with either) / `TRACEBI_PUBLIC_URL` / `TRACEBI_PUBLIC_MCP_URL` (the public MCP address, default `<TRACEBI_PUBLIC_URL origin>/mcp`) / `TRACEBI_OAUTH_REDIRECTS` (extra exact connector redirect URIs) / `TRACEBI_MCP_LOG` (`1` appends one line per gateway tool call to `.tracebi/gateway_log.jsonl` — argument names only, never values; off by default; read it with `tracebi agent log`), `TRACEBI_LIBRARY_SYNC_SECRET` (turns on `POST /api/library/sync`, the git webhook that pulls library checkouts), `TRACEBI_UPDATE_CHECK` (`0` turns off the release check behind `tracebi update` and the web app's "available" badge; on by default, one cached GET to GitHub's releases API, nothing sent) / `TRACEBI_UPDATE_URL` (a mirror answering like `releases/latest`) / `TRACEBI_IN_DOCKER` (set in the image: the update command pulls a new image instead of upgrading in place).

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

**The discoverability definition of done.** A feature agents should use is
not done when it works — it is done when an agent WOULD use it. Every
authoring-surface feature must land with all three, in the same change:
(1) the generated vocabulary documents it (`tracebi/capabilities.py` — the
`tracebi context` / MCP `get_context` payload); (2) the scaffold or the
showcase demonstrates it (`_INIT_SAMPLE_APP_JSX` in `cli.py`, or
`examples/portfolio_project/reports/portfolio_model/portfolio_showcase/`); (3) both agent
guides name it (`AGENTS.md` and `_INIT_AGENTS_MD` in `cli.py`).
`tests/test_agent_guides.py` enforces (1)↔(3) mechanically — every
`data-tb-*` attribute in the vocabulary must be named in both guides, the
locked honesty lines must survive verbatim, and the scaffold must carry the
interactive grammar — so drift fails CI instead of waiting for the next
field test to find it (the round-2 lesson: a feature the guides don't teach
effectively does not exist).

### New transform (phase ①)
1. `tracebi new-transform "Name"` writes `transforms/<name>.sql` and
   `<name>.contract.yaml`, the sink in the idiom of the workspace's tier. The
   SQL is DuckDB statements run top to bottom in ONE fresh warehouse
   connection by `tracebi run-transform <name>` (`docs/reference/transform-sql.md`):
   exactly two placeholders, `{{ sink }}` and `{{ root }}`; relative reads
   resolve against the workspace root; `TEMP` tables and macros are scratch.
   `-- %%` cells fold in editors and mean nothing to the run. When the work
   outgrows SQL, `--python` scaffolds the escape hatch: notebook-shaped pandas
   (`# %%` percent cells, opened AS a notebook by VS Code, Cursor, PyCharm,
   Jupyter via jupytext); literal `.ipynb` works too, run top-to-bottom in a
   fresh namespace. `x.sql` beside `x.py` is refused. Models stay declarative.
2. End by sinking clean star-schema tables: `CREATE OR REPLACE TABLE x AS …`
   lands in the warehouse on every tier (object tier: `<location>/x.parquet`,
   or write `COPY (…) TO '{{ sink }}/x.parquet' (FORMAT PARQUET)` yourself);
   in Python, `DuckDBConnector("warehouse", database=sink_target(ROOT)).write(df, "table")`.
   The contract is the named tables that land, not how you produced them.
   A derivation may stay a definition: `CREATE OR REPLACE VIEW x AS …` over the
   warehouse's own tables and views is a sink view (file and remote tiers), read
   by a model as a table; one over a `-- source:` table, a file, a URL or a TEMP
   object fails the run and is dropped. A view may read only what is frozen:
   materialize the facts you aggregate, view the derivations.
3. Declare the sink contract in `<name>.contract.yaml` (`name`, `note`,
   `checks: - rows: fact_x …`), or in Python a `with contract(name,
   warehouse=sink_target(ROOT)) as c:` block — one vocabulary, one parser
   (`contracts.declare`), closed, no callables. It runs after the transform;
   a failure raises; success records the certificate the report manifests
   join against.
4. Model this on `examples/portfolio_project/transforms/holdings_transform.sql`
   (+ `.contract.yaml`). Keep it idempotent (a rerun replaces the warehouse
   tables). Nothing downstream imports this file.

### New connector
Most sources need no code. **In the app:** a signed-in admin's **Add a connection** on
Sources writes `connections/<name>.yaml` (a secret to the store) and ticks the tables agents
may read (`agents: {tables: [a, b] | "*"}`; absent = none;
`tracebi.connections.agent_may_read(connection, table)` is the one check). **From the CLI:**
`tracebi connect <name> --kind … [--agents a,b|all]`, `tracebi connect --list`. Types: postgres,
mysql, sql, duckdb, snowflake, bigquery, csv, upload (a CSV/Parquet under inputs/).
**Declarative, by hand:** `tracebi connect <name> --kind
postgres|snowflake|bigquery|duckdb` writes `connections/<name>.yaml`
(`docs/reference/connections-yaml.md`): a type and its fields, any value may be
`${ENV_VAR}` (the whole value), and a password or credential-bearing URL MUST
be. Variables resolve when the connection is used (lazily), from the environment
then the workspace `.env`; an unset one is an error naming it.
A postgres or mysql file says its connection as one `url` or as its fields, never
both: `host`, `database` (required), `port`, `user`, `password:
${TRACEBI_<CONNECTION>_PASSWORD}` (the name the app's Save password and `tracebi
connect --host … --password-stdin` write; Save password off / `--password-var NAME`
names a variable the server sets instead), `ssl`, `options`, `connect_timeout`. The
loader builds the URL when the connection is used; `tracebi.connections.build_url(type,
fields)` / `parse_url(type, url)` are that mapping (a `${NAME}` stays whole). The app's
form shows both as Fields | URL tabs; a URL sent with a password is written as the
fields. Snowflake takes `authenticator: password|externalbrowser|key_pair` (+
`private_key_path`); BigQuery `credentials` (a path) or `credentials_json`. A model's connector
says `connection: <name>`; discovery registers the file so the Sources list
(`/data/sources`) shows it (credentials are never resolved to describe it);
`label:` (optional) names a connection for people.
`--python` / `tracebi migrate connection models/_connections/x.py` cover the
legacy module. A new connector *type* is code:
1. Subclass `tracebi.connectors.BaseConnector`
2. Implement `load(name) -> DataSet` — must append a `LineageNode`
3. Register: `registry.add_connector(instance)` in your app module

### New model definition (workspace-scope, no web server required)
1. `tracebi new-model "My Model"` — creates `models/my_model.yaml`, a commented starter (`--python` writes `models/my_model.py` instead). A Python model converts with `tracebi migrate model models/x.py [--write]`, which writes the YAML beside it and leaves the `.py` (it wins until you delete it).
2. Edit the file: wire connectors (`type: warehouse` reads the workspace's warehouse on any tier), tables, relationships, facts, dimensions, measures. The variable-must-be-named-`model` rule applies to the Python form only. A model is one file: `.yaml`/`.yml`/`.json` share one schema and validator (`tracebi/model/model_spec.py`), and two declarative forms of one name are both refused.
3. Import anywhere: `from tracebi.model_registry import get_model; model = get_model("my_model")`
4. The web server auto-discovers `models/` at startup (`TRACEBI_MODELS_DIR` to override).

### New pipeline definition (workspace-scope, no web server required)
1. `tracebi new-pipeline "My ETL"` — creates `pipelines/my_etl.yaml`
   (`docs/reference/pipeline-yaml.md`): `transform` (the Python script it runs),
   `models`, `reports` (`all` or names), `schedule`. It compiles to the
   `model_pipeline` runner, so `tracebi run-pipeline my_etl` and **Refresh
   data** in the app run the transform, then rebuild the reports. A pipeline is
   one file: a `.py` beside the `.yaml` wins. `tracebi migrate pipeline
   pipelines/x.py [--write]` converts a `model_pipeline` runner.
2. `--python` writes `pipelines/my_etl.py` for medallion layers or custom steps: wire connectors, layers, and `runner.register(...)`. The variable **must** be named `runner`.
3. Import anywhere: `from tracebi.pipeline_registry import get_runner; runner = get_runner("my_etl")`
4. The web server auto-discovers `pipelines/` at startup (`TRACEBI_PIPELINES_DIR` to override).

### New report (ad hoc)
The ad-hoc lane is the artifact: `tracebi new-report "My Report"` then
`tracebi dev my_report` — explore inside `data-tb-stage="exploration"` blocks
that die at build. (The old `requests/` script lane was removed in 0.8. A JSON
spec migrates with `tracebi migrate spec reports/<name>.json` — the compiled
package shadows the same-named spec at discovery.)

### New report (web-exposed)
Put a report **package** in `reports/` — a `<name>/` directory (`report.json` +
`template.html`, plus optional `style.css` / `script.js`), or a `<name>.json`
spec that is compiled into exactly that at discovery. Either is auto-discovered
at startup and served in the app, in the library under its model.

**There is one renderer.** A registered report with no package is refused
(HTTP 422 naming the fix), never served through a second path. The old bare
`@register.report` factory rendered a page with no `tracebi.js` runtime, no
trace drawer, no figure claims and a schema-1 manifest — report-shaped, but
carrying materially less of one. `registry.add_report` is still the underlying
registration seam (discovery uses it for packages and specs alike); what was
removed is the fallback that rendered a factory with no package.

### New dashboard (phase ③)
1. `tracebi new-dashboard "Name" [--model <m>]` writes `reports/<m>/<name>/` (the model's
   project folder; `--model`, or a `"<m>/Name"` title, is required with more than one
   model, else it refuses naming them): `report.json`
   bindings pointed at a model (grain + measures it declares) and an `app.jsx`.
   Model this on the reference workspace's `reports/portfolio_model/portfolio_dashboard/`
   (one screen) or `portfolio_desk/` (a sidebar of views).
2. Every figure is a live query against the model — `<Kpi>`, `<Chart>`,
   `<Table>` with literal binding and cell, so the trace names each one.
   `<EChart>` (Apache ECharts) is the chart, and `<Chart>` / `<Spark>` are its
   presets (same props, same figure ids): with literal `binding`, `x`, `y` it
   plots the binding's columns as they are, is a claim, and is drawn by
   tracebi.js's chart engine; an option-only `<EChart>` draws page-computed numbers and carries
   `data-tb-computed`. Every chart filters live (`useBinding` returns rows re-run
   under the selection; `useSelection()`) and a click writes the selection
   (`tracebi.pick`). Recharts 2 also works; every page runs on Redact.
3. Build it: `tracebi report build <name>` (a JSON `ReportSpec` still works and
   compiles with `tracebi migrate spec`; no shipped report uses one). The
   folder is auto-discovered and served in the app, in the library under its model.

### New report as a template package (freeform HTML)
When the spec's section vocabulary is too rigid — a bespoke layout, your own
CSS — scaffold a package instead: `tracebi new-report "My Report"` creates
`reports/my_report/` (`report.json` data bindings + `template.html` / `style.css`
/ `script.js`). `tracebi report build my_report` renders ONE self-contained HTML
(CSS, JS, and fingerprinted data inlined; strict CSP; ECharts vendored, no CDN)
plus a manifest. `report.py` beside `report.json` is the escape hatch for pandas
the model can't express — its output stamps `verifiable: false` and never reads
green under `verify`. Charts render with Apache ECharts in the browser (SVG by
default; `tracebi.js` "The chart engine", the same option builder the kit's
charts use): legend toggles, tooltips, arrow-key reading, animated updates, and
a click on a mark writes the page's selection. It draws only the rows' own
values and colours series from the unfiltered rows. `tracebi.configureChart(id,
patch)` deep-merges a raw ECharts option into any chart (restyle, never
re-source). `"libs": ["echarts"]` is gone (refused at load); `"libs": ["d3"]`
only for an author's `tracebi.draw` figures. The server-side SVG path is kept
only for the (unshipped) PDF renderer.

**A built page is live.** The locked rule: a figure's number is only ever a
query result. The build embeds a slice per fact (`tracebi-slice-<fact>`,
Snappy Parquet) and every binding's calc plan (`tracebi-calc-plans`);
`report.json` `"embed": "required" | "model" | "none"` (default `required`) and
`"embed_budget_mb"` (default 25) say how much. Every `data-tb-filter` (kit
`<Filter>`, `multiple` for several values) writes one selection state, kept in
the URL hash (`#sel=`), and `tracebi-calc.js` re-runs every plan under it: values,
tables, charts, sparks and `tracebi.draw` figures recompute, the chip reads
Local, a figure its field cannot reach carries `data-tb-unfiltered-by`, one the
engine cannot run (SQL binding, `report.py`) `data-tb-fixed`. `tracebi.setSelection`
sets it from code. Every gesture writes that one state too: a click on a bar,
slice, point or legend entry (no control needed; shift adds), a row of a
`data-tb-select-rows` table, a `data-tb-range`; a chart keeps its own field's
other values and dims them (`data-tb-highlight="off"` to narrow instead); the
selection bar (`data-tb-selection`, kit `<SelectionBar/>`) shows it, prints as
one line, and Escape clears it. A multiple filter on a live page is a button naming what is picked that opens a checkbox
panel (tracebi.js paintMulti; the select stays the state, hidden); Escape in the panel
closes it, never clears. A row-select table keeps the other values only
of the fields its own row clicks wrote (`data-tb-select-rows="dim.attr"` names
them); any other writer of the field takes it back, and the hash carries no
owner. `tests/e2e/test_live_cascade.py` walks every
shipped live report through every gesture against `execute_plan`.
`"embed": "none"` builds the old page: filters subset stamped
rows and value figures never react. There is no worker, no wasm and no server
round trip; Python (`calc_plan.execute_plan` over `DataModel.execute`) is the
source of truth, `tests/test_calc_parity.py` holds the port to it, and a page
result is compared to the server's cell by cell within 1e-9 (`calc_plan.rows_match`),
never by a rounded hash. Fingerprint algo 3 (`frame_fingerprint(df, algo=3)`:
9 significant digits, no dtypes, rows total-ordered) is the cross-engine canonical
form; server stamps stay algo 2 and `verify` re-hashes under the recorded algo.
Design: `design/duckdb-first.md`; plan: `design/live-reports-plan.md`.

### New medallion layer
```python
# ManipulationLayer is the canonical name; SilverLayer remains as an alias.
layer = ManipulationLayer(source=bronze_connector, source_table="orders_bronze",
                          sink=db, sink_table="orders_silver").deduplicate(subset=["order_id"])
runner.register(layer, name="orders_silver", schedule="0 * * * *",
                depends_on="orders_bronze")
```
Steps (`cast`, `drop_nulls`, `deduplicate`, `rename`, `filter(where=)`) compile to
one SELECT each (`tracebi/etl/_sql.py`) and run in DuckDB. With the source and the
sink in one DuckDB database the layer runs inside it (`CREATE OR REPLACE TABLE … AS
SELECT`, no frame loaded) and `execute()` returns a `SinkTable`. Each node's metadata
carries `engine: duckdb` and its SQL. `deduplicate` keeps the first row in source
order, and the result keeps that order, because order is part of the fingerprint.
`cast` takes pandas dtype names from `CAST_TYPES` and refuses others by name.
`transform(func)` is the escape hatch: marked `escape_hatch: python` in lineage and
in the run row.

### New FastAPI route
Add a file under `tracebi/web/api/routers/`, include it in `tracebi/web/api/main.py`, and read resources only from the registry — never import app-specific objects directly.

---

## API Routes

```
GET  /api/health
GET  /api/me                                         → {actor, role, sign_in: oidc|basic|proxy|none}
GET  /login?next=  /login/callback   POST /logout    → app sign-in through the OIDC provider (TRACEBI_OIDC_ISSUER; tracebi/web/api/sso.py)
GET  /api/status                                     → version plus what's wrong with this install
GET  /api/schema                                     → machine-readable vocabulary (generated)
GET  /api/discovery                                  → per-file registered/skipped/failed + reason
GET  /api/spec/schema                                → JSON Schema for a report spec
POST /api/spec/validate                              → check a spec without executing it
POST /api/spec/render                                → build a spec and render HTML + manifest
GET  /api/connectors
GET  /api/connectors/{name}
GET  /api/connectors[/{name}]                        → each carries read_by {transforms: [{name, tables}], layers: [{pipeline, layer}], models}, warehouse (bool; Sources lists the rest), label, dialect (SQL)
GET  /api/connectors/{name}/tables                   → {connected, tables: [{name, columns, rows, rows_exact, agents}], agent_tables, hidden_framework_tables} or {connected: false, reason, variable?} (200); rows exact for DuckDB/memory, the Postgres catalog estimate, else null — never count(*) per table
GET  /api/inputs                                     → the inputs/ folder: files with size, modified, read_by (transforms), named_by_scripts (a script in inputs/ that names it: a seed's raw material, never a gap), table (the table API reads it)
GET  /api/warehouse                                  → every warehouse: tier, where, size, engine_version, tables with kind (table|view; a view with bases), rows, columns, written_by, read_by, contract, hidden_framework_tables; writers [{transform, file, note, checks, tables, read}]: what each transform's run read (each with method scanner|arrow|pandas and snapshot), said once per transform; the transform page reads it with /api/transforms and /api/transforms/{name}/source
GET  /api/graph                                      → {summary, nodes, edges, edge_facts}: the workspace as one graph (tracebi/graph.py), the same dict as the gateway's describe_project; reports the caller cannot view left out with their edges
GET  /api/graph/downstream?node=<id>                → {node, kind, measure, reads, summary: {figures, reports}, reports: [{id, name, label, open, built_at, trust, figures: [{id, kind, binding, label, text, open}]}], not_built}: every report figure that depends on a table:, source_table: or measure:<model>:<measure> node, the number its built page prints (the desk's values) and its report's verdict; read from the last builds' manifests (tracebi/graph.py downstream); starts nothing; 404 for any other node
GET  /api/transforms                                 → every file in transforms/: name, form (sql|python|notebook), file, contract_file, note, pipelines, models, tables (per the certificate), written_at, twin_of (a Python file declaring a contract another transform owns: its other form, never a gap)
GET  /api/transforms/{name}/source                   → the transform's file and its .contract.yaml (read-only; name is a stem in transforms/)
GET  /api/models
GET  /api/models/{name}                              → tables, relationships, facts (each with its runnable_measures), dimensions
GET  /api/models/{name}/tables/{t}/preview           → first N (≤500) rows + engine dtypes + total_rows, read through the table API
GET  /api/models/{name}/tables/{t}/export.csv        → full table as CSV, streamed through the table API
GET  /api/tables/{source}/{table}                    → one table wherever it lives (source: a connector, or `inputs` for a file under inputs/): kind, table_kind (table|view, warehouse only), view {transform, bases} for a sink view, rows, rows_exact, columns [{name,type}] in the engine's spelling, written_by, contract, read_by, used_by, transform_read, columns_from (a SQL transform's column lineage, else null); 200 {connected: false…} when unreachable; framework tables 404
GET  /api/tables/{source}/{table}/rows               → ?offset&limit(≤500)&sort&desc&q&where=[{column,op,value}] (closed ops; refused 422 before any SQL) → {columns, rows, offset, limit, total, total_exact, elapsed_ms}
GET  /api/tables/{source}/{table}/profile            → {rows, columns: {name: {type, nulls, null_share, distinct, min, max, mean?, top:[{value,count}]}}}
GET  /api/tables/{source}/{table}/export.csv         → the same cut as CSV, streamed from the engine
POST /api/tables/{source}/{table}/export             → {to: <connection> | s3://… | gs://… | folder/} → {table, to, kind: connection|object, rows, path?} (admin; run row kind=export; the gateway's export_table and `tracebi export` use the same function, warehouse.export_table)
GET  /api/credentials                                → every ${NAME} the workspace references and where it is set (environment|dotenv|store|default|missing), never a value; can_change (viewer)
PUT  /api/credentials/{name}                         → {value} → the status row; 201 new / 200 replaced (identified admin; audit row kind=credential)
DELETE /api/credentials/{name}                       → 204, the store's value only (identified admin)
POST /api/connectors/{name}/test                     → open, list, close: {ok: true, tables: n} | {ok: false, reason} with any secret scrubbed (admin)
GET  /api/connections/types                          → each type and its fields (name, label, kind text|secret|url|path, required, help): the Add a connection form
POST /api/connections                                → {name, type, fields, label?, agents?} → writes connections/<name>.yaml (a typed secret → the store, ${NAME} in the file); 201 as GET /api/connectors/{name}; 409 taken; 422 {errors} (identified admin)
POST /api/connections/test                           → the same body, tested unsaved: {ok, tables} | {ok: false, reason} (identified admin)
PUT  /api/connections/{name}                         → edit in place (comments kept); a secret sent empty is kept; agents when sent, null removes (identified admin)
DELETE /api/connections/{name}                       → 204, or 409 {read_by} while a transform, pipeline step or model reads it (identified admin)
POST /api/inputs?name=x.csv                          → the body is one CSV/Parquet file → inputs/<name>, ≤50 MB (identified admin)
GET  /api/models/{name}/source                       → the model's file (read-only; the Code tab)
GET  /api/models/{name}/context[?brief=true]         → what an agent receives for the model: capabilities.describe_model, the same object as `tracebi context --model` and the gateway's get_context / describe_model (brief drops synonyms)
GET  /api/connectors/{name}/source                   → the model file(s) that declare it
GET  /api/connectors/{name}/warehouse                → tables, row counts, column profiles, per-table sink-contract status (read-only, closed per request); each contract names the `file` that declares its checks and carries the transform's `note`
GET  /api/pipelines/{name}/source                    → the pipeline file + the transform it runs
POST /api/models/{name}/query                        → star-schema query + lineage graph; rows raw (data) and as report-formatted text (display)
GET  /api/reports                                     → omits reports in folders the caller cannot view (_folder.yaml); every /api/reports/{name}/… route and /r/{name} answers 404 for those, as for a missing name; 403 {required_permission} when visible but the folder lacks build/publish
POST /api/reports/{name}/run                         → HTML + lineage manifest JSON (sync)
POST /api/reports/{name}/runs                        → start background run; returns run_id (202)
GET  /api/reports/{name}/runs                        → recent background runs (no payloads)
GET  /api/reports/{name}/runs/{run_id}               → poll status; result/error when settled
GET  /api/reports/{name}/built                       → the last build (disk, else the path in the run store; built once if never)
GET  /api/reports/{name}/cover                       → PNG of the last build's first screen (ETag = its write time; 304); 404 when none (the app draws one); never builds; hidden as /built
GET  /api/runs                                       → run rows (kind, target, limit); viewer may read
GET  /api/runs/counts?kind=                          → [{kind, target, runs, failed}] per target the caller may see (History's "N older runs")
GET  /api/desk[?fresh=1|quick=1]                     → only reports the caller may view: pins, drafts, verdicts, builds (each with `values` [{id, label, text, delta, spark}], its KPIs as the built page printed them; the home draws no figure), sinks; each verdict/build row carries computed_at and cached: a verdict is kept while its manifest, the models it names and their warehouse (+ certificate) are unchanged (tracebi/desk.py; in the process and in the state store's tracebi_verdicts, reused only when its inputs' digest matches; fresh re-runs all; quick re-runs none: the rest come back `pending` with the last answer, which the app shows as Checking, never green, then re-reads without quick)
POST /mcp                                            → the agent gateway, when TRACEBI_MCP_TOKEN, TRACEBI_OIDC_ISSUER or the built-in sign-in is set (bearer; outside app auth)
GET  /.well-known/oauth-*  /authorize /token /register /revoke /oauth/callback → per-person OAuth for /mcp (TRACEBI_OIDC_ISSUER, or the built-in TRACEBI_DEMO_LOGIN / TRACEBI_LOCAL_USERS; tracebi/mcp_oauth.py)
GET  /api/reports/{name}/download?format=xlsx|html|pdf   → html/pdf: the last build; xlsx: rendered
GET  /api/reports/{name}/lineage                     → transform → tables → model → queries → figures flow, from the last build's trace (its manifest)
GET  /api/reports/{name}/mermaid
GET  /api/reports/{name}/source                      → the spec or package files that define it
GET  /r/{name}                                       → share link: the last build as a full page (auth like any GET)
GET  /api/pipelines
POST /api/pipelines/{name}/run
POST /api/pipelines/{name}/layers/{layer}/run
GET  /api/pipelines/{name}/layers/{layer}/history
POST /api/pipelines/{name}/runs                       → background run (202); ?layer=, ?refresh=; joins one already going
GET  /api/pipelines/{name}/runs[/{id}]                → recent runs (app and `run-pipeline`) / one run's status; each lists its steps and the reports it rebuilt
GET  /api/pipelines/{name}/runs/{id}/log?after=N      → what the steps printed, from offset N (analyst)
GET  /api/drafts                                     → the caller's drafts (admin: everyone's)
POST /api/drafts                                     → start (or open) the caller's own draft of a published report or model: {kind, path, from_published}; 201 new, 200 already theirs, 422 refused (a Python model says to edit it from a laptop) (analyst)
PUT  /api/drafts/{owner}/{kind}/{path}/files/{file}  → write one draft file {content}; returns the new version (analyst; owner or admin)
GET  /api/drafts/{owner}/{kind}/{path}/files         → a draft's files (owner or admin)
GET  /api/drafts/{owner}/{kind}/{path}/version       → a draft's version (owner or admin)
GET  /api/drafts/{owner}/{kind}/{path}/preview       → the draft rendered in memory; writes nothing (owner or admin)
GET  /api/drafts/{owner}/{kind}/{path}/impact        → model draft only: each published report that reads the model is unchanged / moves (figures, old and new) / breaks / not_built, from re-running its last build's queries against the draft (owner or admin)
POST /api/drafts/{owner}/{kind}/{path}/publish       → publish a draft; body {note, accept_impact, folder}; a report goes to `folder` (default its own path): Publish there → 200 published, only Build → 202 a publish request, less → 403; `accepts: checkable` folders refuse non-re-runnable reports (422); a model that moves or breaks reports is 409 with the impact until accept_impact; 403 when the published model names `owners` and the caller is neither one nor admin (analyst; owner or admin)
GET  /api/publish-requests?status=                   → the caller's own requests and those into folders where they hold Publish
GET  /api/folders                                    → the folders the caller may see, their own `My published` (`my-published/<sign-in name>`; `personal` is null with no sign-in identity) first; each with level, mode (publish directly / request), accepts, and read-only permissions for Manage and a personal folder's owner
GET  /api/drafts/{owner}/{kind}/{path}/destinations  → where a report draft may go for the caller, each `mode: publish|request` (owner or admin)
GET  /api/reports now also carries `folder` and `owner` (last publisher, or the owner of a My published folder) and `made_from` (`app.jsx` | `template.html` | null: what a package draws its page from); /api/publish-requests rows carry `can_decide`
POST /api/publish-requests/{id}/approve|reject       → publish the request's snapshot (records approver and time) / reject with a {note}; needs Publish on the destination at decision time (analyst)
POST /api/code-requests                              → Python from `tracebi push`: {files: {path: text}, note}; stored under .tracebi/requests/<id>/ + tracebi_code_requests (analyst)
GET  /api/code-requests[/{id}]                       → the caller's own (admin: all); one with each file's diff against what is published, its runs, dry_run (an agent's proposal; the list carries {ok, summary}), commit_sha / commit_note
POST /api/code-requests/{id}/approve|reject          → copy the files in (history under .tracebi/history/code/), commit them in a git work tree, and run the pipelines they touch once; 422 when its dry run failed / reject with a {note} (admin)
POST /api/library/sync                               → git webhook: pull each library checkout, rescan; outside sign-in, needs TRACEBI_LIBRARY_SYNC_SECRET (X-Hub-Signature-256 or X-TraceBi-Sync-Token); 404 without it
DELETE /api/drafts/{owner}/{kind}/{path}             → delete a draft, not the published copy (analyst; owner or admin)
GET  /                                               → React SPA (tracebi/web/ui/dist): four places, Reports (/, the
                                                       library as a directory, a tile per project; /?folder=<path> one project's page (?project= redirects); the sidebar is
                                                       the folder tree, web/ui/src/folders.js; /ask is reached by Ask this model
                                                       on a folder's or a model's page) · Data (/data: a console, its four lists nested under Data in the sidebar
                                                       (plain links), every page in one frame (pages/Data.jsx DataFrame: a folder's
                                                       name as its h1, or a breadcrumb Data › Warehouse › fact_holdings). Home /data
                                                       (pages/DataHome.jsx, a status board: five cards with a health pill, Needs
                                                       attention from the graph's gaps and unreachable sources, Agent access, Recent
                                                       activity, Schedules; View lineage · Add connection · Refresh data ▾). Lineage
                                                       /data/lineage (the map, pages/Map.jsx over GET /api/graph, read through a lens
                                                       ?lens=coverage|flow|freshness|trust|access; ?node=<id> selects a piece and its
                                                       passport rows, components/Passport.jsx, no actions; ?measure=<model>:<measure> a
                                                       model's measure; under the passport Depends on this (components/DependsOn.jsx over
                                                       GET /api/graph/downstream) for a table, source table or measure, links only; a
                                                       pipeline run going now moves on it and on every Lineage tab (api.js
                                                       useRunningRuns, one shared poll; observation only, never a trigger); ?lane=;
                                                       /data?lens|node|lane redirect here). Every list is components/ResourceTable.jsx (?q=, ?filter=, ?sort=,
                                                       a Status column in words.js statusWords' words, a ⋯ row menu); every thing's page
                                                       components/ResourcePage.jsx (name · type chip · status pill · actions top right ·
                                                       tabs at ?tab=: Overview (Details grid, the passport rows among the facts) · its own ·
                                                       Lineage (the map focused on it) · Activity · Agents · Settings; empty tabs left out).
                                                       Sources /data/sources (connections and input files in one list; /data/sources/<name>:
                                                       Overview · Tables (agent ticks) · Lineage · Activity · Agents · Settings (the Setup
                                                       sheet's content), Test and Setup ▾ top right; /data/sources/inputs the folder;
                                                       /data/sources/<name>/<table> and /data/sources/inputs/<path> one table) · Transforms
                                                       /data/transforms (/data/transforms/<name>, pages/Transform.jsx: Refresh data top
                                                       right, its run on Steps; Code; Reads and Produces on Overview) · Warehouse
                                                       /data/warehouse (?view=table, the list, default | schema, the data browser by
                                                       writer: ?table=<id>, ?group=<id>; /data/warehouse/<table> one table: Overview ·
                                                       Data · Columns (From) · Used by · Lineage · Activity, Copy SQL and Export top
                                                       right) · Models /data/models (/data/models/<m>: Overview · Schema (DataBrowser:
                                                       tree, canvas, inspector; ?table= | ?measure= | ?view=… open it) · Measures ·
                                                       Lineage · Activity · Agents · Settings; Ask this model, Edit as a draft top
                                                       right). Nothing under /data is narrowed by ?model=; the old /data/<m>…,
                                                       /data/tables/…, /map and ?source= addresses redirect (movedTo)) · Review (/review) · Docs
                                                       (a report's page /reports/<name>: breadcrumb Library › folder › report, one
                                                       command bar, and on a column 1240px or wider the trace beside the page: the
                                                       clicked figure (or ?figure=<id>) in five steps, source, model, query, fingerprint, re-run;
                                                       ⌘K groups Projects, Reports, Tables, Models and Places)
                                                       (/docs: the handbook in docs/toc.yaml's order; the quickstart at /docs/get-started), plus History
                                                       (/runs) and Verify (/verify); older addresses redirect (movedTo in
                                                       web/ui/src/nav.js; /handbook, /getting-started, /data?view=map,
                                                       /data/map too). FastAPI's API reference is /api-docs. When it has not been
                                                       built, a page naming the build command
```

Failed report/query runs return a structured ``detail``:
``{message, exception_type, traceback}`` — keep that shape; the UI renders it.

---

## What Doesn't Exist Yet

- No Makefile (commands documented in README + this file)
- No migration framework for warehouse tables (layers are idempotent; the state store uses Alembic — `tracebi/migrations`)
- No pre-commit hooks
- No PyPI release (install is `pip install -e .` or from git)
- No `PDFRenderer` class. A package PDF is a print of the built HTML via Playwright (`tracebi report build <name> --format pdf`, `pip install 'tracebi[pdf]'` and `python -m playwright install chromium`); its last pages are the trace printed as an appendix, "How these numbers were made" (one row per figure, the sink contracts, the build, the verify command; tracebi.css's print rules, `@page` margins on every page). `HTMLRenderer.render_pdf()` remains the WeasyPrint path for the legacy renderer; it runs no JavaScript, so a package's charts would print blank, and it is untested without weasyprint/libgobject.

Don't add these unless asked.

---

## Orientation Map

| Goal | Start here |
|---|---|
| Understand the whole framework | `README.md` |
| Add or reorder a handbook page | `docs/toc.yaml`, then `python site/build_docs.py` |
| Understand the three-phase workflow | `docs/concepts/the-three-phase-workflow.md` + `examples/portfolio_project/` |
| Author a phase-① transform | `examples/portfolio_project/transforms/holdings_transform.sql` + `docs/reference/transform-sql.md` |
| Define the model over the warehouse | `examples/portfolio_project/models/portfolio_model.yaml` (its semantic words: `description`, `synonyms`, `questions`) + `docs/concepts/model.md` |
| Build a dashboard | `examples/portfolio_project/reports/portfolio_model/portfolio_dashboard/` |
| Build an app dashboard (React lane) | `tracebi new-dashboard` → `examples/portfolio_project/reports/portfolio_model/portfolio_desk/` + `docs/reference/app-jsx.md` |
| Change how charts draw | `tracebi/reports/assets/tracebi.js` "The chart engine" (`optionFor`, `chartTheme`, `drawChart`) + `docs/reference/chart-style.md`; browser tests `tests/test_charts.py` |
| Build a freeform report package | `tracebi new-report` → `examples/portfolio_project/reports/portfolio_model/portfolio_book/` + `design/report-generator-architecture.md` |
| See a scenario (reader what-if) on public data | `examples/portfolio_project/reports/housing_model/affordability/` + `tracebi/reports/scenario.py` |
| See every artifact feature at once (the app lane) | `examples/portfolio_project/reports/portfolio_model/portfolio_showcase/` — the maintained kitchen-sink demo, an `app.jsx` in Signal: every kit figure, control and gesture (rot-proofed by `tests/e2e/test_reference_project.py`, `tests/e2e/test_live_cascade.py` and `tests/test_agent_guides.py`) |
| See the editorial lane at its best | `examples/portfolio_project/reports/housing_model/affordability/` — the reference long read (`template.html`): the whole template grammar, small multiples, annotated charts, a what-if, a print edition (`tracebi report build housing_model/affordability --format pdf`); `tests/test_agent_guides.py` holds its grammar |
| Understand architecture decisions | `NOTES.md` (the journal) + `design/` (the design notes; internal, never published) |
| Avoid bugs already hit in this repo | `design/pitfalls.md` |
| Decide whether a test is worth writing | `design/test-suite-review.md` |
| See a complete working wiring | `tracebi/web/demo_app/` |
| Understand data flow end-to-end | `examples/phase4_example.py` |
| Add something to the web API | `tracebi/registry.py` (singleton) + `tracebi/web/api/routers/` |
| Change the web app's pages | Data's home is `pages/DataHome.jsx` (a status board over `/api/graph`); Lineage is `pages/Map.jsx` with `components/Passport.jsx`; every Data list is `components/ResourceTable.jsx` and every Data page `components/ResourcePage.jsx`; `web/ui/src/nav.js` (the four places; `DATA_FOLDERS`, `SIDEBAR_FOLDERS` and Data's path helpers `modelPath`, `transformPath`, `warehouseTablePath`, `lineagePath`, …; `movedTo` for old addresses) + `web/ui/src/App.jsx` + `pages/Data.jsx` (`DataFrame`, the frame of every page under /data; a transform's page is `pages/Transform.jsx`); the browser tab's title comes from `components/Layout.jsx` (the page's h1 after its tab; `useDocumentTitle(...parts)` for a page whose h1 is not its name); `web/ui/src/folders.js` (the library's folders, their order and hue) + `components/Directory.jsx` (cover tile, rows, folder tile, Today) |
| Change the data browser (a model's Schema tab, the Warehouse folder's Schema view) | `web/ui/src/components/DataBrowser.jsx` + `components/modelGraph.js` (`modelSchema` / `warehouseSchema` / `layoutSchema`) |
| Write an ad hoc report | `tracebi new-report` → `tracebi dev` (the artifact loop) |
| Migrate a JSON spec to the artifact | `tracebi migrate spec reports/<name>.json` → `tracebi/reports/compile_spec.py` |
| Define a reusable DataModel | `tracebi new-model` → `models/` → `tracebi/model_registry.py` |
| Define a reusable pipeline | `tracebi new-pipeline` → `pipelines/` → `tracebi/pipeline_registry.py` |
| Understand the lineage chain | `tracebi/model/dataset.py` |
| Add a new connector | `tracebi/connectors/` (pick any existing one as a model) |

---

**These guidelines are working if:** diffs are minimal and focused, tests pass before and after, and questions surface before implementation rather than after mistakes.
