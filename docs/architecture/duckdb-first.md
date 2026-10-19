# DuckDB-first — one engine from the sink to the page

**Status: design, decisions closed 2026-10-19.** Written from a maintainer
discussion; the packages at the end are the plan. Supersedes the
engine choice in [[large-detail-artifacts]] (parquet-wasm + Arquero) and the
"controls never compute new numbers" rule in `tracebi/capabilities.py`.
Everything in the three-phase workflow and the honesty rules
([[../../MANIFESTO]]) stands; this changes *how* each phase computes, and
how much the report file may do on its own.

**One line:** DuckDB is the only engine on the server. Transforms are SQL by
default, the model is a DuckDB schema, and the report file carries the slice
of the model it needs plus a small engine of our own that recomputes every
figure live on a filter, offline, with no server anywhere in the loop. Every
number it shows is still a query the trace can name.

---

## 1. What the discussion settled

1. **Pandas is not the engine any more.** DuckDB already runs every model
   query (`data_model.py`, `_execute_duckdb`). The transform phase is the
   last place pandas does the computing; it becomes SQL, with pandas and
   polars kept as a declared escape hatch.
2. **The server holds the model, not the data.** A hosted TraceBi should not
   need the warehouse on its own disk. DuckDB reads Parquet on object
   storage, or a remote engine, in place.
3. **The page gets a small engine of our own, not DuckDB.** DuckDB-wasm was
   measured at 8.8 MB gzipped (§10). The page does not need a database: the
   build flattens each fact with its exposed dimension attributes, so the
   page never joins, and the query vocabulary is the closed JSON spec the
   server already compiles to SQL. A ~50 KB engine (a 20 KB pure-JavaScript Parquet
   reader included) over the blocks' dictionary-encoded columns executes
   that spec directly and replaces parquet-wasm, Arquero and the
   sealed-grain evaluator. Parity with DuckDB is proved per
   measure kind by test, which is finite because the spec is closed.
4. **Controls are released, offline.** A report is assumed to work with no
   server: a `file://` page and the hosted page behave identically.
   Filtering one control recomputes every spec figure on the page from the
   embedded data. The rule that remains is the honesty rule: the data is
   fingerprinted, the query is visible, and the chip says where the number
   was computed. A SQL binding is the power lane and runs at build time
   only; it sits fixed in the file and says so.
5. **Not Qlik.** Live cross-filtering across every object, yes. The
   associative green-white-grey state, synthetic keys and the one-path
   constraint, no. A model's declared relationships are the paths, and a
   dimension may join two facts on different keys.

## 2. Decisions (closed)

