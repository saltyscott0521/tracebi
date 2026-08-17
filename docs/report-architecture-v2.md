# Report Architecture v2 — the one-lane reshape

Status: **decided**. This document is the build plan. Inputs: `reshape-decisions.md` (locked owner direction), the AltsVault field notes, three candidate designs, and three judge verdicts. The skeleton is the *artifact-first* design (selected by two of three judges); mechanisms from *loop-first* and *presentation-first* flagged as graft-worthy are incorporated as decisions, not options, and every fatal flaw raised by any judge is resolved by name in §6.

---

## 1. Decision summary

**What changes:** TraceBi collapses to one report lane. A report is a directory under `reports/` — the existing template package, promoted — containing free agent-authored HTML/CSS/JS plus a `report.json` of stamped data bindings. Verification becomes a property of each **figure** (a DOM element declaring which binding feeds it), not of which folder the file lives in. The `requests/` lane is deprecated; JSON specs survive as a serialization that compiles into the same artifact; the section enum becomes a component vocabulary, not renderer control flow.

**The trust contract, restated per-figure:** every element that displays data either names a stamped binding (resolved query + lineage + SHA-256, embedded as fingerprinted bytes — the existing `embed.py` kernel, untouched) or carries an explicit `data-tb-unverified` mark that is recorded in the manifest and badged on the page. A figure with neither **fails the build**. There is no fourth state, and no silent third one. `report.py` remains the escape hatch; its outputs are stamped `verifiable: false` per binding — never per package — and never read green.

**Why:** the field notes showed the two-lane split forces a rewrite at the exploration→governed boundary, so exploration gets skipped and specs get written cold; meanwhile the governed lane's most-read numbers (metric KPIs) carried no receipt at all while `verify` printed "REPRODUCES", the binding grammar couldn't express "top 10", the REST surface couldn't reach declared measures, and the themed lane was the un-governed one. The reshape fixes all of these structurally rather than patching them: one artifact that starts unverified and *earns* its receipt figure by figure, one binding grammar across Python/spec/REST/MCP, one presentation stack that defaults well and lets agent CSS/JS win by cascade order, and transform contracts that extend the receipt to phase ① with honest wording ("the sink satisfied its contract," never "the pandas was verified").

**What does not change:** the stamping kernel (`embed.py` entire), `frame_fingerprint` as the one algorithm, manifest-first ordering, the CSP and self-contained single-file guarantee, `verifiable: false` never-green, presentation defaults never changing a number, the MCP gateway's no-write-to-warehouse rule, the registry contract (a report is a name plus a zero-arg factory resolving models at call time), the router import paths (the `test_phase5` rebind isolation is untouched), and the three-phase workflow with its freeze points.

**Naming decision (churn resolved):** no file renames. `template.html`, `report.json`, `style.css`, `script.js`, `report.py` keep their names; `TemplatePackage` grows in place and is re-exported as `ReportArtifact` (alias precedent: `BronzeLayer`/`LandingLayer`). Two of three judges scored zero-rename migration as materially lower-risk than artifact-first's `page.html` proposal; the skeleton's rename is dropped.

---

## 2. Architecture

### 2.1 The artifact — what a report IS on disk

A directory under `reports/` (or `TRACEBI_REPORTS_DIR`), building to one self-contained HTML plus one manifest:

```
reports/credit_marks/
  report.json      # declaration: identity + bindings (the stamped part) + libs/theme
  template.html    # the page — free HTML; figures marked with data-tb-* attributes
  style.css        # optional — stacked AFTER the default design system (later wins)
  script.js        # optional — runs AFTER the tracebi.js runtime
  report.py        # optional escape hatch AND exploration scratchpad — per-binding verifiable:false
```

