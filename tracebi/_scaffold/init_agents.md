# Working in this TraceBi workspace

You are an agent working in a **TraceBi** workspace. TraceBi is the trust layer
for AI-generated analytics: every number you put in front of a person should
carry a trace. Read this before you touch anything.

## The one rule

**Every figure in a report names a stamped data binding — never a hard-coded
number.** A number you typed in has no trace and cannot be verified. If a
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
①  transforms/   SQL by default (<name>.sql; pandas is the escape hatch):
                 clean it, then SINK clean star-schema tables into the
                 warehouse (data/warehouse.duckdb) and declare a SINK
                 CONTRACT on what landed (<name>.contract.yaml beside it)
                        ── freeze: the warehouse + its contract ──
②  models/       a declarative DataModel over the sink: grain, keys, measures.
                 It reads the warehouse; it never sees the transform.
                 YAML by default (models/<name>.yaml).
                        ── freeze: the model (the contract) ──
③  reports/      an ARTIFACT PACKAGE in a project named for its model —
                 reports/<model>/<name>/ holding report.json (named query
                 bindings) + template.html (your page, where every figure
                 claims a binding). Builds to one self-contained HTML + a
                 manifest (the trace).
```

A model, its transform and its reports belong together, and a **pipeline**
runs them as one: `models/<model>.yaml`, `pipelines/<model>.yaml` (`transform:`,
`models:`, `reports: all`, `schedule:`; it only names the transform),
`reports/<model>/`. A source is `connections/<name>.yaml`.
`tracebi run-pipeline <model>` runs the transform, then builds every report in
`reports/<model>/`, each with its trace; the app's **Refresh data** (Data,
the transform's page) runs the same pipeline. A report is named by its path (`<model>/<name>`) in every
command, and builds to `output/<model>/<name>.html`. The sample is
`sample_model` — `pipelines/sample_model.py`, `reports/sample_model/`.
People read names, not identifiers: a model's `label` (optional; unset, the name
title-cased) and a report's `report.json` `name` (human, not the folder slug).
A report's `description` is one sentence for the reader, what the page shows; how
it is built goes in `"notes"` or a comment. The masthead's kicker is the model's
label (added by the build when you write none); the `<h1>` is the name or finding.

**Workspace and projects.** The workspace is everything one `tracebi.yaml` covers: one warehouse, its sources, transforms and models, the brand and the default house theme (one per company). A project is one area's reports: a top-level folder under `reports/`, named for the model or models it reads (`reports/saas_model/` is the SaaS project). Models stay shared at the workspace, so two projects can read one model. Folders inside a project stay folders, and `my-published/<name>` is a person's own space, not a project. A theme is set on a report (`report.json` `"theme"`) or the workspace (`tracebi.yaml` `brand: {theme}`), never on a project. Nothing is renamed: the API and the files still say folder (`/api/folders`, `_folder.yaml`) and `describe_project` describes the workspace (`describe_workspace` is the same tool; `docs/concepts/workspace-and-projects.md`).

**Project and folder permissions.** A project or a folder under `reports/` (a directory that is not a package) may hold a `_folder.yaml` granting `view`, `build`, `publish` and `manage` to sign-in groups or names (`docs/reference/folder-yaml.md`). With none, roles decide as before. A report in a folder you cannot view is not listed and every read of it answers as if it did not exist, so a "no such report" over the gateway can mean "not yours": do not look for it another way. A `build` or `publish` refusal names the permission it needs; ask a folder manager rather than working around it.

The phases are decoupled: editing a report never re-runs the transform. Phase ①
is unconstrained — write whatever the data needs; the contract is the
named tables you sink, not how you cleaned them. **Transforms are SQL by
default**: `tracebi new-transform "<Name>"` writes `transforms/<name>.sql`,
DuckDB statements run top to bottom in ONE fresh warehouse connection
(`read_csv('inputs/…')` resolves against the workspace root; a table you
`CREATE OR REPLACE` — not `TEMP` — is a sink table; on the object tier
write `COPY (…) TO '{{ sink }}/<table>.parquet' (FORMAT PARQUET)`, or let
the created table land there). A view you `CREATE OR REPLACE VIEW` is a
sink view on the file and remote tiers: it may read only warehouse tables
and views, and one that reads a `-- source:` table or a file is refused
(the object tier refuses every view). Materialize the facts you aggregate,
view the derivations. Exactly two placeholders: `{{ sink }}` (the
warehouse tracebi.yaml names) and `{{ root }}` (the workspace root). To read
a table from a database outside the warehouse, declare the connection
(`tracebi connect crm --kind postgres` writes `connections/crm.yaml`) and
put `-- source: crm.issuer_ratings` in the transform's header, one line per
table: the runner loads it through the connector before the first statement
and the SQL reads `crm.issuer_ratings`. Ending the line with
`fallback: inputs/issuer_ratings.csv` names a committed snapshot read only
when the connection's `${VAR}` is unset; the certificate records each load
under `sources` (and `source_fallback: csv` when the snapshot stood in), and
`tracebi verify --contracts` re-reads it. In Python,
`load_source("crm.issuer_ratings", ROOT, fallback=...)` from
`tracebi.transforms` returns the same frame and record for
`contract(..., sources=)`. The
escape hatch is pandas or polars (`--python`, which is what
`transforms/sample_transform.py` is). **Transforms are notebook-shaped**:
the scaffolds use `-- %%` / `# %%` cells with markdown cells, so your
editor folds them (and opens the Python as a notebook) while the file stays
plain, reviewable code; literal `.ipynb` works too, and
`tracebi run-transform` executes any form top-to-bottom fresh and reports
`form: sql | python | notebook`, so the sink never comes from
out-of-order kernel state. Declare the sink contract beside the transform
in `transforms/<name>.contract.yaml` (`checks:` — `- rows: fact_x` with
`at_least: 1` beside it), or end a Python transform with a
`with contract(...)` block (see `transforms/sample_transform.py`): declared
checks — `rows`, `unique`, `not_null`, `foreign_key`, `values`, `reconcile` —
run as read-only SQL at sink time, raise on failure, and record a certificate
(`data/warehouse.contracts.json`) that report manifests join against. The
exact claim is "the sink satisfied its contract" — never "the transform was
verified"; nothing machine-checks the SQL or pandas above the sink.

## Starter templates

`tracebi context` lists them under `templates`. `tracebi init <workspace>
--template saas-metrics` (also `saas_metrics`) scaffolds the SaaS metrics
starter: `inputs/subscriptions.csv`, `transforms/saas_transform.py`,
`models/saas_model.yaml` (ending MRR, logo churn, a signup-cohort cut), and
two reports — `saas_model/mrr_dashboard` (dashboard) and
`saas_model/cohort_brief` (tabbed). `tracebi init <workspace>
--template sales-pipeline` (also `sales_pipeline`) scaffolds the sales
pipeline starter: `inputs/opportunities.csv`,
`transforms/sales_pipeline_transform.py`, `models/sales_pipeline_model.yaml`
(open pipeline value, win rate as a ratio of totals, stage / rep / region),
and two reports — `sales_pipeline_model/pipeline_dashboard` (dashboard) and
`sales_pipeline_model/rep_scorecard` (tabbed). Each starter also gets
`pipelines/<model>.py`, so `tracebi run-pipeline <model>` (and the app's
**Refresh data**) runs its transform, then builds its reports. Unknown template
names are
refused with the known list. On real tables, `tracebi connect` and re-point
the model. Default `tracebi init` (no flag) scaffolds the sample orders
dashboard (`transforms/sample_transform.py`).