| # | Decision | Why |
|---|---|---|
| D1 | A transform is a `.sql` file by default; `.py` and `.ipynb` still run and end by handing DuckDB an Arrow table (pandas or polars). The UI names which form ran. | The trace line is drawn at the sink, so a Python transform is exactly as traceable as a SQL one. Only `report.py`, which computes after the model, stays `verifiable: false`. |
| D2 | The warehouse has three storage tiers, chosen per project: a local `.duckdb` file (today), **Parquet on object storage** (the hosted default), or a remote engine (`ATTACH`). The freeze point is the same in all three; only its address moves. | The storage concern. Parquet also sidesteps DuckDB's storage-format versioning and the single-writer file. |
| D3 | The model compiles to a DuckDB schema: one view per table, one `MACRO` per simple measure, and the star-schema joins as the query planner's input. Measures that need the grain (ratio, share, rank, running, percentile) stay model-level and compile per query, as now. | One SQL text the server, the page and `verify` all run. The YAML stays the contract a reviewer reads. |
| D4 | SQL is a first-class figure binding on the server. `{"model", "sql"}` (already in `sql_calc.py`) is promoted, documented and scaffolded; `{{ measure() }}` expands before it runs. It runs at build time and is **fixed in the file**: it does not react to filters, hosted or not. | Authors and agents write what they mean when the spec cannot. The JSON spec stays the governed lane and the only live one; a gap that drives an author to SQL is a gap to close in the spec. |
| D5 | The report file embeds a **sub-star**: for each fact its figures use, that fact at the coarsest grain that still answers every figure and every filter combination, plus the dimensions the report exposes. The build derives it. `embed: model` widens to the whole star; `embed: none` makes a hosted-only report. A size budget refuses a file past it. | Enough to recompute locally, not the whole warehouse in every email. Additive measures let the fact pre-aggregate; a distinct count or percentile forces the finer grain, and the model knows which is which. |
| D6 | The page holds one **selection state**; every spec figure's query is composed with it; a figure whose fact has no declared path to a selected field stays as it was and says so; a SQL figure is fixed and says so. | Live filtering as Power BI, Tableau and Looker do it, in a few dozen lines once the engine is in the page. |
| D7 | **`tracebi-calc`**: our own page engine, plain JavaScript, one file, inlined like the rest of the runtime. Budgets: ≤ 50 KB gzipped, and every spec query over the largest block the embed budget allows completes in ≤ 100 ms on a mid-range laptop; `scripts/ui_audit.py` ratchets both. Blocks stay **Parquet** (uncompressed or Snappy pages, the whole block gzipped for the file), unzipped by the browser's own `DecompressionStream` and read by a pure-JavaScript reader (hyparquet, 20 KB gzipped measured; counted inside the 50 KB budget). Parquet's dictionary pages give the engine integer-coded strings for free. No wasm, so no CSP change. A Rust port is the fallback if the time budget fails; the block format and message protocol are designed so the port swaps the engine and nothing else. `engine: duckdb` (DuckDB-wasm inlined, ~12 MB) is a later opt-in for a report that must recompute arbitrary SQL offline, shipped only when a real report needs it. | Offline is the baseline, so the engine must be in the file; a database engine is 36 MB because it is general, and the page's work is a closed spec over flat, typed columns. Small because it does little, correct because parity is finite, fast because the data is laid out for it. |
| D8 | The chip gains two states and one figure mark. **Local**: this number was computed on this page by the embedded engine from the embedded, fingerprinted data. **Live**: this figure reads a `materialized: view` over a source that can move; never green. **Fixed at build**: a SQL figure that does not react to the selection. | A reader must be able to tell a build-time server number from a click-time page number from a number that may have changed since. |
| D9 | Result fingerprints round floating-point columns to a declared precision (default 9 significant digits) and every stamped query carries a total order. `CURRENT_FINGERPRINT_ALGO` bumps. | DuckDB's parallel aggregation can return a different last bit for the same `SUM`; a byte hash would then read "drifted" on identical data. |
| D10 | Query connections set `enable_external_access = false` and `lock_configuration = true`. Only the transform connection may load `httpfs` and friends. Credentials go through `CREATE TEMPORARY SECRET`, resolved from `${VAR}` in `connections/*.yaml` at run time, never persisted. | `read_csv('http://…')` is a read. Without this, Ask is a server-side request tool. |

## 3. Two engines, one spec

```
 source files ──SQL transform──▶ sink (Parquet or .duckdb) ──▶ model schema (views + macros)
                                       │                              │
                                       │ fingerprinted               ├── server (DuckDB): build, Ask, verify
                                       ▼                              │
                                 sink contract                        └── page (tracebi-calc): the flattened
                                                                           sub-star, the selection state
```

The **JSON query spec** is the contract between them. The server compiles
it to SQL and runs DuckDB; the page executes it directly over the embedded
blocks. A figure's trace records the spec, the selection, the fingerprint
of every table or block it read, and the result fingerprint. `verify`
re-runs the server form. A **Local** number re-runs on the page, and the
server can replay it from the manifest because the blocks are fingerprinted
and the spec is recorded; that replay, plus the per-measure-kind parity
suite, is what makes a page number admissible rather than merely displayed.
A SQL binding has only the server form.

## 4. Phase ① — transforms

**Default form.** `transforms/<name>.sql`, statements in order, run
top-to-bottom in a fresh connection:

```sql
-- transforms/holdings_transform.sql
CREATE OR REPLACE TABLE dim_issuer AS
SELECT row_number() OVER () AS issuer_id, issuer, sector
FROM (SELECT DISTINCT regexp_replace(position, ' — .*$', '') AS issuer,
                      sector_canon(sector) AS sector
      FROM read_csv('inputs/holdings.csv'));
-- …
COPY fact_holdings TO '{{ sink }}/fact_holdings.parquet';
```

`{{ sink }}` resolves to the project's tier (§5). A `connections/<name>.yaml`
becomes an `ATTACH` or a secret before the script runs. The contract block
moves beside it as `transforms/<name>.contract.yaml`, same closed vocabulary.

**Escape hatch.** A `.py` or `.ipynb` transform runs as today and must end by
registering or writing an Arrow-compatible frame; DuckDB reads pandas and
polars without a copy. `tracebi run-transform` reports `form: sql | python`.
Nothing is converted automatically; a pandas transform keeps working until
its author rewrites it.

**Not built.** Dependencies between SQL files (`ref()`). One transform file
per pipeline, order inside it, dependencies between pipelines in
`pipelines/*.yaml`. `dbt_import.py` stays the bridge for a real dbt project.

