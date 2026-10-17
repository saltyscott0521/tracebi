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
                 YAML by default (models/<name>.yaml).
                        ── freeze: the model (the contract) ──
③  reports/      an ARTIFACT PACKAGE in a folder named for its model —
                 reports/<model>/<name>/ holding report.json (named query
                 bindings) + template.html (your page, where every figure
                 claims a binding). Builds to one self-contained HTML + a
                 manifest (the receipt).
```

A model, its transform and its reports belong together, and a **pipeline**
runs them as one: `models/<model>.yaml`, `pipelines/<model>.yaml` (`transform:`,
`models:`, `reports: all`, `schedule:`; it only names the Python transform),
`reports/<model>/`. A source is `connections/<name>.yaml`.
`tracebi run-pipeline <model>` runs the transform, then builds every report in
`reports/<model>/`, each with its receipt; the app's **Refresh data** runs the
same pipeline. A report is named by its path (`<model>/<name>`) in every
command, and builds to `output/<model>/<name>.html`. The sample is
`sample_model` — `pipelines/sample_model.py`, `reports/sample_model/`.
People read names, not identifiers: a model's `label` (optional; unset, the name
title-cased) and a report's `report.json` `name` (human, not the folder slug).

**Folder permissions.** A folder under `reports/` (a directory that is not a package) may hold a `_folder.yaml` granting `view`, `build`, `publish` and `manage` to sign-in groups or names (`docs/reference/folder-yaml.md`). With none, roles decide as before. A report in a folder you cannot view is not listed and every read of it answers as if it did not exist, so a "no such report" over the gateway can mean "not yours": do not look for it another way. A `build` or `publish` refusal names the permission it needs; ask a folder manager rather than working around it.

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

## Starter templates

`tracebi context` lists them under `templates`. `tracebi init <project>
--template saas-metrics` (also `saas_metrics`) scaffolds the SaaS metrics
starter: `inputs/subscriptions.csv`, `transforms/saas_transform.py`,
`models/saas_model.yaml` (ending MRR, logo churn, a signup-cohort cut), and
two reports — `saas_model/mrr_dashboard` (dashboard) and
`saas_model/cohort_brief` (tabbed). `tracebi init <project>
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
fixed kit — `react`, `recharts`, `lucide-react` (import icons by name),
Tailwind classes (`bg-card text-ink border-rule` follow the page's tokens)
and the `tracebi` module. No other import builds; it is still one offline
file. Show numbers through the kit — `<Kpi binding cell format label lead>`,
`<Value>`, `<Chart binding type x y>`, `<Spark>`, `<Table binding>`, with
`<Filter>`, `<Search>`, `<Download>` — and give `binding`, `cell`, `x`, `y`
literal strings: the build reads them as claims and refuses a binding or
column that does not exist. A KPI's change is a stamped figure too:
`<Kpi … deltaBinding="kpis" deltaCell="unrealized" deltaFormat="currency_compact"
deltaGood="up" context="vs cost">` shows it first on the context line with its
arrow, sign and colour (`deltaGood="down"` for costs and churn). Only where
the model measures a comparison; no comparison measure, no delta. `useBinding("name")` hands your own components
the stamped rows; a number your code computes or draws (a Recharts chart, a
sum) is the app's presentation, not a checked figure, and the page says so.
For app behaviour: `<Filter column>` with no `binding` filters the whole page
(every binding with that column; KPIs stay the stamped totals);
`<Segmented options value onChange>` picks which figure shows — a period
toggle is one literal-binding figure per option, never arithmetic; and
`useUrlState("view", "Overview")` keeps a view or period in the URL so a
shared link opens on it; while the page prints, `usePrinting()` is true and
an app with views renders all of them, so the PDF holds the whole report.
Open the page with `<Masthead title kicker period>` (children are the
standfirst; it shows the build time and the verdict chip) and end its main
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
  is optional. The build inlines D3 automatically when the page
  contains a chart figure and draws every chart type with it, in one style
  (bars carry their own values, a line ends in its last value, names wrap
  and are never cut, ticks thin to what fits; legend toggles, tooltips with
  the measure's description and a "Receipt →" link to that figure's record,
  arrow-key reading, a click on a bar or slice sets the
  page's filter control for that column). List `"echarts"` to keep the older ECharts engine; `tracebi.configureChart` patches apply only there.
- "Top N" is declarative: put `order_by` + `limit` in the binding's query.
  Never sort or slice in `script.js` — that moves ordering out of the receipt.
- `filters` is WHERE (before aggregation) — a filter on a measure changes the
  group totals. To keep only groups whose *total* clears a threshold, use
  `having` (HAVING): `"having": {"revenue": {"gte": 250}}`.
- A measure can carry its own filter, declared on the model:
  `add_measure('purchases', column='amount', agg='sum', filters={'activity_type':
  'purchase'})` (YAML: `filters:` on the measure). It restricts only that
  measure, so a query's own filters still narrow every measure; the receipt
  stamps the filter, and `verify` re-runs it.
- A report can calculate its own measures: a `"measures"` block in its
  `report.json`, keyed by model (`{"sample_model": {"big_minus_small":
  {"measure_expr": "big_orders - small_orders"}}}`), takes the model's measure
  keywords. A binding that lists one by name gets it for that query only; the
  model is not changed, and a name the model already declares is refused. The
  receipt labels these "calculated in this report". Promote one into the model
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
  name). The receipt labels it "calculated in this report (SQL)" and records the
  SQL, and `verify` re-runs it. Reach for a model measure first.
- **Scenarios are the one place a page computes.** A
  `data-tb-scenario` block lets the reader ask "what if": `data-tb-input`
  fields, a `data-tb-preset` picker (`data-tb-key`, `data-tb-fill`,
  `data-tb-default`) that fills them from a stamped row, and
  `data-tb-calc` outputs with a closed formula (`+ - * / ^`, `pmt`, `min`,
  `max`, `round`, `abs`) evaluated in the browser. It is never a figure,
  never inside or around one, and never in the receipt: the runtime labels
  it as computed from the reader's inputs, and the manifest records only
  its declaration with `verifiable: false`. Use it for a rate the reader
  remembers, never for a number a query could produce. The build checks
  every formula and preset. See `examples/portfolio_project/reports/housing_model/affordability/`.
- Interactivity: `data-tb-filter` dropdowns + `data-tb-search` inputs subset
  WHICH stamped rows a binding's tables/charts display — they never compute
  new numbers (client-side aggregation would mint numbers; value figures
  never react; a filtered KPI needs its own binding). A `selection` block
  in `report.json` (`{"model", "filters"}`) opts in: `data-tb-filter` posts
  the selection and the model recomputes every figure on it, value figures
  included. The browser displays that result. Ask reads pins, then
  resolves a question to a value one of those controls already has,
  then posts that filter tuple. A question that names one declared
  dimension the report does not already cut becomes a new binding in
  `report.json`, then a rebuild whose verdict is on the reply. A
  question that names no declared value, or names two columns, is
  refused. A number in the reply is a value figure beside its
  fingerprint. Excluded options stay visible
  and inert. The receipt names the selection and whether it is the authored
  one. `data-tb-download` stays the full stamped binding; the receipt
  downloads the sliced view and names the selection in the filename and the
  header. Offline, further slices need the model unless a sealed grain can
  recompute `simple` aggregations and `ratio`; `period_end` does not
  recompute offline. Tables scroll past
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
  *works in* is a dashboard: `tracebi new-dashboard "<Name>"` writes an `app.jsx` with a KPI
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
  page carries the Receipt drawer automatically (the masthead's Receipt button, the
  verdict chip, or a click on a value figure opens it at that figure's row).
- Ask how it should look, once, before you build (a person in the loop; otherwise use
  the defaults): the title and where it sits, one page / top tabs / a sidebar, light /
  dark / the reader's choice, comfortable / compact. Offer the look of their last
  report first. Then on `<html>`: `data-tb-mode="dark"` or `"light"` (unset is `"auto"`, following the
  reader's system), `data-tb-density="compact"`, `data-tb-width="full"`. A sidebar is
  `<div class="tb-tabs" data-tb-nav="side">` with the whole page inside. Every page
  opens with the masthead, `<header class="tb-masthead" data-tb-title="left|center|banner|nav"
  data-tb-period="Q3 2026">`: an optional `.tb-kicker`, the `<h1>`, `<p
  class="tb-standfirst">`, and `<p class="tb-masthead-meta">` with `<span
  data-tb-built></span>` (the build time, from the receipt; never type a date) and `<span
  class="tb-verdict"></span>`. `data-tb-period` names what the numbers cover. The runtime
  fills the meta, adds what is missing, and sets the chip's `data-tb-verdict` from the
  file itself — `draft` on a working preview, `not-checked` on a built file (nothing has
  re-run it; `tracebi verify` does); a page never makes it green (framed in the web app,
  it shows the app's re-check, which the app tells it). An empty
  `.tb-masthead-mark` takes a logo from the report's `style.css`. Every page ends with
  `<footer class="tb-footer" data-tb-methodology>` holding your sources; the build adds
  one line and "How these numbers were made" behind a disclosure (and the whole footer
  when the template has none). `tracebi new-dashboard "<Name>" --mode dark --density
  compact --nav side --title-at nav` writes it — for an app, mode and density go in
  `report.json` `"look"` and the sidebar and title are its own components. Looks never
  change a number. A report may name a shipped theme in `report.json` `"theme"`
  (`tracebi theme list`; each is an accent preset for both grounds, never a mode);
  a report's own `style.css` is that at most — the accent pairs and one display face for
  the masthead `<h1>` and the lead number, no gradient, hatch, glow or resting shadow;
  `tracebi theme use <name>` makes one everyone's default (`reports/_theme.css`). `reports/_style.md` is the team's house style: `tracebi context`
  returns it as `house_style` — follow its Rules over the defaults. Read
  `tracebi knowledge design-dashboard-feel` (and `design-app-dashboards` for an app).
- Blocks marked `data-tb-stage="exploration"` are working scratch: they render
  in dev and are DELETED at the final build.
- Styling: the shipped defaults render well with zero CSS. To restyle, set
  tokens in `reports/_theme.css` (project-wide) or the package's `style.css`
  (per report); later wins. `script.js` may restyle charts via
  `tracebi.configureChart` — config can restyle, never re-source: series data
  always comes from the stamped bytes.
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
  Draw from `rows` only; `tracebi.setSelection({column: value})` filters the
  page from a click. Provenance badges pick their state
  from the manifest; a stylesheet can restyle a badge, never re-color honesty.
  Fonts and images go in the package's `assets/` folder: `url(assets/…)` in
  `style.css` and `src="assets/…"` in `template.html` are inlined as `data:`
  URIs at load, so the file stays self-contained (woff2/woff/ttf/otf,
  svg/png/jpg/webp/gif/avif; a missing file, another type, or a path outside
  `assets/` fails the load).
- Reading data in `script.js`: ALWAYS wrap it in `tracebi.ready(fn)`, never
  call `tracebi.data()` at the top level. A large-detail report embeds its
  data as Parquet and decodes it in a worker AFTER `script.js` runs, so a bare
  call returns `[]` there and rows on a small report. `ready(fn)` behaves the
  same on both.
- The embed format is chosen FOR you, per report, by size: CSV for a normal
  dashboard (tiny), Parquet plus an inlined worker engine once the data is
  large enough that the engine pays for itself. You never declare it and one
  report never mixes both. It is transport, not trust — a CSV block ships the
  fingerprinted triple verbatim, a Parquet block's shipped bytes are hashed
  exactly (`payload_sha256`), and `verify --file` checks both offline with no
  extra dependency. Only BUILDING the Parquet form needs PyArrow
  (`pip install 'tracebi[reports]'`).
- Methodology travels the pipeline: `contract(..., note=...)` (and per-check
  `note=`) records the transform's STATED methodology in the certificate;
  measure `description=` carries modeling intent. Add ONE
  `<footer class="tb-footer" data-tb-methodology></footer>` to the template and the build
  appends them after your own prose, behind "How these numbers were made" — an appendix of what the pipeline
  states about itself, clearly not a verified claim, never badged.

## The loop you run

```bash
tracebi run-transform <name>                # ① clean + sink + contract —
                                            #   runs .py or .ipynb top-to-bottom
                                            #   fresh (python transforms/<name>.py
                                            #   works too for .py)
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
`build_report`, `verify_manifest`);
`answer_question(question, model="")` answers in plain words with each
number beside its fingerprint and measure, never estimates, and builds no
report unless asked; `address_pins(report)` reads `workbench_state`, acts
on each open pin in order, rebuilds, `verify_manifest`s the manifest, then
`resolve_pin`s each with a one-line note.

If you cannot reach the project's files, draft over the gateway instead:
`start_draft`, `write_draft_file`, `preview_draft` (give the person the url it
returns), then `publish_draft` once they agree. For a model, `model_impact(path)`
first: it re-runs the published reports that read it against the draft and lists
which move or break (or are `not_built`); `publish_draft` is refused until you
pass `accept_impact=true`, a break included. A model that names `owners` is published only by one of them or an admin: otherwise `publish_draft` is refused naming them, so draft it, show `model_impact` and ask an owner (a draft cannot add you to `owners`). Drafts live under `drafts/`
and nothing goes live until publish. `publish_draft(..., folder="finance/q3")` publishes a report into that folder; if you hold only Build there it returns `status: "requested"` and a person with Publish approves it (`list_publish_requests`, `decide_publish_request`), so tell the person it is waiting rather than publishing another way. A signed-in person also has `my-published/<their sign-in name>` (My published in the app), where they hold Publish, so `folder` there publishes directly; with no sign-in identity there is none. A folder whose `_folder.yaml` says `accepts: checkable` refuses a report whose numbers a query cannot re-run. Publish a model before a report that uses
it. A declarative model, `models/<name>.yaml` or `.json`, can be drafted this
way (writing the other form replaces the draft file); a Python model cannot.

**What a remote draft may hold.** A report draft takes `report.json`,
`template.html`, `style.css` and `script.js`; a model draft takes its one
`<name>.yaml` or `.json`. Nothing else is accepted: Python would run on the
server with its secrets, so it comes only through a laptop and review:
`tracebi push <paths> --server <url> --note "why"` sends report packages and
declarative models to the person's drafts and Python (transforms, pipelines,
`models/<name>.py`, connections, `report.py`) as one code request an admin
approves; data never goes.
`script.js` is different because it runs only in the reader's browser, in a
sandboxed frame with no network and no access to the app. It may draw
anything, but if it changes the text of a stamped figure the receipt says
"changed on the page by a custom script" for that figure, so leave stamped
numbers to the runtime. `list_models` and `describe_model` report `draftable`
per model.

Resources: `tracebi://guide` (how to author), `tracebi://spec-schema`,
`tracebi://models/{name}`, and `tracebi://knowledge/{slug}` (one lesson
body, the same text as `tracebi knowledge <slug>`).

### The dev iteration, step by step

0. **Discovery comes first — and it has a live surface.** Before any report
   exists, run `tracebi dev` with **no name** (backgrounded — it blocks):
   it opens the web app's Data page, where the project feed is. While it
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
   the app's Transform and Model stages (`tracebi dev --classic` lays
   them out beside the feed on one page). Column names of a sunk
   table come from the MCP `describe_table` tool (or `tracebi warehouse
   tables --table T`) — connector metadata, no row scan. A connector
   that raises is reported in place; the others still list. Use it before you
   write a model or an ad-hoc measure. A model that failed to
   load is listed under `skipped` with its error; fix the file and call
   again (models reload when the file changes). Pins read via the MCP
   `workbench_state` tool called with no `report`. All dev-state; no
   receipts exist before the model boundary, and `show()` is a no-op the
   moment the server is down. When a session shaped the pipeline, save it:
   `tracebi session export` (add `--format md` for the git-review twin)
   writes the full feed to `explorations/<session>` — ONE living record
   that you re-export as the exploration evolves; git is its timeline —
   exploration-stamped, no receipts, `verify` refuses it by name.
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
   embedded bindings, and writes the receipt. `output/<name>.html` (+ its
   `.manifest.json`) is the deliverable to hand over or commit — and the
   package is already served live in the app (`tracebi serve`), on its model's Overview;
   there is no separate publish step. The gateway's
   `build_report(..., format="xlsx")` also writes `<name>.xlsx` in the
   same output directory. The spreadsheet carries no receipt and is not
   verifiable; the HTML and manifest are the checkable artifact.
   Pass that result's `xlsx_path` as `fetch_artifact(path=...)`; the
   workbook comes back base64-encoded. `build_report` returns `output_path`
   and `manifest_path` — pass `manifest_path` as
   `verify_manifest(manifest=...)`. A PDF
   (`tracebi report build <name> --format pdf`, or
   `build_report(..., format="pdf")`) is a print of that built HTML and
   carries no receipt. A pdf build returns `pdf_path`; pass that as
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
disables); a receipt that does not verify is not retried. `tracebi schedule run <name>` runs it now (refresh → build →
verify → email → record in `tracebi_runs`, kind `schedule`; an existing `output/schedule_runs.jsonl` is imported once); a receipt that
does not verify is recorded `refused` and nothing is sent. When `TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` are both set, that successful send also uploads the HTML and the manifest to Slack with the report name, when it rendered, the verify verdict, and up to five headline value figures. A failed upload is recorded on the run and not retried. `--no-send` records the intent and does not call Slack. `TRACEBI_SLACK_WEBHOOK` stays a text ping. Optional `"owner"` is one email address: a run recorded `failed`, `refused`, or `empty` emails that address a plain-text alert and does not email the report to `to`. A binding a figure uses that returned zero rows is recorded `empty` and is not sent. `tracebi schedule serve` runs every
schedule until stopped; `tracebi schedule list` shows each one's last run.

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
   `models/sample_model.yaml`, `pipelines/sample_model.yaml`,
   `reports/sample_model/sample_dashboard/`. They are a complete working
   example of the loop, receipt included.
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
MUST be (a literal secret is a validation error). The variable is read when the
connection is used, never at discovery; a model points at it with
`connection: <name>` in its `connectors:`. (`--python` writes the older
`models/_connections/<name>.py`; a model reads `connections/<name>.yaml`
first, then that.) `tracebi migrate connection models/_connections/<name>.py
[--write]` converts one. Then `tracebi new-model "<Name>" --from <name> --tables a,b,c`
drafts a star schema from column metadata only. Edit every line marked
`# DRAFT: review` before a report depends on it.

Already have dbt marts? `tracebi import dbt <path>` reads a `manifest.json`
(a project root, or the file; it does not run dbt) and drafts `models/<name>.py`
the same way. `--connection <name>` wires the connection `tracebi connect`
wrote. Relationships and measures stay `# DRAFT: review` comments — foreign
keys are not invented.

## Scaffolding commands

`tracebi new-transform "<Name>"` · `tracebi new-model "<Name>"` ·
`tracebi new-report "<Name>"` · `tracebi spec schema` (the ReportSpec JSON
Schema). Discover more with `tracebi --help`.