## Authoring a report (the artifact package)

**Two ways to write a page.** `template.html` (below) is HTML with
`data-tb-*` figures: checkable without running anything, readable with
JavaScript off. Use it for briefs, long-form, emailed and printed reports,
and anything written at volume without review. `app.jsx` instead of
`template.html` is the React lane, for app-like dashboards (navigation,
drawers, drill-downs, toggles): a component (`export default`) built from a
fixed kit — `react`, `echarts`, `recharts` (Recharts 2, which also
works), `lucide-react` (import icons by name),
Tailwind classes (`bg-card text-ink border-rule` follow the page's tokens;
the build writes the CSS for the classes app.jsx spells out, so write each
class whole, never `"text-" + tone`) and the `tracebi` module. No other
import builds, and JSX that does not parse fails the build: the page is
compiled once, at build, and is still one offline file. Show numbers through the kit — `<Kpi binding cell format label lead>`,
`<Value>`, `<Chart binding type x y>`, `<Spark>`, `<Table binding>`, with
`<Filter>`, `<Search>`, `<Download>` — and give `binding`, `cell`, `x`, `y`
literal strings: the build reads them as claims and refuses a binding or
column that does not exist. A KPI's change is a stamped figure too:
`<Kpi … deltaBinding="kpis" deltaCell="unrealized" deltaFormat="currency_compact"
deltaGood="up" context="vs cost">` shows it first on the context line with its
arrow, sign and colour (`deltaGood="down"` for costs and churn). Only where
the model measures a comparison; no comparison measure, no delta. 

