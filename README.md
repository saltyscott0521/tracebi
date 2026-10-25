# TraceBi

[![CI](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml/badge.svg)](https://github.com/saltyscott0521/tracebi/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://github.com/saltyscott0521/tracebi)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A report-as-code framework for Python — that keeps agents in line.**

AI writes the analysis now, and a confident wrong number reads exactly like a
right one. TraceBi makes every report *code*: an **agent** authors it, a
**human** reviews and approves it, guardrails refuse the bad numbers, and a
trace proves the rest reproduce. The metric logic lives in your repo, not
inside a GUI: a real **semantic layer** where a measure is declared once and
referenced by name, a **three-phase workflow** that keeps the slow analysis
and the fast reporting from blocking each other, and a web app where people
read the reports, ask questions, and see how every number is made. The agent
gets a vocabulary, guardrails it can't skip, and an MCP gateway; the human
holds review, publishing, and a warehouse the agent can't write to.

Because every figure is a live query, a built report is one self-contained,
**reproducible** file: `tracebi verify` re-runs the recorded queries, and
`tracebi verify --file` checks an emailed report offline, with no database and
no account. The identity, vocabulary and refusals are in
**[MANIFESTO.md](MANIFESTO.md)**; the handbook is **[docs/](docs/index.md)**
(served in the app as **Docs**).

---

## How it works — the three-phase workflow

TraceBi takes data from messy to reportable in three project-root folders,
each with its own cadence, decoupled by **freeze points**: a materialized
artifact handed from one phase to the next.

```
⓪  SOURCES      inputs/, connections/   raw files, and databases declared as YAML
                                                        │
①  TRANSFORM    transforms/             slow, runs rarely — SQL (pandas the escape hatch)
      read the sources → parse, clean, key, dedupe → SINK star-schema tables
                                                        │
                                       freeze ▼  the warehouse (tracebi.yaml)
②  MODEL        models/                 the contract, changes deliberately
      a declarative star schema over the warehouse — grain, keys, measures,
      a few dozen YAML lines a reviewer reads without opening the transform
                                                        │
                                       freeze ▼  the model (the semantic contract)
③  REPORT       reports/                fast, iterate constantly
      a package pointed at the model — KPI cards, charts, tables, every figure
      a live query with an embedded trace. Nothing re-runs ①.
```

**① Transform** is SQL by default: `transforms/<name>.sql`, DuckDB statements
run top to bottom in one fresh warehouse connection. A header line
`-- source: crm.issuer_ratings` loads a table of a declared connection before
the first statement. The framework does not constrain how you clean; the
contract is *what lands*, the named tables at the end. A
`<name>.contract.yaml` beside it declares closed checks (rows, unique keys,
not-null, foreign keys, value domains, reconciliations) that run at sink time,
raise on failure, and record a certificate report manifests join against: *the
sink satisfied its contract*, never "the transform was verified". When the work
outgrows SQL, a `.py` or `.ipynb` transform (pandas or polars) is the escape
hatch.

**② Model** is a declarative star schema over the warehouse
(`models/<name>.yaml`): tables, facts, dimensions, relationships and named
measures (ratios, windows, period-ends, time intelligence). It reads the sink;
it never sees the transform. A model query runs inside the warehouse, in a
locked read-only DuckDB connection.

**③ Report** is a package pointed at the model: `report.json` (named queries,
the *bindings*) plus an `app.jsx` dashboard or a `template.html` page. `tracebi
report build` renders one self-contained HTML with its trace inlined. The built
page is live: it carries the slice of the model its figures need, and a filter,
a click on a bar or a row re-runs every figure's own query in the page, offline.

**Where trust starts.** Lineage is not traced through the phase-① analysis;
the line is drawn at the **sink**. The trust machinery (stamped queries, a
SHA-256 fingerprint per figure, `tracebi verify`) applies from the model
boundary onward. `verify` proves a number *reproduces* and the file was not
*altered*; it does not prove the number is correct.

Full walkthrough: **[the three-phase workflow](docs/concepts/the-three-phase-workflow.md)**.

---

## Install

TraceBi is not on PyPI yet. Install from a clone:

```bash
git clone https://github.com/saltyscott0521/tracebi
cd tracebi
pip install -e ".[all]"            # the engine, the CLI, the web app, the agent gateway
```

Or without cloning:

```bash
pip install "tracebi[analyst] @ git+https://github.com/saltyscott0521/tracebi"
```

An install straight from git carries the library, the CLI and the API but **no
web UI**: the React bundle (`tracebi/web/ui/dist`) is built, not committed, so
`/` says so. Build it from a clone (`cd web/ui && npm ci && npm run build`), or
use the Docker image or a release wheel, which ship it.

Extras, if you want only some pieces: `duckdb` (required for any model
query), `reports`, `pipeline`, `web`, `mcp`, `postgres`, `bigquery`,
`snowflake`, `lineage`, `pdf`, `analyst` (the data stack for a laptop), `all`,
and `dev` (everything the test suite needs). `tracebi update` says whether a
newer release exists and prints the command for your install
([updating](docs/guides/updating.md)).

---

## The reference project, in one command

`examples/portfolio_project/` is the working project every convention follows:
four models over one warehouse, each with its transform, contract, pipeline and
reports, and one of each kind of source.

```bash
cd examples/portfolio_project
python run_workflow.py      # ① every transform into data/warehouse.duckdb, ③ every report into output/
tracebi serve               # http://127.0.0.1:8000
```

| Model | Source | Transform | Reports |
|---|---|---|---|
| Direct Lending Portfolio | `inputs/holdings.csv` + a Postgres CRM (`connections/crm.yaml`, `TRACEBI_CRM_URL`; without it the committed snapshot stands in, and the certificate says so) | `holdings_transform.sql` (+ `holdings_transform_pandas.py`, the same tables in pandas) | `portfolio_model/`: dashboard, desk, book, overview, concentration, showcase |
| Wealth Management | a core-banking SQLite that ships (`connections/bank.yaml`) | `wealth_transform.sql` | `wealth_model/`: AUM by branch, AUM by region |
| SaaS Subscriptions | a billing SQLite that ships (`connections/billing.yaml`) | `saas_transform.sql` | `saas_model/`: MRR dashboard, cohort brief |
| Housing Affordability | public data, `inputs/housing_history.csv` | `affordability_transform.py` (the pandas escape hatch, `with contract`) | `housing_model/`: affordability, with a reader's what-if |

`docker compose up --build` serves the same project, with the CRM as a
standing Postgres database (below). The public demo at tracebi.com is that
stack.

---

## The app

`tracebi serve` (or the Docker image) serves the web app over your project.
Four places in the sidebar:

- **Reports** (`/`) — the library as a directory: a tile per folder (how many
  reports, when last built; no figures: a number appears only inside a
  report), then rows of covers (the newest
  builds, then each folder), every report with its verdict, when it was built
  and its schedule, narrowed to a model by a chip. The sidebar is the folder
  tree; each folder has a page (`/?folder=<path>`) with what it holds, its builds,
  its reports by kind and **Ask this model**; the library's head has **New
  report** (analysts) and **Refresh data** (admins). A report opens at
  `/reports/<name>` as delivered, under one command bar: **Open**, **Share**,
  **Export** (PDF, Excel, or the HTML with its trace), **Rebuild** and **Edit as
  a draft** for an analyst, and **About this build** (the trace, lineage,
  history and files). On a wide window the trace sits beside the page: the
  figure you last clicked, in five steps from its source table to the re-run
  that checked it. **⌘K** (Ctrl K) jumps to any folder, report, table or page.
- **Ask** (`/ask`, from **Ask this model** on a folder's page or a model's) —
  a question of one model as a sentence of its own tokens
  ("Show fair value by sector, largest first, top 8"), answered with a chart,
  table or number, each measure's definition and the query behind it. **Keep
  this** starts a draft report.
- **Data** (`/data`, analysts and admins) — opens on **Flow**, the board: five
  lanes in the order the data moves (⓪ Sources, ① Transforms, the Warehouse
  grouped by the transform that wrote each table, ② Models, ③ Reports), wires
  between the cards, a model's whole path lit on hover. The tabs behind it list
  the same things: **Sources** (every connection and the `inputs/` folder, what
  each holds and what reads it, and its credentials), **Transforms**,
  **Warehouse** (every table, who wrote it, who reads it, its checks) and
  **Models**. Any table opens on a page of its own (rows with sort, search and
  filters, a column profile, who uses it); a model's page draws its line and
  its tabs (Model, Transform with **Refresh data**, Sources, Runs).
- **Review** (`/review`, analysts and admins) — what needs attention (a failed
  refresh, a build that needs a look, a request to publish), then **Drafts**,
  **History** (what ran, when, for whom, whether it reproduced) and **Verify**
  (drop in a report file and its manifest).
- **Docs** (`/docs`) — this repository's handbook, in the order of `docs/toc.yaml`, **Start here** first.

Roles decide what shows: everyone Reports and Docs; an analyst also Data
(read-only) and Review; only an admin runs a refresh or sets a credential.
With no sign-in configured every caller is admin. FastAPI's API reference is
at `/api-docs`; every route is in [API routes](docs/reference/api-routes.md).

---

## Authoring a report

A report is a package, `reports/<name>/`; by convention it sits in its
model's folder (`tracebi new-report "Portfolio Model/Book"` creates
`reports/portfolio_model/book/`, named by that path). Two forms, one renderer:

