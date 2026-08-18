# AGENTS.md — Working with TraceBi as an AI Agent

Read this before touching a TraceBi project. Deeper references: `WORKFLOW.md`
(the three-phase workflow, end to end), `CLAUDE.md` (codebase rules), `NOTES.md`
(design decisions), `examples/agent_gateway/` (a complete recorded agent
session).

## What TraceBi is

TraceBi is **the trust layer for AI-generated analytics** — a code-first BI
framework where every number has a receipt (see `MANIFESTO.md` for the full
identity and vocabulary canon). The mechanism is a **three-phase workflow**
that carries data from messy to reportable. Each phase is a project-root folder
with its own cadence, decoupled from the next by a **freeze point** — a
materialized artifact handed across the boundary:

| Phase | Folder | You write | Freeze it hands on |
|---|---|---|---|
| ① **Transform** | `transforms/` | ordinary, unconstrained pandas — pull queries, clean, parse, key, dedupe, then **sink** clean star-schema tables. Notebook-shaped by scaffold (`# %%` percent cells + markdown cells — editors open them AS notebooks; the file stays reviewable Python); literal `.ipynb` works too, and `tracebi run-transform` executes either top-to-bottom fresh | `data/warehouse.duckdb` (materialized tables) |
| ② **Model** | `models/` | a declarative `DataModel` over the warehouse — grain, keys, measures, in a few dozen lines a reviewer reads without opening the pandas above it | the model (the semantic contract) |
| ③ **Report** | `reports/` | an **artifact package** (`reports/<name>/`: free HTML whose figures each name a stamped binding or carry `data-tb-unverified`) — or a `ReportSpec` (JSON), which is a serialization of the same thing: `tracebi migrate spec reports/<name>.json` compiles it into the package form, and the package shadows the same-named spec at discovery | the rendered page + its lineage manifest |

Reference implementation, end to end, at `examples/portfolio_project/`:
`transforms/holdings_transform.py` → `models/portfolio_model.py` →
`reports/portfolio_dashboard.json`, wired by `run_workflow.py`.
`WORKFLOW.md` is the full tour; read it first.

The split earns its keep at the freeze points: the slow, unconstrained analysis
(①) and the fast, iterated reporting (③) never block each other, because the
model (②) is a frozen contract between them. Editing a report never re-runs
the pandas. As an agent (or analyst) you author each phase in turn: write the
phase-① transform, declare the phase-② model, author the phase-③ report spec.

## Where the trust machinery applies — and where it does not

TraceBi is also a **trust layer for AI-generated analytics**: AI made producing
reports nearly free; believing them is the expensive part. But be exact about
the boundary. **The trust machinery governs from the model boundary onward — it
covers phases ② and ③, not ①.**

- **Phase ① (`transforms/`) is unconstrained and unverified by design.** It is
  ordinary pandas that writes the warehouse. The framework draws the line at the
  **sink**, where the numbers become a contract you can report against. Lineage
  is *not* traced through the raw analysis, and nothing machine-checks that the
  transform's numbers are right. Phase ① is trusted the way reviewed code is
  trusted — in git — not the way a fingerprint is trusted.
- **What phase ① CAN declare is a sink contract.** End the transform with a
  `with contract(name, warehouse=...) as c:` block (`tracebi.contracts`) —
  closed, declarative checks (`rows`, `unique`, `not_null`, `foreign_key`,
  `values`, `reconcile`) run as read-only SQL against the tables just sunk and
  recorded beside the warehouse with connector-path fingerprints. A failed
  check **raises**, so a broken sink never freezes quietly. At report build,
  every loaded warehouse table is classified in the manifest's
  `transform_contracts` block — `satisfied`, `stale` (re-sunk after its
  contract was checked; never reads green), or `no_contract` — and
  `tracebi verify --contracts` re-runs the declaration. The exact claim is
  **"the sink satisfied its contract"** — never "the transform was verified":
  the checks certify the landed tables' shape, not the pandas above them, and
  contract status never colors a figure status. Declare one whenever you write
  a transform; it is the difference between a warehouse that says nothing and
  one that carries its own certificate.
- **From the model boundary onward, every answer is stamped.** Agents never
  touch the warehouse over the gateway: they speak the semantic contract
  (facts, dimensions, named measures), and every result comes back with its
  resolved query, full lineage chain, and a SHA-256 fingerprint of the complete
  result. Dashboards are declarative specs that validate *before* execution and
  render to artifacts with a lineage manifest. `tracebi verify` re-runs a
  manifest's recorded queries and compares fingerprints — it does **not** read a
  transform and does **not** assert that a number is correct; it proves the
  reported figures still match the warehouse they were drawn from.

