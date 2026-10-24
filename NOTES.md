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
| Phase 5 | ✅ Done | Web UI (FastAPI + React) |
| Phase 6 | ✅ Done | DuckDB engine, push-down filters, layer rename, CLI, auto-discovery, auth, docker-compose |
| Phase 7 | ✅ Done | Correctness sweep, open-core seam, capability surface, ReportSpec, SVG charts, theme layer |
| Artifact | ✅ Done | One report lane, the package: per-figure traces, `app.jsx` dashboards and `template.html` pages, live pages that recompute offline (2026-08 to 10-21) |
| DuckDB-first | ✅ Done | SQL transforms with sink contracts, the model query in a locked DuckDB connection, storage tiers, the medallion layers in DuckDB (2026-10-19 to 10-21) |
| Library | ✅ Done | Folders, sign-in (OIDC, local users), folder permissions, drafts, publish requests, code requests, `tracebi push` (2026-10-08 to 10-18) |
| The app | ✅ Done | Five places (Reports, Ask, Data, Review, Docs); Data as the board; the table page; the credential store (2026-10-23) |
| Docs | ✅ Current | Full update 2026-10-24: executed plans deleted, the handbook checked against the CLI, the routes and the app's addresses. The gateway is 22 tools + 3 prompts. Volatile counts say "run `pytest tests/`" rather than a frozen number. |

---

## 2026-10-24 — Decision: a display face is a token; a package may keep its own look (UI-4B)

Backlog 8 asked whether a project is one accent. The round first said yes and
moved `portfolio_book` (navy), the showcase (teal) and affordability (its own
272-line stylesheet) onto the project's cobalt; the owner wanted the one-off
editorial's theming back, and the goal of the round was the app, not the
reports. So the packages keep their looks, and what the round leaves in the
system stands: one display face as a token of its own, `--tb-font-display`,
which the system places (the masthead headline, the lead number, the trace's
title), so a package that only wants its own face writes one token and its
`@font-face`. A bespoke look remains allowed on the same masthead, grid,
footer and trace; `aum_by_branch` and affordability are the examples.