**Charts.** `<EChart>` (Apache ECharts) is the chart. `<EChart binding="by_sector"
type="treemap" x="dim_issuer.sector" y="fair_value" format="currency_compact">`
plots a binding's columns as they are: `type` bar, barh, line, area, pie,
scatter or any ECharts series type that takes name/value items (funnel,
treemap, sunburst), `series` a column that splits the rows into series,
`unit`, `stack`. With `binding`, `x` and `y` literal it is a claim like
`<Chart>` (`data-tb-figure="chart"`; the build refuses an unknown binding or
column). `option={…}` (an ECharts option, or a function of the rows)
deep-merges on top to style it; it cannot replace the binding's numbers.
An `<EChart option={…}>` alone draws numbers the page computed: it carries
`data-tb-computed` and is the app's presentation, not a checked figure, and
the page's footer says so. The page's ECharts draws bar, line, scatter,
effectScatter, pictorialBar, pie, funnel, treemap, sunburst, heatmap and
sankey series (with legend, dataZoom, brush, visualMap, markArea, toolbox);
any other series type is not in it. Every chart is live: its rows are its binding's
query re-run under the page's selection, and a click on a mark selects its
`x` value (`selects="dim.col"` on an option-only chart; shift adds), its own
field's other values kept and dimmed (`highlight="off"` narrows instead).
Both chart engines draw the house look (`docs/reference/chart-style.md`)
from the `--tb-chart-*` tokens; `renderer="svg"` is the default (vectors,
tabular figures), `renderer="canvas"` for thousands of marks.
`useBinding("name")` hands your own components the same live rows (the
stamped rows on an `"embed": "none"` page) and `useSelection()` the
selection: what you draw from them is live, not a checked figure, and a sum
you compute is the app's presentation. Recharts also works (`import {
BarChart, Bar } from "recharts"`); `<Bar onClick={(d, i, e) =>
window.tracebi.pick("dim_region.region", d.payload["dim_region.region"], e)} />`
selects as a kit chart's click does.

For app behaviour: `<Filter column>` with no `binding` filters the whole page
(every binding with that column; on a live page every figure it reaches
recomputes, and `multiple` picks several values); `<Range column>` is a range
on the page's selection, `<Table selectRows>` selects by row, and
`<SelectionBar />` places the bar of what is picked;
`<Segmented options value onChange>` picks which figure shows — a period
toggle is one literal-binding figure per option, never arithmetic; and
`useUrlState("view", "Overview")` keeps a view or period in the URL so a
shared link opens on it; while the page prints, `usePrinting()` is true and
an app with views renders all of them, so the PDF holds the whole report.
Open the page with `<Masthead title kicker period>` (children are the
standfirst; it shows the build time and the verdict chip; `kicker` defaults to
the model's label) and end its main
column with `<Footer />`, where the build's footer goes; `<main
className="tb-page px-6 py-8">` is the 1,200px page measure.
`tracebi new-dashboard --job overview|trend|leaderboard|scorecard|monitor|funnel`
starts from the shape the dashboard is for. Without JavaScript (an email
preview) the page shows its kit figures as built.
`docs/reference/app-jsx.md` has the kit.

Worked example — the framework builds the figure, you place it. Declare it in
`report.json`, then write `{{ figure("id") }}` where it belongs in `template.html`:

```json
"figures": {"total": {"kind": "value", "binding": "totals", "cell": "revenue", "format": "currency"}}
```
```html
<section class="kpi">{{ figure("total") }}</section>
```

A declared figure the template never places fails `publish_draft` and
`preview_draft` alike.

`tracebi new-report "<Name>"` writes a working example of the hand-written
form (`reports/sample_model/sample_dashboard/`, the sample, is the app form) —
a page of ordinary HTML whose figures each name a binding from `report.json`:

- `data-tb-figure="value|chart|table|custom"` + `data-tb-binding="<name>"` —
  the claim. Values add `data-tb-cell="<column>"` and optionally
  `data-tb-format` (`compact`, `currency`, `comma`, `percent`, …). A value
  figure needs a one-row binding: its own query with no dimensions, or
  `order_by` plus `limit` 1. The cell may be text, such as the top
  sector's name. Charts add
  `data-tb-type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`),
  `data-tb-x`, `data-tb-y` (comma-list for multi-series), optional
  `data-tb-color` and `data-tb-value-format`. Tables optionally add
  `data-tb-columns` and the `tb-table--striped` / `tb-table--compact` classes;
  `data-tb-labels` and `data-tb-formats` set headers and number formats per
  column (`data-tb-formats="revenue=currency; share=percent"`), and
  `data-tb-totals="<binding>"` adds a totals row from a one-row binding (the
  same query with no dimensions — the model computes each total).
  `data-tb-sort` makes a table's headers click-to-sort, `data-tb-bars="col"`
  draws a thin proportional bar after each number in a column, and
  `data-tb-direction="up-good"` (or `"down-good"`) marks a bound change on a
  value figure up or down, good or bad — on a KPI, as `<span class="tb-kpi-delta"
  data-tb-figure="value" … data-tb-direction="up-good">` leading its
  `.tb-kpi-context` line. They reorder or decorate stamped
  values; they never compute one. Tables past 500 rows render only the
  visible rows; printing and download still use every row. Find-in-page
  cannot see rows outside that window — search with `data-tb-search`.
- **Give every figure an `id`** — ids are how humans redirect you
  ("fix `tbl-seniority`").
- **Or let the framework build the figure.** Declare it in `report.json`
  under `figures` — e.g. `"total": {"kind": "value", "binding": "totals",
  "cell": "revenue", "format": "currency"}` — and place it in
  `template.html` with `{{ figure("total") }}`. You keep the whole layout,
  stylesheet and script; the emitted element is byte-identical to what a
  spec would compile, so the grammar above never has to be hand-written.
  The name becomes the id (`fig-<name>`). Kinds: `value` (needs `cell`
  and a one-row binding),
  `chart` (`chart_type`/`x`/`y`/`color`/`palette`), `table`
  (`columns`/`style`); a `custom` figure has no framework markup, so draw
  that one yourself. It refuses the silent failures — an undeclared binding
  fails at load, and a figure declared but never placed (or placed twice)
  fails the build. Hand-written figures still work; this is sugar. `libs`
  is optional. Every chart is drawn by Apache ECharts: the build inlines
  ECharts automatically when the page contains a chart figure, and draws
  every chart type in one style (bars carry their own values, a line ends in
  its last value, names wrap and are never cut, ticks are short; legend
  toggles, tooltips with the measure's description and a "Trace →" link to
  that figure's record, arrow-key reading, a click on a bar or slice writes
  the page's selection). SVG by default; `data-tb-renderer="canvas"` on one
  chart or `"charts": {"renderer": "canvas"}` in `report.json` for thousands
  of marks. `"libs": ["d3"]` is only for your own `tracebi.draw` figures;
  `"echarts"` is no longer a choice.
- "Top N" is declarative: put `order_by` + `limit` in the binding's query.
  Never sort or slice in `script.js` — that moves ordering out of the trace.
- `filters` is WHERE (before aggregation) — a filter on a measure changes the
  group totals. To keep only groups whose *total* clears a threshold, use
  `having` (HAVING): `"having": {"revenue": {"gte": 250}}`.
- A measure can carry its own filter, declared on the model:
  `add_measure('purchases', column='amount', agg='sum', filters={'activity_type':
  'purchase'})` (YAML: `filters:` on the measure). It restricts only that
  measure, so a query's own filters still narrow every measure; the trace
  stamps the filter, and `verify` re-runs it.
- A measure can carry a `label` (YAML: `label: Total revenue` on the measure):
  the name people read in the app. Without one the app humanises the
  identifier; queries and bindings still name the measure by it.
- The model is the semantic layer: `description`, `synonyms` and `questions` are its agent vocabulary (`describe_model` returns them; match a person's word to a synonym, then query the identifier).
- A report can calculate its own measures: a `"measures"` block in its
  `report.json`, keyed by model (`{"sample_model": {"big_minus_small":
  {"measure_expr": "big_orders - small_orders"}}}`), takes the model's measure
  keywords. A binding that lists one by name gets it for that query only; the
  model is not changed, and a name the model already declares is refused. The
  trace labels these "calculated in this report". Promote one into the model
  (a reviewed edit) to make it shared.
- A report can run a SQL calculation the model cannot express (a rollforward, a
  running total): a `"sql_calculations"` block in its `report.json`, keyed by
  model (`{"sample_model": {"running_revenue": "SELECT region_id, order_date,
  SUM(revenue) OVER (PARTITION BY region_id ORDER BY order_date) AS
  running_revenue FROM fact_orders"}}`), bound as `"data": {"running": {"model":
  "sample_model", "sql": "running_revenue"}}`. It is one read-only SELECT over the
  warehouse's own table names; a write, ATTACH, COPY, PRAGMA, or a second statement
  is refused when the report builds. `{{ measure('revenue') }}` inside it expands
  to a model measure (simple and filtered measures only; other kinds are refused by
  name). The trace labels it "calculated in this report (SQL)" and records the
  SQL, and `verify` re-runs it. Reach for a model measure first.
- **Scenarios are the one place a page computes.** A
  `data-tb-scenario` block lets the reader ask "what if": `data-tb-input`
  fields, a `data-tb-preset` picker (`data-tb-key`, `data-tb-fill`,
  `data-tb-default`) that fills them from a stamped row, and
  `data-tb-calc` outputs with a closed formula (`+ - * / ^`, `pmt`, `min`,
  `max`, `round`, `abs`) evaluated in the browser. It is never a figure,
  never inside or around one, and never in the trace: the runtime labels
  it as computed from the reader's inputs, and the manifest records only
  its declaration with `verifiable: false`. Use it for a rate the reader
  remembers, never for a number a query could produce. The build checks
  every formula and preset. See `examples/portfolio_project/reports/housing_model/affordability/`.
- Interactivity: a figure's number is only ever a query result. On a live
  page (the default) `data-tb-filter` dropdowns recompute every figure they
  reach by re-running each binding's plan (The live page, below);
  `data-tb-search` only narrows the rows shown. On a page built with
  `"embed": "none"` filters only subset WHICH stamped rows a binding's
  tables/charts display, and value figures never react (summing the rows
  on screen would be a number no query produced). A `selection` block in
  `report.json` (`{"model", "filters"}`) sets the AUTHORED selection: the
  state the page opens in and the build's trace. Ask reads pins, then
  resolves a question to a value one of those controls already has, then
  recomputes it on the server. A question that names one declared
  dimension the report does not already cut becomes a new binding in
  `report.json`, then a rebuild whose verdict is on the reply. A
  question that names no declared value, or names two columns, is
  refused. A number in the reply is a value figure beside its
  fingerprint. The trace names the selection and whether it is the
  authored one. `data-tb-download` stays the full stamped binding; the trace
  drawer downloads the sliced view and names the selection in the filename
  and the header. Tables scroll past
  `data-tb-rows` (default 10). `data-tb-download` buttons export the
  stamped CSV verbatim (`data-tb-label` sets their text). Layout: tabs via `data-tb-tab` sections inside
  `.tb-tabs`; side-by-side via the 12-column grid (a `.tb-grid` whose panels carry
  `.tb-span-4/6/8/12`). Pick a page by name instead of
  inventing one (`presentation.layout` in `tracebi context`). A page someone *reads* —
  once, emailed, printed — is a report: `tracebi new-report "<Name>"` writes an editorial
  `template.html` (`<article class="tb-article">`: a masthead — `<header class="tb-masthead
  tb-article-head">` with `.tb-kicker`, an `<h1>` stating the finding, `.tb-standfirst`,
  `.tb-masthead-meta` with `data-tb-built` — a bound `.tb-lede`, prose sections,
  `<figure class="tb-figure">` with a `<figcaption>`, `.tb-pullstat`, a table, the
  `.tb-footer`; the register is the default, so its `style.css` stays empty or sets only the
  accent pairs; read `tracebi knowledge design-editorial-report`). `--layout brief` is one
  finding — `.tb-lede`, a few `.tb-kpi` cards, one chart in one `.tb-card`. A page someone
  *works in* is a dashboard: `tracebi new-dashboard "<Name>" --model <model>` writes
  `reports/<model>/<name>/` (`--model` is required with more than one model) with an `app.jsx` with a KPI
  strip, a chart beside its ranking and a filterable detail; `--html` writes it as
  `template.html` (`brief` plus a `.tb-span-8` chart beside a `.tb-span-4` detail); `tracebi init`'s sample is an `app.jsx`. A `.tb-grid` of `.tb-kpi` cells is one KPI strip: mark the page's
  number `.tb-kpi--lead` (larger, not wider), give a number its signal with a
  `.tb-kpi-delta` where the model measures a change, and give a KPI with a trend a `class="tb-spark"` line or area
  chart (the shape alone, no axes). `.tb-span-8` / `.tb-span-4` on a `.tb-grid`'s panels
  put a wide panel beside a narrow one (`.tb-span-6` halves, `.tb-span-12` the row; the
  older `.tb-cols-2` / `.tb-cols-2-1` still work as shorthands).
  `tabbed` is the same header, then `.tb-tabs` / `data-tb-tab` (Overview and Detail).
  Pick by fit — a report to read, a dashboard to work in, `brief` for one finding —
  and ask only when a person is in the loop and the choice is not obvious. Every built
  page carries the trace drawer automatically, headed with the report's name and "How
  each number was made" (the masthead's Trace link, the verdict chip, the footer's
  "How these numbers were made", or a click on a value figure opens it at that figure's row).
