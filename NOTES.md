# TraceBi — Project Notes & Design Decisions

A running log of key discussions, decisions, and concepts for the TraceBi project.

---

## Build Status

| Phase | Status | Description |
|---|---|---|
| Phase 1 | ✅ Done | Connectors, DataModel, DataSet + lineage |
| Phase 2 | ✅ Done | Report Engine (Excel, HTML, manifest) |
| Phase 2.5 | ✅ Done | Medallion architecture, Star schema, Lineage diagram |
| Phase 3 | ❌ Removed | Dashboard server (Dash) — cut 2026-07-27, see entry below |
| Phase 4 | ✅ Done | Pipeline runner (APScheduler, DB write-back, cross-layer lineage) |
| Phase 5 | ✅ Done | Web UI (FastAPI + React, medallion-aware demo) |
| Phase 6 | ✅ Done | DuckDB engine, push-down filters, layer rename, CLI, auto-discovery, auth, docker-compose |
| Docs | ✅ Current | Reconciled 2026-08-19 to the current product: artifact-package phase ③, the removed `requests/` lane (0.8), the 11-tool + `author_report`-prompt gateway, and the trust-layer identity. Volatile counts now say "run `pytest tests/`" rather than a frozen number. |
| Phase 7 | ✅ Done | Correctness sweep, open-core seam, capability surface, ReportSpec, SVG charts, theme layer |

---

## 2026-08-19 — Design decisions of the artifact arc (recorded after the fact)

These landed across the reshape and its fix-waves and were, until now,
recorded only in the CHANGELOG. Kept terse; each names where the decision
lives in code.

- **Sink contracts** (`tracebi/contracts.py`). A transform may close with a
  `with contract(...)` block of declarative checks run as read-only SQL
  against the tables it just sank. Failure raises at sink time; success
  records `data/warehouse.contracts.json` with connector-load-path
  fingerprints. Locked language: *the sink satisfied its contract* — never
  "the transform was verified." Report manifests join against it; status
  `stale` never reads green.
- **The figure-claims layer + verify v2** (`figures.py`, `template_package.py`
  `_validate_figures`, `verify.py`). A manifest records per-figure claims
  (id / kind / binding / cell / unverified). The build refuses a data-bearing
  figure that neither names a binding nor is marked `data-tb-unverified` —
  the *no third state* guarantee is enforced, not aspirational.
- **The presentation stack order** (`tracebi/reports/stack.py`). One place
  composes the page: reset → theme → runtime → author CSS/JS, later layers
  winning. Derivation (`derive.py`) fills labels/formats the author left
  unset but **must never change the number it presents**.
- **The workbench + human pins + `tracebi dev`** (`workbench.py`,
  `_dev_server.py`). A live authoring surface over a package (figures,
  coverage, per-binding cards, pins); with no report named, discovery mode is
  the same surface over phases ① and ②.
- **The embedded semantic-contract slice + the subsetting rule**
  (`capabilities.py`, `tracebi.js`). The artifact carries what the model's
  vocabulary meant; interactive controls subset which stamped rows a figure
  displays and **never compute a new number**, so value figures never react
  and a filtered KPI needs its own binding.
- **pandas-3 dtype canonicalization.** The pandas-3 string-dtype rename moved
  fingerprints; the fix pins a canonical serialization so a correct report
  reproduces across pandas majors (fingerprint corpus green on 2.2 and 3.0).
- **The `requests/` lane removed (0.8).** The ad-hoc script lane had no
  receipt and no way to earn one; a report is authored only as an artifact
  package. Every surface (CLI, public API, web API, UI, discovery) was pruned.

---

## 2026-08-14 — The three-phase workflow becomes the spine

The framing shifts. TraceBi has been described, for a year of these notes, as a
trust layer bolted onto code-first reporting — stamped queries, manifests,
`tracebi verify`. That machinery is real and stays, but it was the answer to a
question nobody outside this repo was asking first. The question they ask first
is: *how do I get from a messy export to a page I trust?* So the product is now
organised around that arc — a **three-phase workflow**, messy to reportable,
with the trust story hanging off phase boundaries rather than being the whole
pitch.

> **Superseded (2026-08-19):** the emphasis in this entry reads the wrong way
> round. The canonical identity is **the trust layer for AI-generated
> analytics** (MANIFESTO §"Why it is shaped this way"; README opening); the
> three-phase workflow is *how* that trust is delivered, not a replacement for
> it. Keep the workflow framing below, but the trust layer is the identity.

### The three phases, each a project-root folder

| Phase | Folder | What it is | Reference impl |
|---|---|---|---|
| ① **Transform** | `transforms/` | Ordinary, unconstrained pandas — window functions, prose parsing, cleaning — that *sinks* clean star-schema tables into a file-backed DuckDB warehouse. The framework does not constrain this phase. | `examples/portfolio_project/transforms/holdings_transform.py` |
| ② **Model** | `models/` | A declarative `DataModel` (grain, keys, measures) over the warehouse, read by a reviewer without opening the pandas above it. It reads the sink; it never sees the transform. | `examples/portfolio_project/models/portfolio_model.py` |
| ③ **Report** | `reports/` | A `ReportSpec` (JSON) pointed at the model — KPI cards, charts, tables — where every figure is a live query, re-rendered in milliseconds. (Also the home of template packages and `@register.report` factories — one folder for every report form.) | `examples/portfolio_project/reports/portfolio_dashboard.json` |