```bash
tracebi new-dashboard "Ops Board"     # report.json + app.jsx: a dashboard from the TraceBi kit
tracebi new-report "Portfolio Book"   # report.json + template.html: a page that reads with JavaScript off
tracebi dev portfolio_book            # the app in dev mode, Build mode on: re-renders as you (or your agent) save
tracebi report build portfolio_book   # → output/portfolio_book.html + .manifest.json (the trace)
tracebi verify output/portfolio_book.html.manifest.json
tracebi verify --file output/portfolio_book.html
```

Every figure names a binding: a query declared in `report.json`, resolved,
fingerprinted and embedded. A number with no binding must carry
`data-tb-unverified`; there is no third state. Explore inside
`data-tb-stage="exploration"` blocks, which die at build. `report.py` beside
`report.json` is the escape hatch for pandas the model can't express; its
outputs are stamped `verifiable: false` and never read green.

A `"schedule"` block in `report.json` makes it recurring: `tracebi schedule
run <name>` (or `serve`, or `TRACEBI_SCHEDULES_IN_SERVER=1`) refreshes, builds,
verifies, and emails it only when it verifies.

The handbook: [your first report](docs/start/your-first-report.md),
[`report.json`](docs/reference/report-json.md),
[`app.jsx`](docs/reference/app-jsx.md),
[`template.html`](docs/reference/template-html.md),
[styling](docs/guides/styling-a-report.md).