## 5. Where the data lives

| Tier | Sink | Model reads | Server disk | Notes |
|---|---|---|---|---|
| **file** | `data/warehouse.duckdb` | the file, read-only | the whole warehouse | today; dev, demos, one process |
| **object** | `COPY … TO 's3://bucket/project/<table>.parquet'` | `read_parquet` through `httpfs` | a cache DuckDB manages | hosted default; R2, S3, GCS |
| **remote** | runs in the remote engine | `ATTACH 'md:…'` or a Postgres warehouse | nothing | MotherDuck or an existing warehouse |

Set once in `tracebi.yaml` (`warehouse: {tier, location}`); `{{ sink }}` in a
transform and `connectors:` in a model resolve from it, so neither file
names a path. Every tier sets `memory_limit`, `threads` and
`temp_directory` on the server so a heavy query spills instead of taking
the process down. The sink certificate records the engine version and, for
the object tier, each file's ETag or footer hash, so a silent overwrite
reads stale.

## 6. Phase ② — the model as a schema

The YAML does not change shape. It compiles to:

- one view per `tables:` entry, over the tier's location;
- one `MACRO` per simple measure (`sum`, `count`, `mean`, `min`, `max`,
  `nunique` of one column, with its filter);
- the relationships, which the query compiler uses to join a fact to the
  dimensions a query or a selection names.

A model holds many facts; a query names one. A dimension joins each fact
on that fact's own declared key, so a calendar dimension can join
`fact_orders` on `order_date_key` and `fact_shipments` on `ship_date_key`,
and a filter on month reaches both. There is no synthetic key, no link
table and no one-path constraint.

Grain-dependent measures (ratio of sums, share, rank, running, percentile,
`partition_by`) stay as they are: the compiler emits them per query, with
the selection folded in before the window. A macro cannot know the grain.

## 7. Phase ③ — the report file

### 7.1 What the build embeds

For each fact the report's figures and filters touch, the build computes
the **required grain**: the union of every field any figure groups by, any
filter exposes, and any grain-dependent measure needs. Additive measures
pre-aggregate to that grain. A measure that is not additive at it
(`nunique`, `p90`, a `median`) forces the base grain for that fact. The
dimensions the report exposes are embedded whole; a conformed dimension is
embedded once. Each block is Parquet, fingerprinted by content as today (the same hash
`verify --file` checks, independent of the container), and listed in the
manifest with its grain, so the trace says what the file holds. A measure
that is a ratio of aggregates (`mean`, `ratio`, `share`) is stored as its
parts (sum and count, numerator and denominator) per grain row, so the page
divides after it filters: an average is recomputed, never averaged.

`report.json`:

```json
"embed": "required" | "model" | "none",
"embed_budget_mb": 25
```

Past the budget the build refuses and names the fix (`embed: none`, or a
coarser grain by removing a filter). `embed: none` is a hosted-only report:
the page asks the server for every recomputation, with the same SQL.

### 7.2 The selection state

One object on the page, replacing the single filter tuple the
`selection` block posts today:

```json
{"dim_issuer.sector": ["Technology", "Software"],
 "dim_date.month": {"gte": "2026-01", "lte": "2026-06"}}
```

Composition is one function, `apply_selection(query, selection, model)`,
shared by the server (`DataModel.query`), the page (`tracebi-calc`) and
Ask. For each selected field it finds the path from the figure's fact
through the model's relationships; with a path it adds the predicate, and
without one it leaves the figure untouched and marks it
`data-tb-unfiltered-by="dim_customer.region"` so the page can say so. A
figure may declare `ignore: [dim_date]` to opt out of one field.

Every spec figure re-runs on every change of the state; a SQL figure stays
fixed and is marked. A value figure re-stamps its text with the new result
and its trace row records the spec with the selection folded in. The state is in the URL hash so a view can be
shared, and the server-side build records the empty selection as the
canonical one `verify` re-runs.

### 7.3 What a figure may do

Any spec query over the embedded blocks, live:

```jsx
<Kpi binding="total_fv" />               // a JSON query; recomputed on every selection change
<Chart binding="by_sector" />            // as today, now live
<Table binding="top3_per_sector" />      // having + partitioned rank, in the spec, live
<Kpi binding="sql_oddity" />             // a {"model","sql"} binding: fixed at build, marked
```

The spec vocabulary the engine executes: measures of every declared kind
(`sum`, `count`, `mean`, `min`, `max`, `nunique`, percentiles, filtered
measures, `expr` over fact columns, `ratio`, `share`, `rank` with
`partition_by`, `running`), dimensions with time grains and bins, filters,
having, order_by, limit. Each kind has a parity test against DuckDB with
the same inputs; a kind the engine does not implement fails the build by
name rather than falling back to a static value.