Note on the word: this workflow phase ③ artifact is a *rendered `ReportSpec`
artifact*, not a live server — it has nothing to do with the Dash-based
"Phase 3 dashboard server" cut on 2026-07-27 (Build Status table above). The
old thing was a running process; this is a JSON spec that renders to HTML.

### The freeze points, and why they matter

The phases are decoupled by two **freeze points** — a materialized artifact
handed from one phase to the next: `warehouse.duckdb` between ① and ②, and the
model itself (the semantic contract) between ② and ③. The reason to build it
this way is that the two phases with opposite cadences never block each other.
Phase ① is slow, unconstrained, run when the source changes. Phase ③ is fast
and iterated — a designer reshapes cards all afternoon. Because the model is a
frozen contract between them, **editing a report never re-runs the
pandas**. That is the whole payoff of the split, and it is why the sink is
file-backed DuckDB rather than an in-process frame.

### Honest scope of lineage — the line is drawn at the sink

State this plainly, because the project has been burned by overselling before.
Lineage is **not** traced *through* phase ①. The raw analysis — the window
functions, the prose parsing — is deliberately outside the audit boundary. The
framework draws the line at the **sink**, where numbers become a contract you
can report against. The trust machinery (stamped queries with a resolved query
+ lineage + SHA-256 fingerprint; validate-before-execute on specs; `tracebi
verify`) applies **from the model boundary onward** — phases ② and ③. `tracebi
verify` re-runs a manifest's recorded queries and compares fingerprints; it
does **not** read a transform and does **not** assert a number is correct.
Never claim it verifies the phase-① analysis. The contract is not *how* you
clean; it is *what* lands — the named tables at the end of the script.

### What shipped

- The reference project (now at `examples/portfolio_project/`):
  `transforms/holdings_transform.py`, `models/portfolio_model.py`,
  `reports/portfolio_dashboard.json`, `run_workflow.py`,
  `inputs/generate_raw.py` (+ `inputs/holdings.csv`),
  `WORKFLOW.md`. `python run_workflow.py` builds the warehouse (phase ①) and
  renders the dashboard once, offline; `python -m tracebi.web.run` serves it.
- **Phase ③ specs live in `reports/`.** There is no separate `dashboards/`
  folder or `TRACEBI_DASHBOARDS_DIR`: a report has always been a name and a
  zero-arg callable, so specs, template packages, and factories all share the
  one `reports/` folder (`TRACEBI_REPORTS_DIR`), auto-discovered at startup.
- **Query-bound KPI cards.** A `"metrics"` spec section may now carry a `data`
  query; a card whose `value` names a measure reads it live from a one-row
  result instead of hard-coding a number that goes stale. Proven in
  `reports/portfolio_dashboard.json` — `value: "fair_value"` etc. over a
  measures-only query.
- **The web UI leads with the workflow.** Home renders a workflow flowchart
  (`components/WorkflowDiagram`), and there is a dedicated `/workflow` page.

### Next step — the AltsVault worked example

The reference impl runs on synthetic holdings from `generate_raw.py`. The
**intended** worked example drives phase ① from real AltsVault API output — a
genuine messy-to-reportable arc on data that was not shaped for us. Recording
it as the next step, **not** as something built: nothing in the repo pulls from
AltsVault today.

---

## 2026-08-13 — The app moved to `tracebi.web.api` (a name is a shared resource)

The wheel had just started shipping the FastAPI app so `tracebi serve` would
work from a pip install. It did — by installing a directory literally named
`web/` into site-packages. `web.py` is a real, long-lived PyPI distribution
that owns that exact path. Two wheels writing the same path is not an error
pip has an opinion about: the second install overwrites the first's files,
`pip check` reports nothing, and one of the two distributions silently stops
working. Reproduced by execution — install `web.py`, then the old TraceBi
wheel, and `hasattr(web, "application")` flips from `True` to `False`.

**The fix is a namespace, not a shim.** The app is now `tracebi.web.api`,
which is pure prefix insertion (`web.api.X` → `tracebi.web.api.X`) and so
preserves every seam that already existed, including the registry re-export
that a test rebinds for isolation. No compatibility shim ships at top-level
`web`: a shim only helps an installed user if it is *packaged*, and packaging
it re-creates the collision. Pre-1.0 and unpublished, the rename plus a
breaking-change entry is the honest trade.

Two things worth remembering:

1. **The bundle moved into the package, the Node workspace did not.**
   `web/ui/` is still a Node workspace at the repo root — it is not Python and
   has no business inside the distribution. But vite's `build.outDir` now
   writes to `tracebi/web/ui/dist`, because `main.py` finds the UI at
   `<its own dir>/../ui/dist` and that expression, after the move, already
   resolved to the right place. The lookup did not change; the output did.
   Every build path has to agree on this — Dockerfile, `vercel.json`, both CI
   workflows, `.gitignore`, `.dockerignore`.