---

## Models, transforms and sources

```bash
tracebi init my_project                      # a complete three-phase project whose sample loop reads REPRODUCES
cd my_project
tracebi run-pipeline sample_model            # the sample's transform, then its reports: what Refresh data runs
tracebi connect crm --kind postgres          # → connections/crm.yaml, the secret as ${NAME} (--store secret: the encrypted store)
tracebi new-transform "Holdings"             # → transforms/holdings.sql + holdings.contract.yaml (--python: pandas)
tracebi run-transform holdings               # runs it top to bottom, fresh; prints form: sql
tracebi new-model "Holdings"                 # → models/holdings.yaml (--from crm --tables a,b: drafted from metadata)
tracebi validate                             # every model loads; dimension keys are unique
tracebi new-pipeline "Holdings"              # → pipelines/holdings.yaml: the transform, then every report in reports/holdings/
```

`tracebi.yaml` at the project root names the warehouse (a DuckDB file by
default; Parquet on object storage, or a remote engine) and the query engine's
limits. The handbook: [transform](docs/concepts/transform.md),
[SQL transforms](docs/reference/transform-sql.md),
[sink contracts](docs/concepts/sink-contracts.md),
[model files](docs/reference/model-json.md),
[measures](docs/reference/measures.md),
[`tracebi.yaml`](docs/reference/tracebi-yaml.md),
[pipeline files](docs/reference/pipeline-yaml.md).

### Credentials

A connection never holds a secret: a password, or a URL that carries one, is a
`${NAME}`, resolved when the connection is used from the environment, then the
project's `.env`, then the project's encrypted store
(`.tracebi/secrets.yml.enc`), then a `${NAME:-default}` that must itself hold
no credential.