- Ask how it should look, once, before you build (a person in the loop; otherwise use
  the defaults): the title and where it sits, one page / top tabs / a sidebar, light /
  dark / the reader's choice, comfortable / compact. Offer the look of their last
  report first. Then on `<html>`: `data-tb-mode="dark"` or `"light"` (unset is `"auto"`, following the
  reader's system), `data-tb-density="compact"`, `data-tb-width="full"`. A sidebar is
  `<div class="tb-tabs" data-tb-nav="side">` with the whole page inside. Every page
  opens with the masthead, `<header class="tb-masthead" data-tb-title="left|center|banner|nav"
  data-tb-period="Q3 2026">`: an optional `.tb-kicker` (left out, the build adds the
  model's label), the `<h1>`, `<p
  class="tb-standfirst">`, and `<p class="tb-masthead-meta">` with `<span
  data-tb-built></span>` (the build time, from the trace; never type a date) and `<span
  class="tb-verdict"></span>`. `data-tb-period` names what the numbers cover. The runtime
  fills the meta, adds what is missing, and sets the chip's `data-tb-verdict` from the
  file itself — `draft` on a working preview, `not-checked` on a built file (nothing has
  re-run it; `tracebi verify` does); a page never makes it green (framed in the web app,
  it shows the app's re-check, which the app tells it). An empty
  `.tb-masthead-mark` takes a logo from the report's `style.css`. Every page ends with
  `<footer class="tb-footer" data-tb-methodology>` holding your sources; the build adds
  one line and "How these numbers were made", which opens the trace drawer (and the whole
  footer when the template has none). `tracebi new-dashboard "<Name>" --mode dark --density
  compact --nav side --title-at nav` writes it — for an app, mode and density go in
  `report.json` `"look"` and the sidebar and title are its own components. Looks never
  change a number.
  A report takes a house theme, a whole look: `ledger` (the default), `nightdesk` or
  `signal` (`report.json` `"theme"`, or the workspace's `tracebi.yaml` `brand: {theme:
  …}`; `tracebi theme list`). Pick a theme or use the brand, never hard-coded colours.
  Offer the house theme once, for a new report or dashboard only: when the workspace sets
  no brand.theme and the person has not named a theme, offer the three in one short line
  each (Ledger: calm, institutional, the default; Nightdesk: dark, dense, monospaced
  numbers, for a desk or ops screen; Signal: bold, big numbers, for a board pack or a
  wall screen), recommend one for what the report is for, and use Ledger if the person
  does not choose. If the workspace sets a theme, use it and say so in one line instead of
  asking. Never ask again for an existing report. The six accent presets (graphite,
  indigo, …) are deprecated. A report's own `style.css` is tokens at most:
  the accent pairs and one
  display face as `--tb-font-display` (the masthead `<h1>` and the lead number), no
  gradient, hatch, glow or resting shadow. `reports/_style.md` is the team's house style: `tracebi context`
  returns it as `house_style` — follow its Rules over the defaults. Read
  `tracebi knowledge design-dashboard-feel` (and `design-app-dashboards` for an app).
- **Brand.** The workspace's brand lives in `tracebi.yaml` `brand:` (`name`, `logo`,
  `accent`, `palette`, optional `font` and `mode`): every report and dashboard takes it,
  its charts included (`tracebi theme list` shows it). The logo and the name sit together
  as the firm mark in the masthead; the kicker stays the model's label. Never hard-code a colour in an
  `<EChart option>` or a style: a series takes the palette in order (`--tb-chart-1..8`),
  and the house chart look (`docs/reference/chart-style.md`) comes from the
  `--tb-chart-*` tokens the brand and the themes set.
- Blocks marked `data-tb-stage="exploration"` are working scratch: they render
  in dev and are DELETED at the final build.
- Styling: the shipped defaults render well with zero CSS. To restyle, set
  tokens in `reports/_theme.css` (workspace-wide) or the package's `style.css`
  (per report); later wins. `script.js` may restyle any chart via
  `tracebi.configureChart(id, patch)`, a raw ECharts option deep-merged in
  (dataZoom, brush, visualMap, markArea) — config can restyle, never
  re-source: series data always comes from the stamped bytes.
- Chart attributes: `data-tb-stack` (stack bar, barh or area series),
  `data-tb-x-title` / `data-tb-y-title`, `data-tb-unit="%"` (a suffix,
  never a rescale), `data-tb-mark="max,last"` (label a
  series' own high, low, first or last row), `data-tb-annotate="2008=Crisis;
  2020=Pandemic"` (a note at a category) and `data-tb-facet="column"` (small
  multiples on one scale). Line and area charts with 8+ categories zoom by
  dragging. None computes a number.
- Code-drawn figures: when the chart types cannot draw it (a treemap, a
  Sankey), add `"libs": ["d3"]` to `report.json`, a `data-tb-figure="custom"`
  element with a `data-tb-binding` and an id, and in `script.js`
  `tracebi.draw("fig-x", function (surface, rows, theme) { … })`. It runs once
  the data is loaded and again whenever the figure's rows change (filter,
  search, selection) or its width does; `rows` are the binding's stamped rows
  as the filters leave them, `theme` the page's tokens (`tracebi.theme()`).
  Draw from `rows` only; `tracebi.setSelection({column: value})` sets the
  page's selection from a click, as a filter would. Provenance badges pick their state
  from the manifest; a stylesheet can restyle a badge, never re-color honesty.
  Fonts and images go in the package's `assets/` folder: `url(assets/…)` in
  `style.css` and `src="assets/…"` in `template.html` are inlined as `data:`
  URIs at load, so the file stays self-contained (woff2/woff/ttf/otf,
  svg/png/jpg/webp/gif/avif; a missing file, another type, or a path outside
  `assets/` fails the load).
