# Production plan — agent reports with a relational selection

**Status: plan (2026-09-21).** The sequence from the receipt kernel that
already ships to a product an agent can author and a person can filter.
This plan does not replace [[report-architecture-v2]] or [[MANIFESTO]].
It sequences the product work those documents leave open: the app is a
review desk, chat compiles packages, and a filter is a selection on the
star schema that every figure recomputes through.

[[ROADMAP]] stays the historical backlog. Where the two disagree on
order, this plan wins.

## What production means

A team installs TraceBi, points an agent at a warehouse, and gets a
report a person can approve.

- The agent writes `transforms/`, `models/`, and `reports/<name>/` in
  git. It queries, builds, and verifies. It does not write the warehouse.
- The person reviews the model in a pull request and the draft through
  pins. The app's job is that review, not chart authoring.
- The page has one selection per model. Choosing a sector, a year, or a
  fund recomputes every figure on that model — headlines included — by
  re-running the declared measure. Related filter values that no longer
  have rows show as excluded.
- The file they email opens offline. `verify` re-runs the **authored**
  selection and the passing verdict is `reproduces`. A further slice the
  reader makes is cited as measure plus selection, and can be re-run.
- Chat applies selections and writes packages. A number in the thread is
  one the tool just returned, fingerprint attached.

Signing, authenticated identity, and a retention archive are the later
institutional tier. They sit on files this loop already produces. They
are not a gate for this plan.

## Decisions this plan locks

1. **One calculator until a second one is proven.** Selections are
   evaluated by `DataModel.query`. The browser displays the result. It
   does not add a column up, and it does not average a ratio.
2. **A selection is the filter grammar that already exists.** Dimension
   attributes, equality, lists, ranges, `contains`, combined with AND.
   `having`, `order_by`, and `limit` stay on the binding. A top-10 under
   a sector selection is the top 10 inside that sector.
3. **Binding filters and the selection compose.** Filters on the binding
   always apply. Selection predicates are conjoined. When both name the
   same target, the selection wins for that target, because that target
   is the control the reader is moving. Filters on targets with no
   control stay fixed.
4. **The authored selection is the receipt.** It lives on the package.
   The report opens on it. Clear returns to it. `verify` re-runs it.
   Any other selection is a live query with its own fingerprint, not a
   silent edit of the published number.
5. **Value figures react only by re-query.** The current rule — controls
   subset stamped rows, and value figures never react — remains the
   behavior of reports that have not opted in. Opt-in is a `selection`
   block on the package. Existing artifacts do not change.
6. **Chat is a client of the gateway.** It has no private query path.
   "What about technology?" sets the selection. "Keep this cut" writes
   that selection into the package and rebuilds. The canvas people keep
   is the artifact.
7. **Offline slicing waits for parity.** Until a worker port of a measure
   kind matches `DataModel` on a pinned corpus, that kind recomputes
   only while `tracebi dev` or `tracebi serve` can reach the model. An
   offline file shows the authored selection and says so on the controls.

## Out of scope

- Drag-and-drop chart authoring.
- The agent writing the warehouse, or pipeline runs over MCP.
- A browser SQL engine as the first implementation of a measure.
- Precomputing every slice.
- Tracing lineage through phase-① pandas.
- L3 signing, per-agent identity, org-wide receipt retention.
- Replacing the medallion runner. It leaves primary navigation. It keeps
  working as a way to refresh a sink.

## Where the code is today

The kernel this plan builds on is in place: stamps, schema-2 manifests,
`tracebi verify`, figure claims, sink contracts, the package lane, and
the MCP gateway (`tracebi/mcp_server.py`). `DataModel.query` already
applies `filters` before aggregation and executes every measure kind.

What does not match the product yet:

| Gap | Where |
|---|---|
| A model loaded once stays loaded for the process | `tracebi/model_registry.py` `get` |
| `info()` tables are name, connector, and source | `DataModel.info` |
| Numeric literals outside figures are a workbench count | `lint_numeric_literals` in `tracebi/reports/figures.py` |
| Web renders return the manifest in memory | `tracebi/web/api/routers/reports.py` (`save_manifest=False`) |
| Get Started teaches `DataSet` chaining | `web/ui/src/pages/GettingStarted.jsx` |
| Filters subset rows; value figures ignore them | `tracebi/reports/assets/tracebi.js` `hydrateControls` |
| The homepage verify button swaps predetermined strings | `site/index.html` |

`docs/architecture/large-detail-artifacts.md` §10 already names the
offline explorable tier and parks it. Step 4 below is that tier, entered
only after the server path is the one people use.

## 1. Ship the authoring loop

The agent can finish a report, and a person can find the file.

**Model reload.** `ModelRegistry.get` reloads a file when its mtime is
newer than the load. A long-lived `tracebi mcp` or `tracebi serve`
picks up an edit to `models/*.py` on the next call. Failed reloads
leave the previous model in place and return the error on that call.

**Schema the agent can read.** `DataModel.info` gains columns and dtypes
per table from the connector's describe path (`DESCRIBE` / information
schema on DuckDB and SQL). It does not `SELECT *` to learn names.
Dimension attributes and declared measures stay the governed vocabulary.
Columns are how the agent stops inventing names for ad-hoc measures.

**Binding stub on every query.** `query_model` includes a `report.json`
fragment for the query it just ran: model, fact, measures, dimensions,
filters, having, order, limit. The agent pastes it. It does not
transcribe the number into HTML.

**Prose gate.** After exploration blocks are stripped, `lint_numeric_literals`
greater than zero fails the build with `FigureError`. Numbers inside
`data-tb-stage="exploration"` stay legal in `tracebi dev`. The published
page has no unclaimed numeral.