```bash
tracebi secret list                 # every ${NAME} the project references, and where each is set
tracebi secret set TRACEBI_CRM_URL  # prompted, no echo; encrypted into the store
tracebi secret edit                 # the decrypted YAML in $EDITOR, encrypted back
tracebi secret unset TRACEBI_CRM_URL
```

A signed-in admin can do the same from Data → Sources, and test the
connection there; a value never comes back to the browser. The key is
`TRACEBI_SECRET_KEY`, or `.tracebi/secret.key` generated on first use. See
[credentials](docs/reference/credentials.md).

---

## Deploy

**One server.** One VM, one container, one project folder: the app, the
schedules and the email run in it. `deploy/compose.yml` mounts your project
(`TRACEBI_PROJECT_DIR`); SQLite is the default, `--profile postgres` adds
Postgres. Step by step: [run TraceBi on one server](docs/guides/one-server.md).

**Docker, the reference project.** The repository's `docker-compose.yml`
serves `examples/portfolio_project` and nothing beside it:

```bash
docker compose up --build           # http://localhost:8000
```

| Service | Does |
|---|---|
| `db` | Postgres. On its first start it creates `crm`, a standing mock CRM loaded once from `inputs/seed_crm.sql`, and `tracebi_state`, the run store (`docker/postgres-init.sql`). Both persist on the `pgdata` volume; `docker compose down -v` starts over. |
| `seed` | Runs the project's four pipelines once (each transform, then its reports) into the `warehouse` volume, then exits. It never writes the CRM. |
| `app` | The web app on `:8000`, over the warehouse `seed` wrote. |

Re-run a model's pipeline with **Refresh data**, or
`docker compose exec app tracebi run-pipeline portfolio_model`.

**Several workers** (`uvicorn tracebi.web.api.main:app --workers 4`, or
several replicas) need Postgres: point `TRACEBI_STATE_URL` at it so runs,
schedules and sessions share one store and its advisory locks keep two
processes from running the same layer or sending the same email (SQLite is one
process only), and give every process the same `TRACEBI_SECRET_KEY`.

**Sign-in** is off until you configure it: HTTP Basic, a trusted proxy header,
named local users (`TRACEBI_LOCAL_USERS`), or your identity provider over OIDC
(`TRACEBI_OIDC_ISSUER`), with roles (viewer, analyst, admin) and folder
permissions (`_folder.yaml`) that narrow them. See
[sign-in](docs/guides/sign-in.md), [folder permissions](docs/reference/folder-yaml.md)
and [environment variables](docs/reference/environment-variables.md).

---

## Agents (MCP)