The built artifact also embeds the **semantic contract as exercised** — a
snapshot of just the facts, dimensions, and measure declarations its
bindings referenced, fingerprinted in the manifest — so a reader with
nothing but the HTML knows what the vocabulary meant when the numbers were
produced, and `verify --file` catches a rewrite of the meaning exactly like
a rewrite of the numbers.

So any number a report puts in front of a person is traceable back to the
query that produced it and re-runnable against the sink. What produced the sink
is phase ① — believed the way you believe reviewed code, not the way you believe
a hash.

## Authoring the artifact

The package's `template.html` is ordinary HTML whose figures each claim a
binding: `data-tb-figure="value|chart|table|custom"` +
`data-tb-binding="<name>"` (values add `data-tb-cell` and optionally
`data-tb-format`; charts add `data-tb-type`/`data-tb-x`/`data-tb-y` and
optionally `data-tb-color`/`data-tb-value-format`; tables optionally
`data-tb-columns`). A figure with no binding carries `data-tb-unverified` —
there is no third state. Give every figure an `id`: ids are how humans
redirect you. `tracebi context` documents the full grammar in its
`presentation` block.

Three rules that keep pages honest:

- **Bind prose numbers.** Any element works as a value figure — a `<span>`
  mid-sentence included — so when you are asked to "explain the results",
  bind the numbers in your sentences instead of typing them. Narrative
  prose is where unverified numbers usually hide; here the honest path
  costs one attribute, and each bound span is a verified figure in the
  manifest.
- **"Top N" is declarative.** Put `order_by` + `limit` in the binding's
  query — never sort or slice in `script.js`, which moves ordering out of
  the receipt.
- **Interactivity subsets, never computes.** The premium objects —
  `data-tb-filter` dropdowns, `data-tb-search`, scrollable tables
  (`data-tb-rows`, default 10), tabs (`data-tb-tab`), `.tb-cols-2/3`
  layouts, `data-tb-download` (the stamped CSV verbatim — a
  receipt-preserving export) — all subset WHICH stamped rows figures
  display. They never compute new numbers: client-side aggregation would
  mint numbers, so value figures never react and a filtered KPI needs its
  own binding. Download buttons take `data-tb-label` for their text.
  Every artifact also carries the receipt drawer (the floating Receipt
  button); the manifest remains the receipt of record. Methodology ships
  via ONE `<section data-tb-methodology>` — the build appends the
  pipeline's stated methodology after your own prose.
  `examples/portfolio_project/reports/portfolio_showcase/` is the
  maintained kitchen-sink demo of all of it.
- **Explore inside the artifact.** Blocks marked
  `data-tb-stage="exploration"` render under `tracebi dev` and are deleted
  at the final build; the workbench at `/__workbench` shows figures,
  coverage, and the pins a human left for you (also via `tracebi report
  status` and the MCP `workbench_state` tool).

And the iteration protocol itself: `tracebi dev <name>` **blocks** — run it
in a background shell (or let the human keep it open; the portal is their
view). Then edit and save; the watcher re-renders. Before every editing
pass, read the pins (`tracebi report status <name>` — 📌 lines — or MCP
`workbench_state`): a pin is the human pointing at a figure with a note, and
it comes first. `tracebi report snapshot <name>` shares a draft (exploration
kept, review banner, no manifest — `verify` refuses it by name). Publishing
is `tracebi report build <name>` + `tracebi verify … --strict --contracts`:
the built `output/<name>.html` + receipt is the deliverable, and the package
is already served on the Reports page — there is no separate publish step.

The workbench starts BEFORE the report exists. `tracebi dev` with **no
name** opens the **discovery workbench** — the live surface for phase ① and
②: while this server is up, `tracebi.workbench.show(df, note=...)` from ANY
script you run (a transform probe, a scratch analysis) posts the frame to
the portal with no configuration, the Warehouse panel lists tables, row
counts and contract status as sinks land, and the Models panel shows the
star schema (facts, dimensions, measures) taking shape as you edit
`models/`. The human pins tables and exhibits there exactly as they pin
figures later (MCP: `workbench_state` with no `report`). Interrogate in the
open — excerpts and visuals in the portal, not buried in chat — then
scaffold the package and the same portal continues into the figure loop.
Everything is dev-state: no receipts are minted before the model boundary.