**Retain the web receipt when the disk allows.** A package render writes
`output/<name>.html` and `output/<name>.html.manifest.json`, the same
names as `tracebi report build`. The HTTP response still carries both.
A read-only filesystem (the demo topology) does not fail the render; the
payload says the manifest was not retained.

**The desk.** The workspace nav is Desk, Report, Contract, and Explore.
Learn is Workflow, Get Started, and Docs. Desk lists
open pins, drafts that still contain exploration, published reports
whose verdict is not `reproduces`, and sinks that are `stale` or
`no_contract`. Report opens the last built artifact, with rebuild as a
secondary action. Contract is the model in one screen — grain, facts,
measures, tables, sink-contract status — and names the `models/*.py`
file. Connectors become a tab on Contract. Pipelines leave the primary
nav; the runner stays available off the contract as Refresh. Get Started
becomes the three-phase scaffold (`new-transform`, `new-model`,
`new-report`, `dev`, `build`, `verify`). The `DataSet.filter().transform()`
tour moves to the handbook as an advanced page.

**Honest marketing widget.** The button on `site/index.html` is labeled
as an illustration, or it runs `verify --file` against a fixture baked
into the page. It does not claim a predetermined string is the verifier.

**Accept when:** from a fresh `tracebi init`, an agent that only has the
gateway reaches a file whose `verify` verdict is `reproduces`, and Desk
opens that file. A hand-typed number in `template.html` fails `report
build`. A model edit is visible to the next `describe_model` without a
process restart.

## 2. Selection through DataModel

Relational recalculation, with the engine that already owns the measures.

**Package block.** Optional, so existing reports keep today's controls:

```json
"selection": {
  "model": "portfolio_model",
  "filters": {"dim_sector.sector": "Technology"}
}
```

Absent or `"filters": {}` means no extra cut. The report opens on
`filters`. Reader session state is not written back unless the person
keeps the cut (step 3).

**Endpoint.** `POST /api/reports/{name}/selection` with a `filters`
object in the query grammar. For each binding on that model, conjoin as
in decision 3 and call `DataModel.query`. Response, per figure: id,
binding, rows (or the one cell), the formatted value, the resolved
query, the fingerprint. Plus, for each control column, `included` and
`excluded` distinct values under the selection. The authored selection
is flagged `authored: true` when the request matches the package block.

Auth is the existing report-run rule. The endpoint computes and returns
stamps. It does not write the warehouse or the package.

**Page.** When the package opts in and the server is reachable,
`data-tb-filter` posts the selection and refreshes every figure on that
model, value figures included. Excluded options stay visible and inert.
The receipt rail shows the selection and whether it is the authored one.
Download of the sliced view names the selection in the filename and the
header. Download of the full binding stays the stamped grain of the
authored query.

When the server is not reachable, the controls do not subset-and-sum.
They show the authored view and a title that further slices need the
model.

**Vocabulary, same change.** The behavior change to `data-tb-filter`
under an opted-in package lands in `tracebi/capabilities.py`, `AGENTS.md`,
and `_INIT_AGENTS_MD` together. `tests/test_agent_guides.py` stays green.
The portfolio showcase opts in only after the endpoint matches
`query_model` on the same filters.

**Accept when:** on the portfolio report, choosing a sector changes fair
value, the ratio, and the holdings table together; a sector with no rows
under the rest of the selection is excluded; the returned fingerprint
equals `query_model` with those filters conjoined; a report without a
`selection` block still subsets rows and leaves value figures still.

## 3. Ask, then keep

Chat and the page share step 2's protocol.

The page control is the dropdown. It posts the selection. The desk
does not host a question box: a sentence that only names a value the
dropdown already has is the dropdown. Questions stay with the agent
outside the site (Cursor or Claude on the gateway). Pins are read
before the next edit.

**Keep this cut** writes the current filters into the package `selection`
block and runs `build_report`, then `verify_manifest`. The agent does
not edit digits in `template.html`. A new grain the page cannot cut —
the detail was never a binding — is a new binding in `report.json`, then
a rebuild, not a total computed in the session.

The HTTP gateway (`tracebi mcp --transport http`) is the backend. Cursor
and Claude use it directly. The site is Desk, Report, and Contract.

**Accept when:** choosing a sector on the open report moves the
selection, the page contains no number that lacks a fingerprint, and
keeping that cut produces a new manifest whose authored selection is
the one on screen and whose verdict is `reproduces`.

## 4. Offline slicing, after parity

Only after step 2 is what people use. This is the parked tier in
[[large-detail-artifacts]] §10, narrowed.

Embed the grain the controls are allowed to cut. A worker evaluates a
measure kind only when a corpus test shows it and `DataModel` produce
the same fingerprint for the same selection. First port: `simple`
aggregations and `ratio`. `share`, `rank`, `running`, `period_end`, and
the time-intelligence kinds stay server-only until their own corpus is
green. Python remains the source of truth. The worker is a port.

`verify --file` reproduces the authored selection with no database. A
documented selection reproduces against the sealed grain with no server.
A kind without a port does not recompute offline.

A report that needs to scan raw detail, rather than the control grain,
opts into the heavy engine. The default report does not pay for it.

**Accept when:** the corpus fails on a one-row drift between the worker
and `DataModel`, the authored view of an opted-in report verifies from
the file alone, and a `period_end` figure still refuses to recompute
offline.

## Order

Steps 1 → 2 → 3 → 4. Step 2 is meaningless if the agent cannot publish
the package it selects against. Step 3 is a client of step 2. Step 4 is
a port of step 2, and shipping it first forks the receipt.

Each step lands with tests for its accept condition, and with the
vocabulary update when it changes what an agent is allowed to say.