- Reading data in `script.js`: ALWAYS wrap it in `tracebi.ready(fn)`, never
  call `tracebi.data()` at the top level. A large-detail report embeds its
  data as Parquet and decodes it at DOM-ready, AFTER `script.js` runs, so a bare
  call returns `[]` there and rows on a small report. `ready(fn)` behaves the
  same on both.
- The embed format is chosen FOR you, per report, by size: CSV for a normal
  dashboard (small, readable as text), Parquet, decoded by the inlined page
  engine (`tracebi-calc.js`), once the data is large enough that the engine
  pays for itself. You never declare it and one
  report never mixes both. It is transport, not trust — a CSV block ships the
  fingerprinted triple verbatim, a Parquet block's shipped bytes are hashed
  exactly (`payload_sha256`), and `verify --file` checks both offline with no
  extra dependency. Only BUILDING the Parquet form needs PyArrow
  (`pip install 'tracebi[reports]'`).
- The slice: besides each binding's stamped rows, the build embeds, per fact
  the page reads, one Parquet block (`tracebi-slice-<fact>`) at the coarsest
  grain that answers every figure and every filter control (base grain when a
  measure is `nunique`, a percentile or a row expression; a mean is stored as
  its sum and count), and a `tracebi-calc-plans` block with each binding's
  calc plan. `report.json` says how much: `"embed": "required"` (the default)
  embeds that grain, `"embed": "model"` every fact at base grain with every
  dimension attribute it reaches, `"embed": "none"` nothing new (the figures
  stay as built). `"embed_budget_mb"` (default 25) caps the slice; past it the
  build fails and names the fix (remove a control or a grouping, raise the
  budget, or `"embed": "none"`). A slice holds numbers, booleans, strings and
  naive datetimes only; another type in a column the page needs fails the
  build by name. A SQL binding and a `report.py` output are never in a slice:
  they stay fixed at build.
- **The live page.** On a page built with a slice, every `data-tb-filter`
  (and `<Filter>`, `<Filter multiple>` to pick several values) writes one
  selection state, and `tracebi-calc.js` re-runs each binding's own calc plan
  over the embedded slice under it, so values, tables, charts, sparks and
  `tracebi.draw` figures all redraw; a figure's number is only ever a query
  result, here the binding's own query re-run under the selection. Options list the values present under the rest of the selection
  first, the others after a separator. The state lives in the URL hash
  (`#sel=…`), so a link opens the same view. While it is not the authored
  selection the chip reads **Local** (never green) and each trace row shows
  the plan, the selection and the slice block's `payload_sha256`. A figure
  that cannot recompute (a SQL binding, a `report.py` output, a `having` on
  `contains`) carries `data-tb-fixed` ("Fixed at build · report.py"); one
  whose fact the selected field does not reach carries
  `data-tb-unfiltered-by` ("Not filtered by Sector"). A filter on a column
  no slice carries subsets stamped rows as before. `tracebi verify <manifest>
  --local` replays every plan by the page engine and by the server.
- **Every gesture is the one selection.** On a live page a click on a bar,
  a pie slice, a line's category or a legend entry selects that value of the
  chart's x (or `data-tb-color` series) column whenever a slice carries it, no
  `data-tb-filter` needed; the same value again removes it, shift-click adds
  it (a sparkline does not select). `data-tb-select-rows` on a table (kit
  `<Table selectRows>`) makes a row click select the row's dimension values;
  `data-tb-select-rows="dim_issuer.issuer"` names the columns it writes, so a
  table can show a sector without selecting by it. The table keeps the other
  rows only for fields its own clicks wrote; a filter on the same field
  narrows it.
  `data-tb-range` with `data-tb-column` (optional `data-tb-label`,
  `data-tb-min`, `data-tb-max`, `data-tb-step`; kit `<Range column label min
  max step>`) is a range control: two handles for a number column (a fact's own
  column, such as a holding's fair value, keeps that fact's slice at base
  grain), from/to pickers for a time grain's labels; it writes `{gte, lte}`.
  A chart keeps its own field's other values and draws the ones not picked at
  reduced emphasis (cross-highlighting; its trace row says Highlights);
  `data-tb-highlight="off"` on a figure or the page root makes it narrow like
  every other figure. The selection bar (`.tb-selection-bar`) sits under the
  masthead on every live page, or where you put `<div data-tb-selection>`
  (kit `<SelectionBar />`): one chip per value with a ×, Clear, and "Download
  what I see" (each visible figure's current rows, the selection in the
  header and the file name). It is hidden as built, Escape clears it, and
  printed (or in the PDF) it is one line, "Filtered to: Sector Software", with
  " · filtered on this page" on the footer's built line. A `data-tb-download`
  taken under a selection starts "# selection: none (full binding)". A field
  is named once for the whole page, chips, notes and trace alike: its
  control's `data-tb-label` or `<label>`, else a table header or chart x
  title for the column, else the column name made readable.
  `tracebi.onSelection(fn)` hears every change as `{selection, authored,
  figures}`; `tracebi.result(id)` reads a figure's current answer.
- Methodology travels the pipeline: `contract(..., note=...)` (and per-check
  `note=`; `note:` in a `.contract.yaml`) records the transform's STATED methodology in the certificate;
  measure `description=` carries modeling intent. Add ONE
  `<footer class="tb-footer" data-tb-methodology></footer>` to the template and the build
  appends them after your own prose, behind "How these numbers were made" — an appendix of what the pipeline
  states about itself, clearly not a verified claim, never badged.

## The loop you run

```bash
tracebi new-transform "<Name>"              # ① scaffold transforms/<name>.sql +
                                            #   <name>.contract.yaml (--python: pandas)
tracebi run-transform <name>                # ① clean + sink + contract —
                                            #   runs .sql, .py or .ipynb top-to-bottom
                                            #   fresh; says which form ran
tracebi new-model "<Name>"                  # ② scaffold models/<name>.yaml (--python: a .py); edit it
tracebi migrate model models/<name>.py [--write]  # a Python model → YAML; the .py stays until you delete it
tracebi new-report "<model>/<Name>" [--layout editorial|brief|tabbed]
                                            # ③ scaffold reports/<model>/<name>/ — a report to read
                                            #   (editorial by default), in its model's folder
tracebi new-dashboard "<model>/<Name>" [--nav top|side]
                                            # ③ a dashboard to work in: an app.jsx (--html: template)
tracebi run-pipeline <model>                # ①→③ run the transform, then build the model's reports
tracebi dev <name>                          # the live loop (see below)
tracebi report status <name>                # earned state in the terminal (📌 pins)
tracebi report build <name>                 # render → output/<name>.html + manifest
tracebi verify output/<name>.html.manifest.json --contracts
tracebi schedule run <name>                 # a report.json "schedule" block: build → verify → email
tracebi serve                               # browse at http://127.0.0.1:8000
tracebi mcp config --client cursor          # snippet for another MCP client
```