2. **`web/__init__.py` was deleted, and that deletion is load-bearing.** The
   top-level `web/` directory still exists in the checkout (it holds `ui/` and
   `requirements.txt`). Without an `__init__.py` it is only a PEP 420
   namespace *portion*, and a regular package anywhere on `sys.path` beats a
   namespace portion regardless of order — measured: from the repo root with
   `web.py` installed, `import web` resolves to site-packages and
   `web.application` is there. Put a single `web/__init__.py` back and the
   same command resolves to the checkout and `web.application` is gone. So
   nothing importable may ever move back under `web/`, and a test pins both
   the absence of that file and the absence of any `*.py` beside it.

---

## 2026-08-03 — The agent gateway, and the inversion behind it

### The product question this answers

A long strategy discussion settled on a reframing: TraceBi's scarce asset is
not the report framework, it is **trust in machine-made numbers**. AI made
creating reports nearly free; believing them is becoming the expensive part.
The corporate question is "we want agents to access the warehouse and create
reports — how do we do that organized and controlled, with a reusable schema
defined for the agents?" The answer is a **semantic gateway**: the agent
never touches the warehouse, it speaks the model's vocabulary, and every
answer carries a receipt.

### The inversion

Previously the renderer was the mandatory door: to get governance you had to
produce a TraceBi-rendered report. That coupled control to presentation and
made every expressiveness gap (six sections, six chart types) a governance
leak — an author who needed more would route around the whole framework.

The gateway moves control down to **data access**, where it belongs, and
makes assurance graded rather than binary:

| Level | Agent does | Company can prove |
|---|---|---|
| L0 | Raw SQL, raw HTML | Nothing |
| L1 | Queries via gateway, renders its own HTML | Every number traceable |
| L2 | Emits a ReportSpec; TraceBi renders | Artifact reproducible |
| L3 | L2 + signed manifest + re-verification | Attestable (future) |

At L1 the agent has unlimited presentation freedom — the framework's
expressiveness ceiling stops being a cage and becomes the premium lane. This
was **not a pivot**: the framework and the gateway are two doors into one
kernel (the dbt Core / dbt Cloud pairing), and the gateway's "reusable
schema" *is* the `DataModel` the framework always had.

### What was built

`tracebi/mcp_server.py` + `tracebi mcp` (extras key `mcp`). Eight tools:
`get_context`, `list_models`, `describe_model`, `query_model`,
`validate_report_spec`, `render_report_spec`, `list_reports`,
`verify_manifest`.

