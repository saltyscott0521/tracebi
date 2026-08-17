# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added — the session record, and a token-lean context tier

- **`tracebi session export`** — save the discovery notebook. The full
  feed (markdown cells, frame excerpts, chart sketches re-rendered as
  real charts, pins with notes) exports chronologically to ONE
  self-contained HTML in `explorations/` — the committed lab-notebook
  record of the analysis that shaped the pipeline. Each exhibit records
  the script that produced it, so the record links narrative → output →
  the committable code behind it. Honesty machinery included: the page
  carries the `exploration` stage stamp and a banner ("numbers here were
  live when shown and carry no receipts"), no manifest is ever written,
  and `tracebi verify` refuses it by name — a lab notebook can never
  impersonate a report. `tracebi session clear` resets a session (refused
  while its dev server is live). The distillation ladder: session record
  (how we figured it out) → contract notes (what the transform states) →
  report methodology appendix (what the reader sees).
- **`tracebi context --brief`** (and MCP `get_context(brief=true)`) — the
  token-lean vocabulary tier: ~2.3k tokens vs ~5.1k full (44%), carrying
  the semantic model, figure grammar, contracts, and conventions —
  everything the package-first loop needs — and naming what it omitted
  (section classes, DataSet verbs, cheat sheets) so more can be fetched
  deliberately. For agents on limited budgets, onboarding just halved.

### Added — the notebook loop, and methodology that travels the pipeline

Three asks from the maintainer's live session, built and drilled:

- **Chart sketches in discovery.** `show(df, chart="bar", x=..., y=...)`
  (all six runtime chart types) renders a real ECharts chart in the feed,
  with its recipe printed beside it. Iterate by re-showing; when the human
  pins one for the report, the agent re-expresses it as a model-query
  binding + figure — the sketch is exploration, the figure is the claim.
- **Markdown notes — the notebook cell.** `show("## Approach\n...")`
  renders as real markdown in the feed (escaped-first, the same safe
  subset the spec compiler uses), and a "read as document" toggle flips
  the feed from newest-first log to top-down narrative — the analysis
  reads like a notebook while it happens.
- **Data-wrangler-lite.** Frame and chart exhibits carry full-frame column
  profiles (nulls, distinct, min/max/mean, top values) behind a toggle,
  excerpt tables are click-to-sort, and warehouse tables in the discovery
  panel get the same profiles via read-only SQL aggregates.
- **Methodology annotations travel the pipeline** (the chosen design:
  pipeline annotations, no dev-state leakage). `contract(..., note=...)`
  and per-check `note=` record the transform's **stated methodology** in
  the certificate; measure descriptions carry modeling intent; one
  `<section data-tb-methodology>` in a template makes the build append
  them after the author's own prose, and the manifest records what
  shipped. The locked language extends: "the transform states" — never
  "verified methodology"; the appendix is prose, never badged, and never
  colors a status. Drilled on the reference project: the certificate's
  cleaning note and the truncated-pull rationale render in the shipped
  page, and verify stays green.

### Added — the discovery workbench: a live surface for phases ① and ②

The workbench previously started at the report — interrogating source data
and designing the model happened in chat, unseen. `tracebi dev` with **no
name** now opens the **discovery workbench**, the portal for the work
before any report exists:

- **Zero-config exhibits.** While the server is up, ANY script can call
  `tracebi.workbench.show(df, note=...)` — a heartbeat file makes the
  env var unnecessary — and the frame excerpt, dtypes, and note appear in
  the live feed. The moment the server is down (builds, CI), `show()` is
  a no-op again; the env var still wins when set explicitly.
- **The warehouse, watched.** Tables, row counts, and column dtypes as
  sinks land, with the sink-contract summary per transform (`5/5 checks
  passed`) beside them.
- **The model, taking shape.** Each model's facts, dimensions, and
  measures render live as `models/` files change; a broken file shows its
  error instead of vanishing.
- **Same pins, earlier.** The human pins warehouse tables and exhibits
  with notes ("before modeling: exclude the par=0 revolvers from the
  grain?"); the agent reads them via `workbench_state` called with no
  `report` — the steer-from-chat loop now covers the whole workflow, and
  the same portal flows into the figure loop once the package exists.
- Everything is dev-state: no receipts are minted before the model
  boundary, nothing enters builds or manifests.

Drilled live on the reference project: a probe script posted a
sector-concentration frame with no configuration, the warehouse panel
showed the three tables and the 5/5 contract, a table pinned in the portal
with a modeling question read back over MCP, and `show()` went silent the
moment the server stopped.

### Changed — the round-2 field-test wave: the new product is now discoverable

A second fresh-agent rebuild (same 233k rows, wiped project) confirmed the
reshape's substance and found its gap: everything new was invisible to the
files agents read first. Fixed:

- **The scaffolded `AGENTS.md` teaches the real product.** `tracebi init`'s
  agent guide now leads with the artifact package, the `data-tb-*` figure
  grammar, sink contracts, the workbench (and its pins), declarative
  `order_by`/`limit` for top-N, and the one rule extended to prose:
  **bind the numbers in your sentences** — any element (a `<span>`
  mid-sentence included) can be a value figure, so "explain the results"
  never needs a typed-in number. `tracebi context` documents the same
  under `presentation.prose_values`.
- **The scaffold demonstrates the one lane.** `tracebi init` now ships
  `reports/sample_dashboard/` — an artifact package with KPI cards, an
  inline prose-bound value, an ordered chart and table, and an exploration
  block that dies at build — instead of a legacy JSON spec. The first
  page a new project renders carries the stack, the badges, the figure
  claims layer, and a receipt that joins the scaffolded sink contract;
  the init loop now ends green under `verify --strict --contracts`.
- **`data-tb-value-format` works on every chart type and mode.** The pie
  branch ignored it (a bar showed `550.7B` while a pie painted
  `550696024575`); now pie, scatter, and the categorical types all format
  labels, value axes, AND tooltips, honoring every named mode (`decimal`
  included), not just `compact` — all with the guarded fallback (an
  unknown mode never blanks a number).
- **`decimal.Decimal` columns land exactly.** `DuckDBConnector.write()`
  casts object-Decimal columns to `DECIMAL(38,12)` — no more too-narrow
  inferred widths failing the sink, and no more silent float64 precision
  loss; the land-as-text workaround is obsolete.
- **`tracebi --version` tells the truth**: `0.6.0.dev0`. The reshape is a
  different product from 0.5.2 and is now programmatically
  distinguishable (the `.dev` marker is deliberate — nothing is released
  until tagged).
- Housekeeping from the same report: `tracebi context` names the contract
  certificate correctly (`data/warehouse.contracts.json`), no longer
  advertises the deprecated `requests/` lane in its conventions, and
  `tracebi validate` stops complaining about the folder's (expected)
  absence — it now warns only when the deprecated lane is still present.
- **The dev-iteration protocol is written down, step by step.** Both
  `AGENTS.md` files now walk the loop an agent actually runs: start
  `tracebi dev` in a background shell (it blocks — or the human keeps the
  portal open), edit and let the watcher re-render, **read the pins before
  every pass** (`tracebi report status` 📌 / MCP `workbench_state`), share
  drafts with `tracebi report snapshot` (no manifest; `verify` refuses it
  by name), and publish with `report build` + `verify --strict
  --contracts` — noting the built package is already live on the Reports
  page, so there is no separate publish step.
- **`build_report` joins the MCP gateway (ten tools).** The gateway could
  read the workbench but not finish: an MCP-driving agent had no way to
  build a package. `build_report` is the publish step over MCP — same
  figure-claim validation and receipt as the CLI, writes only its own
  artifact — and the gateway's authoring guide now teaches the package
  loop (bind prose numbers; pins first; spec rendering as the
  serialization path).
- Verified already-shipped, contrary to the report: `order_by`/`limit` is
  in the query grammar at every surface (spec, REST, MCP, Python) since
  M0 — the round-1 workaround is unnecessary.

An adversarial review of this wave (four dimensions, every finding
independently re-verified) then caught and fixed seventeen more before it
shipped, the ones that matter:

- **A chart-bearing package must opt into ECharts** (`"libs":
  ["echarts"]`), and neither the new scaffold nor the `migrate spec`
  compiler did — every sample and migrated chart would have rendered
  permanently blank. Both now emit the opt-in, test-pinned.
- **Inline prose values rendered as full-width KPI cards**, breaking the
  sentence the feature exists to serve: card treatment was keyed to the
  `data-tb-figure="value"` attribute instead of the `.tb-kpi` class. Now
  scoped to the class; a bare `<span>` stays inline.
- **Table figures' provenance badges detached to the page corner** — a
  `<table>` is an unreliable absolute-positioning anchor, so badges now
  anchor to a wrapper (`.tb-badge-anchor`).
- **`tracebi dev` live-reload was silently dead**: the shipped page's CSP
  (`connect-src 'none'`) blocked the reload poll. Dev-served pages now
  relax exactly that directive to `'self'`; built artifacts keep the
  strict policy (and no longer carry a duplicated CSP meta).
- **The Decimal write path could still round money silently on append** —
  Decimals appended into a column an earlier all-`None` write had typed
  as `INTEGER` coerced `19.99 → 20`. Appending a Decimal column into any
  non-`DECIMAL(38,12)` column now raises with the column, the existing
  type, and the remediation; identifiers are quote-escaped; the
  scale-12 rounding and mixed-column fall-through are documented.
- The analyst guide and web-customization guide — the last two documents
  still teaching `requests/` as current — now lead with the
  artifact-package loop and mark every legacy section deprecated
  (removed in 0.8).

### Fixed — fingerprints survive the pandas 3 string-dtype rename

pandas 3.0 (PDEP-14) renamed the default string dtype (`object` → `str`),
which moved the fingerprint of every string-bearing result — a receipt
rendered under pandas 2 would have stopped re-verifying after a pandas
upgrade, purely over a dtype label whose CSV bytes are identical. Caught
by the pre-change fingerprint corpus in CI (doing exactly the job it was
built for). Dtype names are now canonicalized toward the LEGACY name in
the one shared rule (`canonical_dtypes_repr`, used by `frame_fingerprint`
and the embedded canonical triple): existing manifests keep verifying
byte-for-byte, whichever pandas renders or checks them. The full suite
passes under pandas 2.2 and 3.0.

### Added — reshape M5: migration, and one report lane

The reshape lands its last piece: the artifact package is **the** report
lane, and everything else either compiles into it or is on its way out.

- **`tracebi migrate spec reports/<name>.json`** — compiles a JSON spec
  into an artifact package beside it: every section becomes a
  default-component figure bound to the same `DataRef` (the queries move
  verbatim into `report.json`), markdown TextSections convert through a
  deterministic escaped-first subset, a metric naming a query column
  compiles LIVE (`data-tb-cell`) while a literal metric compiles honestly
  `data-tb-unverified` — and every presentation knob with no runtime
  equivalent is warned about by name, never swallowed. A CI test pins
  receipt monotonicity: the compiled artifact's verifiable claims are a
  superset of the spec render's.
- **The shadowing rule** — at discovery, an artifact directory shadows a
  same-named `.json` spec with a warning naming both. Migration is a
  cutover the moment the directory exists; rollback is deleting it.
- **`requests/` is deprecated, removed in 0.8.** `tracebi init` no longer
  scaffolds the folder; the router, `tracebi run`, `tracebi dev`'s script
  branch, and `new-request` keep working through 0.7 and say the same
  thing: the one report lane is the artifact — exploration lives inside it
  (`tracebi dev` + exploration blocks that die at build).

### Added — reshape M4: transform contracts

The receipt extends to phase ① — honestly. A transform may now end with a
**sink contract**, and the exact claim is locked: *"the sink satisfied its
contract"* — never *"the transform was verified."*

- **`tracebi.contracts`** — `with contract(name, warehouse=...) as c:` at
  the bottom of a transform declares what must be true of the tables just
  sunk: `rows`, `unique`, `not_null`, `foreign_key`, `values`, `reconcile`.
  The vocabulary is closed and declarative (no callables) so every check
  is serializable, reviewable, and re-runnable. Checks run as read-only
  SQL at sink time; **a failed check raises** and writes nothing — a
  warehouse never carries a certificate its sink did not earn. Success
  records `<warehouse>.contracts.json`: every check with its observed
  value, plus a fingerprint per touched table.
- **The fingerprint join, pinned** — recorded fingerprints are computed by
  reading each sunk table back through `DuckDBConnector.load()`, the same
  path the model uses, hashed with the one `frame_fingerprint` algorithm —
  so any write/read dtype normalization sits inside both sides of the
  later comparison. A round-trip equivalence test (ints, floats+NaN,
  strings+None, dates, booleans, nullable Int64) gates it in CI.
- **Manifest `transform_contracts` block** — at artifact build, every
  warehouse table the report loaded is classified: `satisfied` (the
  certificate still fingerprint-matches the table), `stale` (re-sunk
  after its contract was checked — never reads green), or `no_contract`.
  A separate claim beside the figure claims, never blended: contract
  status never colors a figure status.
- **`tracebi verify --contracts`** — prints the recorded block and
  re-runs the declared checks against the current warehouse; a check the
  sink no longer satisfies exits 1 on its own line.
- `tracebi init` / `new-transform` scaffolds carry the contract stanza;
  `tracebi context` (and the MCP `get_context` tool) teach the vocabulary;
  the reference transform declares the reference contract.
- `DuckDBConnector.disconnect()` — deterministic release of the
  persistent read-only handle (one file, one process, one configuration).

### Added — reshape M3: the loop, and the workbench

"Steer from chat, see results in the portal" is now a real page:

- **The workbench** — `tracebi dev <package>` serves `/__workbench`: the
  earn-your-receipt coverage bar, every figure with its provenance badge,
  copy-addresses (`report#fig:id` — the human's pointing language), and
  PINS: flag a figure with a note in the portal and the agent reads it via
  `tracebi report status` (📌) or the new MCP `workbench_state` tool before
  its next edit. Data cards show each binding's rows, dtypes, and
  fingerprint, with QUICK-CHARTS that emit copyable `data-tb-figure`
  markup — adoption is pasting markup you already watched work. The
  exhibit feed carries `tracebi.workbench.show(...)` calls from report.py
  (a no-op outside dev) plus auto-entries when a binding's fingerprint
  changes. Dev-state only: nothing here exists in builds or manifests.
- **Coexistence (field-notes #12 dead)** — file-backed DuckDB connections
  open read-only; `write()` uses a short-lived read-write connection. Dev,
  build, and serve now run together against one warehouse, proven live;
  lock conflicts in either direction explain the actual fix.
- **The dev loop is artifact-native** — in-memory exploration renders
  (exploration blocks kept, ids assigned, badges on), a directory +
  `models/` + `transforms/` + `_theme.css` watcher, and a stale-`.pyc`
  guard for hot-reloaded models.
- **Web parity** — an artifact-backed report served over HTTP is the REAL
  render: embedded fingerprinted bytes, the figure claims layer, the
  schema-2 manifest — so what the browser shows is what `verify --file`
  checks (test-pinned FILE INTACT).
- `tracebi report status [--json]` prints the earned state from the one
  shared state builder; the MCP gateway grows to nine tools.


### Added — reshape M2: the presentation system

A zero-effort artifact page now looks shipped and hydrates itself:

- `tracebi.css` — the shipped design system: tokens (`--tb-*`, chart
  palette seeded from the one DEFAULT_PALETTE), classless report
  typography, components for KPIs / tables (real `--striped` and
  `--compact` variants at last) / charts / callouts, provenance badges,
  an unmistakable exploration-block treatment, and print rules that keep
  honesty visible on paper.
- `tracebi.js` — the dependency-free runtime: one RFC-4180 parser for
  both lanes; `tracebi.data(name)` reading ONLY the embedded fingerprinted
  bytes; a byte-exact port of the compact formatter (fuzz-verified against
  Python, so screen and print finally agree on "550.7B");
  value/table/chart hydration with derive.py's label and format rules
  ported guard-for-guard; `tracebi.configureChart` that can restyle an
  option but never re-source its data.
- `stack.py` — one injection order, which IS the override chain:
  tracebi.css → the project's `reports/_theme.css` brand layer → the
  report's own css, with the author's script running last.
- `HTMLRenderer.for_project` threads every built-in render site (twelve,
  including the notebook preview), so no surface can regress to
  unthemeable; report specs gain top-level `theme` / `script` keys and
  `report build` / `spec render` gain `--theme`.
- Provenance badges default on — verified / python-derived / unverified,
  decided at build from what was actually embedded; `--no-badges` omits
  them for client deliverables without touching the manifest.
- `tracebi context` gains the `presentation` vocabulary, so an agent
  styles a page from the vocabulary alone.

The reference project gains `reports/portfolio_overview`, the
default-component lane with no author CSS or JS — browser-verified:
hydrated KPIs, compact chart labels, derived table formats, and
`--strict` correctly failing on its one honest unverified figure.


### Added — reshape M1: the artifact, figures, and verify v2

Verification becomes a property of each FIGURE — a DOM element declaring
which stamped binding feeds it — not of which folder a file sits in:

- `tracebi/reports/figures.py`, the ONE tokenizer for `data-tb-*` markup
  (stdlib html.parser, never a regex), shared by the build, the
  exploration-strip, and `verify --file`. Hostile markup fails loudly.
- The final build strips `data-tb-stage="exploration"` blocks (deleted by
  the build, not by a rewrite), assigns figure ids, and validates every
  figure: a binding that exists or an explicit `data-tb-unverified` mark —
  no third state. Manifests gain schema 2: a `figures` claims layer and a
  `stage`, with the page carrying a matching stage meta.
- `verify` rolls receipts up per figure (figures first in the verdict);
  author-marked figures are UNVERIFIED, distinct from python-derived
  UNVERIFIABLE; a figure naming an absent binding fails the receipt.
  `--strict` is the CI gate: every figure must reproduce.
- `verify --file` cross-checks figures symmetrically — missing-in-file AND
  unrecorded-in-manifest both fail, so a figure added to a shipped page is
  caught by id — checks the stage, and refuses a snapshot by name. An
  intact verdict names the honest limit: markup and bytes are provable,
  page scripting is not.
- `tracebi report snapshot` — the sendable working state: exploration
  kept, a persistent banner, a read-only code appendix, and NO manifest
  (a draft receipt must never exist to launder).
- `report build` renders to `output/`; `data/` is the warehouse.

The M1 proof-gate drill ran live on the reference project (build → strict
verify → smuggled-figure tamper caught by id → snapshot refused → stage
mismatch caught). The remaining M1 gate — rebuilding the AltsVault report
as one artifact with the maintainer reviewing, and the authoring-experience
kill criterion — awaits the next live drive.


### Changed — reshape M0: the kernel seams (architecture v2 §4)

The first milestone of the one-lane report reshape, closing field-notes
findings #1, #2, and #5 in the current lanes before any new artifact exists:

- **`order_by` / `limit` in the query grammar** — sorting over result columns
  (ratio measures included), so "top 10 by mark" is a governed query at last.
  `limit` without `order_by` is refused everywhere; ties break on the
  remaining dimension columns and the fully resolved ordering is stamped for
  exact replay. A pre-change fingerprint corpus in CI proves no existing
  manifest stopped re-verifying.
- **One grammar, four surfaces** — REST's query endpoint validates through
  `QuerySpec.from_dict` (declared measures finally reachable over HTTP); the
  MCP query tool speaks the same grammar (its transport cap renamed
  `preview_rows`); the spec JSON Schema and `tracebi context` teach it.
- **Metric receipts** — a metrics section's one-row frame is retained,
  fingerprinted, embedded in the page, and verified like any table; the five
  biggest numbers on a dashboard join the audit trail, and `data_coverage`
  counts them.
- **Per-binding verifiability** — a `report.py` beside a package no longer
  poisons the declarative bindings next to it: query bindings stay
  green-eligible; python outputs stay branded `verifiable: false`, never
  green.
- **One query-node rule** — the three copies of "the last lineage node with a
  `query_spec` speaks for the frame" collapse into `last_query_node` in
  `dataset.py`.
- **The receipt-monotonicity harness** — a CI fixture asserting the set of
  fingerprinted, verifiable claims only ever grows; a change that silently
  weakens a receipt now fails the suite by construction.


### Added — `tracebi init` scaffolds an AGENTS.md so a project onboards its own agent

A fresh agent (or analyst) landing in a scaffolded project had nothing there
to orient it — the framework repo's own guides are in a different directory a
new session never reads. init now writes an `AGENTS.md` into the project: the
one rule (every figure is a query, never a hard-coded number), the three-phase
loop with the real commands, the first moves (`tracebi context`, read the
samples), how to `verify`, and the honest boundary. It is self-contained, so
an agent with no other context can work correctly.

### Added — the MCP gateway adopts MCP 2.0 protocol features

The gateway already ran on the MCP 2.0 SDK; now it uses the protocol, not just
the transport.

- **Structured output** on every tool: a typed `outputSchema` is advertised
  and results come back as `structuredContent`, not JSON inside a text blob —
  the stamp (query + lineage + fingerprint) and the verify verdict arrive
  machine-typed. (Required dropping `from __future__ import annotations` in
  `mcp_server.py` so the SDK can resolve the TypedDict return types; the module
  floor is already Python 3.10.)
- **Tool annotations**: the seven read/compute tools are marked
  `readOnlyHint` — the manifesto's "read-and-compute only" refusal, now
  visible in the protocol before a call. `render_report_spec` is marked
  writable but non-destructive (it writes only its own artifact and receipt).
- **Resources**: `tracebi://guide` (the authoring SOP, so an MCP-only agent
  that never sees AGENTS.md still gets the rules — closes audit G29),
  `tracebi://spec-schema` (the ReportSpec JSON Schema, so the grammar is
  obtainable over MCP — closes G11), and a `tracebi://models/{name}` template.
- **Prompt**: `author_report(question)` expands into the full
  discover → query → spec → validate → render → verify loop.

The `gateway_*` functions stay pure Python (typed with stdlib `TypedDict`),
so the layer remains importable and testable without the `mcp` package.

### Added — MANIFESTO.md: the product identity, written down

The trust layer for AI-generated analytics is the identity; the three-phase
workflow is the mechanism. The manifesto opens with the thesis ("Governance
tooling assumes a human wrote the transformation and is still around to ask.
TraceBi assumes a machine wrote it and is gone."), states the honest boundary
as a feature, lists eight refusals a code review can cite, and locks the
vocabulary canon: phase ① is **TRANSFORM**, phase ③'s noun is **REPORT**
("dashboard" is a style of report), and the assurance ladder is L0–L3 with
L3 plainly marked not-yet. The identity sentence now appears on every
first-contact surface: README, pyproject, `tracebi --help`, the docs site
hero, AGENTS.md, and the UI title.

### Changed — the repo separates the framework from the working project

The repo root mixed the tracebi software with a demo working project. Now
the root is the framework and the reference project lives at
`examples/portfolio_project/` — a complete three-phase project (inputs →
transforms → model → reports, driven by `run_workflow.py`) with the exact
shape `tracebi init` scaffolds. The medallion seed tooling moved to
`examples/seeds/`. The bundled demo app is now fully self-contained (its
models ship inside `tracebi/web/demo_app/models/`), and **TRACEBI_APP
defaults to none** — serving shows *your* project; opt into the demo with
`TRACEBI_APP=tracebi.web.demo_app`. Docker bakes and serves the reference
project; the Vercel entry points there too.

### Changed — `tracebi init` scaffolds the whole workflow, ending green

init used to scaffold the pre-three-phase product: no `inputs/`, no
`transforms/`, and a requests-only sample — the one lane `verify` cannot
cover, so a new user's first verify read NOTHING VERIFIED. It now scaffolds
a complete working project — a deliberately messy `inputs/orders.csv`, a
transform that cleans and sinks it, a lazy star-schema model, and a governed
dashboard spec — and the scaffolded README's four commands end with
`tracebi verify` reading REPRODUCES (pinned by tests that run them
verbatim). Also: a new `tracebi new-transform` scaffold; the new-model
template no longer calls `model.connect()` at import; the CLI's directory
defaults honour the `TRACEBI_*_DIR` env vars; `tracebi context` conventions
now name `inputs/` and `transforms/`.

### Added — the report generator: self-contained, provable HTML

A build step that takes a report definition plus live model data and emits
**one self-contained `.html`** (CSS, JS, and the model's data all inlined) plus
a `.manifest.json` receipt. The file is portable — open it offline, email it,
archive it — and *provable*: the numbers the page is built on are embedded as a
canonical `{columns, dtypes, csv}` triple, fingerprinted, and recorded, so a
reviewer with the file alone can confirm offline that the data it ships is
exactly what the recorded queries produced. Full design: `docs/report-generator-architecture.md`.

- **Template packages** — when the built-in section vocabulary is too rigid,
  `tracebi new-report "My Report"` scaffolds `reports/<name>/` (`report.json`
  data bindings + `template.html` / `style.css` / `script.js`). `tracebi report
  build <name>` renders it; `tracebi report preview <name>` opens it.
- **`tracebi verify --file <report.html>`** — the offline complement to
  `verify <manifest>`. It re-hashes the data blocks embedded in a shipped file
  and checks each against the manifest, catching an edited number
  (`FILE ALTERED`) with no database in reach. `verify` proves *do these numbers
  reproduce*; `verify --file` proves *is this the file we rendered*.
- **The `report.py` escape hatch** — a `build()` beside `report.json` for
  pandas the model can't express. Its inputs are stamped and its output
  fingerprinted, but the output stamps `verifiable: false`, so a Python-derived
  page never reads green under `verify`.
- **Strict CSP + safe embedding** — every self-contained file carries a strict
  Content-Security-Policy (`default-src 'none'`, `connect-src 'none'`, no
  `unsafe-eval`); data is embedded via a `<script type="application/json">`
  encoder that escapes `< > &` and line separators, parsed with `JSON.parse`,
  never `innerHTML`.

### Changed — governed charts render client-side with ECharts

The whole report generator now draws charts client-side (architecture §6): a
`ChartSection` in a `ReportSpec`/dashboard HTML render compiles to a sized
ECharts container plus its data **embedded as the canonical triple** and a
generic init script that builds the ECharts `option` from those exact
fingerprinted bytes — no server-side inline SVG in the HTML output. A knock-on
benefit: a governed report with a chart is now file-checkable by
`tracebi verify --file`, and its output carries the strict §5 CSP
(`connect-src 'none'`, no `unsafe-eval`) — the same self-contained-file
contract the freeform lane already had, now from **one** shared implementation
in `tracebi/reports/embed.py`. The ECharts bundle is inlined once per document.

`ChartSpec.to_svg` is **retained for the PDF path only** — WeasyPrint runs no
JS, so `render_pdf` emits static SVG charts from the same `ChartSection` config.

### Added — the three-phase workflow: transform → model → report

A worked, end-to-end path from a messy source file to a served dashboard, with
each phase in its own folder (see `WORKFLOW.md`):

- `transforms/` — phase ①, ordinary pandas that cleans a source and **sinks**
  star-schema tables into a file-backed DuckDB warehouse. As much code as the
  data needs; the contract is what lands, not how it was cleaned.
- `models/portfolio_model.py` (reference project) — phase ②, a `DataModel` over the warehouse. The
  reviewable contract: grain, keys and measures in ~50 declarative lines.
- `reports/` — phase ③. A `ReportSpec` JSON whose every figure is a live query
  against the model, served on the Reports page. Every report form lives in this
  one folder: specs, `@register.report` factories, and template packages alike
  (`TRACEBI_REPORTS_DIR`, default `reports`) — there is no separate
  `dashboards/`.
- `run_workflow.py` drives ①→③ (the reference project lives at
  `examples/portfolio_project/`); `inputs/generate_raw.py` produces a
  synthetic Schedule-of-Investments file so phase ① has real work to do.

A **metrics section can now bind its cards to a query**: a card whose `value`
names a measure reads it from a one-row result, so the KPI strip stays live
instead of hard-coding a number that goes stale. Static (literal-value) metrics
are unchanged.

Fixed a background-report polling bug surfaced by the dashboard: the run-status
poll now continues while the tab is backgrounded (`refetchIntervalInBackground`),
matching the UI's own "you can keep browsing" promise.

### Changed — **BREAKING**: the FastAPI app moved to `tracebi.web.api`

The wheel shipped the library but not the FastAPI app, so an installed TraceBi
had no server at all — `tracebi serve` could not work from a pip install, and
`uvicorn web.api.main:app` had nothing to import. The obvious fix was to add a
top-level `web` package to the wheel; that would have installed a directory
literally named `web/` into site-packages, and `web.py` is a real PyPI
distribution that owns exactly that path. Install both and pip overwrites
`web/__init__.py` with whichever landed second, reports nothing, and
`pip check` stays clean — so one of the two silently stops working. Verified by
execution against a wheel built that way: with `web.py` installed first,
`hasattr(web, "application")` goes from `True` to `False` and every web.py
program in that environment raises `AttributeError`.

So the app ships inside the distribution instead, and both coexist.

The app now lives inside the distribution, as a pure prefix insertion:

| Before | Now |
|---|---|
| `web.api.*` | `tracebi.web.api.*` |
| `web.demo_app` | `tracebi.web.demo_app` |
| `python web/run.py` | `python -m tracebi.web.run` |
| `uvicorn web.api.main:app` | `uvicorn tracebi.web.api.main:app` |

`tracebi/web/__init__.py` — the `register` facade — is untouched:
`from tracebi.web import register` works exactly as before.

**There is no back-compat shim at top-level `web`.** A shim only helps an
installed user if it is packaged, and packaging it re-creates the collision
this change exists to remove. TraceBi is pre-1.0 and unpublished, so the
honest fix is the rename plus this entry. If you pinned `uvicorn
web.api.main:app` (the old README and docker-compose spelling), change it to
`uvicorn tracebi.web.api.main:app`; if you set `TRACEBI_APP=web.demo_app`,
set `TRACEBI_APP=tracebi.web.demo_app`.

**Upgrading in place: delete any leftover `web/api` and `web/demo_app`
directories.** `git pull` cannot remove a directory that still holds an
untracked file, and a stale `__pycache__` is exactly that — so the old paths
survive as *empty namespace packages*. `TRACEBI_APP=web.demo_app` would then
import successfully, register nothing, raise nothing, and boot a server that
passes every healthcheck with an empty registry. Rather than leave that to
chance, a `TRACEBI_APP` naming the top-level `web` package is now refused at
startup with the replacement spelling, whether or not it imports.

The React source stays a Node workspace at the repo root (`web/ui/`), but
vite's `build.outDir` now writes to `tracebi/web/ui/dist` — inside the
package, which is what lets the wheel carry the bundle. `main.py`'s lookup
(`<its own dir>/../ui/dist`) is unchanged; Dockerfile, `vercel.json`,
`.gitignore`, `.dockerignore` and both CI workflows follow the new path. CI
now also asserts the wheel ships **nothing** top-level named `web`.

### Fixed — a derived default multiplied the number it was presenting

`HTMLRenderer`'s derived defaults picked the `percent` format from a column
*name* alone (`_pct`, `_rate`, `_ratio`), and `percent` is `{:.1%}`, which
multiplies by 100. Both conventions live here — a declared ratio measure holds
`0.069`, a hand-computed `pct_change().mul(100)` holds `12.5` — so the shipped
`revenue_trend` demo rendered 12.5% growth as **`1250.0%`**, with a complete
lineage chain attached. The suffix hint now applies only when every non-null
value is fraction-shaped (`|v| <= 1.5`); otherwise the column keeps its own
magnitude and loses the `%`. A model-declared measure format still wins over
the guard. `year` / `id` / `*_key` columns no longer get thousands separators
(`2024`, not `2,024`), and a repeated column label derives no format instead of
raising out of the render.

The demo keeps storing `12.5`, so `revenue_trend` now reads `12.50` under its
`MoM Growth %` heading in HTML and `12.5` in Excel — the same number in both.
`ExcelRenderer` does not derive defaults, so changing the stored convention to
suit the HTML renderer would have moved the hundredfold error into the
spreadsheet rather than removing it. `models/wealth_model.py` did hold a
genuinely pre-scaled column: fund expense ratios written as `0.0945` meaning
0.0945%, which no value-shaped guard can distinguish from a fraction. That is
now `expense_ratio_bps` in basis points (`9.45`), stating its unit in its name.

### Added — the verify loop (`tracebi verify`, `verify_manifest`)

Every `DataModel` query now fingerprints each source table as it loads
(`{table, fingerprint, rows}` on the load lineage node), manifests declare
`schema_version: 1`, and two new checkers close the loop: `tracebi verify
<manifest.json>` and the gateway's 8th tool `verify_manifest`. Each recorded
query is re-run and classified — `reproduces`, `source_drift` (inputs
moved), `model_changed` (a table now loads from a different source or
connector: a governance event, alarming, never counted as benign drift),
`unexplained` (inputs match, result doesn't — the alarm), `unverifiable`
(no recorded query, or post-query transforms). Exit codes 0/2/1. A newer
manifest `schema_version` refuses to verify rather than guess.

The receipt as a whole then gets one **verdict**, the single source of both
the exit code and `ok` (`ok` is `exit_code == 0` by construction, so they
cannot disagree). `reproduces` is the only verdict meaning a number was
re-run and matched: a manifest with no data-bearing section is
`nothing_to_verify` and exits **1** — nothing was checked, so nothing passed
— a manifest whose every section is hand-transformed is `unverifiable`,
still exit 0 because that is a legitimate authoring state, but it now says
so instead of answering the way a reproduced receipt does; and a manifest
refused for a newer `schema_version` is `refused_newer_schema`, which is
"could not check" rather than "nothing to check". A receipt that does
reproduce still names any sections it could not check, so one checked
section out of a hundred does not read like a hundred.

### Changed — validation before execution actually is

`DataModel.check_query_spec` (shared by `spec.validate` and the gateway)
now checks filter columns and dimension attributes, aggregation names,
ad-hoc dict-measure columns, filter operator names, and chart x/y/color
axes against the query's real output — the typo classes agents produce
most, which previously validated `ok: true` and detonated at render.
`dataset` vs `data` in a spec section gets a pointed error. Every
`render_report_spec` failure now returns the documented `{ok: false}`
shape. A bare filter that collides with a dimension attribute warns (both
readings stated) instead of erroring, since execution accepts the
fact-column reading.

### Fixed — the wheel ships the app it tells you to serve

`[tool.hatch.build.targets.wheel]` now ships the app in the wheel, with an
`artifacts` entry for the bundle because hatchling's file selection honours
`.gitignore` and the built bundle is gitignored — `packages` alone produced an
installed server whose `tracebi serve` died on `ModuleNotFoundError`. (This
first shipped the app as a second top-level package named `web`; see the
`tracebi.web.api` entry above for why that did not survive contact with
site-packages, and for the paths as they stand now.) A CI job builds the wheel
and asserts the bundle is inside it, and `.github/workflows/release.yml`
(`workflow_dispatch` or a tag; it builds an artifact and deliberately
publishes nothing) is the path that produces such a wheel.

The bundle is not in the repo, so it is not in a
`pip install "tracebi[web] @ git+https://…"` either: that install gives you
the library and the whole REST API, and no UI. README and `tracebi init`'s
README now say so instead of implying otherwise.

Relatedly, `/` no longer answers a bare 404 when the UI has not been built.
It serves a page — JSON for clients that did not ask for HTML — naming the
remedy that fits the tree it is running in: the `npm run build` command with
a real path from a checkout, and from an installed package the fact that
this install carries no bundle. The same line goes to stderr once at
startup. The gate is `web/ui/dist/index.html`, not the directory, because a
failed `npm run build` leaves the directory behind empty. The API is
unaffected — a missing bundle is not an outage.

### Added — HTTP gateway auth

`tracebi mcp --transport http` refuses to start without a decision: set
`TRACEBI_MCP_TOKEN` (constant-time bearer verification on every request)
or pass `--insecure` explicitly. Whitespace-only tokens count as unset.
A posture line (transport / auth mode / actor) prints on startup, after
the server actually builds. stdio is unchanged.

### Fixed — a custom container section no longer forfeits its lineage

`ReportSection.to_manifest_dict()` and `Report.data_sections()` now find
nested sections wherever a container keeps them — any attribute holding
sections, directly or inside a list, tuple, deque, set, frozenset or dict
(keys as well as values) — and the manifest records them under `sections`,
the key `tracebi verify` already descends into. Previously only `RowSection`
descended, so a project-defined container (the `section_renderers` seam:
tabs, panels, anything the framework has never heard of) rendered real
figures and produced a manifest with no lineage and no fingerprint at all,
which `tracebi verify` then passed as "no data-bearing sections" — and the
HTML lineage appendix, the Excel lineage sheet, `LineageDiagram` and the
`/api/reports/{name}/lineage` graph were blank for the same reason. Both
halves now walk the same helper, so the receipt and the page cannot disagree
about one report. Discovery is by inspection, not by a protocol the section
author opts into, because forgetting to opt in was the bug.

Iterators and generators are deliberately *not* searched: reading one
consumes it, and building a receipt must never empty the report it
describes. An edge that points back up the tree — a `parent` attribute, a
cached owner — is skipped rather than descended into, so an ordinary
back-pointer costs nothing and cannot fail a render. The same section
appearing twice in different branches is a DAG, not a cycle, and is
serialised in both places; a deeply nested diamond therefore costs
exponentially many paths (a 12-deep one is a 2 MB manifest), which no
report-shaped input reaches but which nothing currently caps.

Renderers now build the manifest *before* writing the artifact, so a failure
on the way to the receipt can no longer leave a rendered file on disk that
nothing can audit — the state this whole mechanism exists to prevent.

`schema_version` stays 1: the `sections` key and its meaning are unchanged —
sections that were silently dropped now appear. Re-render any manifest
produced from a custom container to get its receipt back
(`output/interactive_report.html.manifest.json` is one).

### Fixed — analyst-journey and receipt-retention defects

`tracebi serve` without the web package now exits with an actionable
message instead of a raw ModuleNotFoundError; the init-generated README
uses the real git-URL install form; `git rev-parse HEAD` in a commitless
repo no longer records the literal string "HEAD" as provenance (only a
real sha counts, and an unknown sha warns once per process); `.gitignore`
uses `output/*` + `!output/*.manifest.json` so manifests — the receipts —
are actually retainable (the old `output/` directory rule made the
negation impossible, which is also why the agent-gateway example's own
manifest had silently never been committed).


### Security — the role header is only trusted from an upstream proxy

`TRACEBI_AUTH_ROLE_HEADER` used to be read off the raw client request
whatever the auth mode, so under Basic auth any authenticated caller could
send it and promote themselves to `admin` — running pipeline layers,
overriding a `TRACEBI_AUTH_ROLE_MAP` entry that deliberately pinned them to
`viewer`, and having the forged role written into the audit trail.
`_Authorizer` now takes a required `trust_role_header`: proxy mode passes
`True` (the proxy sets the header, and must replace any client copy), Basic
auth passes `False`. An untrusted header is not a role source on its own, so
a Basic deployment whose *only* role config is that header keeps behaving
exactly as before rather than dropping to `viewer`; an explicitly-set
`TRACEBI_AUTH_DEFAULT_ROLE` is a usable source, so that deployment stays
enforced at the role the operator named. `install_if_configured` warns at
startup that the header is ignored and says what that leaves in force. It
also warns when role vars are set with no auth mode at all, where no
middleware is installed and nothing is enforced. In proxy mode the role
header is read from its *last* occurrence, so a proxy that appends its claim
rather than replacing the header is not overridden by a client copy in front
of it.

### Security — bearer-token auth on the MCP HTTP transport

`tracebi mcp --transport http` no longer starts unauthenticated by
default. Set `TRACEBI_MCP_TOKEN` and every request must carry
`Authorization: Bearer <token>` (verified in constant time via the MCP
SDK's `token_verifier` hook; anything else is a 401), or pass
`--insecure` to opt out explicitly — with neither, the server refuses to
start and says exactly what to do. Startup logs one posture line
(transport, auth mode, actor) to stderr. stdio is unchanged, and
attribution remains `mcp:<TRACEBI_MCP_ACTOR>` — per-agent credentials
and scopes are a later, separate design.

### Added — MCP agent gateway (`tracebi mcp`)

`tracebi/mcp_server.py` exposes the kernel over the Model Context Protocol,
so an agent can work against the semantic contract instead of the warehouse:
`get_context` (the vocabulary — nothing outside it validates), `list_models`
/ `describe_model`, `query_model`, `validate_report_spec`,
`render_report_spec`, and `list_reports`.

Every `query_model` response is **stamped**: the resolved query, the full
lineage chain, and a fingerprint of the complete result travel with the
rows. The row payload is transport-capped (default 50, hard cap 500) but the
fingerprint always covers the full result, so a quoted number is verifiable
even when its row was beyond the cap. Queries and renders record an actor of
`mcp:<TRACEBI_MCP_ACTOR>` through the existing audit ContextVar.

Read-and-compute only by design — pipeline execution writes to the
warehouse and stays off this surface until per-agent scopes exist to gate
it. The gateway operations are plain functions with a thin MCP registration
on top, so the test suite covers them without the optional `mcp` package
(`pip install 'tracebi[mcp]'`), and `render_report_spec` refuses a spec
that fails validation. Serve locally with `tracebi mcp` (stdio) or
`tracebi mcp --transport http --port 8765`.

### Added — Vercel + Supabase deployment

`vercel.json`, `api/index.py`, `api/requirements.txt`, and
[docs/deploy-vercel-supabase.md](docs/deploy-vercel-supabase.md). Vercel
hosts the React UI and the FastAPI layer as Python serverless functions;
Supabase Postgres is the data source and, for pipelines, the run-history
store.

The pairing works because of one property on each side. TraceBi never caches
a query — every call recomputes from source — which is what an ephemeral
function wants. And Supabase provides a *remote* Postgres, which fixes the
thing serverless otherwise breaks: the default SQLite lives on a local disk a
Vercel function cannot write to.

**The recent chart work is what made this fit.** A serverless function has a
250 MB unzipped limit and the full dependency set measures ~199 MB. Since
HTML charts are now inline SVG and Excel charts are openpyxl-native,
matplotlib (~35 MB) and networkx (~17 MB) can both be dropped — bringing the
function to ~150 MB with room to spare.

**`VITE_API_BASE`** makes the UI buildable against an API on another origin.
It was hardcoded to a same-origin `/api`, so the UI could only ever be served
from the same host as the API.

Three things do **not** work on serverless, and the docs say so plainly
rather than letting you find out in production: scheduled reports/pipelines
(APScheduler needs a process that outlives a request), background report runs
(the `run_id` lives in an in-process thread pool, so the next poll hits a
different process), and local SQLite. Use `pg_cron`/Vercel Cron, the
synchronous run endpoint, and Supabase Postgres respectively — or keep the
API in a container and host only the UI on Vercel.

Five tests pin the deploy contract, so a dependency creeping back into the
import path fails in CI rather than at a Vercel build.

### Added — themes, custom page templates, and pluggable sections

The HTML renderer kept its stylesheet as a 214-line module constant and
assembled the page with f-strings, so restyling or restructuring output meant
editing — or forking — the renderer. There was no extension point at all.

Three seams replace that:

- **`Theme`** (`tracebi.reports.theme`) — the stylesheet as data.
  `Theme.default().with_overrides(css)` layers on top (appended, so overrides
  win at equal specificity), `Theme.from_file(path)` and `Theme.from_css(...)`
  replace it outright. This covers the common case: make reports look like
  your brand.
- **Custom page shells** — pass `template=` a Jinja2 string to take over the
  document structure (header, footer, nav, analytics tag) while section
  rendering stays intact. `head_extra=` / `body_extra=` handle smaller
  injections without a full template. Rendered with `StrictUndefined`, so a
  mistyped placeholder raises instead of quietly rendering an empty string
  into a report someone will rely on.
- **`section_renderers=`** — `{section_type: callable}` to add a block type or
  replace how a built-in one renders. Accepts a `SectionType` or a plain
  string, so a type the framework doesn't know about works too.

Section *internals* stay in Python deliberately. Table formatting and chart
geometry are logic, not layout; expressing them as templates would make them
harder to read and harder to test. What you override is the shell, the
styling, and whole new block types.

Jinja2 remains optional — the built-in shell needs no template engine, so
reports still work on a base install. It is required only for a custom
template, which is finally what the long-declared, never-imported `jinja2`
dependency is for.

Default output is **byte-for-byte identical** to before this change, verified
across all seven demo reports. The renderer lost 177 lines.

### ⚠️ Changed — charts are inline SVG, not embedded PNGs

`ChartSection` rendered to a base64 matplotlib PNG. It now renders to inline
SVG via a new `ChartSpec` (`tracebi/reports/chart.py`), which is a chart's
definition *plus its resolved rows* as plain JSON.

Five things this fixes:

- **Charts no longer need matplotlib.** A base install rendered the literal
  text *"matplotlib required for charts"* in place of every chart. HTML
  charts now always work; matplotlib remains only for Excel, which genuinely
  needs a raster image.
- **Reports got ~75% smaller.** `revenue_trend` went from 71,886 to 12,841
  bytes, `analyst_demo` from 106,715 to 23,901. Base64 PNGs are enormous.
- **Charts are diffable.** SVG is text, so a chart change reads as a change
  in a pull request instead of 40 KB of altered base64 — and two visually
  identical PNGs could differ byte-for-byte.
- **Charts are themeable.** Every element carries a class (`tb-bar`,
  `tb-grid`, `tb-tick`, `tb-axis-label`, …) and the defaults live in the
  stylesheet, so a chart restyles without touching code.
- **Charts are responsive.** A `viewBox` scales to its container; a
  fixed-DPI bitmap did not.

Deliberately **not** a JS charting library. Vega-Lite and friends need a
browser and either a CDN or ~300 KB of bundled JavaScript, which would stop
a rendered report from being a single self-contained file that opens in six
months with no network. That property matters more here than interactivity.

Same six chart types as before (`bar`, `barh`, `line`, `area`, `pie`,
`scatter`), and `ChartSpec` round-trips through JSON so a tool can emit or
inspect a chart as data.

A chart referencing a column that isn't in its dataset now raises with a
did-you-mean suggestion, rather than silently plotting zeros.

### Added — reports as data (`ReportSpec`)

A `Report` is declarative in Python but holds live `DataSet` objects, so it
could not be written down. A **`ReportSpec`** is the same report as JSON:
presentation structure plus a *declarative reference* to the data rather than
the data itself.

```json
{"name": "Regional Margin",
 "sections": [
   {"type": "text", "title": "Summary", "style": "heading1"},
   {"type": "table", "title": "By Region",
    "data": {"model": "Sales", "query": {
       "fact": "fact_orders",
       "measures": ["revenue", "gross_margin", "margin_pct"],
       "dimensions": ["dim_customer.region"]}}}]}
```

That distinction buys three things a Python-only report cannot have:

- **Validation before execution.** `spec.validate(models)` checks section
  types, field names, enum values, and whether the referenced model, fact,
  measures and dimensions exist — **without loading a single row**. Errors
  carry a path: `sections[0].sections[1].data.query.fact`. An author, human
  or agent, finds out it is wrong before anything runs.
- **Diff and review.** Two specs are two JSON documents, so a change to how a
  number is defined shows up in a pull request.
- **Replay.** The spec is the input, the manifest is the receipt.

Sections serialize **generically from their dataclass fields**, never through
parallel "spec" classes — duplicating the definitions would drift the first
time someone added a field. A test asserts the section mapping covers every
`SectionType`.

`ReportSpec.from_report()` recovers a spec from a live report:
`DataModel.execute()` now stamps the model name and resolved `QuerySpec` into
the lineage, so a dataset produced by a model query can describe itself.
A dataset built from ad-hoc transforms has no declarative form, and
`data_coverage()` says so rather than pretending it round-trips.

New surfaces: `tracebi spec schema | validate | render`,
`GET /api/spec/schema`, `POST /api/spec/validate`, `POST /api/spec/render`,
and a generated JSON Schema so an editor can complete a spec.

### ⚠️ Removed — the Dash dashboard layer

`tracebi.dashboard` (Dashboard, DashboardServer, and the four panel types),
the `/api/dashboards` routes, the `/dashboards/{name}/` WSGI mounts,
`registry.add_dashboard()`, `TRACEBI_EMBED_DASHBOARDS`, the `[dashboard]`
extra (dash + plotly), and the Dashboards page in the UI are all gone.

This is subtraction on purpose, not neglect. The layer had three problems
that compounded:

- **No lineage export.** A dashboard could show a number with no audit
  trail, which contradicts the one thing this framework exists to
  guarantee.
- **Filters didn't traverse relationships.** Selecting a value filtered
  only panels whose own frame happened to carry that column, and silently
  skipped the rest — so a "filtered" dashboard could mix filtered and
  unfiltered numbers side by side.
- **It forced a second charting stack.** Reports render matplotlib; the
  dashboard rendered Plotly, with overlapping-but-different field names.
  Maintaining two chart grammars blocks unifying on one declarative spec,
  which is the prerequisite for AI-authored front-ends.

Plus the mounting itself was a scaling risk — Dash apps embedded in FastAPI
via WSGI at import time, holding in-process state, unable to accept a new
dashboard without a restart.

The **Explore** page and the report engine already cover most of what it
did, and both carry lineage. If live dashboards return, they will be a spec
over the same sections, sharing one chart grammar and inheriting lineage for
free.

Side effects worth noting: the deployed image no longer installs dash or
plotly, and the Starlette `middleware.wsgi` deprecation warning is gone
since nothing mounts WSGI any more.

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

### Added — discovery is no longer silent

Auto-discovery is convention-based and was quiet by nature: a file in the
wrong place never appeared, and a file that raised on import vanished with
only a `warnings.warn` to stderr. There was no way to ask *why* a report
wasn't showing up.

Every attempt is now recorded. `tracebi.web.discovery_report()`,
`GET /api/discovery`, and `tracebi validate` report each file as
`registered`, `skipped` (with which rule skipped it), or `failed` (with the
exception). `tracebi validate` treats a failure as a problem and exits
non-zero, so there is a loud gate as well as an inspectable one.

**Behaviour change:** a broken artifact no longer stops the others. Failures
in `models/` and `pipelines/` were already warnings, but a broken file in
`reports/`, `requests/`, or `scheduled/` propagated and **took down server
startup entirely** — one bad file made the whole app unbootable. Discovery
now records the failure and continues; pass `strict=True` to `auto_discover()`
for the old behaviour. A module that failed mid-import is removed from
`sys.modules` rather than left half-executed.

### Added — a machine-readable description of the framework

**`tracebi.capabilities.describe()`**, **`tracebi context`**, and
**`GET /api/schema`** return TraceBi's vocabulary as plain data: every
report section with its fields, types, defaults and *allowed values*; the DataSet verbs with signatures; measure kinds; filter
operators; number formats; and the file conventions that make a project
discoverable.

It is **generated from dataclass fields and type annotations**, not written
by hand. The section-type → class → parameter mapping previously existed
only in docstrings and two hard-coded renderer dispatchers, so a
hand-maintained copy would drift the first time a field was added. A test
asserts the surface covers every `SectionType`, and another asserts every
*advertised* enum value is actually accepted by the constructor — publishing
a value that raises would be worse than publishing none.

Intended for tools rather than people: an agent authoring a project, an
editor completing a constructor, a UI building a form. Works on the base
install — it reads class metadata and touches no optional dependency.

**`help_text()` on `DataSet`, `DataModel`, and `Report`.** The cheat sheets
were `print()` calls returning `None`, so anything in-process had to capture
stdout to read them. The text now has one source: `help_text()` returns it,
`help()` prints it, and the surface above carries all three.

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
not have and failed on import. An app module is only needed for connectors;
the four artifact directories need none.

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