When a session shaped the pipeline, SAVE it: `tracebi session export`
writes the full feed chronologically to `explorations/<session>` — ONE
living record per session, not a dated diary: re-export as the exploration
evolves and git carries its timeline (per-exhibit source-script provenance
included) —
`--format md` for the git-review twin, HTML for fidelity. The record is
exploration-stamped and carries no receipts; `verify` refuses it by name.
The distillation ladder: session record → contract notes → the report's
methodology appendix.

## The two planes rule

**Change the contract in git. Use the contract over MCP.**

- **Definition plane** (git): `transforms/*.py`, `models/*.py`,
  `reports/*` (specs, packages, and factories; plus `pipelines/*.py`). Every phase is
  authored and code-reviewed here. Missing a measure? The fix is a code-reviewed
  edit to the model file (e.g. `model.add_measure(...)` in
  `models/portfolio_model.py`) — never a workaround in the report layer.
  Missing a *column the measure needs*? That is a phase-① change: sink it in the
  transform. A fresh gateway process sees new vocabulary on its next call (stdio
  one-shot clients get this for free; a long-running server must be restarted —
  Python module caching keeps the old model loaded).
- **Access plane** (MCP): read-and-compute only, and only from the model
  boundary onward. Queries, validation, and spec rendering persist nothing
  beyond an output file. Phase ① never runs over the gateway — it writes the
  warehouse, and the gateway has no write surface, on purpose. Pipeline
  execution (the older warehouse-writing path) is likewise absent from this
  surface.

## Assurance ladder

These levels grade how you author the reporting side (phase ③) once the model is
frozen; they say nothing about phase ①, which the ladder does not reach.

| Level | Agent does | Requires today |
|---|---|---|
| L0 | Raw SQL, raw HTML | Nothing — and proves nothing. Avoid. |
| L1 | Queries via gateway, renders its own HTML | Every number from `query_model`; cite its fingerprint alongside the figure |
| L2 | Emits a ReportSpec; TraceBi renders | Spec passes `validate_report_spec`; artifact + manifest come from `render_report_spec` |
| L3 | L2 + signed manifest + re-verification | Re-verification exists (`verify_manifest` / `tracebi verify`, drift-aware via input fingerprints recorded at render); **signing not yet built** |

Prefer L2. Use L1 when you need presentation freedom the spec grammar lacks —
governed data, ungoverned presentation.

## The gateway

Start it with `tracebi mcp` (stdio, local agent) or
`tracebi mcp --transport http --port 8765` (remote). Needs
`pip install 'tracebi[mcp]'`. Register with Claude Code:
`claude mcp add tracebi -- tracebi mcp`. Work is attributed as
`mcp:<TRACEBI_MCP_ACTOR>` (default `mcp:agent`).
The http transport requires `TRACEBI_MCP_TOKEN` (send
`Authorization: Bearer <token>`) — it refuses to start without it unless
`--insecure` is passed explicitly.

Ten tools (`tracebi/mcp_server.py`):

| Tool | Purpose |
|---|---|
| `get_context` | Full vocabulary: section/chart types, DataSet verbs, measure kinds, filter operators; `model=<name>` adds that model's schema. **Call first.** |
| `list_models` | Project models with tables, facts, dimensions, measures |
| `describe_model` | One model's full schema |
| `query_model` | Star-schema query → stamped result. `measures` is declared measure names (ratios included) or `{column: agg}` (`sum, count, mean, min, max, nunique`); dimensions are `dim_name.attribute`; `filters` take equality, lists (IN), or operator dicts (`gte`, `between`, `contains`, …) and are **WHERE** — applied before aggregation, so a filter on a measure changes the group totals; `having` is **HAVING** — same spellings on aggregated result columns (measures, ratios), so `having={'revenue':{'gte':250}}` keeps groups whose *total* clears 250 with totals intact; `order_by` (`{column, desc}` or `'-col'`) + `limit` express "top N" (limit **requires** order_by); `preview_rows` caps transport only |
| `validate_report_spec` | Check a spec against the models without loading a row; errors carry a path like `sections[0].data.query.fact` — repair and retry |
| `render_report_spec` | Validate, build, render to self-contained HTML + lineage manifest; **refuses invalid specs** |
| `list_reports` | Per-file discovery status (note: a bare `tracebi mcp` process has not run web discovery, so this may be empty — models and queries are unaffected) |
| `workbench_state` | The workbench state for an artifact package: figures with provenance, coverage, per-binding cards, the human's **pins**, and the exhibit feed — read it to see what the human flagged in the portal before your next edit |
| `build_report` | The **publish step for the package lane**: build `reports/<name>/` to one self-contained HTML + manifest (exploration stripped, every figure claim validated). Returns the figure records, embedded fingerprints, and the `transform_contracts` join; writes only its own artifact and receipt |
| `verify_manifest` | Re-run every recorded query in a rendered manifest and classify: `reproduces` / `source_drift` / `model_changed` / `unexplained` / `unverifiable`. Read the receipt-level `verdict`, not just `ok`: only `reproduces` means a number was re-run and matched — and it names any sections it could not check, so read `verdict_detail` too. `nothing_to_verify` (no data-bearing section — a broken receipt) and `refused_newer_schema` (written by a newer tracebi; not read at all) are not ok; `unverifiable` (every section hand-transformed) is ok but proves nothing |

