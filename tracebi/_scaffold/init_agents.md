# Working in this TraceBi project

You are an agent working in a **TraceBi** project. TraceBi is the trust layer
for AI-generated analytics: every number you put in front of a person should
carry a receipt. Read this before you touch anything.

## The one rule

**Every figure in a report names a stamped data binding — never a hard-coded
number.** A number you typed in has no receipt and cannot be verified. If a
figure genuinely cannot come from a query, mark the element
`data-tb-unverified` (with a `data-tb-note` saying why); do not fake it.
There is no third state.

This includes prose. A sentence's numbers can be live: any element — a
`<span>` mid-sentence included — can carry
`data-tb-figure="value" data-tb-binding="..." data-tb-cell="..."` and the
runtime fills it from the fingerprinted bytes. When you are asked to
"explain the results", bind the numbers in your sentences instead of typing
them; narrative prose is where unverified numbers usually hide, and here the
honest path costs one attribute.

## The workflow — three phases, three folders

```
⓪  inputs/       raw data lands here (a CSV, an API export, a SQL dump)
①  transforms/   ordinary pandas: clean it, then SINK clean star-schema
                 tables into the warehouse (data/warehouse.duckdb) and
                 declare a SINK CONTRACT on what landed
                        ── freeze: the warehouse + its contract ──
②  models/       a declarative DataModel over the sink: grain, keys, measures.
                 It reads the warehouse; it never sees the transform.
                        ── freeze: the model (the contract) ──
③  reports/      an ARTIFACT PACKAGE — reports/<name>/ holding report.json
                 (named query bindings) + template.html (your page, where
                 every figure claims a binding). Builds to one self-contained
                 HTML + a manifest (the receipt).
```

The phases are decoupled: editing a report never re-runs the pandas. Phase ①
is unconstrained — write whatever pandas the data needs; the contract is the
named tables you sink, not how you cleaned them. **Transforms are
notebook-shaped**: the scaffolds use `# %%` percent cells with markdown
cells, so your editor opens them as notebooks (collapse cells, run
cell-by-cell, prose beside code) while the file stays plain, reviewable
Python; literal `.ipynb` works too, and `tracebi run-transform` executes
either top-to-bottom in a fresh namespace so the sink never comes from
out-of-order kernel state. End the transform with a
`with contract(...)` block (see `transforms/sample_transform.py`): declared
checks — `rows`, `unique`, `not_null`, `foreign_key`, `values`, `reconcile` —
run as read-only SQL at sink time, raise on failure, and record a certificate
(`data/warehouse.contracts.json`) that report manifests join against. The
exact claim is "the sink satisfied its contract" — never "the transform was
verified"; nothing machine-checks the pandas above the sink.

## Authoring a report (the artifact package)

`reports/sample_dashboard/` is the working example — a page of ordinary HTML
whose figures each name a binding from `report.json`:

- `data-tb-figure="value|chart|table|custom"` + `data-tb-binding="<name>"` —
  the claim. Values add `data-tb-cell="<column>"` and optionally
  `data-tb-format` (`compact`, `currency`, `comma`, `percent`, …). Charts add
  `data-tb-type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`),
  `data-tb-x`, `data-tb-y` (comma-list for multi-series), optional
  `data-tb-color` and `data-tb-value-format`. Tables optionally add
  `data-tb-columns` and the `tb-table--striped` / `tb-table--compact` classes.
- **Give every figure an `id`** — ids are how humans redirect you
  ("fix `tbl-seniority`").
- "Top N" is declarative: put `order_by` + `limit` in the binding's query.
  Never sort or slice in `script.js` — that moves ordering out of the receipt.
- `filters` is WHERE (before aggregation) — a filter on a measure changes the
  group totals. To keep only groups whose *total* clears a threshold, use
  `having` (HAVING): `"having": {"revenue": {"gte": 250}}`.
- Interactivity: `data-tb-filter` dropdowns + `data-tb-search` inputs subset
  WHICH stamped rows a binding's tables/charts display — they never compute
  new numbers (client-side aggregation would mint numbers; value figures
  never react; a filtered KPI needs its own binding). Tables scroll past
  `data-tb-rows` (default 10). `data-tb-download` buttons export the
  stamped CSV verbatim (`data-tb-label` sets their text). Layout: tabs via `data-tb-tab` sections inside
  `.tb-tabs`; side-by-side via `.tb-cols-2` / `.tb-cols-3`. Every built
  page carries the Receipt drawer automatically.
- Blocks marked `data-tb-stage="exploration"` are working scratch: they render
  in dev and are DELETED at the final build.
- Styling: the shipped defaults render well with zero CSS. To restyle, set
  tokens in `reports/_theme.css` (project-wide) or the package's `style.css`
  (per report); later wins. `script.js` may restyle charts via
  `tracebi.configureChart` — config can restyle, never re-source: series data
  always comes from the stamped bytes. Provenance badges pick their state
  from the manifest; a stylesheet can restyle a badge, never re-color honesty.
- Methodology travels the pipeline: `contract(..., note=...)` (and per-check
  `note=`) records the transform's STATED methodology in the certificate;
  measure `description=` carries modeling intent. Add ONE
  `<section data-tb-methodology></section>` to the template and the build
  appends them after your own prose — an appendix of what the pipeline
  states about itself, clearly not a verified claim, never badged.

## The loop you run

