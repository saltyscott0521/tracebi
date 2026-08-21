# Large-detail artifacts — data-heavy, offline, still verifiable

**Status:** BUILT on `feat/artifact-parquet-embed` (not yet merged). The design below is the
plan as agreed; §11 records where the implementation deliberately diverged after two
adversarial reviews. Supersedes the "just add a size guard" stopgap and the
DuckDB-vs-Parquet open question in the scale audit (ROADMAP 11c).

**One-line:** let a single self-contained artifact embed up to ~500MB-of-JSON-equivalent
of detail, filter it client-side, and still open offline and re-check with `verify --file` —
by shipping **Parquet + parquet-wasm + Arquero in a Web Worker**, all inlined, with the
receipt moved to a format-independent content hash.

---

## 1. The problem

Today every figure's data is embedded as **CSV** in `<script type="application/json">`, and
`tracebi.js` renders one `<tr>` per row. Measured ceiling (scale audit): the browser render
wall hits first — ~500k rows freezes the tab — and file size hits second (~44MB HTML at 500k
rows). That caps the artifact at "aggregates + small tables," and any interactive filter over
detail is impossible because the detail isn't there.

Requirement (maintainer): hold up to **~500MB JSON-equivalent** of detail so a reader can
**filter interactively** — and keep **one method for every artifact** (no CSV/Parquet split,
engine always included), still **opening offline from `file://`** (emailable receipt).

---

## 2. The decision

**Embed Parquet(ZSTD). Decode it with parquet-wasm. Query it with Arquero (Arrow bridge =
`@uwdata/flechette`). Run all of that in a blob-URL Web Worker. Inline everything so it opens
offline with no network.**

| Layer | Choice | Why |
|---|---|---|
| Data format | **Parquet (ZSTD)** | ~50× smaller than JSON *on our data*; the one self-compressing columnar container that a WASM reader decodes natively. No CSV/Parquet mix. |
| Decoder | **parquet-wasm** (~1.2MB brotli; read-only build ~456KB) | Small WASM, instantiates from an embedded byte buffer — no HTTP fetch, works from `file://`. |
| Query engine | **Arquero** (~0.2MB) via **flechette** (~14KB gz) | Column-oriented filter/groupby/rollup over the decoded Arrow; million-row proven; tiny. |
| Execution | **blob-URL Web Worker** | Keeps the 0.5–0.9s query off the main thread so the UI never freezes; blob workers run from `file://`. |
| Charts / tables | **ECharts** (shipped); grouped results render directly in the vanilla runtime | We aggregate first, so the rendered output is always small — no virtualization library needed. The artifact runtime is vanilla `tracebi.js`, not React. |

**Engine floor ≈ 3MB** per artifact (parquet-wasm + Arquero + flechette), in the same weight
class as the ECharts runtime we already ship. A 500MB-JSON-equivalent artifact lands **~14MB**.

### Why not DuckDB-WASM
Not a speed decision — it's fast enough (TPC-H Q1 0.855s/3M rows; HF SQL Console filters 12.6M
rows in <3s). It loses on our constraints:
- **Hostile to `file://`**: needs its wasm fetched over HTTP with CORS, wants COOP/COEP headers a
  double-clicked offline file can't set. Effectively requires a web server.
- **~18MB eh.wasm (~6–10MB gz)** engine — every artifact would pay it.
- Needs cross-origin isolation to multithread (unavailable in a static file).

**Reserve DuckDB-WASM** only if full in-browser SQL (multi-table joins, window functions) or
>~10–20M rows ever becomes a hard requirement. hyparquet (pure-JS, ~10KB) is dead on its
row-object path (measured 22s / 2M rows) but has a columnar `onChunk` API worth a re-benchmark
to maybe drop parquet-wasm's WASM — later, not now.

---

## 3. Everything runs offline — no internet, ever

The Web Worker is a background thread *inside the tab*, not a server. Self-contained means:
- **Worker code** — embedded as text, started via a `blob:` URL built in memory.
- **Engine (parquet-wasm)** — embedded as base64, decoded to bytes, `WebAssembly.instantiate(bytes)`
  inside the worker. No download.
- **Data (Parquet)** — embedded as base64 in the same file.