Every tool returns **structured output** (a typed `outputSchema` and
`structuredContent`, not JSON inside a text blob), so the stamp and the verdict
arrive machine-typed. The read tools carry a `readOnlyHint` **annotation** — the
"read-and-compute only" promise, visible in the protocol before you call.

### Resources and a prompt

The gateway also exposes reference material as MCP **resources** — pull them
into context rather than guessing:

- `tracebi://guide` — the authoring rules (this SOP, on the surface itself).
- `tracebi://spec-schema` — the ReportSpec JSON Schema. Read it before writing
  a spec instead of guessing the grammar.
- `tracebi://models/{name}` — one model's full schema as a document.

And a **prompt**, `author_report(question)`, that expands into the whole loop
below for a given question — the fastest way to start correctly.

### The canonical loop

1. **Discover** — `get_context`, then `list_models` / `describe_model`.
2. **Explore** — `query_model` to probe the data before deciding what to write.
3. **Author** — write a ReportSpec using only vocabulary the gateway showed you.
4. **Validate** — `validate_report_spec`; fix pathed errors until clean.
5. **Render** — `render_report_spec`; keep the manifest with the HTML.
6. **Verify** — `verify_manifest` on the manifest you just produced; any
   verdict but `reproduces` needs explaining before a human sees the number —
   including the two that check nothing at all (`nothing_to_verify`,
   `unverifiable`), which is why `ok` alone is not the question to ask.
7. **Cite** — every number you quote anywhere carries its fingerprint.

Rows are transport; the stamp is the truth. `query_model` caps rows (default
50, hard cap 500) but fingerprints the *uncapped* result, so a figure beyond
the cap is still verifiable: re-run the recorded query, compare fingerprints.

CLI equivalents (no MCP needed): `tracebi context [--model NAME]`,
`tracebi spec schema`, `tracebi spec validate report.json`,
`tracebi spec render report.json`, `tracebi verify out.manifest.json`.

## Audit your own transcription

At L1 you transcribe numbers into your own page, and nothing machine-checks
the transcription — so write and run a verifier that re-runs the recorded
queries, compares fingerprints, and checks every displayed figure
(`examples/agent_gateway/verify_report.py` is the template).

The cautionary tale: the gateway's first agent session produced a page whose
fingerprints all matched yet whose total read `+$523,045` when the truth was
`$523,044.32` — it had summed rounded per-row gains instead of rounding the
sum. The matching fingerprints proved the data hadn't drifted, localizing the
fault to transcription instantly; no human eye would have caught one dollar in
seven and a half million.

## Never

- **Never invent vocabulary.** Only facts, dimensions, measures, section
  types, and operators returned by `get_context` / `describe_model` exist.
  Nothing outside the contract will validate.
- **Never render or ship an unvalidated spec.** `render_report_spec` refuses
  invalid specs by design; do not route around it with hand-built artifacts
  pretending to be governed.
- **Never quote a number without its fingerprint.** An uncited figure is
  exactly the untraceable output this system exists to prevent.
- **Never mutate models, measures, or pipelines at runtime.** Contract
  changes belong in `models/*.py` (and friends) through git — the definition
  plane. The gateway has no write surface, on purpose.
- **Never page raw rows to dodge the cap.** More than 500 rows means you are
  building a table; do it through a report spec.