Worked example, `report.json` (each `data` entry is exactly today's `DataRef`, resolved through `stamp()` → `embed_block()` → `embedded_record()` — kernel untouched):

```json
{
  "name": "credit_marks",
  "author": "agent",
  "description": "BDC credit marks — book stress, Q2 2026",
  "libs": ["echarts"],
  "theme": "brand.css",
  "data": {
    "kpi_universe": {
      "model": "altsvault_credit_marks",
      "query": {"fact": "fact_fund_marks",
                "measures": ["funds", "book_fv", "share_below_stress"]}
    },
    "marks_by_band": {
      "model": "altsvault_credit_marks",
      "query": {"fact": "fact_fund_marks", "measures": ["marked_fv"],
                "dimensions": ["dim_mark_band.band_label"],
                "order_by": [{"column": "dim_mark_band.band_order"}]}
    },
    "top_stressed": {
      "model": "altsvault_credit_marks",
      "query": {"fact": "fact_fund_marks",
                "measures": ["marked_fv", "fv_below_stress"],
                "dimensions": ["dim_fund.fund_name"],
                "order_by": [{"column": "fv_below_stress", "desc": true}],
                "limit": 10}
    }
  }
}
```

And `template.html` (excerpt) — the **figure grammar**:

```html
<!-- KPI: one cell of a one-row stamped binding. Closes field-notes finding #1. -->
<div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpi_universe"
     data-tb-cell="book_fv" data-tb-format="compact" id="fig-book">
  <span class="tb-kpi-label">Book at fair value</span>
  <span class="tb-kpi-value"><!-- filled by tracebi.js from the fingerprinted csv --></span>
</div>

<!-- Chart: default wiring draws from the embedded triple via ECharts. -->
<div data-tb-figure="chart" data-tb-binding="marks_by_band" data-tb-type="bar"
     data-tb-x="dim_mark_band.band_label" data-tb-y="marked_fv"
     data-tb-value-format="compact" id="fig-bands" style="height:320px"></div>

<!-- Table: rendered by tracebi.js with derived labels/formats. -->
<table data-tb-figure="table" data-tb-binding="top_stressed" id="fig-top10"></table>

<!-- Free-form: the agent's own script.js draws it; the receipt still covers the bytes. -->
<div data-tb-figure="custom" data-tb-binding="marks_by_band" id="fig-heat"></div>

<!-- Honestly unverified: allowed, badged, recorded in the manifest, never green. -->
<div class="tb-kpi" data-tb-figure="value" data-tb-unverified
     data-tb-note="analyst estimate, not model-backed" id="fig-estimate">…</div>

<!-- Exploration content: ships in dev and snapshots, stripped at final build. -->
<section data-tb-stage="exploration">
  <h3>Working note: null-mark funds</h3>
  <p>9 of 179 funds have a book but no computable marks. Options considered…</p>
  <table data-tb-figure="table" data-tb-binding="null_mark_funds" id="fig-nulls"></table>
</section>
```

**Rules (all build-enforced):**

- Any element carrying `data-tb-figure` must either name a binding (`data-tb-binding` naming a `report.json` entry or a `report.py` output) or carry `data-tb-unverified`. Neither → **hard build error** with did-you-mean hints. No fourth state.
- A `value` figure reads row 0 of the named column from the embedded triple — the same bytes the fingerprint covers (the `embed.py` no-display-copy invariant, extended to KPIs). A `value` figure over a multi-row binding is a **build error** with a hint.
- `id` is the stable figure address. Build assigns `fig-<n>` when absent, with a warning — authors should set ids, because ids are how humans redirect agents (§2.5).
- Figure extraction uses **stdlib `html.parser`** — a single tokenizer module, `tracebi/reports/figures.py`, shared by `report build`, the exploration-strip, and `verify --file`. Never a regex. Malformed nesting fails loudly (the `insert_before` philosophy). This resolves the skeleton's one silent-receipt-weakening vector (§6, flaw 1).
- Prose numbers outside figures are the accepted unprovable remainder (owner concession: layout is not provable, numbers are). The workbench and `report status` lint them non-blockingly ("3 numeric literals outside figures") — visibility, while the marked path remains the only compliant one for anything KPI-shaped.

**Embedding is never keyed off figures** (§6, flaw 3). At every build, all declared `data` bindings are embedded with `verifiable: true` and all `report.py` outputs with `verifiable: false` — always, whether zero figures or fifty reference them. Figures are a *claims layer* joined at verify time, not the embed driver. A zero-figure legacy package (e.g. `examples/portfolio_project/reports/portfolio_concentration/`) therefore embeds exactly what it does today, gains `figures: []` in its manifest, and verifies per-binding — no implementer guess, no silent coverage change.

**The per-binding verifiability seam:** the flattening at `template_package.py:221–227` is removed. A `report.py` in the directory no longer poisons the declarative bindings beside it — query bindings stay green-eligible; only python outputs are grey. `verify`'s `_verdict_fields` already handles the mixed receipt; this is a receipt *strengthening* (see monotonicity harness, §5).

**Lifecycle — exploratory to earned.** No mode field, no promotion step. Day 1 the agent scaffolds the artifact, writes everything in `report.py`, binds figures to python outputs: everything renders, everything badges grey, `verify` says so honestly. Hardening = moving stabilized queries from `report.py` into `data` bindings (and their logic upstream into transforms + declared measures); the figure markup doesn't change, only the binding's source. Exploration blocks hold scratch tables and working notes in the same file and are deleted by the build, not by a rewrite. **The file that found the answer is the file that ships.**

### 2.2 The binding grammar — one grammar, four surfaces

The grammar is `DataRef = {model, query: QuerySpec}`. Two changes:

**`QuerySpec` gains `order_by` and `limit`** (`tracebi/model/data_model.py:153–209`):

```python
order_by: tuple[dict, ...] = ()   # ({"column": str, "desc": bool}, ...)
limit: Optional[int] = None
```

- `from_dict` accepts the dict form plus `"col"`/`"-col"` string shorthand, normalized to the dict form — the stamped resolved spec is always canonical, so replay compares like with like.
- Sort applies after aggregation over result columns (validated via `spec_result_columns` in `check_query_spec`, agent-shaped did-you-mean errors); `limit` applies after sort.
- **`limit` without `order_by` is a validation ERROR, not a warning** (§6, flaw 2). "First 10 in groupby order" masquerading as "top 10" is the exact finding-#5 trap; the grammar refuses to express it.
- **Determinism guard, fingerprint-safe** (§6, flaw 7): when `order_by` or `limit` is present, the engine appends the remaining dimension columns as an implicit ascending tie-break and records the fully resolved ordering in the stamped spec — a "top 10" is reproducible on ties. When *neither* is present, the engine's output path is **byte-for-byte unchanged** — no tie-break is applied — so no existing v1 fingerprint can move. The regression test cites `data_model.py:1758–1760` (the engine already `ORDER BY`s group columns) as the reason today's fingerprints are stable, and asserts a corpus of pre-change fingerprints byte-identical post-change.
- Touch list: `QuerySpec` `to_dict`/`from_dict`, both engines, `check_query_spec`, `spec.json_schema()`, MCP tool schemas, `tracebi context`.

**One parser everywhere** (closes finding #2): `POST /api/models/{name}/query` drops its dict-only pydantic body and becomes a passthrough validated by `QuerySpec.from_dict` + `check_query_spec` — `measures: list[str] | dict[str,str]`, declared measures (ratio measures especially) reachable over HTTP, `order_by`/`limit` included, structured error shape preserved. The dict form remains valid, so no consumer breaks. The MCP gateway's query tool uses the same `from_dict`. One grammar in Python, JSON, REST, MCP; one validator behind all four.

**The metric-receipt hole (finding #1) closes in both lanes:**

- *Artifact lane, by construction:* a KPI is a `value` figure over a one-row binding — stamped, embedded, offline-checkable, replay-checkable, with zero new trust code.
- *Legacy spec lane, patched:* `spec.section_from_dict` stops discarding the metrics one-row frame — it attaches it as `section.dataset`, so the base-class manifest hook fingerprints it automatically and `verify` classifies it like any table; `data_coverage` counts METRICS as data-bearing; and `HTMLRenderer` generalizes `_chart_bindings` to `_data_bindings` so the one-row triple is **embedded in legacy spec HTML too** — `verify --file` covers the five biggest numbers on unmigrated pages, not just the manifest.

### 2.3 Per-figure verification — manifest v2 and both checks

`MANIFEST_SCHEMA_VERSION = 2` for artifact builds (legacy renderer output stays v1; the refuse-newer-schema path in `verify.py:424–440` is the compatibility mechanism it was reserved for). v2 adds:

```json
{
  "schema_version": 2,
  "stage": "final",
  "figures": [
    {"id": "fig-book",     "kind": "value", "binding": "kpi_universe", "cell": "book_fv"},
    {"id": "fig-bands",    "kind": "chart", "binding": "marks_by_band"},
    {"id": "fig-top10",    "kind": "table", "binding": "top_stressed"},
    {"id": "fig-heat",     "kind": "custom","binding": "marks_by_band"},
    {"id": "fig-estimate", "kind": "value", "binding": null, "unverified": true,
     "note": "analyst estimate, not model-backed"}
  ],
  "embedded_data": [ {"name": "...", "embedded_sha256": "...", "query_spec": {},
                      "model": "...", "verifiable": true} ],
  "sections": ["...carrier sections, unchanged shape..."],
  "transform_contracts": {"...": "see §2.6"}
}
```

**`verify` (replay):** per-binding classification is unchanged (`_verify_section` statuses: `reproduces / source_drift / model_changed / unverifiable / …`, including the `verifiable:false → UNVERIFIABLE` short-circuit). New rollup: each figure inherits its binding's status; `unverified: true` figures get a distinct **`UNVERIFIED`** status (author-marked — distinguishable from python-derived `UNVERIFIABLE`, so the receipt separates "we ran python" from "nobody claimed anything"); a figure naming a binding absent from the receipt is `ERROR` (internally inconsistent — fails). Verdict speaks figures first, bindings second:

```
figures: 12 checked — 9 reproduce, 2 unverifiable (python-derived), 1 unverified (marked)
bindings: 7 — 6 reproduce, 1 unverifiable
NOT fully verified: 3 figure(s) carry no green receipt (listed above)
```

Exit codes stay decided in one place: tampering/inconsistency fails; `unverifiable`/`unverified` never fail by default and never read green. New `--strict` flag fails when figure coverage < 100% — the CI gate for finalized reports. A v1 manifest (no `figures`) verifies exactly as today.

**`verify --file` (offline):** byte checks unchanged (`matches / tampered / missing_in_file / unrecorded_in_manifest / unbacked_by_section`). Added, using the same `figures.py` parser as build:

- every manifest figure must exist in the file with the same binding → else `figure_missing_in_file` (fails);
- every figure in the file must exist in `manifest.figures` → else `figure_unrecorded` (**fails** — an agent adding a figure to a shipped page, even one wired to an already-embedded block, is caught; symmetric with `unrecorded_in_manifest`);
- a bound figure whose data block is tampered/missing inherits that failure;
- **stage check:** the built HTML carries `<meta name="tracebi-stage">`; manifest `stage` vs file meta mismatch → `file_altered`. A draft can never be passed off as final.

The honest limit is printed, not hidden: *"figure markup verified; page scripting is not provable — the receipt covers the embedded bytes and the declared figure↔binding map."*

**Web parity:** artifact runs through the reports router stop using in-memory `build_manifest` (which bypasses `_augment_manifest` and ships no `embedded_data`); the router serves the real artifact render with read-only DuckDB connections, so web-rendered HTML becomes file-checkable for the first time. Rendering requires `analyst` (it executes queries); it persists nothing.

**Consolidation:** the three copies of the last-node-with-`query_spec` rule (`embed._query_metadata`, `verify._query_node`, `spec._data_ref_of`) collapse into one helper in `tracebi/model/dataset.py`.

### 2.4 The presentation system

**The stack.** New `tracebi/reports/stack.py` with one function, `presentation_stack(...)`, called by both `TemplatePackage.render` and `HTMLRenderer`. Injection order — via the existing `insert_before`, loud on missing tags — *is* the override chain (the `Theme.with_overrides` append-so-later-wins semantic promoted to page scale):

```
<head>:  CSP meta → tracebi.css (shipped) → reports/_theme.css (project) → style.css (report)
</body>: echarts → tracebi.js (shipped) → data blocks → tracebi-figures config → script.js (report)
```

The agent adopts, overrides, or ignores; it never forks. `reports/_theme.css` is the project-wide brand layer (underscore prefix — already skipped by discovery). CSP unchanged; everything inlined; self-contained guarantee intact.

**`tracebi.css`** — tokens (`--tb-font`, `--tb-ink`, `--tb-accent`, `--tb-chart-1..8` seeded from `ChartSpec.DEFAULT_PALETTE`, spacing/radius scale) and components: `.tb-page`, `.tb-grid`, `.tb-card`, `.tb-kpi`, `.tb-table` **including real `--striped`/`--compact` variants (finding #13 dies here)**, `.tb-callout`, receipt badges (`.tb-badge--verified` green, `.tb-badge--derived` grey "python-derived", `.tb-badge--unverified` amber), the exploration-block treatment, print rules. Rebranding is a dozen token overrides. The misleading "themeable from here" comment on the SVG chart classes in `theme.py` is corrected to "print/PDF path only."

**`tracebi.js`** — dependency-free runtime: parses each `tracebi-data-*` block once (the RFC-4180 parser promoted out of `_CHART_INIT_JS` — one parser, both lanes; **the stamped bytes are the only data source**); exposes `tracebi.data(name)`; auto-hydrates figures (tables with labels/formats derived per `derive.py` precedence including the `_FRACTION_BOUND` percent guard ported verbatim; `value` cells; ECharts option building with a `formatter` that is a JS port of `ChartSpec._fmt(compact=True)` — one implementation of "550.7B", so screen and print finally agree and **finding #11 dies**). A raw-ECharts deep-merge escape valve exists, but data series are always re-sourced from the stamped bytes afterward — config can restyle, never re-source. **Presentation defaults never change a number.**

**Receipt badges are ON by default in final output** (§6, flaw 8), rendered from the manifest-derived `tracebi-figures` config — author CSS cannot flip a grey badge green because the badge class is chosen from provenance, not by stylesheet. `report build --no-badges` exists for client deliverables; the manifest is unaffected either way.

**Threading:** `HTMLRenderer.for_project(root)` (resolving stack layers 1–2) replaces all **twelve** bare `HTMLRenderer()` construction sites — the eleven from finding #10 (`cli.py:135,754,1085,1966`; `_dev_server.py:66`; `mcp_server.py:436`; `web/api/main.py:162`; `routers/reports.py:47,64,122`; `routers/requests.py:97`) **plus `reports/report.py:778`** (the notebook `_repr_html_` preview, which no design listed; verified this session). `ReportSpec` gains top-level `theme` and `script` keys (schema regenerated, `additionalProperties` stays false); `report build` and `spec render` gain `--theme`. One choke point; no future site can regress to unthemeable. Finding #10 dies as a category.

**Vocabulary as data:** `tracebi context` gains a `presentation` key — tokens, component classes, `data-tb-*` attributes, runtime signatures as JSON. The field notes proved agents author successfully from context JSON alone; the new surface ships the same way.

### 2.5 The authoring loop and the human-review surface

**Division of labor, stated plainly:** the *narrative* of an investigation — "I
tried X, saw Y, so did Z" — lives in the agent↔human conversation, which does
it better than any artifact could. TraceBi's job is the **evidence layer the
narrative points at**: addressable figures, inspectable data, visible code,
honest badges. Everything below builds that layer and deliberately stops
short of replicating a notebook's narrative spine. (Scaffold guidance:
exploration blocks are allowed to be ugly — default components only; layout
polish is finalization work.)

**`tracebi dev <name>` becomes artifact-native.** The dev server's build function is replaced by a form-aware `render_target` (artifact directory → in-memory artifact render; legacy `.json` spec → spec render; legacy request script → deprecated path, one minor version). The watcher is **rewritten from single-file mtime to a directory + `models/` scan** — the current loop watches one file (`_dev_server.py:93–107`), and no milestone estimate assumes otherwise (§6, flaw 5). All DuckDB connections in dev/serve open **read-only**, so `dev`, `report build`, and `serve` coexist (bug #12's fix is a sequenced dependency, see M3). Errors render as the existing auto-reloading traceback page.

**The workbench** — `GET /__workbench` on the dev server (dev-only; never injected into build output): a generated review page, same design system, four panels:

1. **Figures** — every figure: id, kind, binding, live provenance badge, resolved query pretty-printed, and a **copy-address** (`credit_marks#fig:top10`) so the human redirects the agent in precise terms ("kill `#fig:by_manager`, make `#fig:top10` a top-10 by marked dollars"). Coverage headline: *"9 of 12 figures model-backed"* — the earn-your-receipt progress bar.
2. **Data** — per binding: first rows (the exact triple bytes), dtypes, row count, fingerprint prefix, source (query vs `report.py`), unused-binding warnings. **Quick-charts:** pick a binding and x/y in the panel to see a dev-only chart immediately — with the generated `data-tb-figure` markup beside it, ready to paste into `template.html`. This keeps interrogation at notebook-cell ceremony (declare a binding, see the table; two clicks, see the chart); adopting a figure is copying markup you already watched work. Quick-charts never persist and never touch the build.
3. **Code** — `report.py`, `report.json`, `script.js`, read-only and highlighted; the eight-cleaning-decisions problem becomes visible to the reviewer instead of buried.
4. **Lint** — non-blocking: numeric literals outside figures, bindings no figure references.

**The exhibit feed (owner iteration, 2026-08-16: "steer from chat, see
results in the workbench").** A fifth panel — chronological, newest first —
that makes the workbench the agent's *show* surface, not only an inspection
surface. Two sources feed it:

- **Explicit exhibits** — `from tracebi.workbench import show;
  show(df, note="after dropping the 9 null-mark funds")` callable from
  `report.py` or any exploration code. Accepts a frame (excerpt + dtypes), a
  binding name (renders its table/quick-chart), a code string, or markdown.
  Zero ceremony — the notebook-cell-output equivalent. `show()` is a **no-op
  outside dev** (a build or CI run ignores it entirely), exhibits carry no
  receipts and never enter builds; snapshots include the feed as part of the
  exploration record.
- **Auto-entries** — the dev loop appends one-line events as work lands:
  "binding `marks_by_band` updated · 6 rows · fingerprint 18ac…", "figure
  `#fig:top10` bound". The feed reads as a live lab log of the session.

**Pins — the one portal→chat gesture.** The human can pin any exhibit or
figure in the workbench; pins (with an optional one-line note) surface in
`tracebi report status --json` and the MCP `workbench_state` tool, so the
agent's next look at the project sees exactly what the human flagged.
Steering stays in chat; *pointing* happens where the evidence is. Pins are
dev-state, never in builds or manifests.

**The sendable snapshot** — for a human not at the dev server: `tracebi report snapshot <name>` → one self-contained file with exploration blocks kept, a persistent visible EXPLORATION banner, `<meta name="tracebi-stage" content="exploration">`, and **no manifest at all**; `verify --file` recognizes the meta and refuses by name ("this is a review snapshot, not a published report"). The snapshot ends with a **code appendix** — `report.py`, `report.json`, `script.js`, read-only and highlighted — so a reviewer away from the dev server can still "look through the code if necessary" (notebook-export parity), receipt-free like the rest of the file. A weaker-looking receipt is worse than none, so the snapshot carries none — and the stage meta plus manifest `stage` cross-check (§2.3) means no draft-shaped output can ever read as final. This resolves the skeleton's missing non-colocated handoff without ever minting a draft receipt.

**Agent-facing coverage:** `tracebi report status <name>` prints the earned state from the CLI (`17 figures: 12 query-backed, 3 python-derived, 1 unverified, 1 unbound-ERROR; 1 declared binding unused`) — what a driving agent and CI actually call. The MCP gateway gains a read-only `workbench_state` tool returning the same JSON the panels render from; no-write-to-warehouse untouched.

**Finalize:** `tracebi report build <name>` → exploration blocks stripped (same `figures.py` parser, loud on malformed nesting), manifest-first, one HTML + v2 manifest in `output/`; `tracebi verify --strict` as the CI gate for "finished."

### 2.6 Transform contracts — the receipt extends to phase ①, honestly

New module `tracebi/contracts.py`. Declared in the transform, checked at sink time against the sunk tables as read-only SQL, recorded — never tracing the pandas (manifesto refusal stands).

```python
# transforms/holdings_transform.py — after the sinks
from tracebi.contracts import contract

with contract("holdings", warehouse=WAREHOUSE) as c:
    c.rows("fact_fund_marks", at_least=50_000)
    c.unique("dim_fund", ["fund_key"])
    c.not_null("fact_fund_marks", ["fund_key", "marked_fv"])
    c.foreign_key("fact_fund_marks", "fund_key", refers_to=("dim_fund", "fund_key"))
    c.reconcile("fact_fund_marks", "book_fv", against=("fact_positions", "fv"),
                by="fund_key", tolerance=0.01)
```

Closed declarative check vocabulary (`rows`, `unique`, `not_null`, `foreign_key`, `values`, `reconcile`) — no callables, fully re-runnable data. Any failure **raises**: a sink that violates its contract does not freeze a warehouse that claims otherwise. On success the record is written to `data/warehouse.contracts.json` beside the warehouse (the freeze point carries its own certificate): per check `{check, params, observed, passed}`, per table a fingerprint, timestamp, transform name.

**The fingerprint join, pinned** (§6, flaw 4 — the one flaw all three designs shared): the sink-time table fingerprint is **not** computed from the in-memory pandas frame handed to `write()`. It is computed by reading the sunk table back through **`DuckDBConnector.load()` — the same connector path the model uses at load time** — and fingerprinting that frame with the one algorithm (`frame_fingerprint`, `dataset.py:20–35`). Any dtype or ordering normalization the write-then-read round trip performs is therefore *inside* both sides of the comparison, and the join to the manifest's per-table input fingerprints (`_input_index`) cannot be permanently "stale" with no actual drift. A round-trip equivalence test (write → load → fingerprint twice, must match) gates M4.

At `report build`, contract results attach to the manifest's `transform_contracts` block only where the recorded table fingerprint **equals** the report's input fingerprint → `satisfied`; mismatch → `stale` (the warehouse moved after the check — stale can never inherit green); absent → `no_contract` (reported, never failed — contracts are opt-in like all attribution). Fixed verify language, locked by design review: **"the sink satisfied its contract" — never "the transform was verified"** — and **"contract status never colors figure statuses: two claims, reported side by side, never blended."** `tracebi verify --contracts` optionally re-runs the checks against the current warehouse and classifies drift. The scaffold transform and `tracebi context` grow a contract stanza so agents declare them by default — the field notes' "it was conscience, not the framework" becomes the framework.

---

## 3. What happens to every existing form

| Form | Fate | Mechanism |
|---|---|---|
| **Template packages** (`reports/<name>/`) | **They ARE the artifact.** | No file renames. Per-binding `verifiable` replaces the flatten; figure grammar and stack are additive. Zero-figure packages embed exactly as today (§2.1) and verify per-binding. `TemplatePackage` re-exported as `ReportArtifact`. |
| **JSON specs** (`reports/<name>.json`) | **Kept as a serialization; not a lane.** | Continue rendering through the current path (now themed via `for_project`, with metric fingerprints + embedded KPI triples — findings #1/#10 closed in place). `tracebi migrate spec <file>` compiles a spec into an artifact: each section becomes a default-component figure bound to its `DataRef`; the section enum becomes compile vocabulary, not renderer control flow. Until migrated, nothing breaks. |
| **`requests/`** | **Deprecated; working; removed in 0.8.** | Router, `tracebi run`, and `dev --request` keep working through 0.7 with deprecation notes; `tracebi init` stops scaffolding the folder; docs/`tracebi context` present the one lane. Migration is mechanical: queries → bindings, pandas → `report.py`, sections → component figures. No auto-converter — a request that matters gets rebuilt in the loop once. |
| **Section enum** (`SECTION_CLASSES`) | **Kept** as the compiler's vocabulary and the carrier-section mechanism; dies as renderer control flow for the primary lane. |
| **Excel renderer** | **Kept, unchanged semantics** — applies only explicit `number_formats`, derives nothing; a spec rendering to both stays checked in both. |
| **PDF/SVG chart path** | **Kept, unshipped**, for the future PDF renderer only; docstring corrected. `chart_dpi`/`chart_style` no-ops stay deprecated. |
| **`Theme` / `DEFAULT_CSS`** | **Kept** — `Theme` feeds the stack; `DEFAULT_CSS` serves the legacy shell. |
| **Kernel, verify, registry, discovery, CSP** | **Kept, untouched in contract** — `embed.py` entire; verify statuses extended, never re-meant; report = name + zero-arg factory; no router import paths change. |
| **Removed now** | **Nothing.** The first release is purely additive plus the M0 fixes. |

---

## 4. Phased build plan — riskiest first

The kernel exists; the two genuinely risky claims are (i) the per-figure receipt on a free-form page and (ii) whether the one-lane loop is actually good to author in. M0 de-risks (i)'s seams inside the current lanes; M1 proves (i) and (ii) together on the real workload, with kill criteria.

**M0 — Kernel seams (small; de-risks everything; v1 manifests throughout).** ✅ **Shipped 2026-08-16** — all proof gates green (mixed receipt honest; grammar unified with fingerprint parity; pre-change corpus byte-identical; findings #1/#2/#5 closed; monotonicity harness in CI).
Per-binding `verifiable` in `TemplatePackage.render`; `QuerySpec.order_by/limit` with canonical normalization, the guarded tie-break (only when order_by/limit present), and limit-without-order_by as a hard error; REST/MCP grammar unification on `QuerySpec.from_dict`; `MetricSection.dataset` retention + `data_coverage` counting METRICS + `_data_bindings` KPI embedding in legacy HTML; the query-node-rule consolidation; the **receipt-monotonicity harness** built as a fixture (see §5) and wired into CI from here on.
*Proof gate:* a mixed receipt verifies honestly today with v1 manifests; the same spec through Python/spec/REST returns identical fingerprints; a corpus of pre-change fingerprints is byte-identical post-change (citing `data_model.py:1758–1760`); findings #1/#2/#5 closed in the current lanes before any new artifact exists.

**M1 — The artifact, figures, verify v2 (the riskiest, on solid seams).** ✅ **Shipped 2026-08-16** — mechanical proof gates green (figure validation, strip, schema-2 manifests, per-figure verify + --strict, symmetric offline cross-check, snapshot refused by name, stage mismatch caught; drilled live on the reference project). *Outstanding: the AltsVault artifact rebuild with the maintainer reviewing — the authoring-experience kill criterion is judged there.*
`figures.py` (`html.parser` extraction — build, strip, and `--file` share it); figure↔binding build validation incl. `data-tb-unverified` and the multi-row-value error; exploration blocks + strip; manifest schema 2 (`figures`, `stage`); verify per-figure rollup with `UNVERIFIED`; `--file` symmetric cross-check (`figure_missing_in_file` / `figure_unrecorded`) + stage check; `--strict`; `report snapshot` (no manifest, refused by verify); output to `output/`.
*Proof gate (the milestone that validates or falsifies the design):* **rebuild the AltsVault 28-section report end-to-end as one artifact, agent-driving, human reviewing** — mixed verifiable/derived/unverified figures classified correctly offline and by replay; a tampered figure caught offline; a snapshot refused; a stage mismatch caught. *Kill criterion, stated honestly:* if authoring free HTML with components is worse than the spec enum was, we learn it here for the price of one milestone, before M2+ builds on it.

**M2 — The presentation system.** ✅ **Shipped 2026-08-16** — all proof gates green (zero-effort page browser-verified; later-wins chain pinned; byte-exact fmt parity fuzz-verified; CSP + self-containment hold; findings #10/#11/#13 dead at every surface including the notebook preview).
`tracebi.css` (tokens, components incl. `--striped/--compact`, badges, print), `tracebi.js` (parser promotion, hydration, `_fmt` port, config merge), `stack.py` + `HTMLRenderer.for_project` threaded through all **twelve** sites, `reports/_theme.css` layer, spec `theme`/`script` keys, `--theme`, badges default-on + `--no-badges`, `presentation` key in `tracebi context`.
*Proof gate:* zero-effort page looks shipped; later-wins override chain tested; screen and print agree on `550.7B`; CSP and self-containment byte-verified; findings #10/#11/#13 dead at every surface including the notebook preview.

**M3 — The loop.** ✅ **Shipped 2026-08-16** — proof gates green live: the workbench served with coverage bar, provenance badges, copy-addresses, quick-charts; a pin placed in the portal read back through `report status` (📌) and MCP `workbench_state`; `report build` succeeded WHILE `tracebi dev` served the same warehouse (bug #12 dead); web-rendered artifact HTML passes `verify --file`.
`tracebi dev` artifact-native with the rewritten directory + `models/` watcher; read-only DuckDB in dev/serve (**hard dependency: bug #12's fix lands first**); `__workbench` with the four panels and copy-addresses; `report status`; MCP `workbench_state`; web-run parity (`embedded_data` over HTTP, mtime-cached).
*Proof gate:* land → interrogate → review at one URL → finalize with no rewrite; `dev` + `build` + `serve` coexist against one warehouse; web-rendered artifact HTML passes `verify --file`.

**M4 — Transform contracts.** ✅ **Shipped 2026-08-16** — all proof gates drilled live on the reference project: the transform's assertions (row floor, unique issuer key, not-null, two foreign keys) declared as its contract and surfaced in the shipped manifest's `transform_contracts` block; a violated contract raised at sink time and wrote no certificate; a silent re-sink read `stale` in the rebuilt manifest while the figures stayed honestly green (two claims, side by side, never blended); `verify --contracts` re-ran the declaration and exited 1 on a check the sink no longer satisfied; the write→load→fingerprint round-trip equivalence test (ints, floats+NaN, strings+None, dates, booleans, nullable Int64) gates the join in CI.
`tracebi/contracts.py` with the closed vocabulary; `data/warehouse.contracts.json`; the **pinned** connector-load-path fingerprint plus the round-trip equivalence test; manifest `transform_contracts` join (`satisfied/stale/no_contract`); `verify --contracts`; scaffold + `tracebi context` stanzas.
*Proof gate:* the AltsVault transform's four hand-written assertions express as declared contracts and surface in the shipped receipt; a violated contract fails the transform run; a re-sunk table reads `stale`, never green; the round-trip test passes on every shipped connector dtype.

**M5 — Migration and deprecation.** ✅ **Shipped 2026-08-16** — the reference spec compiled live (`tracebi migrate spec reports/portfolio_dashboard.json`): every dropped presentation knob warned by name, the compiled package built through the ordinary artifact gate with all 7 figures REPRODUCES and the contract join satisfied, its claim set a superset of the spec render's (4/4 fingerprints carried, then figures on top), the package shadowed the spec at discovery with a warning naming both, and rollback was deleting the directory — the spec lane rebuilt and verified green. A superset test (`test_compile_spec.py::TestCompiledArtifactBuilds`) pins the monotonicity gate in CI; `init` no longer scaffolds `requests/`; the requests surfaces (router, `tracebi run`, `dev` script branch, `new-request`) carry one shared deprecation note, removal in 0.8.
`tracebi migrate spec` compiler (every `SectionType` compiles, markdown TextSections honored — absorbing #4's docs promise); `init`/`new-report` scaffold the artifact and no `requests/`; deprecation notices (requests router, `tracebi run`, `dev --request`); docs/`AGENTS.md`/MANIFESTO/`WORKFLOW.md`/CHANGELOG vocabulary; the test-flip ledger (§5) fully executed.
*Proof gate:* the AltsVault 28-section spec compiles to an artifact whose verify output is a strict superset of the original's (monotonicity harness) — nothing that was green goes dark; a fresh `tracebi init` onboards an agent straight into the loop.

Intersecting pure bugs, sequenced not designed: **#12** (DuckDB lock) before M3; **#14** (`output/` naming) settled in M1; **#3** (preview NaN) sanitizer reused by the workbench data panel; **#8** (`git init`) strengthens every manifest M1 produces.

---

## 5. The test and migration story

The suite (849 passing; run it for the current count) grows and is never reorganized. Phase-scoped files stay phase-scoped (CLAUDE.md rule); the deliberately-fragile registry-rebind isolation in `tests/test_phase5.py::TestPipelineRunEndpoint::test_run_all_layers` is untouched by every milestone — no router import paths change.

**New files, one per area:** `tests/test_artifact.py` (folder load, figure extraction incl. hostile markup through `html.parser`, exploration strip, per-binding verifiable, zero-figure embed equivalence, stack injection order), `tests/test_binding_grammar.py` (order_by/limit canonicalization; tie-break determinism; limit-without-order_by rejected; REST/Python/spec fingerprint parity; pre-change fingerprint corpus), `tests/test_verify_v2.py` (figure rollup, `UNVERIFIED` vs `UNVERIFIABLE`, `figure_unrecorded`, stage mismatch, snapshot refusal, `--strict`, v1-manifest bit-for-bit regression), `tests/test_presentation.py` (later-wins, badge provenance, formatter parity, CSP), `tests/test_contracts.py` (vocabulary, sink failure raises, round-trip fingerprint equivalence, `stale`/`no_contract`), `tests/test_compile_spec.py` (every SectionType compiles).

**The receipt-monotonicity harness** (grafted; CI from M0): for every example spec and package, build old-path and new-path manifests and assert the set of fingerprinted, verifiable claims in the new one is a **superset**. A change that silently weakens a receipt fails CI — the design's own contract applied to itself.

**The test-flip ledger** (grafted) — existing expectations that change, each tied to its milestone, enumerated up front rather than discovered mid-build:

| Milestone | Flip |
|---|---|
| M0 | Package tests asserting all-or-nothing `verifiable` → per-binding. Metric-manifest golden dicts gain `dataset_fingerprint`/`dataset_lineage`. `data_coverage` tallies change. REST tests asserting 422 on list-form measures → 200. |
| M1 | Artifact-build manifest goldens → `schema_version: 2` + `figures` + `stage`. `report build` output path assertions → `output/`. |
| M2 | Any golden HTML → includes the default stack (badges on). |
| M3 | Discovery test asserting the package factory returns the carrier Report → returns the real page. |
| M4 | v2 manifest goldens gain `transform_contracts`. |

Everything else in the current suite passes unmodified: the v1 manifest path and the legacy render path are its subject, and both are unchanged except the M0 fixes, whose assertions land inside the owning phase files.

---

## 6. Explicitly resolved flaws, and open questions

### Every fatal flaw the judges raised, and how it is resolved

1. **Regex figure extraction (artifact-first; judges 1 & 2 — the silent-receipt-weakening vector).** A regex-missed figure would vanish from both build validation and the offline check. *Resolved:* one stdlib `html.parser` tokenizer module (`tracebi/reports/figures.py`) is the sole extractor, shared by `report build`, the exploration strip, and `verify --file`; malformed nesting fails loudly. No regex touches figure markup anywhere (§2.1, §2.3, M1).
2. **`limit` without `order_by` only warns (artifact-first; judges 2 & 3).** *Resolved:* hard validation error in `check_query_spec` — the grammar refuses to express "first N masquerading as top N" (§2.2, M0).
3. **Zero-figure embedding unspecified (artifact-first; judge 1).** *Resolved:* embedding is decoupled from figures entirely — all declared bindings always embed `verifiable:true`, all `report.py` outputs `verifiable:false`, figures are a claims layer joined at verify. Zero-figure legacy packages embed exactly as today, with a dedicated equivalence test (§2.1, M1).
4. **Contract fingerprint join can be permanently stale (all three designs; judge 1).** *Resolved:* the sink-time fingerprint is pinned to the connector load path — read the sunk table back through `DuckDBConnector.load()` and fingerprint that frame, so any write/read dtype or ordering normalization sits inside both sides of the join; a round-trip equivalence test gates M4 (§2.6).
5. **"Dev watch loop kept verbatim" is false (loop-first; judge 1).** *Resolved by not inheriting the claim:* M3 explicitly budgets a rewrite from single-file mtime polling to a directory + `models/` scan (§2.5).
6. **No explicit unverified mark (loop-first & presentation-first; all judges).** *Not applicable to the skeleton, and locked in:* `data-tb-unverified` + `data-tb-note`, recorded in the manifest, distinct `UNVERIFIED` verify status, build fails on a figure with neither binding nor mark (§2.1, §2.3).
7. **Always-on total ordering could move existing v1 fingerprints (loop-first; judge 2).** *Resolved:* the tie-break applies only when `order_by`/`limit` is present; queries without them keep today's byte-for-byte output, guarded by a pre/post fingerprint corpus test citing `data_model.py:1758–1760` (§2.2, M0).
8. **Receipt badges opt-in on shipped pages (presentation-first; judges 2 & 3).** *Resolved:* badges default-on in final output, provenance-derived so author CSS can't flip them, `--no-badges` for client deliverables, manifest unaffected either way (§2.4).
9. **Missing figure cross-check on shipped pages (loop-first; judge 2).** *Kept from the skeleton and made symmetric:* `figure_unrecorded` and `figure_missing_in_file` both fail `verify --file` (§2.3).
10. **No non-colocated review handoff / draft-receipt risk (artifact-first ding; judges 1 & 2 with conflicting grafts).** *Resolved by combining them:* the sendable form is the receipt-**free** snapshot (EXPLORATION banner, stage meta, no manifest, refused by verify by name) — no draft receipt ever exists to launder — while the stage meta + manifest `stage` cross-check supplies loop-first's draft-never-reads-final guarantee for anything that *does* carry a manifest (§2.5, §2.3).

### Open questions — resolved by the maintainer (2026-08-16)

1. **`requests/` removal horizon** — confirmed: deprecated through 0.7, removed in 0.8.
2. **`output/` naming** — confirmed: `report build` renders to `output/` (finding #14 absorbed the cheap way; no folder renames).
3. **`migrate spec` disposition** — confirmed: emit alongside, warn on name collision; the discovery-shadowing rule is: an artifact directory shadows a same-named `.json` spec, with a startup warning naming both.
4. **0.6.0 sequencing** — moot: no release for months by the maintainer's direction; milestones are release-agnostic and the cut point stays the maintainer's.