An agent works against your semantic contract, not your warehouse.
`tracebi mcp` serves the kernel over the
[Model Context Protocol](https://modelcontextprotocol.io): 22 tools and three
prompts. The agent reads the vocabulary (`get_context`), queries the model
(`query_model`: every answer is stamped with the resolved query, its lineage
and a SHA-256 fingerprint of the full result), builds and verifies reports
(`build_report`, `verify_manifest`), and writes drafts a person publishes
(`start_draft`, `write_draft_file`, `preview_draft`, `publish_draft`). It is
read-and-compute only: nothing it can call writes to the warehouse.

```bash
pip install -e ".[mcp]"
claude mcp add tracebi -- tracebi mcp          # a local agent, from the project folder (tracebi init writes .mcp.json)

export TRACEBI_MCP_TOKEN=$(openssl rand -hex 32)
tracebi mcp --transport http --host 0.0.0.0 --port 8765   # a remote agent; the token is required
```

With `TRACEBI_MCP_TOKEN` or `TRACEBI_OIDC_ISSUER` set, the web app also serves
the gateway at `/mcp`, so ChatGPT and Claude connectors sign each person in
with their company login ([connect ChatGPT and Claude](docs/guides/connect-chatgpt-and-claude.md)).
From a laptop, `tracebi login` and `tracebi push` send report packages and
models as drafts, and Python as a code request an admin approves
([push from a laptop](docs/guides/push-from-a-laptop.md)).

The playbook an agent reads first (the two planes, the assurance ladder, every
tool, the authoring loop) is **[AGENTS.md](AGENTS.md)**; `tracebi context`
prints the generated vocabulary.

---

## The trace

Every build writes `<report>.html.manifest.json` beside the file: per figure,
the model, the exact query and a fingerprint of the data it returned. Keep the
manifests; a trace you discarded proves nothing.

| Command | Asks |
|---|---|
| `tracebi verify <manifest>` | Do these numbers still reproduce? Re-runs every recorded query: `REPRODUCES`, source drift, model changed, or unexplained. Exit 0 only when something was checked and nothing failed. |
| `tracebi verify <manifest> --contracts` | Does the sink still satisfy its contract, and did its sources move? |
| `tracebi verify <manifest> --local` | Does the page engine's recomputation match the server's, plan by plan? |
| `tracebi verify --file <report.html>` | Is this the file we rendered? Offline, no database: an edited number reads `FILE ALTERED`. |

See [the trace](docs/concepts/trace.md) for what it proves and what it does not.

---

## The Python library

The engine underneath is a Python library you can use from a notebook or a
script: an immutable, lineage-tracked `DataSet`, `DataModel` with its
star-schema query, the medallion layers (`LandingLayer`, `ManipulationLayer`,
`FinalLayer`, compiled to DuckDB SQL), `PipelineRunner` with APScheduler, and
the connectors (CSV, SQL, BigQuery, Snowflake, DuckDB, memory). Check
`tracebi/__init__.py` for what it exports.

```python
from tracebi.model_registry import get_model

model = get_model("portfolio_model")          # no web server needed
orders = model.load("fact_holdings")           # a DataSet: rich preview in Jupyter
orders.print_lineage()
```

The [analyst guide](docs/guides/analyst-guide.md) and the
[notebook guide](docs/guides/notebook-guide.md) cover it; the examples run
it end to end:

```bash
python examples/analyst_quickstart.py  # notebook-first tour: rich previews, report styling
python examples/phase1_example.py      # connectors + DataModel + lineage
python examples/phase2_example.py      # report engine (opens a browser)
python examples/phase25_example.py     # medallion layers + star schema + lineage diagram
python examples/seeds/seed_db.py       # seed data/seed.db for the next one
python examples/phase4_example.py      # the full pipeline runner
```

`tracebi/web/demo_app/` is the bundled example of wiring an app module in
Python (medallion layers built in code, `registry.add_*`). It is opt-in
(`TRACEBI_APP=tracebi.web.demo_app`) and never served beside a project; see
[customizing the web app](docs/guides/web-customization.md).

---

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/                       # the full suite (it prints the count)
```

End-to-end journeys live in `tests/e2e/` and drive the real CLI, web app and
MCP tools in-process. The browser tests need `TRACEBI_E2E=1`, a built UI and
Playwright's Chromium.

---

## Project structure

```
tracebi/                        ← the framework repo
├── tracebi/                    the Python package (what the wheel ships)
│   ├── connectors/             CSV, SQL, BigQuery, Snowflake, Memory, DuckDB
│   ├── model/                  DataSet, DataModel, engine.py (the locked query connection)
│   ├── etl/                    Landing / Manipulation / Final layers, compiled to DuckDB SQL
│   ├── reports/                the artifact build, calc plans, the page runtime (assets/)
│   ├── pipeline/               PipelineRunner (APScheduler + the run store)
│   ├── web/                    FastAPI app (api/), the demo app, the built UI (ui/dist)
│   ├── mcp_server.py           the agent gateway
│   └── cli.py                  `tracebi …`
├── web/ui/                     the React UI source (Vite); `npm run build` writes tracebi/web/ui/dist
├── examples/portfolio_project/ THE reference project: tracebi.yaml, inputs/, connections/,
│                               transforms/, models/, reports/, pipelines/, run_workflow.py
├── tests/                      the pytest suite; tests/e2e/ the journeys
├── docs/                       the handbook (an Obsidian vault): start, concepts, guides,
│                               reference, agents; docs/toc.yaml orders it
├── design/                     internal: design notes, strategy, pitfalls (never published)
├── AGENTS.md                   the agent's brief
├── MANIFESTO.md                what TraceBi is, and what it refuses to build
├── NOTES.md                    the decision journal
└── CHANGELOG.md
```

`tracebi init` gives your own project the same shape as
`examples/portfolio_project/`.

---

## License

MIT