Open the `.html` on a plane → worker spins up locally → engine loads from embedded bytes →
queries embedded data. Zero network in the loop. Keep the **strict CSP**; the one thing that
would need a network fetch (apache-arrow-js's ZSTD-IPC codec) is avoided because parquet-wasm
decodes ZSTD-Parquet internally.

---

## 4. Scale envelope (measured + validated)

Measured in-app Chromium, representative BI fact table (dims + high-card id + float measures):

| rows | Parquet(ZSTD) | JSON-equiv | parquet-wasm decode | Arquero query | self-contained file |
|---|---|---|---|---|---|
| 1M | 4.3 MB | ~214 MB | ~420 ms | ~450–900 ms | ~7 MB |
| 2M | 8.4 MB | ~427 MB | ~420 ms | ~500–935 ms | ~14 MB |

Validated against production usage:
- 2.3M rows / ~14MB is **~8× below** the demonstrated 18M-rows-in-browser point (Mosaic/DuckDB-WASM)
  and **~40× below** the ~100M-row / 2–4GB-WASM OOM wall.
- Base64 ~14MB in one `<script>` node ≈ 2% of V8's ~512M-char string cap, and lives in one node
  (no DOM-node memory blowup).
- Precedent: HF SQL Console, Observable/Mosaic, Evidence, Tableau Public (15M rows / 1GB cap).

**We are novel** in inlining data into *one* file — Evidence, Observable Framework, and marimo all
deliberately split data into HTTP-fetched assets (caching/lazy-load). We forgo browser caching for
portability; a fair trade for an emailable receipt.

**Real risks (design around, not blockers):**
- **Mobile Safari memory** — decoded columns materialize in RAM (~100–200MB at 2M rows), and WASM
  memory plateaus at its high-water mark. The grain contract (§6) is the governor; mobile needs
  explicit testing.
- **Interaction latency** — a full rescan per brush is >100ms. Mitigate with the worker (perceived
  responsiveness) and, for continuous brushing, precomputed bins (§6).

---

## 5. Rendering the result — vanilla, small by default, virtualized when not

The artifact runtime is vanilla `tracebi.js`, **not React** — but "aggregate-first" does **not**
guarantee a small *output*: a high-cardinality group-by ("revenue by customer" over millions of
customers) or a **filtered detail view** (the core of the "hold detail + filter" premise) can return
tens of thousands to millions of rows. So:

- **Charts**: **ECharts** (canvas, already vendored) — TanStack is a tabular/list tool, not a charting
  library, so it plays no part here.
- **Tables ≤ ~10 rows**: render inline, no scroll box.
- **Tables > ~10 rows (configurable): one fixed-height, scrollable table component**, backed by
  **`@tanstack/virtual-core`** — framework-agnostic (zero deps, no React; a few KB), drops into vanilla
  `tracebi.js`. It's headless: it hands back visible row indices + offsets and `tracebi.js` renders the
  `<tr>`s. The *same* component serves 11 rows and 900k rows with identical UX — at 11 it renders all 11
  and scrolls; at scale it renders only the ~visible window. No small-vs-large code fork. Pairs with the
  worker (worker returns the result, virtual-core windows the DOM).
- **Print / no-JS / screen-reader**: **expand to the full set** — print CSS unsets `max-height`, the
  runtime renders all rows (or the SSR'd full slice) — so the numbers stay real, verifiable text on
  paper and offline. Compact scroll box on screen; linearized full table on print.

**Why DOM virtualization, not a canvas grid (Glide/Perspective):** `virtual-core` keeps **semantic
DOM** — the numbers stay real text, so they **print, are screen-reader accessible, and server-render**
for the no-JS/receipt story. A canvas grid's cells are *pixels* — no print, no a11y, no SSR — which
breaks the "the number in the file is real, verifiable text" property the receipt depends on. DOM
virtualization caps ~650k–930k rows (browser scroll-pixel ceiling); past that, paginate or cap. Reach
for a canvas grid (Glide) or FINOS Perspective only if a raw multi-million-row grid ever becomes the
deliverable — explicitly outside this design, and in tension with the receipt.

No WebGL/deck.gl (that's for 1M+ individual marks, which an aggregated BI artifact never draws).

---

## 6. Trust core (orthogonal to the engine, but this is where the care goes)

1. **Content-hash fingerprint (fingerprint_algo v-next). — DE-RISKED (Phase-2 spike).** Parquet bytes
   are **not reproducible** (writer version, row-group layout, codec details vary), so we cannot hash
   the blob. Hash a **format-independent canonical content digest**: SHA-256 over column names +
   per-column canonical serialization of values **in row order** (row order is preserved across
   writers — do NOT sort). Serialize **by declared type**: `Decimal`→exact `str` (money-safe),
   float→shortest-round-trip `repr` normalizing `-0.0`→`0.0` and NaN, int→`str`, date/ts→ISO instant
   (tz-normalized), null→sentinel. **Proven format-independent**: one hash across 5 Parquet
   encodings/writers while raw bytes differ; verify recomputes it from the decoded data. Storage
   (Parquet) is transport; the receipt is over content, so storage can change later without orphaning
   a receipt. **Money decision resolved:** no float-vs-decimal fork — a `DECIMAL` column round-trips
   exact, so preserving declared types is sufficient (the connector already protects Decimal on write).
2. **Server-render the default (unfiltered) figure values** at build time, so numbers are legible with
   JS off (email/print/screen-reader). The worker engine hydrates only for filtering/drill.
3. **`verify` re-runs the aggregations** against the embedded Parquet — a *stronger* receipt than
   today: it can prove a KPI equals `SUM(...)` over the shipped detail, not just re-hash a pre-agg
   result. Two tiers: integrity (hash the embedded content, no deps) and reproduction (re-run queries,
   needs a Parquet engine — Python `verify` already has DuckDB).
4. **Filter-grain contract** — the size + memory governor *and* an honesty guarantee: embed at the
   **coarsest grain that still contains every declared control's column**; a control over a missing
   column is a **build error**. This is Tableau's row-level-vs-aggregated-extract rule, made
   mechanical. For continuous brushing, extend it to **precompute the bins the controls brush over**
   (Falcon/Mosaic data-cube pattern).

---

## 7. Open decisions to lock at kickoff

- ~~**Money/decimal serialization** in the content hash~~ — **RESOLVED** (Phase-2 spike): no
  float-vs-decimal fork; serialize by declared type (Decimal exact, float via canonical repr). See §6.1.
- **`fingerprint_algo` / `ARTIFACT_MANIFEST_SCHEMA_VERSION` sequencing** — this change wants a bump;
  coordinate with the other pending v3 wants (time-intelligence, governed-figures) so the
  `refused_newer_schema` forward-compat gate isn't undermined.
- **Does author `script.js` run in the receipted lane** once the engine is client-side? (The red-team
  laundering question — badge/docs language must not overclaim while page scripting is unprovable.)
- **Brushing scope for v1** — click-to-filter (worker + ~0.5s, ship first) vs continuous brushing
  (needs precomputed bins, later).

---

## 8. Implementation plan (sequenced)

**Phase 0 — Lock the receipt decisions.** Content-hash algo design + money/decimal call +
schema-version sequencing. Gates everything; one-time.

**Phase 1 — End-to-end prototype (scratch, de-risk).** Parquet embed + parquet-wasm + Arquero **in a
blob-URL worker** + one live filter + SSR'd default values + a `verify` re-run. Measure *perceived*
latency (not just query time) and mobile memory. Decide brushing scope from real numbers.

**Phase 2 — Content-hash fingerprint** in the Python build + `verify` (the v-next algo), behind the
schema-version bump. Re-pin the fingerprint corpus.

**Phase 3 — Columnar embed + worker runtime in the artifact build.** Vendor parquet-wasm + Arquero +
flechette (self-contained, offline, provenance/NOTICE like ECharts). Emit Parquet instead of CSV;
build the worker; keep strict CSP.

**Phase 4 — Filter-grain contract + interactive controls** wired to the worker engine (build-time
grain check → build error on a control the grain can't back).

**Phase 5 — No-JS / print legibility** — SSR default values + print receipt appendix (also fixes the
artifact-last-mile "blank verified numbers" finding).

**Phase 6 (optional/later) — Precomputed bins/cubes** for continuous brushing; hyparquet-columnar
re-benchmark to maybe shed parquet-wasm's WASM.

**Cross-cutting gates (execution charter):** full suite green on both pandas majors before every push;
receipts-monotonicity + showcase + agent-guides drift tests as hard gates; the discoverability trio
(vocabulary + scaffold + both guides) for any new authoring surface; browser drills incl. `file://`
open and mobile; NOTICE/SBOM for the new WASM deps.

---

## 9. Phase 1 prototype — results (proven)

A scratch end-to-end prototype was built and measured (in-app Chromium). All core bets held,
and it surfaced one decision-grade finding.

**Proven:**
- **Self-contained + offline.** A single `artifact.html` (11.7 MB) with the engine, data, and
  worker all inlined ran with **zero network** — the network log showed only the document itself
  plus an in-memory `blob:` worker; no fetch of the wasm, Parquet, worker, ECharts, or engine. It
  opens identically offline / from `file://`.
- **The full loop works:** embedded Parquet → blob-URL Web Worker → parquet-wasm decode → Arquero
  query → ECharts + a `virtual-core` fixed-height virtualized table.
- **The worker offloads the freeze:** running the same query on the main thread froze the UI for
  the query's full duration; in the worker the main thread stayed responsive.

**The decision-grade finding — the grain contract is the performance foundation, not a nicety:**
- Over **raw 2M rows**, Arquero is too slow for interactive filtering: the *filter alone* is
  ~1.8 s and each rollup ~1–2.7 s → a realistic multi-figure query is **~4 s**.
- Pre-aggregating to the **control grain** (segment × region × product = **6,000 rows**) is a
  **one-time ~2.9 s build step** (in Python/DuckDB) after which interactive queries are **1–2 ms**
  — ~2000× faster — and the embedded data is **50 KB** instead of 8.4 MB.
- So: **never embed raw millions for interactive filtering; embed at the control grain.** This is
  exactly what §6's filter-grain contract enforces, and it simultaneously governs size, memory,
  and latency. It also settles the engine debate: at grain scale Arquero is instant, so
  parquet-wasm + Arquero is more than sufficient and DuckDB's raw-scan speed is moot.

**Refinements to bank:**
- **Engine floor ≈ 9–12 MB** (the parquet-wasm wasm base64-inlined dominates); data is negligible
  once grain-contracted. The KPI-floor number in §2 (~3 MB) assumes the read-only-no-codecs
  parquet-wasm build + gzip-inlining; the prototype used the full 6.5 MB wasm raw-base64 → 11.7 MB.
  Confirm the smaller build + gzip-inline path in Phase 3 to hit the ~3 MB floor.
- **Measuring perceived latency needs a foreground browser** — a backgrounded/automated tab
  throttles `requestAnimationFrame` (ECharts won't paint) and clamps timers to ~1 s (inflates any
  freeze metric). Decomposed main-thread timing gave the clean numbers; re-measure perceived
  latency on a real foreground browser (and mobile Safari) before finalizing.

## 10. Future tier (PARKED) — raw-scan "explorable data app"

Not being built now; documented so the door stays open. The grain contract is the *default*, not a
ceiling. When a report genuinely needs to **scan/pivot millions of raw records** (Tableau-class ad-hoc
exploration, not pre-declared aggregates), it becomes a deliberate **opt-in heavy tier**:

| Tier | Engine | Data | Feels like | File |
|---|---|---|---|---|
| **Governed dashboard** (default, built) | parquet-wasm + Arquero | grain-contracted | instant, emailable | ~3–12 MB |
| **Explorable data app** (parked) | DuckDB-WASM | raw detail | Tableau-class scan/pivot | ~34 MB + data |

- **Engine:** DuckDB-WASM is the one that genuinely does it — HF's SQL Console filters 12.6M raw rows
  in <3s client-side; ceiling ~100M rows / 4GB, which *exceeds* Tableau Public's 15M/1GB. Arquero
  can't (Phase-1: ~4s over raw 2M). This is the "reserve DuckDB" case from §2, now given a name.
- **Costs:** ~34MB engine (every such file; it's a "download the data app," not an email attachment),
  hundreds-of-MB–GB tab memory, low-tens-of-millions-row ceiling.
- **The reason it's worth it (and beyond a BI tool):** fingerprint the embedded **raw** detail and
  **every number a reader derives by exploring is verifiable against the sealed raw** — an explorable
  AND tamper-evident dataset. No incumbent (Tableau/Qlik) ships that. This is the strongest form of the
  receipt story, not a compromise of it. Mirrors Tableau's aggregated-vs-row-level extract distinction.
- **Can be hybrid in one file:** grain for instant dashboards + raw detail for drill-through, DuckDB
  scanning the raw only on a deliberate explore action.
- **The one unverified assumption blocking it:** whether DuckDB-WASM runs in a *self-contained offline*
  file (`file://`, inlined wasm, blob worker, single-threaded, no COOP/COEP). The plan earlier *assumed*
  it's file://-hostile — that was a guess, not a test. The inline-wasm + blob-worker pattern proven for
  parquet-wasm in Phase 1 may well carry single-threaded DuckDB too. **A ~half-day spike settles it**;
  do that first if/when this tier is pursued.

## Appendix — key sources (2024–2025)

- HF SQL Console (DuckDB-WASM client-side, 12.6M rows <3s): https://huggingface.co/blog/sql-console
- Mosaic / 18M points in-browser: https://motherduck.com/case-studies/dominik-moritz/ ; https://github.com/uwdata/mosaic
- Mosaic Selections paper (~100M-row / 4GB ceiling, data cubes): https://arxiv.org/html/2507.19690v1
- DuckDB-WASM COOP/COEP + single-thread: https://duckdb.org/2021/10/29/duckdb-wasm
- parquet-wasm sizes/adoption: https://github.com/kylebarron/parquet-wasm ; https://developmentseed.org/lonboard/
- Arquero + flechette: https://github.com/uwdata/arquero ; https://github.com/uwdata/flechette
- Perspective (ex-JPMorgan, FINOS): https://perspective.finos.org/
- V8 string cap / self-contained limits: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/String/length
- Retool "keep what React holds small": https://docs.retool.com/apps/guides/data/table/pagination

---

## 11. How the implementation diverged from this plan

Two adversarial reviews (38 then 27 confirmed findings) changed three things:

1. **pyarrow, not DuckDB, does the Parquet round-trip.** The receipt depends on a frame
   coming back *exactly* as it went in, and that is a property of the writer. DuckDB maps
   Parquet through its own SQL types and rewrote tz-aware timestamps into the READER's
   local zone — so the same untouched artifact verified INTACT in New York and ALTERED in
   London. pyarrow preserves far more, but not everything.
2. **The format choice PROVES the round-trip instead of trusting a dtype list.**
   Three separate attempts to enumerate "safe" dtypes each missed cases (non-string
   categoricals, object columns of non-strings, `datetime64[s]`, differing Decimal scales).
   `choose_embed_format` now encodes, decodes and re-fingerprints the actual data, and
   falls back to CSV unless the receipt demonstrably survives — correct by construction,
   including for dtypes nobody has thought of yet.
3. **Parquet also requires types the BROWSER renders identically.** The receipt survives
   more types than the display does: Arrow hands the worker a Decimal as an unscaled
   integer, a tz-aware timestamp with the zone dropped, a timedelta as raw nanoseconds.
   Reproducing pandas' formatting in JS for every such type is the same losing game, so
   those types keep the CSV transport. Only numbers, booleans, strings and naive datetimes
   take the Parquet path.

The net effect is that Parquet is used **less often than this plan assumed** — and always
provably, never hopefully.

4. **(Final architecture.) The Parquet receipt hashes the SHIPPED bytes — nothing is ever
   re-derived.** A third review proved re-derivation is unfixable in principle: pandas'
   `to_csv` line terminator follows the *host's* `os.linesep`, so a Windows-built artifact
   read FILE ALTERED on Linux — and no build-time check can see cross-machine drift, because
   build-time checks run on one machine. The manifest now records `payload_sha256` (SHA-256
   of the exact embedded Parquet bytes, from the ONE encoding that also produced the page
   block — `EmbedPlan`), and `verify --file` re-hashes the shipped bytes: byte-exact,
   host-independent, and dependency-free (no Parquet reader needed to verify). This REVERSED
   divergence #2's narrowing: with the receipt no longer hostage to Parquet's type mapping,
   the round-trip gate was deleted and formerly excluded dtypes (non-string categoricals,
   object-of-scalars, any datetime unit) take the Parquet transport freely. The only
   remaining gate is display parity (`_renders_identically`): types the browser engine
   cannot yet render exactly as pandas spells them (tz-aware, sub-second, timedelta,
   Decimal, mixed-object) stay on CSV — a display concern, not a trust one.

5. **A Parquet artifact has WEAKER display verification than CSV, by deliberate scope.** For a
   CSV artifact the embedded bytes hash to `embedded_sha256`, which is also the section
   `dataset_fingerprint` that `verify_manifest` reproduces — so offline file-integrity and
   model-side reproduction pin the *same* value and compose into a display↔query tie for free.
   A Parquet block is hashed by a separate `payload_sha256`, which reproduction does not
   reproduce, so `verify --file` on a Parquet artifact is tamper-evidence only: it proves the
   file was not edited after render relative to its manifest, but a payload swapped **at build**
   for different numbers (with `payload_sha256` updated to match and `embedded_sha256` left
   honest) passes it — exactly as a CSV author-forgery would.

   **What is NOT shipped, and why.** A model-bearing tie was prototyped — decode each Parquet
   payload at verify time and compare to the re-run result — but closing it soundly requires the
   verifier to determine *which block a browser renders for each figure*, i.e. to parse the page
   byte-for-byte as a browser's HTML5 parser + runtime does. Python's `html.parser` is not that,
   and successive adversarial reviews each found a new parser/selection divergence an attacker
   could exploit (attribute order, an escaped `"parquet"` token, a duplicated `id` attribute, …).
   That is a browser-grade problem, not a patch, so the tie is intentionally **deferred**: doing
   it right needs a spec-compliant HTML5 parser (e.g. html5lib) or a headless-browser oracle, as
   its own design pass. **Guidance:** use a CSV artifact where the display↔query tie matters
   (small/medium reports, the common case); use a Parquet artifact for large detail, where
   `verify --file` gives tamper-evidence and the model-side `verify` still proves every query
   reproduces.