The phone pass made the system, not the packages, responsible for reading at
390: tables scroll across with a frozen first column, controls are one
sideways row, the selection bar rides the bottom of the screen, a run of
numbers on an axis thins instead of turning, and stacked small multiples share
one row of names. Item 36 (the code's "receipt" names) stays open: the app's
frame bridge and `ReceiptFrame.jsx` would have to move in the same change.

---

## 2026-10-23 — UI round 3, one demo, the board, the credential store (#273–#275)

Three pull requests closed the third UI round and the work it opened.

**UI round 3, waves 2 and 3 (#273).** Every table now has one page,
`/data/tables/<source>/<table>`, read through one read-only table API (rows
paged, sorted, searched and filtered in the engine; a profile; the same cut as
CSV), so a warehouse table, a SQL connection's table and a file under
`inputs/` look and behave alike. Warehouse and Sources were rebuilt around it;
the model page became an explorer whose view lives in the address. Data opened
to analysts, read-only (the run buttons and credential forms stay admin's),
because the people who read a model need to see how it is made. The desk keeps
a verdict while its manifest, the models it names and their warehouse are
unchanged, so Reports no longer waits on a re-run it already did; Check again
forces one. Titles and words: every browser tab names its page, a table's
checks are named by their file, and About this build says Dashboard or Page.

**One demo (#273).** tracebi.com served two projects at once and the visitor
saw four sets of rules. Now `docker compose up` serves the reference project
alone, and it follows its own conventions: one warehouse declared in
`tracebi.yaml`, every transform SQL with a contract (housing's pandas declares
one in code), every model YAML. Wealth Management moved in from the demo app as
the fourth model, read from a core-banking SQLite that ships; SaaS reads a
billing SQLite. The CRM is a standing Postgres database loaded once. The demo
app stays in the package as the example of Python wiring, opt-in.

**The credential store (#273, #275).** A connection's `${NAME}` resolves from
the environment, then `.env`, then the project's encrypted store, so an admin
can set a secret from Data → Sources or `tracebi secret set` without reaching
the box's environment. The environment stays first, so nothing a deployment
configures is overridden by the app. The store began as JSON with per-value
tokens and became one encrypted YAML document, `.tracebi/secrets.yml.enc`, the
shape Rails credentials and Ansible Vault use, with `tracebi secret edit`
opening it decrypted in `$EDITOR`; who set what moved to History's credential
rows, where the audit already was. Credential writes need an identified admin:
the one place the no-lockout rule is narrowed, because an open demo would
otherwise let anyone repoint the server's connections.

**The board and the Transforms tab (#274).** Data's tabs had named the
implementation (some models' first node read "pipeline") and put sources after
models. Data now opens on Flow, one board read left to right in the order the
data moves, sources to reports, with wires drawn only from facts the API
already gives; a mechanism is a chip, never a stage. Transforms got a tab of
their own (`/api/transforms`). The Map retired into the board.

**DuckDB 2.0.** From 2.0 a result fetched part-way stays pending on its
connection and the next `register()` there raises. The engine's connection
completes such a result once the row is out, and the pin below 2 is lifted;
1.5 and 2.0 both pass.

**Three bugs only CI found**, each a race a fast runner wins and a laptop
loses:

1. The five-second render cache, meant for polling, answered an explicit
   Rebuild, so the run finished at once with the previous page and no new
   build row. A run someone asked for now always renders.
2. With that fixed, a journey that started a background report run could end
   while the run was still building; the run then read the next journey's
   registries and held its warehouse open as that journey's transform tried to
   write. The run store keeps the futures it started, and the journeys'
   isolation fixture waits for them at teardown.
3. History's filter built its next address from the search params of the
   page's last render, so two quick changes (Every run, then a kind) lost the
   first. It reads the live address.

---

## 2026-10-23 — The reference project follows its own conventions (U-D1)

`design/one-demo.md`, rules 1–4, for the three models that exist.
`examples/portfolio_project/tracebi.yaml` declares the one warehouse
(`data/warehouse.duckdb`) and the engine limits; housing's model says
`type: warehouse` and its transform sinks through `sink_target()`, so
`data/housing.duckdb` and the `housing_warehouse` connector are gone.
`saas_transform.py` became `saas_transform.sql` + `.contract.yaml`: the four
tables fingerprint exactly as the pandas ones did (checked side by side), so
no SaaS figure moved. The 2026-10-19 entry below says both stayed Python;
housing still does, because following each buyer year by year through
refinances is a loop, not a query.

**One name had to move.** Housing and SaaS both sank a `dim_cohort`. Housing's
now lands as `dim_purchase_cohort` and `housing_model.yaml` maps it back with
`source:`, so the model, its dimension and every report binding still say
`dim_cohort`; only the warehouse table and the contract's checks are renamed.

**The served stack is that project alone.** `docker-compose.yml` no longer
sets `TRACEBI_APP` (the demo app stays opt-in). The CRM is a standing mock
database, `crm`, created and loaded from `inputs/seed_crm.sql` by
`docker/postgres-init.sql` the first time Postgres starts on an empty volume,
and written by nothing after. `seed` runs the three pipelines into a shared
`warehouse` volume, so the app's certificate records the CRM rather than the
snapshot the image was baked with.

## 2026-10-20 — A Postgres source in the reference project (P-1)

The ask: at least one star table whose source is a real relational database,
end to end. The reference project's `dim_rating` now comes from a Postgres
CRM (`connections/crm.yaml`, `issuer_ratings`), read by the SQL transform
through one new directive, `-- source: crm.issuer_ratings`.

**Through the connector, not DuckDB's postgres extension.** `ATTACH …
(TYPE postgres)` needs an extension downloaded from extensions.duckdb.org,
which a locked-down host (and this build machine) cannot reach. The connector
path (SQLAlchemy and psycopg, the same `SQLConnector` a connection file
builds) works wherever the driver installs. So the runner loads each named
table whole, through `tracebi.transforms.load_source`, and registers it in
an in-memory database attached under the connection's name: the SQL reads
`crm.issuer_ratings`, and nothing of the source can land in the warehouse
(the object tier lands only the current database's tables). The brief said
`CREATE SCHEMA crm` in the warehouse connection; on the file tier that schema
and its view would persist in the warehouse file, pointing at a frame that is
gone, so the attach replaced it.

**The certificate names its inputs.** The claim stays "the sink satisfied its
contract"; it now says against what: `sources` holds each load's connection,
rows and fingerprint, read through the same loader `verify --contracts` uses
to re-read it. The loaded rows are sorted by every column first, because
Postgres returns heap order and an `UPDATE` moves a row: an unsorted
fingerprint would read CHANGED after a vacuum. A source that moved reads
`CHANGED` and exits 1, while the figures can still reproduce: the warehouse
did not move, but a re-run would land other tables. A source that cannot be
read now is `not checked`, never green and never a failure.

**The fallback is for an unset variable only.** The demo must build on a
fresh clone and in CI's default jobs, which have no database, so
`fallback: inputs/issuer_ratings.csv` names a committed snapshot read when the
connection's `${VAR}` is unset (`ConnectionConfigError`), and the certificate
says `source_fallback: csv` with the reason; every report trace carries it.
A URL that is set but unreachable stops the run: a snapshot quietly covering
for a broken CRM is the dishonest version. `verify --contracts` re-reads a
snapshot-fed load from the snapshot, so a later-set URL does not turn a
like-for-like check into a cross-source one.

**Proof.** The reference journey seeds the CRM with `inputs/seed_crm.py` in a
real Postgres (`TRACEBI_TEST_POSTGRES_URL`, a service container in CI; else a
throwaway server from the local binaries, run as the `postgres` user when the
suite runs as root; else a skip naming why), runs the pipeline, follows
`dim_rating` from a model query's load fingerprint to the certificate to the
connection, and changes a rating to see `CHANGED`. Every other reference step
runs on the snapshot, and the SQL and pandas forms still sink seven
identical tables.

## 2026-10-19 — SQL transforms, the contract beside them (S-3)

Decision 21 of the live-reports plan. A transform is `transforms/<name>.sql`
by default (`tracebi/transforms.py`): statements in order, in one fresh
read-write connection taken the way `write()` takes it (so it waits for a
reader on the file tier and carries the engine limits). Two placeholders,
`{{ sink }}` and `{{ root }}`, substituted as text with quotes doubled;
anything else in `{{ }}` is refused by name. Relative reads resolve against
the project root through DuckDB's `file_search_path`; writes are not covered
by it (DuckDB resolves a write against the process's working directory), so
a write names `{{ sink }}` or `{{ root }}`.

**A created table is a sink table, on every tier.** The reference project
runs on the file tier and, in the pipeline journey, on the object tier, and
no single explicit idiom works on both (`{{ sink }}` is a `.duckdb` path on
one and a prefix on the other). So a table the script creates (not `TEMP`)
lands where the tier says: in the file, in the attached remote database, or,
on the object tier, copied to `<location>/<table>.parquet` after the script
(staged and renamed in a directory, as `write()` does). The explicit `COPY …
TO '{{ sink }}/x.parquet'` stays available and is what `new-transform`
scaffolds on the object tier, with the staging tables `TEMP`.

**The contract file shares the Python form's parser.** `contracts.declare()`
holds the closed vocabulary once; the `c.rows(...)` methods and the
`.contract.yaml` loader both build `{check, table, params, note?}` through it,
and `_Contract.check()` runs a declaration. The checks run after the
transform's connection is closed, not in it as the plan put it: on the object
tier that connection holds in-memory tables that are not the sink, and the
certificate's fingerprints read through the connector load path, which
cannot open a DuckDB file the transform still holds read-write.

**Both forms sink identical tables, which took two roundings.** The pandas
transform rounds a coupon that is a numpy float (its `spread_bps` comes out
of an `Int64` column as a numpy integer), so it rounds as numpy does: scale
by 100, round half to even, scale back. DuckDB's `round(x, 2)` rounds a tie
away from zero (505711.125 → .13) and `round_even(x, 2)` does not scale the
same way (296054.975, held as 296054.97499…, → .98); the SQL spells it as
`round_even(x * 100, 0) / 100`. Row order follows the file: `row_number()
OVER ()` over `read_csv` numbers rows in file order, the dedupe keeps the
first by it, and the flows carry their holding and their place within it so
ties sort as pandas' stable sort left them. All six tables' fingerprints are
equal, and the nine reference manifests built from the pandas warehouse
verify as reproducing against the SQL one.

Left as they were: the `init` sample, the `saas-metrics` and
`sales-pipeline` templates, and the reference project's `saas_transform.py`
and `affordability_transform.py` stay Python (journeys and starters depend on
them; the plan converts only the reference transform).

## 2026-10-19 — Storage tiers: one `warehouse:` block (S-2)

Decision 20 of the live-reports plan. `tracebi.yaml` gains `warehouse: {tier:
file | object | remote, location, …}`, read by `project_config.warehouse()`
into a `tracebi.warehouse.Warehouse`. The seam that made it small is
`Warehouse.sink`: a `str` subclass (`SinkTarget`) that remembers its
warehouse. A transform writes `DuckDBConnector(name, database=sink_target())`
and `contract(name, warehouse=sink_target())` exactly as before, and every
place that already passed `connector.database` around (the contract join,
`verify --contracts`, the Warehouse tab) carries the tier along without a new
parameter. A model says `type: warehouse`; `type: duckdb, database:` still
names one file.

**The object tier's lock needed a second wall.** A locked connection cannot
read files, so the views over `read_parquet` are allowed through DuckDB's
`allowed_paths` (the exact files, globbed when the connection opens). DuckDB
lets a statement write an allowed path as well as read it (`COPY … TO … 
(USE_TMP_FILE false)` overwrote the warehouse in a probe), so a query
connection that allows paths refuses `COPY`, `EXPORT`, `ATTACH` and `DETACH`
by statement type, from `extract_statements`. The file tier is unchanged: it
attaches READ_ONLY and allows nothing.

**Stale without re-hashing.** On the object tier the certificate
(`<location>/_contracts.json`, inside the prefix, so the freeze point still
carries it) records each file's ETag from a SigV4-signed HEAD (checked
against botocore's S3 signer), size and last-modified, and every record
carries `engine_version`. A file whose version moved reads stale even when
its bytes hash the same; `verify --contracts` says `REWRITTEN`.

Not reachable here: DuckDB's `httpfs` extension cannot be fetched in this
environment, so the S3 journey step (moto) skips with that reason and the
same code path runs on a local directory. Not done: AWS session tokens and
credential chains (only key_id/secret), a remote tier over Postgres (the
model's views assume a DuckDB `main` schema), and atomic multi-table swaps on
the object tier (each file is replaced on its own).

## 2026-10-19 — The medallion layers run in DuckDB (S-4)

Decision 22 of the live-reports plan. `tracebi/etl/_sql.py` compiles each
Manipulation step to one SELECT over the relation the step before left
(`cast` → `SELECT * REPLACE (CAST(…))`, `drop_nulls` / `filter` → `WHERE`,
`deduplicate` → `QUALIFY row_number() OVER (PARTITION BY … ORDER BY
__tb_row) = 1`, `rename` → `SELECT * RENAME (…)`), each materialized as a
temporary table so every lineage node still reports rows before and after.
Where it runs depends on the source: the same DuckDB database as the sink
means the whole step runs inside it and ends in `CREATE OR REPLACE TABLE …
AS SELECT`, with no frame loaded (Landing too: one CTAS); any other source's
`load()` frame enters an in-memory DuckDB as an Arrow table and the result
goes to the sink's `write()` as before. `execute()` on the in-warehouse path
returns a `SinkTable` (`len()`, `lineage`, `columns`, `to_pandas()` reading
the sink on demand) rather than a `DataSet`, because a `DataSet` is a frame.

**Order is part of the fingerprint, so it is carried, not hoped for.** A
hidden `__tb_row` is taken from the source (`rowid` for a DuckDB table, the
frame's position for Arrow, `row_number() OVER ()` for a DuckDB view, which
has no stored order) and the result is written `ORDER BY __tb_row`; dedupe
keeps the lowest, which is pandas' first occurrence. The demo pipelines'
tables fingerprint identically before and after.

**A cast never changes a number silently.** DuckDB rounds `10.7` to `11`
casting to an integer where pandas truncated, and reads the text `'10.5'` as
`11` where pandas refused it; integer targets compile to `trunc()` and to an
`error()` for text that is not a whole number. Text and boolean casts follow
DuckDB's spelling (`true`, a null stays null) and are documented in
`CAST_TYPES`. `object` is refused: in pandas it is no cast at all.

**`transform(func)` is the escape hatch.** It still hands a pandas frame to
the callable; its node says `escape_hatch: python` and the runner writes
`{"escape_hatch": "python"}` into that layer's run row (`detail`), which
`run-pipeline --status` prints. The Data page does not show it yet.

## 2026-10-19 — S-1: the model as a schema, in a locked connection

`DataModel.execute` opens one read-only DuckDB connection per call
(`tracebi/model/engine.py`; per call, not per request, because a call is the
one seam every caller shares: the web routes, the gateway, builds, `verify`
and `execute_plan`). It attaches each file-backed warehouse READ_ONLY, makes
the tables the query reads into views (or, for a source with no engine,
loads the frame through its connector and registers it as Arrow), locks the
connection, and runs the same star SQL as before. The views reproduce the
frame round trip the old path did (NaN to null, DECIMAL to double, DATE to
timestamp), which is why every fingerprint and the parity fixtures stayed
byte-identical. Kept in pandas this round: the post-aggregation steps
(ratios, shares, windows, pops, to-dates, HAVING, ordering, labels), on the
small result. Not done: per-measure macros. Follow-up: the warehouse input
fingerprint still loads the table through the connector into pandas (once
per warehouse version, cached); a warehouse-side hash would avoid the load,
but it is a new fingerprint algorithm and was out of scope.

---

## 2026-10-19 — Decision: DuckDB-first on the server, a small engine of our own in the page

**Decision.** DuckDB becomes the only engine on the server. Transforms are
SQL by default (pandas and polars stay as a declared escape hatch that ends
in an Arrow table), the warehouse gets three storage tiers with Parquet on
object storage as the hosted default so the server holds the model and not
the data, the model compiles to a DuckDB schema (views + measure macros),
and SQL is a first-class binding that runs at build time and sits fixed in
the file. The report file is assumed to work **offline**: it carries the
flattened sub-star its figures need and `tracebi-calc`, a ~50 KB engine of
our own that executes the closed JSON query spec directly, so every spec
figure recomputes live on a filter with no server in the loop. The
"controls never compute new numbers" rule is replaced by: any spec query
over the embedded, fingerprinted data, the query in the trace, and a new
**Local** chip state. Parity with DuckDB is proved per measure kind by
test. Not Qlik: live cross-filtering through the model's declared
relationships, no associative state, no one-path rule.

**Measured before deciding:** DuckDB-wasm is 8.8 MB gzipped (~11.7 MB
inlined) against 2.9 MB for today's parquet-wasm + Arquero engine, and the
page's work is a closed spec over flat typed columns, so the page engine is
ours. A Rust port is the fallback if the 100 ms query budget fails;
`engine: duckdb` is a later opt-in for arbitrary SQL offline.

Design, closed decisions and the eight packages:
`design/duckdb-first.md`.

---

## 2026-10-18 — Decision: "receipt" becomes "trace"

**Decision.** The word *receipt* is retired from the canon and from every
surface a reader sees. The concept is **traceability**; the noun is
**trace**; the verb is "how this number was made" / "trace this number".
The MANIFESTO's "The receipt" is now "The trace": every number drawn through
the model has a trace; everything else must be marked as not having one.

**Why.** A receipt is proof of a purchase: it says a transaction happened
and was paid for, which is close to the claim TraceBi refuses to make (that a
number is right). Readers took "receipt" as "verified". A trace says what the
thing actually is: how the number was made, so it can be checked. It is also
the product's name and the brand mark's own figure ("Every number, traced",
A2-5), so the canon now says one word where it said two.

**The reader rule.** The noun names the thing at most once per screen;
everywhere else, say what it does. In the artifact: the masthead link is
"Trace", the footer is one line ending "▸ How these numbers were made" (it
opens the drawer; the footer's `<details>` stays in the file for a reader
without JavaScript and hides once the runtime has a drawer, whose About this
build holds the same notes, the app note included), the drawer is headed with
the report's name and "How each number was made", and the honesty sentence is
"This page does not claim the numbers are right; it records how each was made
so it can be checked." ("does not claim the numbers are right" is unchanged).
In the app: the panel's Trace tab, "Every report, and whether its numbers
still hold", "Only a build that re-runs to the same numbers reads green",
Export's "HTML · the file with its trace".

**Kept internal, on purpose.** The `tracebi-receipt` block id, `.tb-receipt*`
classes, `data-tb-receipt-*` attributes, `renderReceipt` /
`receiptFileName`, Python `receipt_*` names, manifest keys, `/api/...` fields,
`ReceiptFrame.jsx`, the panel's `receipt` tab key, and the `receipt_drawer`
key in `tracebi context`. Renaming them buys a reader nothing and moves the
artifact contract that every file already built depends on. A later rename is
item 36 in `design/ui-backlog.md`. History (`changes/*.md`, this
file, the architecture and strategy records) keeps the word it was written
in. `tests/test_agent_guides.py` now fails if AGENTS.md, the scaffolded
AGENTS.md or `tracebi context` says "receipt" outside those identifiers.

## 2026-10-18 — Step 4 of the UX plan: Ask

Step 4 made Ask the reader's path to a stamped number without code: one
commit on `step4-ask` (the 2026-10-17 UX plan).

**Decision: no language model in the app.** The app does not call a model;
the connected agent does (`answer_question`, `query_model`). So Ask in the app
is a *structured* question, not free text: one input that reads "Show
[measure] by [dimension] for [filter], [order], top [n]", where each slot is a
token from `GET /api/models/{name}` (declared measures with their
descriptions, the dimension attributes the fact joins) or from the new
`GET /api/models/{name}/dimensions/{dim.attr}/values`. Typing only finds
tokens ("fair value by sector top 8" takes one per part); a question is always
a query the model can run. When an agent can reach the app (the gateway at
`/mcp`, or dev mode), one line says "Or ask your agent: it answers from the
same definitions". The natural-language layer is the agent's job.

**What shipped.** The answer is `POST /api/models/{name}/query` drawn from its
own rows: the sentence and the response's row count; a bar chart (one measure,
one dimension, at most 12 rows), a table, or the number; each measure's
definition in words; the query line as the receipt writes it; a **Not
checked** chip, never green (an ad hoc query has no receipt). The question is
in the URL (`?q=`) and the session's last five sit under the input. **Keep
this** (analyst+) starts a report draft holding one binding, `answer`, with
the query (never the numbers) and a one-figure `app.jsx`, then opens the
draft's page. **Advanced** is the old Explore builder editing the same
question. The sentence, the suggestions, the definitions and Keep this's files
are one pure module (`web/ui/src/ask.js`) that the web journey runs in node, so
the test builds the files the page writes. `AskCut` (the report page's hidden
Ask box) is deleted, not reused: it cut one report's selection, where Ask asks
a model.

**What the captures showed.** `/ask` with no model lists the models; a model's
empty Ask shows the sentence's dashed slots and three questions the model can
answer. Fair value by sector, largest first, draws six accent bars with the
display text at each end, labels whole; the table answer (fair value, cost
basis and mark by issuer, top 8) right-aligns three formatted columns; the
one-number answer is $285,904,445 at 40px. Advanced opens with Fair value
and Sector ticked. Keep this landed on the draft's page with its preview: the
masthead titled with the question, the chart, a Draft chip. A viewer sees no
Keep this. At 390 the sentence wraps over three lines above a full-width Ask
button, the suggestions open under it, Advanced stays folded. Dark keeps the
accent bars and a neutral chip. No console errors.

**Deliberately left** (`design/ui-backlog.md` 28–31): no fingerprint on an Ask
answer (the HTTP query returns lineage, not `query_model`'s stamp); filters
are equality on dimension values (ranges and `having` are Advanced only);
measure labels are humanised names ("Fv share"); Keep this starts at
`<model>/<slug>` and the folder is chosen at publish.

---

## 2026-10-18 — Step 3 of the UX plan: Data and Review

Step 3 gave the app its last two places and retired the old frame: three
packages, one commit each on `step3-data-review` (the 2026-10-17 UX plan).

| Package | What shipped |
|---|---|
| D-1 | Data: `/data` lists the models one row each (shape, the reports' verdicts as counts, last refresh), with the Map as its picture view (`?view=map`, drawn with the line's nodes); `/data/<model>` leads with the line, then tabs Model · Transform · Sources · Runs. |
| D-2 | Review: Needs attention first (failed refreshes and runs, builds that need a look, publish requests decided in place, the person's own requests), then Drafts, then Verify a file as a small drop zone. |
| D-3 | Retire: dead code and CSS out, every old address checked to land (and the whole `movedTo` table in the smoke test), the words follow the four places everywhere but `CLAUDE.md`, the ui-audit baselines re-run. |

**Decisions.** *The line as navigation*: on a model's Data page the three
stations are the page's header and its links: Transform and Model select their
tabs, Reports opens the library narrowed to the model; the Reports stage with
its preview is gone. *Refresh data is admin-only, on Transform*: the one
primary action of the Transform tab, and it, Run all and every step's run
button render only for an admin (with no sign-in everyone is admin), because
they write to the warehouse. *Review's three sections*, in the order a person
acts: what needs attention, drafts, then checking a file; *requests are rows*:
a publish request waiting on the person is a Needs attention row they decide
in place, their own shows "Waiting on <folder>'s approvers", and decided ones
fold under Requests. `/runs` (History) and `/verify` keep their own pages under
Review; every other old address redirects (`movedTo`).

**What the captures showed.** The four places, a report page, History and
Verify at 1440 and 390, light and dark, after the cleanup: nothing regressed,
no console errors. The Data page's line stacks on a phone with the Transform
station current; Review empty reads "Nothing needs attention" and a person's
drafts empty state; Get started's "How the app fits together" is one entry per
place. 34 old addresses land where `movedTo` says in a browser.
The re-run ui-audit baselines (reference / demo, against Step 1's): score 34 →
62 / 33 → 75; findings 30 → 19 / 30 → 17. Gone: `scope-mismatch`,
`nav-you-are-here` on the old Reports page, `theme-decoration` (the
segmented bar's gradient), the model link's `small-target` on an open report,
and the open report's findings repeated under each old address. Left:
`blank-page`, `no-focus-ring` and `one-h1` on the open affordability report
(the demo: `one-h1` on medallion_revenue), the rail's "Reports" crumb and the
header's verdict chip as `small-target`, Review's "All history →" as
`small-target` (new with D-2), and `slow-page` (13 each, a timing check).
Report metrics did not move (fonts 5, accents 4 / 5, shadows 16, gradients 60,
looks 5 / 6); `bundle_js_kb` reads 1,215, not 2,345: the Step 1 run counted a
stale second bundle in `dist/`.

**Deliberately left** (`design/ui-backlog.md`): `CLAUDE.md` still says reports are
served "on the model's Overview" (the project instructions are the owner's to
edit); the Map's labels in mono; the Model tab's inner tab row and its lone
Edit as a draft button; the Transform flow's two-step zoom; the report page's
Ask box, off (`SHOW_ASK`), for Step 4; `notebook-guide.md`'s factory section
predates the one renderer; route splitting for the 1.2 MB bundle (the dead-code
pass did not move it: the bundler already dropped what nothing imported).

---

## 2026-10-17 — Step 2 of the UX plan: the reports home

Step 2 turned the app around the reports: five packages, one commit each on
`step2-reports-home` (the 2026-10-17 UX plan).

| Package | What shipped |
|---|---|
| R-2 | Names, not identifiers: a model's optional `label` (default: the name title-cased), `display_name` on `/api/reports`, `/api/runs` and `/api/desk`; identifiers only in Code and the receipt's query line. |
| R-3 | One `Verdict` chip (`Shared.jsx`) and one rule deriving it (`verdictOf` in `verdict.js`), used by every list, header, History and Build mode. |
| R-1 | `/` is the library (folders by model, a row per report: name, two-line description on a phone, verdict, built, schedule); four places in the sidebar; every old address redirects. |
| R-4 | The report page is the artifact full width under one command bar, with one panel, "About this build" (Receipt, Lineage, History, Files). |
| R-5 | History rows as sentences (what, verdict, when, how long, who), grouped by day, empty columns not drawn, cards on a phone. |

**Decisions.** *Four places*: Reports (home), Ask, Data, Review; the model is
a filter (a chip on Reports and History, the path on Data, Ask's own pick),
not the frame of the app. *Display names*: people read `report.json`'s
`name` and a model's `label`; `name` stays the identifier commands and
bindings take. *One verdict*: Reproduces, Needs a look, Does not reproduce,
Not checked (plus Draft and Never built in the app). No build: Never built;
the re-check failed: Does not reproduce; files saved after the build, the data
drifted, the check could not run, or a table was past its sink checks when
built: Needs a look; numbers from `report.py`, nothing recorded or a newer
TraceBi: Not checked; otherwise the re-check's Reproduces. Nothing else is
ever green, and a build row in History is never a check: only the newest
build of a report carries the list's verdict. *The host tells the frame*: the
app posts `{type: "tracebi:verdict", state, detail}` to the report's frame,
only a state `verdictOf` computed and never for Build mode's preview;
`tracebi.js` puts it on the masthead chip and in the drawer. Opened on its own
the file still says Not checked, and a draft stays Draft. *About this build*
replaces Details, Lineage, History and Code: the Receipt tab draws the
build's own certificate with its own `tracebi.js` in a sandboxed frame.

**What the captures showed.** The library and History read in names at 1440
and 390, light and dark. At 390 the library's descriptions wrap to two lines,
and the dashboard, concentration and book show nothing floating over content
in the app's frame or on `/r/`: DS-6 already moved the receipt into the
masthead, so finding 15's floating pill is gone. History at 390 is a card
list; most builds show no duration, because `tracebi report build` records
no finish time, so Took appears only beside background runs, schedules and
pipeline runs. The phone header is translucent over a scrolled list.

**Deliberately left** (`design/ui-backlog.md`): the Data page's Reports-stage
preview keeps its Preview/Config switch until Step 3 retires it; the
committed ui-audit baselines still name the old addresses (re-run them);
about nine lines in the Markdown docs (and their `site/docs` twins) still
say reports are served "on the model's Overview", for D-3;
`tracebi migrate model` drops `owners` (a bug, not UI);
`docs/guides/demo-script.md` still points at "the green badges above the
report"; `site/sample/portfolio_showcase.html` was built with the runtime
before Step 1; a report build records no finish time, so History cannot say
how long it took.

---

## 2026-10-17 — Step 1 of the UX plan: the report design system v2

The audit (the 2026-10-17 UX audit) found four visual languages in the
reports; the plan (the 2026-10-17 UX plan) cut the fix into nine packages, one
commit each on `design-system-v2`.

| Package | What shipped |
|---|---|
| DS-1 | `tracebi.css` §1 is the system: a seven-step type scale, three weights, tabular numerals; the accent is chart series 1; a dark palette of its own; `auto` mode; themes as accent presets; no hatch, gradient or resting shadow. |
| DS-2 | A masthead (kicker, h1, standfirst, period, built time, verdict chip) and a footer on every page; the About block leaves the body; 1,200px measure, 12-column grid. |
| DS-3 | The lead KPI larger, not wider; a delta is a stamped figure, never computed in the browser. |
| DS-4 | One D3 chart style: 55% bars, direct labels, nothing cut, thinned ticks, 6% gridlines; the tooltip links the receipt. |
| DS-5 | Tables: tabular numbers right, a 6px data bar in its own lane, sticky header, one totals style. |
| DS-6 | The receipt as a certificate: verdict, how to check, one row per figure (value, definition, query, short fingerprint). |
| DS-7 | The editorial on the same tokens and masthead, a 68-character column on a sheet. |
| DS-8 | Showcase, scaffolds, `init` bundles and demo app on the system; `aum_by_branch` the one bespoke look. |
| DS-9 | `scripts/ui_audit.py` renders every report, both modes and widths, into `report-sheet.png` and ratchets fonts, accents, shadows, gradients and looks per project. |

**What the captures showed.** The report sheet puts every reference and demo
report on one frame in both modes. It also showed what the package captures
missed: they were taken at 390px in a desktop browser, and no built page but
affordability named a viewport, so a real phone laid every report out 980px
wide and shrank it. The build now adds the meta (`stack.apply_stack`).

**Decisions.** *`auto` is the default mode*: a page follows the reader's
system; light or dark is pinned on purpose only. *The verdict chip is never
green on a file*: a file says Not checked or Draft; Reproduces needs a re-run
(`tracebi verify`, or a host passing a verdict). *Themes are accent presets*:
a light/dark accent pair and an optional display face, nothing structural; a
report's `style.css` follows the same rule. *The 12-column grid*
(`.tb-grid` + `.tb-span-*`) replaces Tailwind grid columns and `.tb-cols-2-1`.
*One receipt component*: Step 2 mounts `tracebi.renderReceipt(mount,
receipt, options)` in the app's report panel.

**Deliberately left** (`design/ui-backlog.md`): small multiples are dense on a phone;
the showcase's striped frozen column keeps a light shade in dark; the
selection handshake with a parent that is not the app; affordability keeps
its own look (Inter, green, paper, shadows, gradients), pinned light; the
reference project keeps per-report accents (book, showcase), so it has more
than one look.

---

## 2026-10-17 — Reports and dashboards: the editorial page, the React lane, themes

**Two kinds of page, picked by what the reader does.** `tracebi new-report`
writes a page to be *read* — by default an editorial `template.html`
(`.tb-article`: a headline that states the finding, standfirst, byline with the
build time, prose with bound numbers, captioned figures, a pull-stat, "What to
do", the methodology). `tracebi new-dashboard` writes a page to be *worked in* —
an `app.jsx` (the React lane), `--job overview|trend|leaderboard|scorecard`,
`--html` for the template version. Both read the same `report.json` bindings.

**The React lane, and why it is shaped this way.**

- *A fixed kit, no Node.* The page carries React 18, Sucrase (compiles the JSX
  in the page), Tailwind's browser build, and — only when imported — Recharts
  and the lucide icons named. The CSP is unchanged: inline scripts allowed,
  `eval` refused. Bundles are vendored under `tracebi/reports/assets/`, rebuilt
  from `assets/_react_src/` (`REACT_NOTICE.md`). Any other import fails the
  build. An npm/esbuild lane was considered and deferred: every builder and the
  server would need a JS toolchain.
- *Numbers keep receipts through the kit.* `<Kpi>`, `<Value>`, `<Chart>`,
  `<Spark>`, `<Table>` render the same `data-tb-*` elements a template holds and
  `tracebi.js` fills them. The build reads their *literal* props from the
  source (`app_lane.scan_figures`) to record claims and refuse a bad
  binding/column without running the app — hence `binding`/`cell`/`x`/`y` must
  be literal strings. A number the app computes is presentation; the About
  block says so.
- *Figures mounted after load* (a view switch) are hydrated by
  `tracebi.refresh()`; each hydrator touches an element once (`fresh()`).
- *No JavaScript* (email previews, file viewers): the build writes the kit
  figures into the mount point as a static view, SSR-filled like any template
  figure; it is also where the claims are read. The app replaces it.
- *CSS layering.* On app pages `tracebi.css` sits in `@layer tracebi`, between
  Tailwind's reset and its utilities, so a utility class wins; template-page
  element defaults are scoped with `:where(:root:not([data-tb-app]))`.
- *App behaviour honest by construction.* A page-wide `<Filter column>` subsets
  every binding with the column but never a KPI; `<Segmented>` picks *which*
  literal-binding figure shows; `useUrlState` keeps view/period in the URL.

**Look and practice, not app storage.** The look is asked once in the agent
dialog (mode, density, nav, title placement). Six contrast-checked shipped
themes (`report.json` `"theme"`, `tracebi theme use` → `reports/_theme.css`);
`reports/_style.md` is the team's house style, returned as `house_style` by
`tracebi context` / `get_context`. Design lessons: `design-dashboard-feel`,
`design-app-dashboards`, `design-editorial-report`.

**Open.** Dark mode overrides a light theme's accent (deliberate: contrast).
Label acronyms are a short fixed list (`derive._ACRONYMS`, mirrored in
`tracebi.js`). More dashboard jobs (operational monitor, funnel) can follow the
`_app_scaffold.py` pattern. PDF of an app prints its first view only.

---

## 2026-10-13 — Navigation redesign, the report page, a built-in MCP sign-in

Handoff from the cloud session that did this work. Merged: #253–#260.

**The app is organised as the process, not a list of pages.** A model's
**Overview** is the line: ① Transform → ② Model → ③ Reports, as tabs, with the
two hand-offs shown between them (the warehouse file, the measures). The
sidebar is Overview, Map, Explore, Drafts, Verify a file; **Map** is the same
process for the whole project as a graph (a backup for the line). Names are
shown exactly as the author wrote them, never prettified. URLs changed
(`/m/<model>`, `/m/<model>/{reports,model,transform}`, `/map`); the old ones
redirect. The mockups are the design canvas
https://claude.ai/artifact/D8UH4mqipmDL7whbjoyprL (private to the owner).

**One status rule, app-wide (#258).** Only exceptions get colour, always a
glyph plus words: `✕` failed, `△` source changed or stale, `○` never built or
cannot be re-run. A fine state is a plain fact, never green, so "reproduced"
does not appear on every row. The locked sentence is still "the sink satisfied
its contract". A failed contract raises *after* the tables are written (no
rollback, no certificate), and the failure copy says so.

**Edit as a draft (#253).** `POST /api/drafts` starts a user's own draft of a
published report or model (201 new, 200 already theirs); the UI button is
`components/EditAsDraft.jsx`. A Python model or a report with a `report.py` /
`script.js` is refused with "edit it from a laptop". The MCP `start_draft` tool
copies nothing unless `from_published` is true, so a bare call makes an empty
draft; that is a trap for agents (open question below).

**The open report page (#257, #259).** The Reports stage is a list beside the
last build. An open report keeps the app's nav as a 56px rail, has a two-row
header (where it is; name, exception chip, built / data refreshed / schedule),
a labelled toolbar (Rebuild, Export, Share, Edit as a draft; Lineage, History,
Details) and a docked panel (Details, Lineage, History, Code; a drawer under
1100px; open state remembered). A build that is not fine gets a bar under the
toolbar. The "More" menu was removed on purpose: it hid eight actions and read
as a developer tool.

**A built-in MCP sign-in (#260).** Claude's and ChatGPT's custom connectors need
OAuth; a static bearer token only works from Claude Code. Until now that meant
registering TraceBi at a company identity provider. With no provider:
`TRACEBI_DEMO_LOGIN=<role>` (a one-click demo user) and/or
`TRACEBI_LOCAL_USERS=name:role:password,…` serve a sign-in page at
`/oauth/callback`; everything after it is the existing authorization server.
Needs `TRACEBI_PUBLIC_URL` and `TRACEBI_OAUTH_SECRET`; cannot be combined with
`TRACEBI_OIDC_ISSUER`; `/mcp` only (the app's own pages are untouched);
failures are throttled in-process, so run one worker. The demo button lets in
anyone with the address: only for a server with sample data. In the connector
`admin` has the same tools as `analyst`.

### Not done: the hosted demo is not connected

The cloud session could not reach tracebi.com (its network proxy answered 403),
so nothing was checked against the live server. To connect the demo from
claude.ai: redeploy `tracebi-demo` from main; set `TRACEBI_DEMO_LOGIN=admin`,
`TRACEBI_OAUTH_SECRET` (`openssl rand -hex 32`) and `TRACEBI_PUBLIC_URL`; unset
any `TRACEBI_OIDC_*`; make `site/nginx.conf` forward `/mcp`, `/authorize`,
`/token`, `/register`, `/revoke`, `/oauth/callback` and `/.well-known/` to the
demo; then add `https://tracebi.com/mcp` as a custom connector. Two things to
verify first: `deploy/mcp/README.md` says `TRACEBI_PUBLIC_URL=https://tracebi.com/app`,
but the connector address must equal that URL's origin plus `/mcp` exactly or the
sign-in loops; and only `/mcp` is documented as forwarded. Check with
`curl -i https://tracebi.com/mcp` (401 with `WWW-Authenticate`) and
`/.well-known/oauth-authorization-server`.

### Open

- Demo role: admin (the plan) or a viewer for a safe public demo; a read-only
  guest can be added with `TRACEBI_LOCAL_USERS=guest:viewer:<password>`.
- Make `start_draft` copy the published report by default for reports.
- Report names are still monospace; whether to switch them to the normal font
  app-wide (still exactly as written) was offered, not done.
- Remote authoring steps 3 (`tracebi push`, a git-mounted library) and 4
  (pipelines publish with approval, run on the server); see
  `design/strategy/remote-authoring.md`.
- The AltsVault worked example (see 2026-08-14) is still parked.

### Notes for whoever continues

- Use `python -m pytest`, and `PYTHONPATH=$PWD` inside a git worktree (the
  editable install points at another checkout).
- Browser journeys: `TRACEBI_E2E=1 python -m pytest tests/test_ui_smoke.py
  tests/test_ui_build_mode.py tests/test_table_window.py tests/test_pdf.py
  tests/test_d3_charts.py`. Chromium is preinstalled; never `playwright install`.
- `tests/test_gateway_log.py` once failed because it searched the whole log
  line for a value that a random session id contained; it now ignores the
  random fields. Beware assertions that substring-match random ids.
- After editing docs run `python site/build_docs.py`; a test checks the site is
  in sync.

---

## 2026-10-07 — Handoff: type, Refresh log, Code views, one app for building (#226–#239)

A long session (Oct 5–7). Everything below is **merged** on main; nothing is in
flight. Later work (the navigation redesign, #240+) landed after this and may
have moved pages around: check names against the current app.

**What shipped, and why**
- **Look:** Hanken Grotesk + IBM Plex Mono replace Geist in the app; the report
  stylesheet (`tracebi.css`) matches the app and inlines Hanken Grotesk as base64
  (strict CSP unchanged). Licences in `NOTICE`. (#226)
- **Refresh log:** Run all / a step's Run start a background run
  (`POST /api/pipelines/{name}/runs`); output is captured per thread
  (`tracebi/pipeline/runlog.py`, ContextVar) into
  `data/logs/pipelines/<name>/<id>.log` and polled by byte offset. The recording
  core is `tracebi/pipeline/run_record.py`, shared by the app and
  `tracebi run-pipeline`, so both appear in one Runs list; a finished run lists
  the reports it rebuilt. Reading a log needs `analyst`. (#227, #230)
- **Bug found on the way:** a pipeline released only its own model's warehouse
  handle, so refreshing `portfolio_model` failed once `saas_model` (same
  `warehouse.duckdb`) was loaded. Now every model is released. (#227)
- **Code views:** read-only Code tab on Data model and Refresh, View code on
  Sources, Explore shows the query as Python and as a report.json binding. (#228)
- **Explore speaks the model's language:** named measures (only those a fact can
  run: `runnable_measures` in `info()`), results in the declared formats via the
  report build's own formatting code (`display` beside `data`), NaN/inf as null.
  (#231, #235)
- **New projects follow the convention:** `tracebi init` and the `--template`
  starters write `pipelines/<model>.py` and put reports under `reports/<model>/`.
  (#229, #232)
- **Report page:** one action row, a Download menu, full-width open report;
  Runs uses the same verdict words as Reports. (#233)
- **One app for building:** `tracebi dev <name>` opens the app with Build mode on;
  `--classic` keeps the stdlib preview. Build panel gained Data and Checks;
  a project feed shows the agent's exhibits and your notes before any report
  exists. (#236) The dev app releases the warehouse between requests and a write
  waits up to 10s for another process's read, so `run-transform` works with the
  app open. (#237) The preview formats numbers like the build. (#238)
- **Warehouse view** on Sources: tables, row counts, column profiles, per-table
  sink-contract status in the locked wording. (#239)

**Not done**
- Runs page waits on `/api/desk` for verdicts (about 0.75s slower); caching the
  desk check server-side would fix Reports and Runs together.
- A run row left `running` by a killed process (SIGKILL) never clears and keeps
  Run all disabled; needs a heartbeat or stale-row sweep. Ctrl-C is handled.
- Grouping by a dimension the fact can't join returns a 500 (DuckDB binder
  error), not a 400.
- Contract status fingerprints each certified table in full: fine on the demo
  projects, untuned for very large warehouses.

**Gotchas for whoever continues**
- Subagent worktrees import `tracebi` from the MAIN checkout (editable install):
  run with `PYTHONPATH=<worktree>` (the literal path; `export PYTHONPATH=$PWD`
  was refused by the sandbox). The UI smoke test starts a subprocess server and
  needs it too.
- `ui_audit` `slow-page` is a timing check; under machine load a different page
  trips each run. Re-run on a quiet machine before believing it.
- Two journeys in `tests/e2e/test_pipeline_journey.py` hand-built the old layout
  before #229; init now scaffolds it, so don't re-add that setup.
- Chart axis ticks in Explore still use K/M shorthand (a percent measure's axis
  reads 0.97 while its tooltip reads 97.0%); table headers there are raw names.

## 2026-09-24 — Off Vercel, design policy in the stylesheet, docs tidied

**Hosting.** tracebi.com (site) and tracebi.com/app (the demo) moved from Vercel
to one Hetzner box running Coolify, behind the Cloudflare tunnel. The site's
nginx proxies `/app/` and `/api/` to the demo under an internal-only host name.
Because the demo therefore sees that internal Host, its CSRF guard needs
`TRACEBI_ALLOWED_ORIGINS=https://tracebi.com,https://www.tracebi.com`; without
it every POST from the browser (Rebuild included) is refused as cross-site.
The Vercel files (`vercel.json`, `vercel-build.sh`, `api/`, the Vercel guide)
stayed as a rollback until the Vercel project was paused; they were removed
together on 2026-09-26.

**Design policy lives in three layers, strongest first.**
1. *Defaults in `tracebi.css` and the runtime*: what every report gets with no
   author effort (tabular right-aligned numbers, visible focus, readable line
   length, `.tb-lede` / `.tb-kpi-context`, direction tones). A value figure
   with no format now takes a table column's precedence (declared measure
   format, then the shape default), identically in the server render and the
   browser.
2. *Build-time and validate-time checks*: `spec validate` warns with the lesson
   to read; bad `data-tb-bars` / `data-tb-direction` fail the build.
3. *Lessons and the `tracebi-designer` skill*: the judgment the first two can't
   encode. 18 `design-` lessons, enforced into both guides by
   `tests/test_knowledge.py`.
Reason: an agent composing at volume doesn't read guidance it isn't made to
read, so a policy that can be a default should be one.

**Reader aids, and the rule they follow.** Sortable headers, in-cell bars and
up/down marks (from TanStack Table, shadcn/ui and Tremor) were added under the
existing interactivity law: they reorder or decorate stamped values and never
compute one. Sorting keeps the totals row because every row is still shown;
bars scale over all stamped rows so a filter never rescales them; a direction
mark changes a class, never the text the receipt reads. Pagination, column
pickers and gauges were left out on purpose.

**Docs.** The plans the epics replaced (ROADMAP, production-plan,
next-level-plan, product-readiness-audit) and the stale `overview.html` moved
to `docs/strategy/archive/`, so `docs/architecture/` holds only architecture.
`WORKFLOW.md` was folded into `docs/concepts/the-three-phase-workflow.md` and
left as a pointer. The sink-contracts concept page had wrong call signatures
for every check; fixed against `tracebi/contracts.py`.

---

## 2026-08-20 — Front-end surfaces: tracebi.com vs. the distributed app

Decided the boundary between the public product site and the UI that ships to
customer deployments, before there is anything to untangle (today there is only
the app UI in `web/ui/`; no marketing site exists yet). Three surfaces:
**tracebi.com** (marketing/explanation/docs/pricing — its own project, never in
the wheel), **the app UI** (`web/ui/` → `tracebi/web/ui/dist`, ships in the
wheel, runs against a customer's own registry), and a later **hosted control
plane** (the paid tier). The adopted flow: tracebi.com carries the pitch and
branches into a **live demo** — a hosted instance of the app UI (the
Vercel+Supabase demo topology), seeded with the reference project. The boundary
rule: *a logged-out stranger's content is .com; anything needing a customer's
warehouse loaded is the app.* Growing the app is endorsed — as an operational +
**trust console** (browse/verify/run/schedule, trust made visible), never a
drag-and-drop viz builder, which is the Tableau turf the artifact displaces.
Full write-up: [design/frontend-surfaces.md](design/frontend-surfaces.md).

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
  the same surface over phases ① and ②. `tracebi dev` opens it in the web app
  (Build panel and project feed, on `/api/reports/<name>/workbench/*` and
  `/api/workbench/project`); `_dev_server.py` is the `--classic` fallback.
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
| ① **Transform** | `transforms/` | Ordinary, unconstrained pandas — window functions, prose parsing, cleaning — that *sinks* clean star-schema tables into a file-backed DuckDB warehouse. The framework does not constrain this phase. | `examples/portfolio_project/transforms/holdings_transform.sql` (SQL since S-3; the pandas original is `holdings_transform_pandas.py`) |
| ② **Model** | `models/` | A declarative `DataModel` (grain, keys, measures) over the warehouse, read by a reviewer without opening the pandas above it. It reads the sink; it never sees the transform. | `examples/portfolio_project/models/portfolio_model.yaml` |
| ③ **Report** | `reports/` | A `ReportSpec` (JSON) pointed at the model — KPI cards, charts, tables — where every figure is a live query, re-rendered in milliseconds. (Also the home of template packages and `@register.report` factories — one folder for every report form.) | `examples/portfolio_project/reports/portfolio_model/portfolio_dashboard.json` |

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
  `transforms/holdings_transform.py`, `models/portfolio_model.yaml`,
  `reports/portfolio_model/portfolio_dashboard.json`, `run_workflow.py`,
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
  `reports/portfolio_model/portfolio_dashboard.json` — `value: "fair_value"` etc. over a
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
  `docs/guides/deploy-vercel-supabase.md` §5 instructs, raised on the first
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
`docs/guides/deploy-vercel-supabase.md` already prescribes — "run the API in a
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
  delete. *(2026-09-24: moved to `docs/strategy/archive/`.)*
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

Removed 2026-10-24: `CLAUDE.md` (Repository Layout, Core Invariants) and
`README.md` carry the architecture as it is now, and the entries in this file
carry why.

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

Open as of 2026-10-24 (the four questions that sat here, about the `requests/`
lane, were resolved and the lane removed in 0.8):

- **Who issued a trace.** A trace is made by whoever built the report, so
  between two parties it is documentation, not evidence. Signed traces are
  planned, not designed.
- **Per-recipient versions and row-level security.** A report parameter in the
  filter grammar, fanned out per value at delivery and keyed on the viewer for
  row-level security. Not started.
- **Running pushed Python in a sandbox.** Remote drafts carry no Python today;
  a locked-down worker with dev credentials is the proposed answer
  (`design/strategy/analyst-freedom.md`, `remote-authoring.md`).
- **DuckDB-first, what is not built:** per-measure `MACRO`s, the object tier's
  manifest swap, `tracebi migrate warehouse`, and the questions in
  `design/duckdb-first.md` §14 (the parity definitions, the default
  `embed`, Local in the library chip).
- **The word "receipt" in identifiers** (`tracebi-receipt`, `.tb-receipt*`,
  `renderReceipt`): renamed together or never (`ui-backlog.md` item 36).
- **The PyPI name.** Installs come from git until the `tracebi` name there is
  settled.

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
  CLAUDE.md and docs/guides/web-customization.md all show `uvicorn --workers 4`, so
  the docs were steering people straight into it. `_execute` now takes a
  `pg_try_advisory_lock` per layer on Postgres, keyed on a namespaced crc32 of
  the layer name; session-scoped, so a crashed worker's lock is released by
  the server rather than leaving a row to reap. Proved with two forked
  processes against a real Postgres: one RAN, one REFUSED, and with the DB
  lock neutered both ran. SQLite still yields True — it is the single-process
  fallback, and that is now documented rather than implied.
- Fingerprint is content-based but row-order-sensitive (intentional:
  reports are order-sensitive deliverables).