The lint that today refuses arithmetic in JSX (`lint_jsx_numbers`) stays:
a number is still minted by a query, never by `a / b` in the template.
What goes away is the sealed grain, the "value figures never react"
exception, the selection evaluator, and the limit of one posted filter.

### 7.4 Hosted and offline are the same page

A report is assumed to work offline. The hosted page (`/r/<name>`, the app)
and the `file://` page are the same bytes and compute the same way, from
what the file carries. `embed: none` therefore means a report with no live
filtering anywhere, not one that filters only when hosted. Both show the
**Local** chip for anything recomputed after the build.

## 8. Trust

- **Reproduces** (green): the build-time server result, re-run by `verify`,
  fingerprints equal. Unchanged.
- **Local**: recomputed on this page from embedded, fingerprinted blocks by
  the embedded engine; the SQL is in the trace; the server can replay it.
  Never green on its own, never red: it is a different claim.
- **Live**: a `materialized: view` over a source that can change between
  reads. The trace names the source; the chip never reads green.
- **Not checked** and **Draft**: as today.

D9 is the correctness condition for all four: a fingerprint over rounded
numerics in a total order. `verify` grows `--local` to replay the page's
recorded Local queries against the manifest's blocks.

## 9. Security

- The connection that serves a model query, an Ask query or a page replay
  cannot reach outside the attached tables (D10). The one that runs a
  transform can, and runs only from the CLI, the scheduler or an approved
  code request.
- Ask gets a statement timeout and a row cap, and DuckDB's `interrupt` is
  wired to request cancellation.
- Embedded blocks are data leaving the server. `_folder.yaml`'s `accepts:`
  gains `embed: none` so a folder can refuse files that carry detail rows,
  and the manifest lists each block's grain so a reviewer can see what a
  file holds before it is sent.

## 10. Operations

- **Extensions** (`httpfs`, `iceberg`, `delta`, `postgres`) are pinned to the
  DuckDB version and pre-installed in the Docker image and the wheel's
  optional extras, so an air-gapped install does not fail on its first
  remote read.
- **Versions**: `duckdb` is pinned in `pyproject.toml`; the certificate and
  every manifest record it. The object tier needs no storage-format
  migration; the file tier gets `tracebi migrate warehouse` (export,
  reimport) when the pin moves a major.
- **One writer**: on the file tier the transform writes to a temp file and
  renames; the server reopens read-only after a build. On the object tier
  a `COPY` to a new key and a manifest swap is atomic enough.
- **Page engine size, measured and budgeted** (2026-10-19):

  | | raw | gzip | inlined |
  |---|---|---|---|
  | today's engine (worker JS + parquet-wasm) | 7.3 MB | 2.9 MB | ~3.5 MB |
  | `@duckdb/duckdb-wasm` 1.33 `eh` + worker | 36.7 MB | 8.8 MB | ~11.7 MB |
  | hyparquet 1.31 (pure-JS Parquet reader), bundled + minified | 64 KB | 20 KB | |
  | **`tracebi-calc` + reader budget** | | **≤ 50 KB** | |

  Browsers decompress only gzip and deflate in `DecompressionStream`, so
  brotli would not have helped an inlined DuckDB. The measurement is why
  the page engine is ours (D7). `scripts/ui_audit.py` ratchets the engine
  size, each built report's size, and the slowest spec query over the
  reference project's largest block.

## 11. What goes away, and what stays

Removed (small, and mostly third-party):

- `tracebi-engine.worker.js` (1.1 MB: parquet-wasm, Arquero and Arrow
  wrapped by ~200 lines of our protocol), `parquet_wasm_bg.wasm.gz`
  (1.8 MB), `_engine_src/`.
- `selection_eval.py` (365 lines) and `selection_eval.js` (214 lines), the
  sealed-grain evaluator, and the subset-only branch of the runtime's
  selection path.
- The "controls never compute new numbers" paragraph in `capabilities.py`,
  `AGENTS.md` and `init_agents.md`, replaced by §7.3's rule.
- Pandas as a required dependency of the query path. It remains an optional
  extra for the escape hatch and `ExcelRenderer`.

Kept, and doing more (this is the library):

- `tracebi.js` (~5,000 lines: hydration, the D3 chart engine, controls,
  tabs, scenarios, the trace drawer, downloads, the stamped-figure watch).
  Live filtering plugs into its existing selection path; the charts redraw
  as they do today. `tracebi.css` and the React kit, untouched.