`tracebi init` already wrote `.mcp.json` (Claude Code) and `.cursor/mcp.json`
(Cursor). Both run `tracebi mcp` over stdio from this folder, so your
agent's TraceBi tools are already wired. `tracebi mcp config --client
claude-code|cursor|claude-desktop` prints the snippet for another client.
`--http URL` prints the streamable-HTTP form. The Authorization placeholder
differs by client: `Bearer ${TRACEBI_MCP_TOKEN}` for Claude Code,
`Bearer ${env:TRACEBI_MCP_TOKEN}` for Cursor — never a real token. The
`--http` form is not offered for Claude Desktop (add the URL as a custom
connector under Settings → Connectors).

The gateway also ships three prompts: `author_report(question)` walks the
package loop (query, paste each `binding` object under `data.<name>`,
`build_report`, `verify_manifest`), with files or, without them, through
drafts (`start_draft(kind='reports')`, `write_draft_file`, `preview_draft`,
`publish_draft`);
`answer_question(question, model="")` reads `describe_model` (with no
model named, `list_models` first: each model's description), answers in
plain words with each number beside its fingerprint and measure, never
estimates, and builds no report unless asked; asked whether a number is
checked, it says two things, never blended: `downstream(node=
'measure:<model>:<measure>')` names the built figures that show it, each
report with its verdict and `manifest_path` for `verify_manifest`, and
`describe_table(table)`'s `contract` says whether the sink satisfied its
contract. `address_pins(report)` reads `workbench_state`, acts on each open
pin in order (in place, or as a report draft over the gateway; a pin that
doubts a number is checked with `query_model` before anything changes),
rebuilds, `verify_manifest`s the manifest, then `resolve_pin`s each with a
one-line note. `list_reports` gives each built report's `built.manifest_path`.

What breaks if a table or measure goes: `downstream(node='table:<warehouse>.<table>')`
(or `source_table:<connection>.<table>`, `measure:<model>:<measure>`) lists every
built report figure that reads it, from the builds' manifests; `model_impact` on a
what-if model draft proves it, and `delete_draft(kind, path)` drops the draft after.

**The workbench in the agent (MCP Apps).** `preview_draft`,
`workbench_state` and `build_report` declare the `ui://tracebi/workbench` app:
a host that shows MCP Apps (Claude on the web and in the desktop app) opens
the workbench in the conversation with that report or draft, live (the page
itself, each figure's status, the open pins, what you last did; it refreshes
after each `write_draft_file` or build). A pin the human makes there on a
figure lands in the report path's `pins.json` and arrives as a message
("Pinned on kpi-revenue in the draft of …"): read it with
`workbench_state(report=path, draft=true)` (no `draft` for a library
package), act on it, then `resolve_pin(..., draft=true)`. The panel only pins,
selects and asks; its two tools (`workbench_view`, `workbench_pin`) are the
panel's, not yours. Without MCP Apps you get the same results plus a link: the
draft's `url`, or `workbench_url` (the app's `/reports/<name>`; `tracebi dev
<name>` serves it).

If you cannot reach the workspace's files, draft over the gateway instead:
`start_draft`, `write_draft_file`, `preview_draft` (give the person the url it
returns), then `publish_draft` once they agree. `start_draft` of a path that is
published starts from the published copy (`from_published=false` starts empty). For a model, `model_impact(path)`
first: it re-runs the published reports that read it against the draft and lists
which move or break (or are `not_built`); `publish_draft` is refused until you
pass `accept_impact=true`, a break included. A model that names `owners` is published only by one of them or an admin: otherwise `publish_draft` is refused naming them, so draft it, show `model_impact` and ask an owner (a draft cannot add you to `owners`). Drafts live under `drafts/`
and nothing goes live until publish. `publish_draft(..., folder="finance/q3")` publishes a report into that folder; if you hold only Build there it returns `status: "requested"` and a person with Publish approves it (`list_publish_requests`, `decide_publish_request`), so tell the person it is waiting rather than publishing another way. A signed-in person also has `my-published/<their sign-in name>` (My published in the app), where they hold Publish, so `folder` there publishes directly; with no sign-in identity there is none. A folder whose `_folder.yaml` says `accepts: checkable` refuses a report whose numbers a query cannot re-run. Publish a model before a report that uses
it. A declarative model, `models/<name>.yaml` or `.json`, can be drafted this
way (writing the other form replaces the draft file); a Python model cannot.

**No model yet? Start from a connection.** A person sets up the connection
and ticks the tables agents may read (`agents: {tables: [a, b]}` in
`connections/<name>.yaml`); seven tools take it from there, in this order
(`docs/agents/sop-onboarding.md` in the TraceBi handbook walks it):

