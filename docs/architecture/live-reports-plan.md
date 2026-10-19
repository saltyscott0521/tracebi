# Live reports — the plan

**Status: in execution, 2026-10-19.** The package plan for the page half of
[[duckdb-first]] (D5–D9), re-ordered around the maintainer's goal:

> The built report is one file, works offline, covers every chart and table
> type, and is state-driven: a filter changes every figure on the page.

The server half of [[duckdb-first]] (SQL transforms, storage tiers, the model
as a DuckDB schema) is a later round; nothing here depends on it.

## Decisions (closed)

1. **The page engine is ours.** `tracebi-calc.js`: plain JavaScript, inlined
   like `tracebi.js`, executing a closed **calc plan** over embedded Parquet
   blocks. Budget ≤ 50 KB gzipped including the Parquet reader (hyparquet,
   20 KB measured). No wasm, no CSP change.
2. **The build does the thinking.** For each report the build derives the
   **slice**: per fact, the coarsest grain that answers every figure and every
   control, flattened with the dimension attributes the page exposes, time
   grains and bins pre-computed as columns, ratio measures stored as their
   parts. The page only filters, groups, sums, divides and post-processes.
3. **One calc plan per binding, compiled on the server.** `calc_plan.py`
   turns a `QuerySpec` + model into closed JSON (group columns, aggregates
   with source columns, ratio parts, post-ops for share / rank / running /
   having / order / limit, and the binding's fixed filters). The plan is what
   the engine runs and what the trace records. The engine never sees a model.
4. **One selection state per page**, `{"dim_issuer.sector": ["Technology"], …}`,
   composed onto every binding's plan by one rule: a selected field applies
   to a fact when the slice for that fact carries that column (the build put
   it there because a declared relationship reaches it); otherwise the figure
   is untouched and marked `data-tb-unfiltered-by`. Multi-select. The state
   lives in the URL hash.
5. **Every figure kind recomputes**: value, chart (bar, barh, line, area, pie,
   scatter, with facets, stacks and annotations), table (sort, bars, totals,
   windowing), spark, and custom `tracebi.draw` figures through
   `tracebi.rows`. The runtime's existing `_liveRows` → `refreshBinding` /
   `paintValues` path is the plug-in point; the React kit changes nothing in
   how authors write figures.
6. **What cannot recompute is marked, never silently stale.** A `{"model","sql"}`
   binding, a `report.py` output, and any measure kind the engine does not
   implement (`period_end`, `offset`, `to_date` in this round) carry
   `data-tb-fixed` and the trace row says "fixed at build". A binding whose
   plan the server refused to compile is fixed too, with the reason.
7. **Trust.** The chip gains **Local** (recomputed on this page from embedded,
   fingerprinted blocks; the trace row records plan + selection + block
   hashes; `verify --local` replays it on the server). Fingerprints round
   floats to 9 significant digits under a total order before hashing (new
   algo version; verify reads both). Parquet blocks hash the shipped bytes
   (`payload_sha256`), as [[large-detail-artifacts]] §11 settled.
8. **Parquet types in a slice** are numbers, booleans, strings and naive
   datetimes only; grains are strings (`2026-03`, `2026-Q1`, `2026-W09`);
   anything else fails the build by name. Snappy or uncompressed pages (what
   the reader decodes natively). **Amended after L-2:** the block travels as
   today's Parquet blocks do, raw bytes base64, not gzipped, so the page has
   one carrier.
9. **The old path goes.** parquet-wasm, Arquero, the worker, the sealed-grain
   evaluator and the host selection round trip for filters are removed in the
   last package. Ask keeps its server endpoint (it answers questions, it does
   not filter pages). The locked guide line "never compute new numbers"
   becomes "**a figure's number is only ever a query result**", changed in
   the test, both guides and the vocabulary in one commit.
10. **Budgets the audit ratchets**: engine ≤ 50 KB gz; every binding on the
    reference project's largest slice recomputes ≤ 100 ms (Playwright,
    `performance.now()` around the engine call); each built report's size
    against its baseline.