```bash
tracebi run-transform <name>                # ① clean + sink + contract —
                                            #   runs .py or .ipynb top-to-bottom
                                            #   fresh (python transforms/<name>.py
                                            #   works too for .py)
tracebi new-model "<Name>"                  # ② scaffold a model; edit it
tracebi new-report "<Name>"                 # ③ scaffold reports/<name>/
tracebi dev <name>                          # the live loop (see below)
tracebi report status <name>                # earned state in the terminal (📌 pins)
tracebi report build <name>                 # render → output/<name>.html + manifest
tracebi verify output/<name>.html.manifest.json --contracts
tracebi serve                               # browse at http://127.0.0.1:8000
```

### The dev iteration, step by step

0. **Discovery comes first — and it has a live surface.** Before any report
   exists, run `tracebi dev` with **no name** (backgrounded — it blocks):
   the discovery workbench. While it serves, ANY script you run can call
   `tracebi.workbench.show(...)` — no env var needed — and the portal
   updates live. **Work like a notebook**: `show("## Approach\n...")`
   renders as a markdown cell (narrate the methodology as you go — the
   human can flip the feed to read top-down as a document);
   `show(df, note=...)` posts a frame excerpt with column profiles;
   `show(df, chart="bar", x=..., y=...)` sketches a real chart (bar,
   barh, line, area, pie, scatter) — iterate by re-showing, and when the
   human pins one for the report, re-express it as a model-query binding
   + figure: the sketch is exploration, the figure is the claim. The
   Warehouse panel lists tables, row counts, column profiles, and
   sink-contract status as transforms land; the Models panel shows the
   star schema taking shape as you edit `models/`. Pins read via the MCP
   `workbench_state` tool called with no `report`. All dev-state; no
   receipts exist before the model boundary, and `show()` is a no-op the
   moment the server is down. When a session shaped the pipeline, save it:
   `tracebi session export` (add `--format md` for the git-review twin)
   writes the full feed to `explorations/<session>` — ONE living record
   that you re-export as the exploration evolves; git is its timeline —
   exploration-stamped, no receipts, `verify` refuses it by name.
1. **Start the dev server — it blocks.** Run `tracebi dev <name>` in a
   background shell (or ask the human to run it and keep the tab open; the
   page is their view, not yours). It serves the report at the root and the
   workbench at `/__workbench`, and reloads on every save to the package,
   `models/`, `transforms/`, or `reports/_theme.css`.
2. **Edit; the portal follows.** Work in `template.html` / `report.json` /
   `style.css` / `script.js`. Explore inside `data-tb-stage="exploration"`
   blocks — they render in dev and die at build. From `report.py`,
   `tracebi.workbench.show(title, df_or_fig, note=...)` posts exhibits to
   the workbench feed during dev and is a no-op everywhere else, so probe
   code needs no cleanup and no promotion step.
3. **Read the pins before every pass.** The human steers by PINNING figures
   in the workbench with a note ("make this top 8 sectors only"). Read them
   with `tracebi report status <name>` (pins print with 📌) or the MCP
   `workbench_state` tool. Address pins first; they are the human pointing.
4. **Share a draft with `tracebi report snapshot <name>`.** One HTML with
   the exploration blocks KEPT and a review banner; it carries no manifest
   and `verify` refuses it by name — a draft can never impersonate a
   final. Use it when the human wants to look without a dev server.
5. **Publish with `tracebi report build <name>`**, then
   `tracebi verify output/<name>.html.manifest.json --strict --contracts`.
   The build strips exploration, validates every figure claim against the
   embedded bindings, and writes the receipt. `output/<name>.html` (+ its
   `.manifest.json`) is the deliverable to hand over or commit — and the
   package is already served live on the Reports page of `tracebi serve`;
   there is no separate publish step.

`tracebi verify` is the point: it re-runs the recorded queries and confirms
every figure still reproduces. Only `REPRODUCES` means a number was re-run
and matched. `--contracts` also re-runs the sink contracts. Run it before
you tell a human a report is done.

## First moves

1. Run `tracebi context --brief` — the token-lean vocabulary tier (~2.3k
   tokens): the semantic model, the figure grammar, contracts, and
   conventions — everything this loop needs; it names what it omitted.
   Nothing outside the vocabulary validates. Add `--model <name>` for one
   model's schema; drop `--brief` only when writing Python against the
   library directly.
2. Read the sample files: `transforms/sample_transform.py`,
   `models/sample_model.py`, `reports/sample_dashboard/`. They are a complete
   working example of the loop, receipt included.
3. Read `README.md` for the run commands.

## The honest boundary — do not overclaim

The trust machinery covers the model boundary onward (the query and the
report), **not** the phase-① pandas that built the warehouse. `verify` checks
that a number still reproduces from its recorded query; it does not assert the
number is *correct*, and it never reads the transform. The sink contract
certifies what landed, not how. Say so honestly. An "unverifiable" that says
so beats a green badge on unchecked work.

## Legacy forms

A JSON `ReportSpec` under `reports/` still renders (it is a serialization,
not a lane) and `tracebi migrate spec reports/<name>.json` compiles one into
an artifact package that shadows it. The `requests/` script lane is
deprecated and removed in 0.8 — do not create it.

## Scaffolding commands

`tracebi new-transform "<Name>"` · `tracebi new-model "<Name>"` ·
`tracebi new-report "<Name>"` · `tracebi spec schema` (the ReportSpec JSON
Schema). Discover more with `tracebi --help`.