> **Updated (2026-08-19):** the surface grew to **11 tools + 1 `author_report`
> prompt** — added `workbench_state`, `build_report` (renders an artifact
> package over MCP), and `fetch_artifact` (returns the built bytes, closing the
> agent-can't-deliver gap).

Decisions worth recording:

- **The stamp covers the full result; rows are transport.** `query_model`
  caps rows (default 50, hard cap 500) but fingerprints the uncapped
  DataSet, and a test pins that capping cannot change the fingerprint. An
  agent quoting a number beyond the cap is still auditable: re-run the
  recorded query, compare hashes. The smoke test showed the raw query
  fingerprint and the rendered report's manifest fingerprint coming back
  identical — same hash, provably the same data — which is the entire
  product in one line of output.
- **Read-and-compute only.** No pipeline execution over MCP yet: that
  writes to the warehouse, and per-agent scopes (which models, which
  operations, per credential) don't exist. Adding writes before scopes
  would put the highest-privilege operation on the least-attributable
  surface.
- **Plain functions under a thin MCP skin.** The `gateway_*` operations are
  ordinary functions; `build_server()` is the only place `mcp` is imported
  (fail-loudly rule). The suite tests the gateway with no MCP dependency;
  one `importorskip` test checks tool registration.
- **`render_report_spec` refuses an invalid spec** rather than rendering
  best-effort. An artifact from a spec that failed validation is exactly
  the ungoverned output the surface exists to prevent.
- Attribution reuses the audit ContextVar: `mcp:<TRACEBI_MCP_ACTOR>`.

Side effect discovered while wiring: installing `mcp` upgraded starlette
past the pinned-by-luck fastapi, breaking every TestClient test with
`Router.__init__() got an unexpected keyword argument 'on_startup'`.
Fastapi upgraded to match; suite back to green (620).

### Open

- **Per-agent scopes** — which models/measures per credential; the gate for
  ever exposing pipeline runs over MCP.
- ~~**`tracebi verify`** — drift-aware re-verification.~~ Shipped: input
  fingerprints are recorded at render, and `verify` (plus the gateway's
  `verify_manifest`) classifies reproduces / source drift / model changed /
  mismatch / unexplained / unverifiable / error.
- **L1 receipts for foreign renderers** — a stable URL or token per stamped
  query an agent can cite from its own HTML.
- ~~The HTTP transport has no auth of its own yet~~ — since the Now-tier
  sprint the HTTP transport requires `TRACEBI_MCP_TOKEN` (bearer) or an
  explicit `--insecure`; per-agent scopes remain open.


## 2026-07-27 — Deployment planes, and what a corporate rollout requires

Written after taking tracebi.com live on Vercel. The question that prompted it:
is this the right stack given the product eventually goes to corporations, and
should the requirements be split along some logical line? Recording the
reasoning now because the answer turns out to be about the registry, not the
host, and that is easy to forget once the site is up and working.

### What Vercel actually costs, measured rather than assumed

| Constraint | What we observed |
|---|---|
| Scheduling | Cannot work at all. Every layer registers a cron (`"0 * * * *"`), and APScheduler needs a process that outlives a request. On serverless those schedules are decorative. |
| Run history | Does not persist. The demo pipeline's SQLite now falls back to the system temp dir, which serverless scopes per-invocation. |
| Background report runs | Worked, but by luck. `POST /reports/{n}/runs` then polling went running → succeeded over ~9s only because Fluid compute reused the instance holding the in-memory run registry. A poll landing on a cold instance finds nothing. |
| Function size | The 250 MB limit already forced `api/requirements.txt` to drop matplotlib, networkx and apscheduler relative to the project extras. |
| Cold start | ~1.4s to import with the demo app, including a full six-layer pipeline run. Most of that is pandas and would be paid anywhere. |

None of these are platform defects. They are the shape of serverless meeting the
shape of a stateful framework.

### The comparison that clarified it

AltsVault (`bdc-fund-dashboard`) runs happily on Vercel + Supabase, which
invites the conclusion that it simply does not need functions. It does — there
is a full set under `src/app/api` (compare, fund, graph, leaders, coinvest…).
The difference is what those functions are asked to do:

```
[pipeline/ — its own installable Python package, never deployed to Vercel]
        │ writes
        ▼
[Supabase Postgres]        ← the contract
        ▲
        │ reads
[Next.js on Vercel — stateless, request-scoped]
```

Its batch and stateful work was moved out of the serving layer entirely.
Vercel is fine there because nothing stateful is ever asked of it.

TraceBi collapses those planes into one process. That is the whole difference.

### Three planes

| Plane | What lives here | Where it can run | State |
|---|---|---|---|
| **Definition** | `models/`, `reports/`, `pipelines/` as code | git | none |
| **Execution** | pipeline runs, materialisation, schedules | container, cron, Airflow, whatever the org already operates | **writes** Postgres |
| **Serving** | FastAPI read+compute, React UI | anywhere, stateless | **reads** Postgres |

Postgres — or any SQLAlchemy URL — is the seam. Make that the contract and
every other piece becomes swappable, which is what "agnostic to the underlying
pieces" actually requires in practice.

### The coupling that blocks it

`tracebi/registry.py` is a process-global singleton populated at import. That
one decision is why:

- the web server must import the app module, and therefore runs whatever that
  module runs — which is exactly why the demo pipeline's read-only filesystem
  failure took the reports and connectors down with it
- the scheduler has to live in the web process
- background run ids live in memory and cannot survive a second instance

The host is downstream of this. Moving off Vercel without addressing the
registry buys working schedules and little else.

### What is already agnostic

More than expected, and worth not undoing:

- ~~`PipelineRunner(db_url=...)` and `SQLConnector` both accept any SQLAlchemy URL~~
  **Wrong when written, corrected 2026-07-27.** `SQLConnector` was fine.
  `PipelineRunner` accepted any URL and worked only on SQLite: the schema DDL
  used `INTEGER PRIMARY KEY AUTOINCREMENT`, the layer upsert used
  `INSERT OR REPLACE`, and run ids came from `last_insert_rowid()` — all three
  SQLite-only. Pointing it at Postgres, which is exactly what
  `docs/deploy-vercel-supabase.md` §5 instructs, raised on the first
  `CREATE TABLE`. This was assumed from the signature rather than checked, and
  only surfaced on actually running it. Now dialect-aware and verified against
  a real Postgres end to end.
- `pyproject.toml` extras already name the planes — `pipeline` (apscheduler,
  sqlalchemy), `web` (fastapi), `reports` (matplotlib), `lineage` (networkx),
  with `pandas` as the only core dependency. The logical split being asked for
  is already declared; it is the deployment that ignores it.
- proxy-header auth (`TRACEBI_AUTH_PROXY_HEADER` + `TRACEBI_AUTH_PROXY_TRUSTED_IPS`)
  is the shape that sits behind corporate SSO
- a Dockerfile and docker-compose already exist

### What a corporate rollout adds

| Requirement | Status |
|---|---|
| Bring your own Postgres | Supported today |
| SSO | Proxy-header mode fits; trusted-IP configuration needs documenting, not building |
| No outbound egress | Inter is now self-hosted rather than CDN-loaded. Worth auditing that nothing else reaches out. |
| Container delivery | Dockerfile exists |
| **Multi-tenancy** | **Open.** One global registry per process means one tenant per process. This is the decision with the largest blast radius and it has not been made. |

### Recommendation

Ship the product as a container with Postgres as its only hard dependency and
scheduling pluggable. Vercel then becomes one deployment target for the demo
and marketing surface rather than the architecture. This is also what
`docs/deploy-vercel-supabase.md` already prescribes — "run the API in a
container and keep only the UI on Vercel" — so the split is a matter of
following advice the project already gives, once the registry allows it.

### First step taken — `tracebi run-pipeline`

Investigating the above turned up something sharper than "the registry is a
singleton": **there was no way to run a pipeline outside the web server at
all.** The CLI's `run` executes a request script; `list-pipelines` only lists
files. The single execution path was
`POST /api/pipelines/{name}/layers/{layer}/run`. Batch work was not merely
coupled to the serving process, it was only expressible as an HTTP request to
it.

`tracebi run-pipeline <name>` closes that, built entirely on existing public
runner API (`layers`, `execution_order`, `execute_layer`, `last_run`):

- no `--layer`: every registered layer, upstream-first, each run once
- `--layer X [--refresh]`: one layer, optionally preceded by its chain
- `--status`: last run per layer, executing nothing
- non-zero exit if any layer fails, and it reports *every* failure rather than
  stopping at the first — downstream layers read what upstream wrote, so a
  partial run leaves the rest resting on stale data and the operator should
  see the whole picture

Any external scheduler can now drive execution: cron, a Kubernetes CronJob,
Airflow, CI. That is the execution plane becoming addressable, and it is the
prerequisite for the container split — the serving plane can stop being the
only thing that can do work, without the registry being touched at all.

Note this does *not* by itself fix the demo: on serverless with a
per-invocation temp filesystem there is nowhere durable for an execution
plane to write, so `tracebi/web/demo_app` still runs its pipeline at import. The demo
can only be split once it has a real database behind it. That ordering —
Postgres first, then split — is worth respecting.

### Open decisions

- Multi-tenancy: one process per tenant, or a registry that can hold many?
- Should the serving plane be permitted to trigger execution at all
  (`POST /pipelines/{n}/layers/{l}/run`), or is that strictly the execution
  plane's job with serving reduced to reads?
- Requirements profiles: a serving install (light, no apscheduler or
  matplotlib) versus an execution install (full). The extras already exist;
  what is missing is a documented pairing of profile to plane.

---

## 2026-07-27 — Product scope review, correctness sweep, and the AI-authoring turn

A long session. Three things happened: a full scope review that changed the
positioning, a correctness sweep that found seven silent-wrong-output bugs,
and the beginning of the AI-authoring architecture. Recording the decisions
and — more usefully — what was rejected and why.

### Positioning, settled

| Question | Decision |
|---|---|
| ETL scope | **Own the last mile.** Landing/Manipulation/Final stay, for transforms close to the report. Not a dbt/Airflow/Dagster competitor; stop implying we own ingest. |
| Associative model | **Drop the Qlik framing entirely.** Owner: *"i dont want to copy qlik, i feel like we can get away with just a good well defined semantic model."* |
| Open core | Library (`tracebi/`) eventually OSS, web app proprietary. Fix the seam now, publish later. |
| AI direction | External agent toolkit first, building toward AI-authored reports and front-ends. |

The Qlik claim was a check the code could not cash. None of Qlik's three
defining features existed — no selection-state propagation, no automatic
key association, no set analysis — and the dashboard's filter code literally
said `# column not present — skip (associative: no error)`. Dropping the
claim removed a marketing liability; it did **not** remove the obligation to
have a good semantic layer, so the same session added dimension-attribute
filters, twelve operators, named measures, and `QuerySpec`.

### The seven bugs, and the pattern in them

All seven produced **silently wrong or unverifiable output** — the exact
failure mode this framework exists to prevent:

1. Dimension fan-out: $150 of revenue reported as $250, with a complete
   lineage chain attached. The lineage already recorded `rows_left`/
   `rows_after` — the framework observed the fan-out, wrote it into the audit
   trail, and said nothing.
2. Non-deterministic row order: identical queries produced different
   `fingerprint()` values, so manifest fingerprints were not re-verifiable.
   DuckDB returned hash order; pandas `groupby` sorts. The two engines also
   disagreed with each other.
3. `heading1`/`heading2` discarded `content`, losing real narrative in five
   of seven demo reports.
4. Nested `RowSection` vanished from the lineage walk — the most elaborate
   reports were the ones losing their audit trail.
5. `import tracebi` hard-required networkx against a pandas-only dep list.
6. A broken file in `reports/` took down server startup entirely.
7. A missing chart column silently plotted zeros — **a regression I
   introduced hours after fixing the same class of bug**, while rewriting the
   chart renderer.

**Four of the seven surfaced from tests written for something else**, and the
seventh came from a rewrite forgetting why a check existed. None would have
been found by reading code. The implication for the AI direction is direct:
when an agent writes the analytics, the human magnitude-check disappears, and
this stops being an embarrassment and becomes the primary risk. Bias hard
toward loud failure and toward tests that assert *absence* of a wrong answer,
not just presence of a right one.

### Cut: the Dash dashboard layer

Removed, 1,047 LOC plus mounting. Three compounding problems:

- **No lineage export.** A dashboard could show a number with no audit
  trail, contradicting the whole premise.
- **Filters did not traverse relationships.** A "filtered" dashboard could
  mix filtered and unfiltered numbers side by side.
- **It forced a second charting stack** (Plotly alongside matplotlib), and
  two chart grammars is what blocked unifying on one declarative spec.

Explore plus the report engine already cover most of the use case, and both
carry lineage. If live dashboards return, they should be a spec over the same
sections, sharing one chart grammar and inheriting lineage for free.

### Rejected: Vega-Lite for charts

Charts moved from base64 matplotlib PNGs to inline SVG. Vega-Lite was the
obvious candidate — it *is* a JSON chart grammar, which is what an agent
should emit — and it was rejected deliberately:

- Needs a browser plus either a CDN or ~300 KB of bundled JS.
- Cannot produce a static artifact server-side without Node.
- A rendered report must stay a single self-contained file that still opens
  in six months with no network. That property beats interactivity **for an
  archived audit artifact**, and the live-dashboard case that would have
  justified Vega-Lite had just been deleted.

Hand-rolled SVG gets diffability, theming, and responsiveness with no
runtime. Side effects: reports shrank ~75% (base64 PNGs were most of the
weight), and charts stopped needing matplotlib at all — a base install had
been rendering the literal text *"matplotlib required for charts"* where
every chart should have been.

### The keystone: reports as data

`ReportSpec` — presentation structure plus a declarative `DataRef`
(model + `QuerySpec`) instead of a live `DataSet`. This is what makes
AI-authoring tractable, because it enables **validation before execution**:
section types, field names, enum values, and whether the referenced model,
fact, measures and dimensions exist — all checked without loading a row,
with errors carrying a path like `sections[0].sections[1].data.query.fact`.

Two design rules worth preserving:

- **Sections serialize generically from their dataclass fields**, never
  through parallel spec classes. Duplicating the definitions would drift the
  first time someone added a field. A test asserts the mapping covers every
  `SectionType`.
- **Measures are declarative data, never callables.** A lambda cannot be
  serialized, diffed, reviewed, or validated before execution. Accepting one
  would forfeit reproducibility at the root. This is the single most
  consequential API constraint in the codebase — do not relax it.

`Report → spec` is best-effort by design: a dataset built from ad-hoc
transforms has no declarative form, and `data_coverage()` reports that rather
than pretending it round-trips.

### Template layer, and what stayed in Python

`Theme` (stylesheet as data), custom Jinja2 page shells, and a
`section_renderers` registry. Jinja2 had been declared in `pyproject.toml`
three times and imported nowhere; it now gates exactly one thing — a custom
shell — and the built-in shell needs no template engine, so reports still
work on a base install.

Section *internals* stayed in Python on purpose. Table formatting and chart
geometry are logic, not layout; as templates they would be harder to read and
harder to test. What you override is the shell, the styling, and whole new
block types.

Default output was verified **byte-for-byte identical** across all seven demo
reports. The first attempt was two blank lines off from empty head/body
placeholders — fixed rather than waved through, because "probably fine" is
how output drift starts in a tool whose promise is reproducibility.

### Deployment: Vercel + Supabase

Moved off Railway. Vercel hosts the UI and the FastAPI layer as Python
serverless functions; Supabase Postgres is the data source and pipeline
history store.

This fits for a non-obvious reason on each side: TraceBi never caches a query
— every call recomputes from source — which is what an ephemeral function
wants; and Supabase provides a *remote* Postgres, fixing the one thing
serverless otherwise breaks (default SQLite on a local disk).

**The SVG chart work is what made it viable at all.** Functions cap at 250 MB
unzipped and the full dep set is ~199 MB; dropping matplotlib (~35 MB) and
networkx (~17 MB) brings it to ~150 MB.

Three things cannot work on serverless, documented rather than discovered in
production: the scheduler (APScheduler needs a process outliving the
request), background report runs (the `run_id` lives in an in-process thread
pool, so the next poll hits a different process), and local SQLite.

### Open

- **`docs/overview.html`** — 38 KB, stale. Documents the removed Dash layer
  and Jinja2 templates that did not exist until this session. Rewrite or
  delete.
- **`tracebi.yaml`** — removed. It was scaffolded by `init` and parsed by no
  code, inviting users to configure a connector that would never be read.
  Restorable as a real project manifest if wanted.
- **Lazy `DataSet` over a query graph** — still the eventual scaling wall.
  DuckDB currently registers full pandas frames rather than pushing down, so
  it is a local aggregation engine, not a query engine. Not blocking
  anything; the seam is designed to allow it.
- **The MCP server** — should now be thin: it mostly wraps `describe()`,
  `ReportSpec.validate()`, `discovery_report()`, and the render endpoints.
- **Six merged branches** deleted; repo is down to `main`.


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

> **Superseded (2026-08-19):** the package layout that once sat here listed
> `dashboard/` (Dash — removed 2026-07-27) and `requests/` (the ad-hoc lane —
> removed in 0.8). The current, maintained layout lives in **CLAUDE.md →
> Repository Layout**; do not duplicate it here.

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

- **Registry** (`tracebi/web/api/registry.py`) — central singleton; connectors, models,
  reports, pipelines, and dashboards are all registered here at startup
- **App module** (`tracebi/web/demo_app.py`) — imported on startup; detects `data/tracebi.db`
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
TRACEBI_APP=myproject.tracebi_config python -m tracebi.web.run
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

## 2026-06-12 — Project-Root Artifact Directories

### Decision

Models and pipelines were only definable inside the web app module package
(`tracebi/web/demo_app/`), meaning an analyst had to understand the web layer to
reuse anything across notebooks. The new convention makes all four artifact
types first-class project-root citizens, usable with or without the web server:

```
my_project/
  models/       # DataModel definitions
  pipelines/    # PipelineRunner definitions
  reports/      # Named web-exposed report factories
  requests/     # Ad-hoc parameterised report scripts
```

### How each works

**`models/` and `pipelines/`** use a variable-name convention: the file must
expose a module-level `model` (DataModel) or `runner` (PipelineRunner).
`tracebi/model_registry.py` and `tracebi/pipeline_registry.py` provide
standalone lazy-loading registries that auto-discover these directories from
cwd on first access — no web server required.

**`reports/`** uses the existing `@register.report()` decorator pattern.
Files are imported at server startup and the decorator fires as a side effect,
exactly like `requests/` files already worked.

**`requests/`** is unchanged — ad-hoc parameterised scripts with `run()`.

### Web server auto-discovery

`tracebi/web/api/main.py` scans all four directories at startup using
`TRACEBI_MODELS_DIR`, `TRACEBI_PIPELINES_DIR`, `TRACEBI_REPORTS_DIR`,
`TRACEBI_REQUESTS_DIR` (defaults: directory names without leading path).
Models and pipelines are loaded via their respective registries and registered
into the web registry; reports and requests use the existing `auto_discover()`
decorator-firing path.

### App module role narrowed

`TRACEBI_APP` / `tracebi/web/demo_app/` remains the right place for connector
construction (credentials come from env vars, not from a file convention) and
for Dash dashboard wiring. Models, pipelines, and named reports no longer need
to live there — `tracebi/web/demo_app/` is now a reference for connector + dashboard
wiring, not the mandatory home of all project configuration.

### Notebook/script workflow

```python
from tracebi.model_registry import get_model, list_models
from tracebi.pipeline_registry import get_runner

model = get_model("sales_model")     # loads models/sales_model.py lazily
runner = get_runner("sales_etl")     # loads pipelines/sales_etl.py lazily
runner.run("orders_silver")
```

### CLI additions

- `tracebi new-model "Sales Model"` → `models/sales_model.py`
- `tracebi list-models`
- `tracebi new-pipeline "Sales ETL"` → `pipelines/sales_etl.py`
- `tracebi list-pipelines`
- Global flags: `--models-dir`, `--pipelines-dir`

### TODO (resolved)

- [x] Create `tracebi/model_registry.py` with lazy-loading registry
- [x] Create `tracebi/pipeline_registry.py` with lazy-loading registry
- [x] Add CLI scaffold commands for models and pipelines
- [x] Auto-discover `models/`, `pipelines/`, `reports/` in `tracebi/web/api/main.py`
- [x] Update `tracebi.web.register` to fall back to standalone registries
- [x] Update all docs (README, CLAUDE.md, analyst-guide, notebook-guide, web-customization, CHANGELOG, .env.example)

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
| 3 | `threading.RLock` around Registry mutators and compound reads | `tracebi/web/api/registry.py` |
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
7. `tracebi/web/api/registry.py` mutated at import time — under uvicorn `--reload` can produce duplicate registrations. Guard with `is_registered` check, or `Registry.from_module(name)` factory that wipes state first.
8. `tracebi/web/api/routers/*` endpoints are sync, calling blocking pandas. Single-worker uvicorn serializes all requests. Convert to `async def` + `await asyncio.to_thread(...)` or document multi-worker as required.
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

`tracebi/web/demo_app.py` is a monolithic file (~460 LOC) mixing data setup, reports,
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
  demo_app/                    ← replaces demo_app.py; TRACEBI_APP=tracebi.web.demo_app
    __init__.py                ← from tracebi.web.demo_app import registry  (triggers wiring)
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

- `TRACEBI_APP=tracebi.web.demo_app` must keep working (no change to the env var).
- `model` object from `model.py` is the shared default — `pipeline.py`,
  `dashboard.py`, and reports all import from `model.py`, never redefine it.
- `registry.py` is the only file that imports from `tracebi.web.api.registry` —
  individual report files stay pure Python (importable without the web stack).
- `pipeline.py` creates `_runner` and runs the startup sequence; `registry.py`
  calls `registry.add_pipeline("sales", _runner)`.

### TODO (completed 2026-06-05)

- [x] Create `tracebi/web/demo_app/` folder with the layout above
- [x] Migrate each report function to its own file under `reports/`
- [x] Pull connector + DataModel into `model.py`
- [x] Pull pipeline layers + PipelineRunner into `pipeline.py`
- [x] Pull Dashboard + DashboardServer into `dashboard.py`
- [x] Write `registry.py` that imports + wires everything (except reports)
- [x] Write `__init__.py` that imports registry (side-effect import)
- [x] Delete `tracebi/web/demo_app.py`
- [x] `TRACEBI_APP=tracebi.web.demo_app` still works — resolves to `__init__.py`
- [x] Full test suite: 243 passed, 0 regressions

---

## 2026-06-09 — Registry Seam Hardened + Explore Query Builder

A principal-level audit (see PR #21) found the web layer reaching into
`_private` attributes of framework objects — the registry was documented as
"the seam" but the seam was fiction. Decisions made:

### Public surfaces are now the contract

- `PipelineRunner.layers()` / `last_run()` / `run_history()` /
  `execute_layer()` / `execution_order()` — routers never touch `_layers`,
  `_engine_()`, or `_execute()` again. History queries are parametrized.
- `DataModel.info()` — full structure (tables, relationships, facts,
  dimensions) as a dict. `describe()` keeps printing for humans.
- `BaseConnector.describe()` — replaces hasattr-sniffing that silently never
  matched CSV/SQL connectors. `SQLConnector` redacts passwords via
  SQLAlchemy's `render_as_string(hide_password=True)`.
- `Registry.dashboards()` — main.py no longer iterates `_dashboards`.

Rule going forward (also in CLAUDE.md anti-patterns): a router that needs
something new gets a public method on the framework object, not an
underscore reach-in.

### Explore (visual query builder)

`POST /api/models/{name}/query` wraps `DataModel.query()`. ValueError
(unknown fact/dim/agg) → 400 with the message; runtime failures → 500 with
`{message, exception_type, traceback}`. The UI builds queries from
`model.info()` facts/dimensions and renders the result + the lineage graph
of that exact run — the "show your work" pitch made tangible.

Chart is pure CSS bars — deliberately no chart library in the React bundle;
revisit only if Explore needs more than 1-dimension visuals.

### Deployment posture

Demo/MVP hosting only (Railway). Therefore: warn-don't-refuse when auth is
missing; `.dockerignore` keeps `.env`/DBs out of image layers; proxy auth
without trusted IPs warns about header spoofing. If TraceBi ever targets
self-serve production hosting, revisit refuse-to-start.

> **Superseded 2026-07-27.** Railway is gone — `tracebi.com` pointed at a
> deleted Railway app returning "Application not found" until it was repointed.
> The demo now runs on Vercel at `www.tracebi.com` with the apex redirecting,
> serving `tracebi.web.demo_app` via `TRACEBI_APP`. The reasoning above still holds and
> is now load-bearing rather than hypothetical: the deployment is public with
> **no auth at all**, a deliberate call given both models are synthetic
> `MemoryConnector` data and no credentials are deployed. The exposure is
> compute abuse, not disclosure. That calculus inverts the moment a model
> points at real tables — see the deployment-planes entry above.

### Open follow-ups (agreed, not yet built)

- Background report execution (run id + polling) — after PR #21 merges.
- CI constraints file for deterministic installs; coverage reporting.
- `logging` adoption in runner/web (zero `import logging` outside renderers).

---

## 2026-06-11 — Lineage Hardening Sprint (P0/P1 execution)

Executed the remaining P0 and quick-win P1 items from the 2026-05-22
architecture review. Theme: make the audit-trail promise actually hold.

### Shipped

| Review item | Status |
|---|---|
| P0-1 Parameterize pipeline SQL | Already done in PR #21 |
| P0-3 `RLock` around Registry | ✅ All mutators + compound reads guarded |
| P0-4 Per-layer run lock in PipelineRunner | ✅ In-process `threading.Lock` per layer; concurrent run raises `RuntimeError` |
| P0-5 Frozen `LineageNode` | ✅ `@dataclass(frozen=True)`; `connector`/`metadata` are `MappingProxyType` |
| P1 `git_sha` in `ReportManifest` | ✅ Cached `git rev-parse HEAD`; falls back to `"unknown"` |
| P1 SHA-256 fingerprint | ✅ Canonical columns + dtypes + CSV bytes; deterministic across pandas versions |
| P1 `query()` raise on missing dim attributes | ✅ Plus measure and filter columns — all with did-you-mean hints |

The `query()` validation also fixed a silent-wrong-answer bug: the pandas
engine skipped filters whose column didn't exist (`if col in df.columns`),
so a typo'd filter returned **unfiltered** data. Both engines now fail
loudly before execution.

### Deliberately not done (still open)

- P0-2 Credential callables/env-var indirection in connectors —
  `SQLConnector.describe()` already redacts passwords; full credential
  rework is a bigger change.
- ~~Per-layer lock is in-process only. Multi-worker uvicorn or multiple
  schedulers on one DB can still race; a DB advisory/file lock is the
  cross-process answer if that deployment shape becomes real.~~
  **Done 2026-07-27.** That deployment shape was already real — README,
  CLAUDE.md and docs/web-customization.md all show `uvicorn --workers 4`, so
  the docs were steering people straight into it. `_execute` now takes a
  `pg_try_advisory_lock` per layer on Postgres, keyed on a namespaced crc32 of
  the layer name; session-scoped, so a crashed worker's lock is released by
  the server rather than leaving a row to reap. Proved with two forked
  processes against a real Postgres: one RAN, one REFUSED, and with the DB
  lock neutered both ran. SQLite still yields True — it is the single-process
  fallback, and that is now documented rather than implied.
- Fingerprint is content-based but row-order-sensitive (intentional:
  reports are order-sensitive deliverables).