## Packages

Branch `live-reports`. L-1 and L-2 are Python and disjoint, so they run in
parallel worktrees; L-3 needs both; L-4 needs L-3; L-5 closes.

### L-1 — The calc plan and the parity oracle (Python)

- `tracebi/reports/calc_plan.py`: `compile_plan(model, query, slice_columns)
  -> dict` for every `_Resolved` kind: `agg_map` (sum, count, mean as
  sum/count parts, min, max, nunique, `p<N>` as `quantile_cont`), `derived`
  row expressions (closed arithmetic over fact columns; parsed to an AST the
  engine evaluates, no eval), `ratios`, `shares`, `ranks` with
  `partition_by`, `runnings`, `having`, `order_by`, `limit`, binding
  `filters`, per-query `calculated` measures. Kinds not implemented this
  round return `{"fixed": reason}`.
- `apply_selection(plan, selection)`: the one composition rule (decision 4),
  in Python, with the engine's port tested against it.
- Fingerprint rounding (decision 7): `frame_fingerprint` v3, `verify` accepts
  v2 and v3.
- Parity fixtures: `tests/fixtures/calc_parity/<case>.json`, each a small
  slice (rows + column types), a plan, a selection, and the expected rows
  from DuckDB. One case per measure kind × with/without selection, plus
  having, order, limit, partitioned rank, nunique, p50/p90, a derived
  expression, a two-fact page with a shared dimension and one unreachable
  field. Generated by `scripts/gen_calc_parity.py` from the reference model;
  committed, so L-3 runs without DuckDB.
- Unit test (kept family: query semantics): every fixture's expected rows
  equal `DataModel.execute` on the same slice under the same selection.

Verify: fixtures regenerate byte-identically; the suite passes.

### L-2 — The slice (Python)

- `tracebi/reports/slice.py`: `required_grain(package, model)` per fact =
  union of every binding's dimensions, every control's column, every
  `partition_by`, every time grain / bin the page names; `build_slice(...)`
  runs ONE DuckDB query per fact: filter nothing, group by the required
  grain, aggregate every additive measure the page uses, keep base-grain
  rows for a fact whose page uses `nunique` / percentiles / `derived`
  expressions over row values; join the exposed dimension attributes;
  emit grains and bins as string columns; ratio parts as columns.
- `report.json`: `"embed": "required" | "model" | "none"` (default
  `required`) and `"embed_budget_mb"` (default 25). Over budget fails the
  build naming the fix.
- Blocks: one Parquet block per fact (`tracebi-slice-<fact>`), decision 8,
  `payload_sha256` in the manifest with the block's grain and columns; the
  calc payload (`tracebi-calc-plans`: every binding's plan, the control
  columns, the model label) embedded as JSON. The existing per-binding
  stamped blocks stay (they are the build-time values and the trace).
- `embed: none` emits neither and the page behaves as today.

Verify: for every reference report, each binding's plan run by
`DataModel.execute` over the slice equals the binding's stamped rows
(fingerprints equal under the rounding rule). A journey step in
`test_reference_project.py` asserts it for all of them.

### L-3 — `tracebi-calc.js` (JavaScript)

- `tracebi/reports/assets/_calc_src/`: `engine.js` (filter, group,
  aggregate, post-ops, exactly the plan vocabulary), `parquet.js`
  (hyparquet vendored, Snappy only), `index.js` (the message-free API:
  `tracebiCalc.load(blocks)`, `.run(plan, selection) -> {cols, rows}`,
  `.domains(column) -> values`). esbuild to `tracebi-calc.js`;
  `CALC_NOTICE.md` with attribution; `test_engine_assets.py` checks the
  bundle is rebuilt from source.
- Parity in node: `tests/test_calc_parity.py` runs every L-1 fixture through
  the bundle and compares rows after the rounding rule; float summation uses
  pairwise (Kahan) sums so 1e6-row columns stay within the rounding.