- `describe_project` (or `describe_workspace`, the same tool) — the workspace as a graph: every source, transform, table, model and report, what feeds what, and what you may read (a transform's `passport.agents.blocked` lists each `-- source:` line naming a table you may not read: no change is offered while one is there). Call it first. A table a SQL transform wrote carries `columns_from` (also on `describe_table`): the source columns each column is computed from, as DuckDB's parser proved it; `null` with a reason where it could not follow, nothing for pandas.
- `read_transform(name)` — a transform that exists: its SQL and `.contract.yaml`, its form, the tables it writes, what its last run read and its column lineage, `other_forms` (a pandas twin declaring the same contract, which a proposed change does not reach), and `change`: the call to make, or why not, naming each blocking `-- source:` line. Code, never rows.
- `list_connections` — each connection's type and the tables agents may read.
- `list_source_tables(connection)` — those tables, with columns and row estimates. A connection that cannot be reached answers `ok: false` with `reason`, `snapshots` (the committed files transforms read in a table's place, `-- source: <connection>.<table> fallback: inputs/<file>.csv`), `unread_inputs` and a `note`.
- `describe_source_table(connection, table, sample=20)` — columns, a profile and sample rows; any other table is "not found".
- `propose_transform(name, sql, contract_yaml, note, change=false)` — the SQL and its contract as a code request (`change=true` changes an existing SQL transform; it must keep writing every table a model reads, and a Python transform is a person's, through `tracebi push`). It is dry-run at once against a throwaway copy — nothing real is written, a `-- sink:` line is not sent — and `dry_run` gives each table it made (columns, rows, `state` — `new`, `changed` or `unchanged` against the warehouse — and the first 20 rows of a new or changed one), each check (`passed`, `failing_rows`), the column lineage and any error with its statement. SQL that does not parse comes back as that one error. While it fails, fix it and propose again: a failed one cannot be approved. An admin approves it and it runs once (and is committed, in a git workspace), so wait for that, then draft the model.
- `export_table(source, table, to)` — admin only: a warehouse table out to a connection or an object prefix.

**What a remote draft may hold.** A report draft takes `report.json`,
`template.html`, `app.jsx`, `style.css` and `script.js`; a model draft takes its one
`<name>.yaml` or `.json`. Nothing else is accepted: Python would run on the
server with its secrets, so it comes only through a laptop and review:
`tracebi push <paths> --server <url> --note "why"` sends report packages and
declarative models to the person's drafts and Python (transforms, pipelines,
`models/<name>.py`, connections, `report.py`) as one code request an admin
approves; data never goes.
`script.js` is different because it runs only in the reader's browser, in a
sandboxed frame with no network and no access to the app. It may draw
anything, but if it changes the text of a stamped figure the trace says
"changed on the page by a custom script" for that figure, so leave stamped
numbers to the runtime. `list_models` and `describe_model` report `draftable`
per model.

Resources: `tracebi://guide` (how to author), `tracebi://spec-schema`,
`tracebi://models/{name}`, and `tracebi://knowledge/{slug}` (one lesson
body, the same text as `tracebi knowledge <slug>`).

### The dev iteration, step by step

0. **Discovery comes first — and it has a live surface.** Before any report
   exists, run `tracebi dev` with **no name** (backgrounded — it blocks):
   it opens the web app's Data page, where the workspace feed is. While it
   serves, ANY script you run can call `tracebi.workbench.show(...)` — no
   env var needed — and the feed (*From your agent*) updates live; the
   human leaves you notes there. Your MCP work posts there too, with
   nothing to call: each `query_model` result, each build and each refusal. **Work like a notebook**: `show("## Approach\n...")`
   renders as a markdown cell (narrate the methodology as you go — the
   human can flip the feed to read top-down as a document);
   `show(df, note=...)` posts a frame excerpt with column profiles;
   `show(df, chart="bar", x=..., y=...)` sketches a real chart (bar,
   barh, line, area, pie, scatter) — iterate by re-showing, and when the
   human asks to keep one for the report, re-express it as a model-query
   binding + figure: the sketch is exploration, the figure is the claim.
   `workbench_state` (no `report`) lists the warehouse's tables, row counts,
   column profiles, and sink-contract status as transforms land, and the
   star schema taking shape as you edit `models/`; the human sees them in
   the transform's and the model's pages under Data (`tracebi dev --classic` lays
   them out beside the feed on one page). Column names of a sunk
   table come from the MCP `describe_table` tool (or `tracebi warehouse
   tables --table T`) — connector metadata, no row scan. A connector
   that raises is reported in place; the others still list. Use it before you
   write a model or an ad-hoc measure. A model that failed to
   load is listed under `skipped` with its error; fix the file and call
   again (models reload when the file changes). Pins read via the MCP
   `workbench_state` tool called with no `report`. All dev-state; no
   traces exist before the model boundary, and `show()` is a no-op the
   moment the server is down. When a session shaped the pipeline, save it:
   `tracebi session export` (add `--format md` for the git-review twin)
   writes the full feed to `explorations/<session>` — ONE living record
   that you re-export as the exploration evolves; git is its timeline —
   exploration-stamped, no trace, `verify` refuses it by name.
1. **Start the dev server — it blocks.** Run `tracebi dev <name>` in a
   background shell (or ask the human to run it and keep the tab open; the
   page is their view, not yours). It opens the web app on that report with
   Build mode on — the report beside the workbench panel — and reloads on
   every save to the package, `models/`, `transforms/`, or
   `reports/_theme.css`. (`tracebi dev --classic` is the older stdlib
   preview with its own `/__workbench` page: the fallback when the web
   extra is not installed.)
2. **Edit; the portal follows.** Work in `template.html` / `report.json` /
   `style.css` / `script.js`. Explore inside `data-tb-stage="exploration"`
   blocks — they render in dev and die at build. From `report.py`,
   `tracebi.workbench.show(title, df_or_fig, note=...)` posts exhibits to
   the workbench feed during dev and is a no-op everywhere else, so probe
   code needs no cleanup and no promotion step.
3. **Read what they point at, then the pins, before every pass.** In the
   web app's Build mode (`tracebi dev <name>` turns it on; `tracebi serve`
   with `TRACEBI_DEV_MODE=1` has the **Build** button) the human clicks a
   figure or an area of the report; the workbench beside it is where they
   watch you work: the report re-rendered each time you save, which figures
   each save changed, your exhibits, the pins you resolve, **Data** (each
   binding's model, rows × columns, the figures that read it, a few rows)
   and **Checks** (figures with no data behind them, bindings no figure
   reads, numbers typed outside figures — they point; the final build
   enforces). They instruct you in chat, and can leave a note in the
   panel's note box. `workbench_state` returns what they point at as `pointing`: a figure
   (`id`, `binding`, `cell`) or an element (`selector`, `text`, `section`).
   When they say "this" or "here", that is what they mean; there is no
   pointing when `pointing` is null, so ask. A note they leave is a pin
   ("make this top 8 sectors only"; on the `--classic` page they can also
   pin a figure). Read them
   with `tracebi report status <name>` (pins print with 📌) or the MCP
   `workbench_state` tool. Address pins first; they are the human pointing.
   A `"kind": "promote"` pin (a `→ keep:` line) is the human pressing
   **Keep this** on an exhibit (on the `--classic` page): its `request`
   says which exhibit, the code
   that produced it, and how to promote it — a model binding + figure when
   the model can express it, else `report.py` (python-derived). A
   `"kind": "message"` pin (a `→ message:` line) is the human typing in
   the note box — an instruction for you. Then resolve the pin
   with a one-line note (`tracebi report pins <name> --resolve <id>
   --note "..."`, or MCP `resolve_pin`). The workbench never
   edits the report; you do.
4. **Share a draft with `tracebi report snapshot <name>`.** One HTML with
   the exploration blocks KEPT and a review banner; it carries no manifest
   and `verify` refuses it by name — a draft can never impersonate a
   final. Use it when the human wants to look without a dev server.
5. **Publish with `tracebi report build <name>`**, then
   `tracebi verify output/<name>.html.manifest.json --strict --contracts`.
   The build strips exploration, validates every figure claim against the
   embedded bindings, and writes the manifest. `output/<name>.html` (+ its
   `.manifest.json`) is the deliverable to hand over or commit — and the
   package is already served live in the app (`tracebi serve`), in the library under its model;
   there is no separate publish step. The gateway's
   `build_report(..., format="xlsx")` also writes `<name>.xlsx` in the
   same output directory. The spreadsheet carries no trace and is not
   verifiable; the HTML and manifest are the checkable artifact.
   Pass that result's `xlsx_path` as `fetch_artifact(path=...)`; the
   workbook comes back base64-encoded. `build_report` returns `output_path`
   and `manifest_path` — pass `manifest_path` as
   `verify_manifest(manifest=...)`. A PDF
   (`tracebi report build <name> --format pdf`, or
   `build_report(..., format="pdf")`) is a print of that built HTML: its
   last pages, "How these numbers were made", print each figure's query
   and a short fingerprint, the sink contracts, the build and the
   `tracebi verify` command, but the PDF itself is not verifiable. A pdf
   build returns `pdf_path`; pass that as
   `fetch_artifact(path=...)`.

**Repeat it with a `schedule` block.** A recurring report declares when it
runs and who receives it in `report.json`:
`"schedule": {"cron": "0 9 * * MON", "timezone": "America/New_York",
"to": ["cfo@example.com"]}` (`to` optional: without it a run only rebuilds).
A `burst` block builds one copy per filter value and emails that copy to
`burst.to[value]`: `"burst": {"filter": {"dim_region.region": {"in":
["EMEA", "APAC"]}}, "to": {"EMEA": ["emea@example.com"], "APAC":
["apac@example.com"]}}`. The filter is applied at build through the same
selection filter path a kept selection uses. A value with no `burst.to`
entry is skipped and recorded, and is not sent to the top-level `to`. Each
slice is verified on its own; a refused, empty, or failed slice is not
sent, and the others still are. One owner alert names every slice that
failed, came back empty, or was refused.
The reviewer approves when and to whom in the same diff as what.
Add `"refresh": {"transforms": ["<name>"], "pipelines": ["<name>"]}` to
run those first, so the report shows fresh data; a failed step (including a
sink contract that refuses the new data) fails the run before anything is
built or sent. A failed refresh or build is retried twice, after 1 minute
and then 5 minutes, unless `"retries"` is an integer from 0 to 5 (0
disables); a build that does not verify is not retried. `tracebi schedule run <name>` runs it now (refresh → build →
verify → email → record in `tracebi_runs`, kind `schedule`; an existing `output/schedule_runs.jsonl` is imported once); a build that
does not verify is recorded `refused` and nothing is sent. When `TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` are both set, that successful send also uploads the HTML and the manifest to Slack with the report name, when it rendered, the verify verdict, and up to five headline value figures. A failed upload is recorded on the run and not retried. `--no-send` records the intent and does not call Slack. `TRACEBI_SLACK_WEBHOOK` stays a text ping. Optional `"owner"` is one email address: a run recorded `failed`, `refused`, or `empty` emails that address a plain-text alert and does not email the report to `to`. A binding a figure uses that returned zero rows is recorded `empty` and is not sent. `tracebi schedule serve` runs every
schedule until stopped; `tracebi schedule list` shows each one's last run.

`tracebi verify` is the point: it re-runs the recorded queries and confirms
every figure still reproduces. Only `REPRODUCES` means a number was re-run
and matched. `--contracts` also re-runs the sink contracts. Run it before
you tell a human a report is done.

## First moves

1. Run `tracebi context --brief` — the token-lean vocabulary tier (at most
   45% of the full payload): the semantic model, contracts, conventions and
   drafts; it names what it omitted as topics. Before you write a page, run
   `tracebi context --topic presentation` (the figure grammar, the kit,
   `report.json`; over the gateway, `get_context(topic='presentation')`).
   Nothing outside the vocabulary validates. Add `--model <name>` for one
   model's schema; drop `--brief` only when writing Python against the
   library directly.
2. Read the sample files: `transforms/sample_transform.py`,
   `models/sample_model.yaml`, `pipelines/sample_model.yaml`,
   `reports/sample_model/sample_dashboard/`. They are a complete working
   example of the loop, trace included.
3. Run `tracebi knowledge` — the analyst good-practice lessons. Read the one
   whose *when* matches your decision (`tracebi knowledge <slug>`, or over
   the gateway `tracebi://knowledge/{slug}`) before
   choosing a measure or grain: a rate is a ratio of totals not a mean of
   ratios, a "weighted" average needs a weight, pick the grain first. Doing the
   analysis *right* is the job; these catch the confident-but-wrong number.
   The `design-` lessons do the same for the page: before calling a report
   done, run `tracebi knowledge design-cut-the-chrome` and
   `tracebi knowledge design-lead-with-the-answer` — one question per page, the
   title states the finding, three to five KPIs with comparisons, no decorative
   color or emoji. Start from the shipped classes before writing CSS: `.tb-lede`
   for the answer sentence under the title, `.tb-kpi-context` for a KPI's
   comparison line (`tracebi knowledge design-theme-with-tokens` for the rest).
4. Read `README.md` for the run commands.

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

## Your own data

Already have tables? `tracebi connect <name> --kind postgres|snowflake|bigquery|duckdb`
tests the warehouse, writes the secret to `.env`, and writes
`connections/<name>.yaml`: a type and its fields, where any value may be
`${ENV_VAR}` (the whole value) and a password, or a URL that carries one,
MUST be (a literal secret is a validation error). `${ENV_VAR:-default}` adds a
default for when the name is set nowhere; it is checked like a literal, so a
password has none. The variable is read when the connection is used, never at
discovery, from the environment, then `.env`, then the workspace's encrypted
store (`tracebi secret set NAME`; `tracebi secret list` shows what is missing);
a model points at it with
`connection: <name>` in its `connectors:`. (`--python` writes the older
`models/_connections/<name>.py`; a model reads `connections/<name>.yaml`
first, then that.) `tracebi migrate connection models/_connections/<name>.py
[--write]` converts one. Then `tracebi new-model "<Name>" --from <name> --tables a,b,c`
drafts a star schema from column metadata only. Edit every line marked
`# DRAFT: review` before a report depends on it.

The query engine's limits live in `tracebi.yaml` at the workspace root
(`tracebi init` writes a commented one): `engine: {memory_limit, threads,
temp_directory, query_timeout_s}`. Every model query runs in one read-only
DuckDB connection over the warehouse that cannot open a file, a URL, an
extension or another database: a model source that reaches for
`read_csv('http://…')` is refused by DuckDB, by name. An Explore, Ask or agent
query stops at `query_timeout_s` (default 30) with an error naming the limit.
Only a transform reaches the outside world. The same file's `warehouse:`
block says where the warehouse lives: `tier: file` (the default,
`data/warehouse.duckdb`), `object` (a Parquet file per table under `s3://`,
`gs://` or a directory; `key_id` and `secret` must be `${ENV_VAR}`) or
`remote` (`md:…`). Write a model's connector as `type: warehouse` and sink a
transform to `sink_target()` (`from tracebi.project_config import
sink_target`), and both follow the tier without naming a path. Reference:
`docs/reference/tracebi-yaml.md`.

Already have dbt marts? `tracebi import dbt <path>` reads a `manifest.json`
(a dbt project root, or the file; it does not run dbt) and drafts `models/<name>.py`
the same way. `--connection <name>` wires the connection `tracebi connect`
wrote. Relationships and measures stay `# DRAFT: review` comments — foreign
keys are not invented.

## Scaffolding commands

`tracebi new-transform "<Name>"` · `tracebi new-model "<Name>"` ·
`tracebi new-report "<Name>"` · `tracebi spec schema` (the ReportSpec JSON
Schema). Discover more with `tracebi --help`.