- The query compiler in `data_model.py`: the page engine executes the spec
  it compiles, so it becomes the parity oracle rather than being replaced.
- `template_package.py`, stamping, manifests, `verify`, contracts, the model
  loader, discovery, the web app, Ask, drafts, permissions.
- The parity suite, now per measure kind against DuckDB; the query-semantics
  test, which already pins the spec.
- On the server, `tracebi/etl/` (~450 lines of pandas medallion layers)
  migrates to DuckDB SQL over time; `DataSet` and lineage stay for
  connectors and the model load path.

## 12. Not building

- Qlik's associative state (possible / excluded values per field).
- Association across models. Within a model, shared dimensions do it.
- `ref()`-style dependencies between SQL transform files.
- DuckDB-wasm in the page by default, or any page that needs a network or
  a server to filter. `engine: duckdb` is the opt-in, later, if a report
  needs arbitrary SQL recomputed offline.
- A Rust page engine before the 100 ms budget fails on a real block.
- A migration that rewrites pandas transforms into SQL.

## 13. Packages

Each lands with the discoverability trio (vocabulary, scaffold or
showcase, both guides), the full gate, and a journey step. In order,
because each one's seam is the next one's input.

| # | Package | Verify |
|---|---|---|
| Q-1 | **Fingerprint rule** (D9): rounding + total order, algo bump, `verify` reads both algos. | The verify journey re-runs the reference project with `threads=1` and `threads=8` and reads Reproduces on both. |
| Q-2 | **Model as schema** (D3, D10): compile views + macros, locked read-only connections, `apply_selection` as the one composition function (Python now, ported to the page in Q-6b), multi-key dimension joins. | A model with two facts and one calendar dimension on different keys; one selection reaches both; `read_csv('http://…')` from Ask is refused by name. |
| Q-3 | **SQL binding promoted** (D4): scaffold and showcase figures, the fixed-at-build mark, the guides say when to reach for it. | The author journey builds a report with a SQL KPI; verify reads green; the figure carries the fixed mark and ignores a selection. |
| Q-4 | **Storage tiers** (D2): `tracebi.yaml` warehouse block, `{{ sink }}`, secrets, object tier in the reference project behind an env var, certificate records ETags and engine version. | The pipeline journey sinks to a local MinIO-style endpoint and the model reads it; a rewritten Parquet reads stale. |
| Q-5 | **SQL transforms** (D1): `.sql` form, `new-transform` scaffolds it, `run-transform` reports the form, the reference project's transform rewritten in SQL with the pandas one kept beside it as the escape-hatch example. | Both forms sink identical tables (fingerprints equal). |
| Q-6a | **Blocks and parity** (D5, D9): the flattened sub-star build, the typed-column block format with dictionary-encoded strings, the manifest entries, and the parity suite: every measure kind, time grain and bin, DuckDB against a reference implementation, with the fixtures Q-6b's engine must pass. | Each parity case runs the spec through DuckDB and through the reference and the fingerprints match; a rewritten block reads stale. |
| Q-6b | **`tracebi-calc`** (D6–D8): the engine against Q-6a's fixtures, the selection state, live figures through the runtime's existing selection path, Local chip and fixed-at-build mark, `verify --local`, `embed:` and the two budgets, folder `accepts`. | The web journey filters a sector on the showcase opened from `file://` and every spec figure changes, the trace shows the spec with the selection in it, `verify --local` replays it, and the audit ratchet holds 50 KB and 100 ms. |
| Q-7 | **Retire** (§11): remove the old engine and the evaluator, prune the tests, update the docs that describe them. | The suite passes with the three libraries gone from the tree. |

Q-1 through Q-3 touch nothing a reader sees and can merge while Q-6 is
being built. Q-4 and Q-5 are independent of Q-6. Q-6a's parity fixtures
exist before Q-6b writes a line of the engine.

## 14. Open questions

0. **Three parity definitions to write down before Q-6a:** week and
   quarter truncation (ISO weeks, and in which time zone a date-only column
   is truncated), percentile interpolation (DuckDB's `quantile_cont`
   semantics), and float summation order (covered by D9's rounding).

1. **Default `embed`.** `required` makes every report live by default;
   `none` keeps a report static until an author opts in. With a 50 KB
   engine the cost is only the blocks, so the draft says `required` with
   the budget as the guard. To confirm against real file sizes after Q-6a.
2. **Local in the library chip.** Whether a report whose last build is
   green but whose page is mostly Local shows Reproduces or Local in the
   Reports list. The draft says Reproduces (the build is what the list
   describes) with Local only on the figure.