- Budget tests: bundle ≤ 50 KB gz; every fixture ≤ 100 ms in node.

Verify: parity suite green in node; budgets hold.

### L-4 — The live page (JavaScript, both lanes)

- `tracebi.js`: when `tracebi-calc-plans` is present, controls write the
  selection state (multi-select `data-tb-filter`, `data-tb-search` stays a
  display subset), the state goes to the URL hash, every binding's plan runs
  through `tracebiCalc.run`, results land in `_liveRows` and `paintValues`,
  `refreshBinding` redraws tables, charts, sparks and drawers. Control
  domains come from `tracebiCalc.domains` (values present under the current
  selection first, the rest after, none hidden). `data-tb-unfiltered-by`
  and `data-tb-fixed` set and shown as a small note. The trace drawer's row
  for a Local figure shows the plan, the selection and the block hash; the
  chip reads Local while the selection is not the authored one.
- Kit: `<Filter>` without `binding` is the page filter (already `"*"`);
  `<Filter multiple>`; nothing else changes for authors.
- Host bridge: the app stops answering `selection-request`; it still
  receives `tracebi-selection` to show the state in its header. Ask's
  "Keep this" posts the selection into the URL hash of the frame.
- Captures of every reference report at 1440 and 390, light and dark,
  before and after a selection; look at them.

Verify: the web journey opens the showcase from `file://`, selects a sector,
and asserts every value, chart, table and spark changed and the SQL figure
did not and is marked; `verify --local` (added here: replay the Local rows
the page recorded in a `data-tb-local` manifest block) reads Reproduces.

### L-5 — Coverage, retirement, the guides

- The showcase exercises every figure kind and chart type live, with a
  two-fact model (add `fact_cashflows` to the reference project's transform
  and model, joined on `dim_fund` and `dim_date`) so an unreachable field is
  demonstrated. `_INIT_SAMPLE_APP_JSX` carries a page filter. The two
  scaffold templates and the demo app's reports get a `<Filter>`.
- Remove: `tracebi-engine.worker.js`, `parquet_wasm_bg.wasm.gz`,
  `_engine_src/`, `selection_eval.py/.js`, the `tracebi-grain` block, the
  host `selection-request` path, `test_engine_float_parity.py`,
  `TestOfflinePort`, the "Further slices need the model" strings.
- Vocabulary (`capabilities.py` controls section rewritten around the
  selection state and `data-tb-fixed` / `data-tb-unfiltered-by`), both
  guides, the locked line (decision 9), `docs/reference/app-jsx.md`,
  `report-architecture-v2.md` §controls, `large-detail-artifacts.md` status
  line, CHANGELOG.
- Audit: `scripts/ui_audit.py` gains the engine-size and recompute-time
  metrics; baselines regenerated.

Verify: the full gate, `TRACEBI_E2E=1 test_ui_smoke.py`, the audit against
the new baselines, and a fresh `tracebi init` project builds and filters.

### L-6 — Time intelligence on the page (added after L-2b)

The SaaS reports are entirely `period_end` measures, so "every chart and
table type live" needs them. `period_end` is a grouped sum over (dims +
snapshot date) reduced to each group's latest date (`_apply_period_ends`);
`offset`/`growth` read a base measure one period earlier along the query's
time grain; `to_date` accumulates a base within a reset period. All three
are closed and portable:

- `calc_plan.py`: `period_ends: [{name, value_part, date_column}]` run after
  aggregates (the slice must carry the snapshot date column and `value:sum`
  at a grain that includes it; `slice.py` adds the date to the required
  grain for any fact with a period_end binding), `pops: [{name, base, unit,
  n, mode}]` and `to_dates: [{name, base, period}]` run after windows, over
  the result's time-grain column (string grains: the engine shifts
  `2026-03` by n months and derives the reset period from the grain label).
- Fixtures for each, with and without a selection; engine port; the
  reference journey's fixed-reason list shrinks to `sql binding`,
  `report.py`, `stddev`, `raw rows`, `having-contains`.
- `stddev` too if it is one function; raw-row tables (`aggregate=False`) as
  a plain filtered projection.

## Out of this round

The server half of [[duckdb-first]] (Q-2, Q-4, Q-5), `engine: duckdb`, a
Rust port, Qlik-style excluded values.

## Round 2 — the cascade (2026-10-19)

Round 1 made the page able to recompute. Round 2 makes every shipped report
use it, and gives the page the full interaction grammar a state-driven
report needs. Branch `cascade`.

### Decisions (closed)

11. **Every interaction is the one selection state.** A control, a click on a
    chart mark, a click on a table row, a range, a chip in the selection bar,
    the URL hash and `tracebi.setSelection` all write the same object; every
    figure re-runs from it. Nothing else moves a number.
12. **A chart mark click selects without a control.** On a live page a click
    on a bar, slice, point or legend entry writes `{column: [value]}` for the
    mark's x (or series) column when that column is in any fact's slice; a
    second click on the same value removes it; shift-click adds to the list.
    No `data-tb-filter` is needed for the column. Pages with `embed: none`
    keep today's control-only behaviour.
13. **A selection bar is always present on a live page.** The runtime
    inserts one under the masthead (`.tb-selection-bar`, or where the author
    put `<div data-tb-selection>` / kit `<SelectionBar/>`): one chip per
    selected field and value ("Sector: Software ×"), a "Clear" when more than
    one, hidden when the state equals the authored one. Escape clears.
14. **Ranges are a control.** `data-tb-range` (kit `<Range column min max step>`)
    writes `{column: {gte, lte}}` for a number column or a grain-label
    column (lexical, ISO-ordered); a two-handle slider for numbers, two
    month/quarter pickers for grains. Domain from `tracebiCalc.domains`.
15. **Cross-highlighting is presentation only.** Marks whose category is not
    in the current selection of their column draw at reduced emphasis in
    every chart on the page; numbers are untouched; off with
    `data-tb-highlight="off"`.
16. **Prose stays honest under a selection.** An inline `<Value>` in editorial
    copy recomputes like any figure; copy that asserts scope ("across all
    three funds") is either bound to a figure or rewritten so it is true
    under any selection. The reference reports are the example of how.
17. **The proof is mechanical.** One table-driven journey walks EVERY shipped
    report with a slice (reference, scaffold templates, demo): for each
    control picks its first present value, for each chart clicks its first
    mark, and asserts every non-fixed figure equals `execute_plan` over the
    slice under the resulting state, and that the trace rows record it. A
    new report with a control is covered the day it is added.

### Packages

- **C-1 Interaction grammar** (runtime, kit, CSS, vocabulary, guides,
  showcase, the table-driven journey of decision 17): 11–15 and 17.
- **C-2 Cascade: the portfolio reports** (book, concentration, overview,
  dashboard, desk): controls where each layout has a natural place (sector,
  fund, a fair-value range, a spread range), chart clicks, honest prose,
  bindings re-cut so no figure on these pages is `unfiltered-by` under the
  page's own controls; captures before/after, light/dark, desk/phone.
- **C-3 Cascade: housing, SaaS, templates, demo**: affordability (a year
  range and a cohort filter beside its scenarios), cohort_brief (cohort,
  month range), mrr_dashboard (plan + month range), the two scaffold
  templates, the two demo reports; same bar as C-2.
- **C-4 Audit pass** (orchestrator): fresh captures of every report, the
  audit script's ratchet, a fix round if needed.

## Round 3 — the server half

After the cascade: [[duckdb-first]] Q-2 (the model as a DuckDB schema and
locked read-only query connections), Q-4 (storage tiers, Parquet on object
storage as the hosted default), Q-5 (SQL transforms with Python as the
escape hatch), and the pandas medallion layers in `tracebi/etl/` moved to
DuckDB. Packages S-1 to S-4, briefed when Round 2 merges.
