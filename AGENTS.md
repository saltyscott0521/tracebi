# AGENTS.md — Working with TraceBi as an AI Agent

Read this before touching a TraceBi workspace. Deeper references: `docs/concepts/the-three-phase-workflow.md`
(the three-phase workflow, end to end), `CLAUDE.md` (codebase rules), `NOTES.md`
(design decisions), `examples/agent_gateway/` (a complete recorded agent
session), `design/pitfalls.md` (bugs already hit here, and the rule that
prevents each: read it before changing the runtime, styles or compiler).

## What TraceBi is

TraceBi is **the trust layer for AI-generated analytics** — a code-first BI
framework where every number has a trace (see `MANIFESTO.md` for the full
identity and vocabulary canon). The mechanism is a **three-phase workflow**
that carries data from messy to reportable. Each phase is a workspace-root folder
with its own cadence, decoupled from the next by a **freeze point** — a
materialized artifact handed across the boundary:

| Phase | Folder | You write | Freeze it hands on |
|---|---|---|---|
| ① **Transform** | `transforms/` | **SQL by default**: `transforms/<name>.sql`, DuckDB statements run top to bottom in one fresh warehouse connection — read, clean, parse (`regexp_extract`), key, dedupe (`QUALIFY row_number()`), then **sink** clean star-schema tables (`CREATE OR REPLACE TABLE`, or on the object tier `COPY (…) TO '{{ sink }}/<table>.parquet'`). A derivation may stay a **sink view** (`CREATE OR REPLACE VIEW`, file and remote tiers): it reads only warehouse tables and views, and one over a `-- source:` table or a file is refused. Two placeholders only: `{{ sink }}` and `{{ root }}`. The sink contract sits beside it as `<name>.contract.yaml`. The escape hatch is pandas or polars (`tracebi new-transform --python`: notebook-shaped `# %%` cells; literal `.ipynb` works too). `tracebi run-transform` executes any form top-to-bottom fresh and reports `form: sql \| python \| notebook` | `data/warehouse.duckdb` (materialized tables) |
| ② **Model** | `models/` | a declarative `DataModel` over the warehouse — grain, keys, measures, in a few dozen lines a reviewer reads without opening the pandas above it | the model (the semantic contract) |
| ③ **Report** | `reports/` | an **artifact package**, in a project named for its model (`reports/<model>/<name>/`, named `<model>/<name>` in every command: free HTML whose figures each name a stamped binding or carry `data-tb-unverified`) — or a `ReportSpec` (JSON), which is a serialization of the same thing: `tracebi migrate spec reports/<name>.json` compiles it into the package form, and the package shadows the same-named spec at discovery | the rendered page + its lineage manifest |

**Workspace and projects.** The workspace is everything one `tracebi.yaml` covers: one warehouse, its sources, transforms and models, the brand and the default house theme (one per company). A project is one area's reports: a top-level folder under `reports/`, named for the model or models it reads (`reports/saas_model/` is the SaaS project). Models stay shared at the workspace, so two projects can read one model. Folders inside a project stay folders, and `my-published/<name>` is a person's own space, not a project. A theme is set on a report (`report.json` `"theme"`) or the workspace (`tracebi.yaml` `brand: {theme}`), never on a project. Nothing is renamed: the API and the files still say folder (`/api/folders`, `_folder.yaml`) and `describe_project` describes the workspace (`describe_workspace` is the same tool; `docs/concepts/workspace-and-projects.md`).

**Project and folder permissions.** A project or a folder under `reports/` (a directory that is not a package) may hold a `_folder.yaml` granting `view`, `build`, `publish` and `manage` to sign-in groups or names (`docs/reference/folder-yaml.md`). With none, roles decide as before. A report in a folder you cannot view is not listed and every read of it answers as if it did not exist, so a "no such report" over the gateway can mean "not yours": do not look for it another way. A `build` or `publish` refusal names the permission it needs; ask a folder manager rather than working around it.

Reference implementation, end to end, at `examples/portfolio_project/`:
`transforms/holdings_transform.sql` (+ `holdings_transform.contract.yaml`; the
same work in pandas is `holdings_transform_pandas.py`, the escape hatch) →
`models/portfolio_model.yaml` →
`reports/portfolio_model/portfolio_dashboard/` (an `app.jsx` dashboard), wired by `run_workflow.py`.
`docs/concepts/the-three-phase-workflow.md` is the full tour; read it first.

**A source outside the warehouse.** A SQL transform reads a table of a
declared connection (`connections/<name>.yaml`; `tracebi connect crm --kind
postgres` writes one) with a header line `-- source: crm.issuer_ratings`, one
per table (`-- source: crm` alone is refused). The runner loads it through the
connector before the first statement and the SQL reads `crm.issuer_ratings`;
nothing of it lands in the warehouse. `fallback: inputs/issuer_ratings.csv` at
the end of the line names a committed snapshot read only when the connection's
`${VAR}` is unset. The certificate records each load under `sources`
(`connection`, `rows`, `fingerprint`, `loaded_at`, and `source_fallback: csv`
when the snapshot stood in), and `tracebi verify --contracts` re-reads it:
`CHANGED` when the source moved since. In Python,
`load_source("crm.issuer_ratings", ROOT, fallback=...)` from
`tracebi.transforms` returns the same frame and record for
`contract(..., sources=)`. The reference workspace's `dim_rating` comes from a
Postgres CRM this way (`docs/reference/transform-sql.md`).

A model is YAML by default: `models/<name>.yaml` (`tracebi new-model` writes a
commented starter; `--python` writes the old `.py`). It loads through the same
validator as a `.json` model, a repeated key is an error, and a model is one
file (a `.py` beside a `.yaml` wins; two declarative forms of one name are both
refused). `tracebi migrate model models/<name>.py [--write]` converts a Python
model and leaves the `.py` in place until you delete it. A model draft over the
gateway may be `<name>.yaml` or `<name>.json`.

Names, not identifiers: give a model a `label` (`label: Direct Lending Portfolio`;
`DataModel(name, label=)` in Python; unset, the name title-cased) and a report a
human `report.json` `name` (`"Portfolio Overview"`, not the folder slug). People
read those; commands, bindings and URLs keep taking the identifier. A report's
`description` is one sentence for the reader, what the page shows ("Ending MRR,
customers and logo churn, month by month and by plan"); how the page is built
goes in `"notes"` or a comment, never there. The masthead's kicker is the
model's label (the build adds it when you write none); the `<h1>` is the
report's name or its finding.

A model also gets a pipeline, `pipelines/<model>.yaml` (`transform:`, `models:`,
`reports: all`, `schedule:`; it only names the transform; `.py` with
`model_pipeline(...)` still works and wins on a name clash): `tracebi
run-pipeline <model>` runs the transform, then builds every report in
`reports/<model>/`, and the app's **Refresh data** (Data, the
transform's page) runs the same. `tracebi
new-pipeline` writes YAML; `tracebi migrate pipeline pipelines/x.py [--write]`
converts. Sources are declarative too: `connections/<name>.yaml` (see below). `tracebi init` scaffolds exactly this
for `sample_model`.

The split earns its keep at the freeze points: the slow, unconstrained analysis
(①) and the fast, iterated reporting (③) never block each other, because the
model (②) is a frozen contract between them. Editing a report never re-runs
the pandas. As an agent (or analyst) you author each phase in turn: write the
phase-① transform, declare the phase-② model, author the phase-③ report spec.

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
drafts a star schema from column metadata only, as `models/<name>.yaml` (`type: warehouse`
from the workspace's warehouse, else `connection: <name>`). Edit every line marked
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

Starting from a question? `tracebi init <workspace> --template saas-metrics`
(also `saas_metrics`) scaffolds the SaaS metrics starter: ending MRR, logo
churn, and a signup-cohort cut, plus the reports `saas_model/mrr_dashboard`
and `saas_model/cohort_brief`, over a small sample that verifies.
`tracebi init <workspace> --template sales-pipeline` (also `sales_pipeline`)
scaffolds the sales pipeline starter: open pipeline value and win rate
(won deals over closed deals — a ratio of totals), cut by stage, rep, and
region, plus `sales_pipeline_model/pipeline_dashboard` and
`sales_pipeline_model/rep_scorecard`. Unknown template names are refused
with the known list. `tracebi context` lists them under `templates`. Next,
`tracebi connect` and point the model's `connection:` at it (`models/saas_model.yaml` or
`models/sales_pipeline_model.yaml`). Default `tracebi init` (no flag)
scaffolds the sample orders dashboard.

## Where the trust machinery applies — and where it does not

TraceBi is also a **trust layer for AI-generated analytics**: AI made producing
reports nearly free; believing them is the expensive part. But be exact about
the boundary. **The trust machinery governs from the model boundary onward — it
covers phases ② and ③, not ①.**

- **Phase ① (`transforms/`) is unconstrained and unverified by design.** It is
  ordinary SQL (or pandas, the escape hatch) that writes the warehouse. The framework draws the line at the
  **sink**, where the numbers become a contract you can report against. Lineage
  is *not* traced through the raw analysis, and nothing machine-checks that the
  transform's numbers are right. Phase ① is trusted the way reviewed code is
  trusted — in git — not the way a fingerprint is trusted.
- **What phase ① CAN declare is a sink contract.** Put it beside the
  transform as `transforms/<name>.contract.yaml` (`name:`, `note:`, `checks:`
  — each entry `- rows: fact_x` with its parameters beside it), or end a
  Python transform with a
  `with contract(name, warehouse=...) as c:` block (`tracebi.contracts`) —
  the same closed, declarative checks (`rows`, `unique`, `not_null`, `foreign_key`,
  `values`, `reconcile`) run as read-only SQL against the tables just sunk and
  recorded beside the warehouse with connector-path fingerprints. A failed
  check **raises**, so a broken sink never freezes quietly. At report build,
  every loaded warehouse table is classified in the manifest's
  `transform_contracts` block — `satisfied`, `stale` (re-sunk after its
  contract was checked; never reads green), or `no_contract` — and
  `tracebi verify --contracts` re-runs the declaration. The exact claim is
  **"the sink satisfied its contract"** — never "the transform was verified":
  the checks certify the landed tables' shape, not the SQL or pandas above them, and
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
`preview_draft` alike. The hand-written form below is the grammar behind it.

The package's `template.html` is ordinary HTML whose figures each claim a
binding: `data-tb-figure="value|chart|table|custom"` +
`data-tb-binding="<name>"` (values add `data-tb-cell` and optionally
`data-tb-format`; charts add `data-tb-type`/`data-tb-x`/`data-tb-y` and
optionally `data-tb-color`/`data-tb-value-format`; tables optionally
`data-tb-columns`, plus `data-tb-labels` and `data-tb-formats` to name headers
and number formats per column, e.g. `data-tb-formats="fair_value=currency0;
mark=percent"`, and `data-tb-totals="<one-row binding>"` for a totals row:
declare the same query with no dimensions, so the model computes each total
and never the browser). Three reader aids decorate or reorder stamped values
and compute nothing: `data-tb-sort` on a table makes its headers click-to-sort
(ascending, descending, back to the query's order); `data-tb-bars="col, col2"`
draws a thin proportional bar after each named numeric cell (zero at the left,
or centered when the column has negatives); and `data-tb-direction="up-good"` or
`"down-good"` on a value figure marks a bound change up or down, good or bad,
from its sign — on a KPI, as `<span class="tb-kpi-delta" data-tb-figure="value"
… data-tb-direction="up-good">` leading its `.tb-kpi-context` line. Add `tb-table--freeze` to keep a wide table's first column in
view. Tables past 500 rows render only the visible rows; printing and download still use every row. Find-in-page cannot see rows outside that window — search with `data-tb-search`. A figure with no binding carries `data-tb-unverified` —
there is no third state. Give every figure an `id`: ids are how humans
redirect you. `tracebi context` documents the full grammar in its
`presentation` block, including `presentation.layout` — the page structures
you pick by name instead of inventing one. A value figure needs a one-row
binding: its own query with no dimensions, or `order_by` plus `limit` 1.
The cell may be text, such as the top sector's name.

**A report or a dashboard? Pick by what the reader does.** Someone who
*reads* it — once, in an email, printed, at a meeting — gets a **report**:
`tracebi new-report "<Name>"` writes an editorial `template.html` — an
`<article class="tb-article">` opened by a masthead (`<header
class="tb-masthead tb-article-head">`: a `.tb-kicker`, an `<h1>` that states
the finding, a `.tb-standfirst`, a `.tb-masthead-meta` with `<span
data-tb-built>`), a `.tb-lede` with its numbers bound, `<h2>` sections of prose, `<figure
class="tb-figure">` with a `<figcaption>` that says what to see, an `<aside
class="tb-pullstat">`, a table, "What to do", and the `.tb-footer`. That
register is the default (prose in a 68ch serif column, figures at the sheet's
width, the hero on the accent): leave `style.css` empty or set only the accent
pairs, never a hero colour of its own. Someone
who *works in* it — checks it daily, switches views, drills in — gets a
**dashboard**: `tracebi new-dashboard "<Name>" --model <model>` writes
`reports/<model>/<name>/` (`--model` is required with more than one model, or
title it `"<model>/<Name>"`) with an `app.jsx` with the
title, a KPI strip with a lead, a chart beside its ranking and a filterable
detail, as `tracebi init`'s sample is; `--html` writes it as `template.html`
(`brief`, then a `.tb-span-8` chart beside a `.tb-span-4` detail). Other report layouts:
`new-report --layout brief` (one finding — `.tb-lede`, a few `.tb-kpi`
cards, one chart in one `.tb-card`) and `--layout tabbed` (the same header,
then `.tb-tabs` / `data-tb-tab`). Ask only when a person is in the loop and
the choice is not obvious. Read `tracebi knowledge design-editorial-report`
before writing a report.

**Lay it out like a dashboard.** A `.tb-grid` of `.tb-kpi` cells is one
KPI strip; mark the number the page is about `.tb-kpi--lead` (larger, not
wider) rather than a row of identical boxes; a `.tb-kpi-delta` gives a number
its signal where the model measures a change. Under a KPI with a trend, add a
`class="tb-spark"` line or area chart bound to the by-period query — the
shape alone, no axes. Lay panels on the 12-column grid: give a `.tb-grid`'s
panels `.tb-span-8` / `.tb-span-4` for a wide panel beside a narrow one
(`.tb-span-6` for halves, `.tb-span-12` for the row; `.tb-cols-2` and
`.tb-cols-2-1` still work as shorthands); a `.tb-note` straight after a card's `<h2>` is its
subtitle, and a table that ends a card runs edge to edge.

**Ask how it should look, once, before you build.** With a person in the
loop, ask in one short message: the title and where it sits (left, centred,
a banner, or at the top of a sidebar); one page, top tabs or a sidebar;
light, dark or the reader's choice; comfortable or compact. Offer the look
of their last report first ("same as `sales_book`?") and skip what they
already said. With nobody in the loop, use the defaults. Then:

- the page: on `<html>`, `data-tb-mode="dark"` or `"light"` (unset is
  `"auto"`, which follows the reader's system), `data-tb-density="compact"`, and
  `data-tb-width="full"` for a dashboard that uses the whole window;
- a sidebar: `<div class="tb-tabs" data-tb-nav="side">` with the same
  `data-tb-tab` sections, and the whole page inside it;
- the masthead, which opens every page: `<header class="tb-masthead"
  data-tb-title="left|center|banner|nav" data-tb-period="Q3 2026">` with an
  optional `.tb-kicker` (left out, the build adds the model's label), the
  `<h1>`, a `<p class="tb-standfirst">`, and a
  `<p class="tb-masthead-meta">` holding `<span data-tb-built></span>` (when
  the file was built, from its trace; never type a date) and `<span
  class="tb-verdict"></span>`, the verdict chip. `data-tb-period` names what
  the numbers cover. The runtime fills the meta and adds what is missing; it
  sets the chip's `data-tb-verdict` from the file itself: `draft` on a
  working preview, `not-checked` on a built file (nothing has re-run its
  queries; `tracebi verify` does). A page never makes it green; framed in
  the web app, the chip shows the app's re-check, which the app tells it. An empty
  `.tb-masthead-mark` takes a logo from the report's `style.css`. `nav` moves
  the masthead to the top of the sidebar;
- the footer, which ends every page: `<footer class="tb-footer"
  data-tb-methodology>` with your sources. The build adds one line (when,
  which model by its label, and that the page does not claim the numbers are
  right) and "How these numbers were made", which opens the trace drawer (a
  disclosure holds the same notes for a reader without the runtime); with no
  footer in the template it adds the whole thing.

`tracebi new-dashboard "<Name>" --mode dark --density compact --nav side
--title-at nav` writes exactly that — as an app, whose mode and density ride
in `report.json` `"look"` (an `app.jsx` has no `<html>`) and whose sidebar and
title are its own components; `new-report` and `new-dashboard --html` write
it as the template attributes above. These change how a page looks, never a number or the trace's tones.

**Brand.** A workspace's brand lives in `tracebi.yaml` `brand:` (`name`,
`logo`, `accent`, `palette`, optional `font` and `mode`): every report and
dashboard of the workspace takes it, its charts included (`tracebi theme list`
shows it). The logo and the name sit together as the firm mark in the
masthead; the kicker stays the model's label. Never hard-code a colour in an `<EChart option>` or a style: a
series takes the palette in order (`--tb-chart-1..8`), and the house chart
look (`docs/reference/chart-style.md`) comes from the `--tb-chart-*` tokens
the brand and the themes set.

**House themes.** A report or dashboard takes one of three house themes, each
a whole look (surfaces, depth, density, numerals, the chart tokens): `ledger`
(the default), `nightdesk` or `signal` (`docs/reference/chart-style.md`). The
workspace picks one in `tracebi.yaml` `brand: {theme: …}`; one report in
`report.json` `"theme"` (`--theme` on `new-report` / `new-dashboard`, `theme`
on the gateway's `start_draft`); `tracebi theme list` shows them. Pick a theme
or use the brand, never hard-coded colours. Offer the house theme once, for a
new report or dashboard only: when the workspace sets no brand.theme and the
person has not named a theme, offer the three in one short line each (Ledger:
calm, institutional, the default; Nightdesk: dark, dense, monospaced numbers,
for a desk or ops screen; Signal: bold, big numbers, for a board pack or a
wall screen), recommend one for what the report is for, and use Ledger if the
person does not choose. If the workspace sets a theme, use it and say so in one
line instead of asking. Never ask again for an existing report. The six accent
presets (graphite, indigo, midnight, ocean, plum, sand) are deprecated: a
report that names one still builds, in the house theme with that accent, and
the build says so. A theme is never a mode or a layout. A report's own
`style.css` is tokens at most:
the accent pairs (`--tb-accent` / `--tb-accent-text`, `--tb-dark-accent` /
`--tb-dark-accent-text`) and one display face as `--tb-font-display` (the
system sets it on the `.tb-masthead h1`, the lead number and the trace's
title): tokens only, no rule of its own, no gradient, hatch, glow or resting
shadow, and no second set of components. Set the pairs where a report should
differ from the workspace's accent; the reference workspace keeps a navy book, a
Signal app showcase and the affordability editorial's green on one system.
`reports/_style.md` is the team's house style — `tracebi context` and
`get_context` return it as `house_style`. Read it before you build and follow
its Rules over these defaults. Before you build, read
`tracebi knowledge design-dashboard-feel` (and `design-app-dashboards` for an
app).

**You can also have the framework build the figure for you.** Declare it in
`report.json` under `figures`, then place it in `template.html` with
`{{ figure("name") }}`:

```json
"figures": {
  "total":  {"kind": "value", "binding": "totals", "cell": "revenue",
             "label": "Revenue", "format": "currency"},
  "detail": {"kind": "table", "binding": "by_region"}
}
```
```html
<section class="my-own-card">{{ figure("total") }}</section>
```

The emitted element is byte-identical to what a spec would compile, so you
keep the whole layout, stylesheet and script while never hand-writing the
grammar. The declared name becomes the figure id (`fig-<name>`). Kinds:
`value` (needs `cell` and a one-row binding), `chart` (`chart_type`/`x`/`y`/`color`/`palette`),
`table` (`columns`/`style`) — a `custom` figure has no framework markup, so
draw it in code with `tracebi.draw` (below). It refuses the silent failures: a figure
naming an undeclared binding fails at load, and a figure declared but never
placed — or placed twice — fails the build. Hand-written figures still work
everywhere; this is sugar, not a replacement. `libs` is optional. Every
chart is drawn by Apache ECharts: the build inlines ECharts automatically when
the page contains a chart figure, and draws every chart type in one style:
bars carry their own values at their free end (none on stacks or small
multiples), a line ends in its last value, category names wrap or turn but
are never cut, and axis ticks are short. A legend that toggles series, a
tooltip on every mark (the value, the measure's description from the model,
and "Trace →", which opens the drawer at that figure), arrow-key reading,
animated updates when a filter changes, and a click on a bar or slice that
writes the page's selection. SVG by default; `data-tb-renderer="canvas"` on
one chart (`"renderer": "canvas"` on a declared figure) or
`"charts": {"renderer": "canvas"}` in `report.json` for thousands of marks (a
canvas chart prints as SVG). `tracebi.configureChart(id, patch)` in
`script.js` deep-merges a raw ECharts option into any chart (dataZoom, brush,
visualMap, markArea): it restyles and never re-sources. `"libs": ["d3"]` is
only for your own `tracebi.draw` figures; `"echarts"` is no longer a choice.

Chart attributes beyond the wiring: `data-tb-stack` (stack bar, barh or area
series in one slot), `data-tb-x-title` / `data-tb-y-title` (axis titles),
`data-tb-unit="%"` (a suffix on every value, never a rescale),
`data-tb-mark="max,last"` (circle and label a series' own high, low, first or
last row), `data-tb-annotate="2008=Financial crisis; 2020=Pandemic"` (a dashed
rule and note at a category) and `data-tb-facet="dim_fund.fund"` (small
multiples on one shared scale). Line and area charts with 8 or more categories
zoom by dragging across the plot. None of them computes a number: a mark labels
a row's own value, and a stack lays rows end to end with no total written.

**Code-drawn figures (d3).** When the chart types above cannot draw what the
page needs (a treemap, a Sankey, an annotated waterfall), write it: put
`"libs": ["d3"]` in `report.json`, a `<div data-tb-figure="custom"
data-tb-binding="…" id="fig-…">` in the template, and in `script.js`:

```js
tracebi.draw("fig-flows", function (surface, rows, theme) {
  var svg = d3.select(surface).append("svg");   // surface: an empty div, cleared each call
  // rows: the binding's stamped rows as the page's filters leave them
  // theme: {ink, muted, rule, bg, accent, font, palette, …} from the page's tokens
});
```

`fn` runs once the data is loaded and again whenever the figure's rows change
(a filter, the search, a selection) or its width does, so the figure follows
the theme and the page's controls with no wiring of its own. Draw from `rows`
only; `tracebi.setSelection({column: value})` filters the page from a click.
The portfolio book's issuer table (`portfolio_book/script.js`) is the worked example.

**Custom fonts and images.** Fonts and images go in the package's `assets/` folder: `url(assets/…)` in `style.css` and `src="assets/…"` in `template.html` are inlined as `data:` URIs at load, so the file stays self-contained (woff2/woff/ttf/otf, svg/png/jpg/webp/gif/avif; a missing file, another type, or a path outside `assets/` fails the load). The editorial showcase
(`examples/portfolio_project/reports/housing_model/affordability/`) uses it for its
one display face (Fraunces, with its licence beside it); the reference
workspace's `reports/wealth_model/aum_by_branch` for its faces and its hero
artwork.

Three rules that keep pages honest:

- **Bind prose numbers.** Any element works as a value figure — a `<span>`
  mid-sentence included — so when you are asked to "explain the results",
  bind the numbers in your sentences instead of typing them. Narrative
  prose is where unverified numbers usually hide; here the honest path
  costs one attribute, and each bound span is a verified figure in the
  manifest.
- **"Top N" is declarative.** Put `order_by` + `limit` in the binding's
  query — never sort or slice in `script.js`, which moves ordering out of
  the trace.
- **Reading data in `script.js` goes through `tracebi.ready(fn)`.** Never
  call `tracebi.data()` at the top level: a large-detail artifact decodes
  its data at DOM-ready, AFTER `script.js` runs, so a bare call returns `[]`
  there and rows on a small report. `ready(fn)` behaves the same on both.
- **The embed format is chosen for you, per artifact, by size.** CSV for a
  normal dashboard (small, readable as text); Parquet, decoded by the
  inlined page engine (`tracebi-calc.js`), once the data is large enough
  that the engine pays for itself. You never declare it, and one artifact never mixes both.
  It is transport, not trust: a CSV block ships the fingerprinted triple
  verbatim, a Parquet block's shipped bytes are hashed exactly
  (`payload_sha256`), and `verify --file` checks both offline — the Parquet
  check needs no extra dependency at all. Only BUILDING the Parquet form
  needs PyArrow (`pip install 'tracebi[reports]'`).
- **The slice: what a built page carries to recompute.** Besides each
  binding's stamped rows, the build embeds, per fact the page reads, one
  Parquet block (`tracebi-slice-<fact>`) at the coarsest grain that answers
  every figure and every filter control (base grain when a measure is
  `nunique`, a percentile or a row expression; a mean is stored as its sum
  and count), and a `tracebi-calc-plans` block with each binding's calc
  plan. `report.json` says how much: `"embed": "required"` (the default)
  embeds that grain, `"embed": "model"` every fact at base grain with every
  dimension attribute it reaches, `"embed": "none"` nothing new (the figures
  stay as built). `"embed_budget_mb"` (default 25) caps the slice; past it
  the build fails and names the fix (remove a control or a grouping, raise
  the budget, or `"embed": "none"`). A slice holds numbers, booleans,
  strings and naive datetimes only; another type in a column the page needs
  fails the build by name. A SQL binding and a `report.py` output are never
  in a slice: they stay fixed at build. The manifest records each block's
  `payload_sha256` under `slice`.
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
- **Interactivity recomputes by query, never by arithmetic.** The rule
  is that a figure's number is only ever a query result. On a live page (the
  default) a `data-tb-filter` recomputes every figure it reaches by re-running
  each binding's plan (above); on a page built with `"embed": "none"` the
  controls — `data-tb-filter` dropdowns, `data-tb-search`, scrollable tables
  (`data-tb-rows`, default 10), tabs (`data-tb-tab`), `.tb-cols-2/3`
  layouts — only subset WHICH stamped rows tables and charts display, and
  value figures never react: summing the rows on screen would be a number no
  query produced. `data-tb-download` is always the FULL binding, never the
  filtered view — the stamped CSV verbatim on a CSV artifact, that same data
  re-serialised on a Parquet one. A `selection` block on `report.json` sets
  the AUTHORED selection: the state the page opens in and the build's trace;
  `verify` re-runs the authored filters. Binding filters always apply; the
  selection wins on the same target. `having`, `order_by`, and `limit` stay
  on the binding. Ask on the desk reads pins, then resolves a question to a value one of those
  controls already has ("software" becomes the sector filter), then
  posts that tuple. A question that names one declared dimension the
  report does not already cut becomes a new binding in `report.json`,
  then a rebuild whose verdict is on the reply. A question that names
  no declared value, or names two columns, is refused. A number in
  the reply is a value figure beside its fingerprint. The trace drawer downloads the sliced view and names the selection in the filename and
  the header. In the web app the report's header shows the page's state too:
  **Local** and a chip per selected field ("Sector: Technology ×") that
  clears it. Download buttons take `data-tb-label` for their text.
  Every artifact also carries the trace drawer, headed with the report's name
  and "How these numbers were made" (opened from the masthead's Trace link or
  verdict chip, a click on a value figure, a chart tooltip's "Trace →", or
  the footer's "How these numbers were made"): per figure its value,
  definition, query in one line and fingerprint, raw detail behind "Raw";
  the sink contracts name who wrote each table (its transform) and what
  that run read ("crm.issuer_ratings — snapshot inputs/issuer_ratings.csv",
  the input files). Printed (and in a PDF) it is a compact appendix: one
  row per figure (label, query in one line, short fingerprint), the sink
  contracts, the build time and git SHA, the `tracebi verify` command, no
  raw JSON. The manifest remains the trace of record. Methodology ships
  via ONE `<footer class="tb-footer" data-tb-methodology>` — the build
  appends the pipeline's stated methodology after your own prose, behind
  "How these numbers were made".
  `examples/portfolio_project/reports/housing_model/affordability/` is the
  maintained editorial showcase of all of it (the template lane);
  `portfolio_model/portfolio_showcase/` is the app lane's (`app.jsx`).
- **Explore inside the artifact.** Blocks marked
  `data-tb-stage="exploration"` render under `tracebi dev` and are deleted
  at the final build; the app's Build panel shows the data each binding reads,
  the checks on the report, and the pins and notes a human left for you (also
  via `tracebi report status` and the MCP `workbench_state` tool).

**Pointing.** `tracebi dev <name>` opens the web app on that report with Build
mode on (the server runs with `TRACEBI_DEV_MODE=1`, on loopback only; on
another report the human clicks **Build**): the workbench opens beside the
report, and a click on a figure or an area is
what they point at. Read it with the MCP `workbench_state` tool: `pointing`
is a figure (`id`, `binding`, `cell`) or an element (`selector`, `text`,
`section`), and is what "this" or "here" means in their message. They give
you instructions in chat; the panel's note box leaves you a note too, which
you read as an open `message` pin. The pane is how they watch you
work, live: the report re-rendered each time you save the package, a timeline
of which figures each save changed (they can flip back to the version before),
your `show()` exhibits, and the pins you `resolve_pin` (with your note). It
also lists **Data** (each binding: its model, rows × columns, the figures
that read it, a few rows) and **Checks** (figures with no data behind them,
bindings no figure reads, numbers typed outside figures — they point; the
final build enforces). It
is dev-state only: it never reaches a build or a trace, and when
`pointing` is null they are pointing at nothing, so ask.
`tracebi dev --classic` is the older stdlib preview server with its own
`/__workbench` page: the fallback when the web extra is not installed.

And the iteration protocol itself: `tracebi dev <name>` **blocks** — run it
in a background shell (or let the human keep it open; the app is their
view). Then edit and save; the watcher re-renders. Before every editing
pass, read the pins (`tracebi report status <name>` — 📌 lines — or MCP
`workbench_state`): a pin is a note the human left (on a figure on the
`--classic` page, or in the app's note box), and
it comes first. A pin with `"kind": "promote"` is the human pressing **Keep
this** on an exhibit (on the `--classic` page): its `request` field (a `→ keep:` line in `report
status`) says which exhibit, the code that produced it, and what to do —
re-express it as a model binding + figure when the model can, else in
`report.py` (python-derived) — then resolve the pin with a one-line note
(`tracebi report pins <name> --resolve <id> --note "..."`, or MCP
`resolve_pin`). A `"kind": "message"`
pin (a `→ message:` line) is the human leaving a note in the note box:
treat it as an instruction, then resolve the pin with a one-line note. The workbench never
edits the report; you do. `tracebi report snapshot <name>` shares a draft (exploration
kept, review banner, no manifest — `verify` refuses it by name). Publishing
is `tracebi report build <name>` + `tracebi verify … --strict --contracts`:
the built `output/<name>.html` + its manifest is the deliverable, and the package
is already served in the app, in the library under its model — there is no separate publish step.
A PDF (`tracebi report build <name> --format pdf`, or
`build_report(..., format="pdf")`) is a print of that built HTML and carries
no trace. A pdf build returns `pdf_path`; pass that as
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

The workbench starts BEFORE the report exists. `tracebi dev` with **no
name** opens the app's Data page, with the **workspace feed** — the live
surface for phase ① and ②: while this server is up,
`tracebi.workbench.show(df, note=...)` from ANY script you run (a transform
probe, a scratch analysis) posts the frame to the feed (the app's Data page, under
*From your agent*) with no configuration, and the human leaves you notes there.
Your gateway work lands there too, with nothing to call: each `query_model`
result as a table, and each `build_report` / `render_report_spec` as one
line, refusals included — so the human watches you work
(MCP: `workbench_state` with no `report` returns the feed and pins, plus
the warehouse's tables with row counts and contract status as sinks land,
and the models' star schemas taking shape as you edit `models/`). The human
browses the warehouse under Data › Warehouse (each table on its own page) and
the model on its page under Data › Models; `tracebi dev --classic`
lays the Warehouse, Models and
Packages
panels out beside the feed on one page. Interrogate in the
open — excerpts and visuals in the app, not buried in chat — then
scaffold the package and `tracebi dev <name>` continues into the figure loop
in the same app. Everything is dev-state: no traces are minted before the
model boundary.

When a session shaped the pipeline, SAVE it: `tracebi session export`
writes the full feed chronologically to `explorations/<session>` — ONE
living record per session, not a dated diary: re-export as the exploration
evolves and git carries its timeline (per-exhibit source-script provenance
included) —
`--format md` for the git-review twin, HTML for fidelity. The record is
exploration-stamped and carries no trace; `verify` refuses it by name.
The distillation ladder: session record → contract notes → the report's
methodology appendix.

## Do the analysis right — the knowledge base

Producing *a* number is easy; producing the *right* one, clearly, is the job.
The framework ships a curriculum of analyst good-practice so any agent behaves
like a senior analyst, not just a query typist. **Reach for it whenever you
choose a measure, a grain, or a model** — the guidance for the decision you are
making is one command away:

- `tracebi knowledge` — list the lessons (each with a *when* to reach for it).
- `tracebi knowledge <slug>` — read one in full; the same set rides in
  `tracebi context` under `analyst_knowledge`. Over the gateway that index
  is `get_context`'s `analyst_knowledge.lessons`, and the body is the
  `tracebi://knowledge/{slug}` resource (not an extra tool).

The ones you will use constantly: **ratio-of-totals** (a rate is a ratio of
summed totals, never a mean of per-row ratios — `agg="mean"` on a rate is almost
always wrong), **weighted-vs-plain-mean** (a "weighted average" with `agg="mean"`
underneath is a lie — a weighted mean is a ratio whose numerator carries the
weight), **grain-and-fanout** (pick the grain first; the fanout guard refusing
your query means your grain is wrong), and **verify-your-own-work** (close the
loop yourself before claiming a number). Skill-aware agents can activate the
same discipline as the **`tracebi-analyst`** skill. Silent-wrong output — a
confident, well-formatted, wrong number — is TraceBi's cardinal sin; the
knowledge base exists to help you catch it before a reader does.

**The same knowledge base covers report design.** The lessons whose slugs start
`design-` are for the page, not the number: **design-lead-with-the-answer** (one
question per page; the title states the finding), **design-kpis-with-context**
(three to five KPIs, each with a governed comparison), **design-choose-the-chart**,
**design-color-with-meaning**, **design-format-for-reading**,
**design-fewer-columns** (about five columns, `data-tb-search` first),
**design-plan-every-state**, **design-cut-the-chrome** (the telltale marks of
a generated report), **design-show-the-difference** (chart the variance, not two
lines to subtract), **design-honest-axes**, **design-layout-by-importance**,
**design-consistency-over-variety**, **design-accessible-by-default**,
**design-hierarchy-and-emphasis** (one loud element per view),
**design-grid-and-spacing** (the layout classes and the `--tb-space-*` scale),
**design-tables-that-read**, **design-words-on-the-page** (titles state
findings, labels carry units, controls get a `<label>`) and
**design-theme-with-tokens** (restyle through `--tb-*` tokens in
`reports/_theme.css`, never a fork). The shipped stylesheet already bakes much
of this in — `.tb-lede` for the answer sentence under the title,
`.tb-kpi-context` for a KPI's comparison line, `.tb-good` / `.tb-bad`, visible
focus, right-aligned tabular numbers — and a value figure with no
`data-tb-format` is formatted like a table column. Reach for them whenever you write `template.html` or
`style.css`; skill-aware agents get the same review as the
**`tracebi-designer`** skill. Presentation never changes a number — restyle
freely, never re-source.

## The two planes rule

**Change the contract in git. Use the contract over MCP.**

- **Definition plane** (git): `transforms/*.sql` (and `*.py`), `models/*.yaml`
  (and `*.py`), `reports/*` (specs, packages, and factories; plus
  `pipelines/*.yaml`). Every phase is authored and code-reviewed here. Missing a
  measure? The fix is a code-reviewed edit to the model file (e.g. a
  `measures:` entry in `models/portfolio_model.yaml`) — never a workaround in
  the report layer.
  A measure can carry its own filter (`add_measure('purchases', column='amount',
  agg='sum', filters={'activity_type': 'purchase'})`, or `filters:` in the YAML):
  it restricts that measure only, and the trace stamps the filter.
  A measure can carry a `label` (`label: Share of fair value` in the YAML, or
  `add_measure(..., label=...)`): the name people read in the app. Without one
  the app humanises the identifier; queries still name the measure by it.
  The model is the semantic layer: `description`, `synonyms` and `questions` are its agent vocabulary (`describe_model` returns them; match a person's word to a synonym, then query the identifier).
  A report can also calculate its own measures: a `measures` block in its
  `report.json`, keyed by model, takes the model's measure keywords. They serve
  that report's bindings only, the model is not changed, and the trace labels
  them "calculated in this report". Promote a reused one into the model through
  review.
  A report can also run a SQL calculation the model cannot express (a rollforward,
  a running total): a `sql_calculations` block in its `report.json`, keyed by model
  (`{"sample_model": {"running_revenue": "SELECT region_id, order_date,
  SUM(revenue) OVER (PARTITION BY region_id ORDER BY order_date) AS running_revenue
  FROM fact_orders"}}`), bound as `"data": {"running": {"model": "sample_model",
  "sql": "running_revenue"}}`. It is one read-only SELECT over the warehouse's own
  table names; a write, ATTACH, COPY, PRAGMA, or a second statement is refused when
  the report builds. `{{ measure('revenue') }}` inside it expands to a model measure
  (simple and filtered measures only; other kinds are refused by name). The trace
  labels it "calculated in this report (SQL)" and records the SQL; `verify` re-runs
  it. Reach for a model measure first.
  Missing a *column the measure needs*? That is a phase-① change: sink it in the
  transform. A fresh gateway process sees new vocabulary on its next call (stdio
  one-shot clients get this for free; a long-running server must be restarted —
  Python module caching keeps the old model loaded).
- **Access plane** (MCP): read-and-compute only, and only from the model
  boundary onward. Queries, validation, and spec rendering persist nothing
  beyond an output file. Phase ① never runs over the gateway — it writes the
  warehouse — so an agent reads one (`read_transform`) and proposes a new one
  or a change (`propose_transform`): it is dry-run against a throwaway copy at
  once, and runs for real once an admin approves it. Pipeline
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
`pip install 'tracebi[mcp]'`. `tracebi init` writes `.mcp.json` (Claude
Code) and `.cursor/mcp.json` (Cursor), both running `tracebi mcp` over
stdio from the workspace folder. `tracebi mcp config --client claude-code|cursor|claude-desktop`
prints the snippet for another client; `--http URL` prints the
streamable-HTTP form. The Authorization placeholder differs by client:
`Bearer ${TRACEBI_MCP_TOKEN}` for Claude Code, `Bearer ${env:TRACEBI_MCP_TOKEN}`
for Cursor — a placeholder, never a token. The `--http` form is not offered
for Claude Desktop (add the URL as a custom connector under Settings →
Connectors). Register by hand with Claude Code:
`claude mcp add tracebi -- tracebi mcp`. Work is attributed as
`mcp:<TRACEBI_MCP_ACTOR>` (default `mcp:agent`).
With `TRACEBI_MCP_LOG=1` the gateway also keeps a local call log
(`.tracebi/gateway_log.jsonl`: tool, ok or error, duration, argument names —
never values); `tracebi agent log` summarizes it.
The http transport requires `TRACEBI_MCP_TOKEN` (send
`Authorization: Bearer <token>`) — it refuses to start without it unless
`--insecure` is passed explicitly.

Twenty-seven tools (`tracebi/mcp_server.py`):

| Tool | Purpose |
|---|---|
| `get_context` | Full vocabulary: section/chart types, DataSet verbs, measure kinds, filter operators; `model=<name>` adds that model's schema. **Call first**, with `brief=true`: the lean tier (at most 45% of the full payload) for discovering, querying and drafting. It leaves out the sections `brief.omitted` names; `topic=<name>` returns one of them alone — `topic='presentation'` (the `data-tb-*` figure grammar, the kit, `report.json`) before you write a page. `tracebi context --brief` / `--topic <name>` on a shell |
| `list_models` | Workspace models, each with its `description` (pick the model a question is about here), tables, facts, dimensions, measures. A model that failed to load is listed under `skipped` with its error; fix the file and call again (models reload when the file changes). |
| `describe_table` | Column names and types of a warehouse table, from connector metadata (`table`, optional `connector`). Omit `table` to list tables. Never returns rows. A connector that raises is reported in place (`error`: exception type plus the first message line); the others still list. Learn column names here before writing a model or an ad-hoc measure. With a `table`, `contract` is its sink-contract status now (`satisfied`, `stale` or `no_contract`, with `writer`, the transform that wrote it, its `checks` and `checked_at`): "the sink satisfied its contract", never "the number was verified". The CLI is `tracebi warehouse tables`. |
| `describe_model` | One model's full schema |
| `query_model` | Star-schema query → stamped result. `measures` is declared measure names (ratios included) or `{column: agg}` (`sum, count, mean, min, max, nunique`); dimensions are `dim_name.attribute`; `filters` take equality, lists (IN), or operator dicts (`gte`, `between`, `contains`, …) and are **WHERE** — applied before aggregation, so a filter on a measure changes the group totals; `having` is **HAVING** — same spellings on aggregated result columns (measures, ratios), so `having={'revenue':{'gte':250}}` keeps groups whose *total* clears 250 with totals intact; `order_by` (`{column, desc}` or `'-col'`) + `limit` express "top N" (limit **requires** order_by); `preview_rows` caps transport only |
| `validate_report_spec` | Check a spec against the models without loading a row; errors carry a path like `sections[0].data.query.fact` — repair and retry |
| `render_report_spec` | Validate, build, render to self-contained HTML + lineage manifest; **refuses invalid specs** |
| `list_reports` | Per-file discovery status, without the reports in folders you cannot view. A report that has been built carries `built`: `{output_path, manifest_path, built_at}`, its last build (pass `manifest_path` to `verify_manifest`). A bare `tracebi mcp` process scans the library itself |
| `workbench_state` | The workbench state for an artifact package: figures with provenance, coverage, per-binding cards, the human's **pins**, the exhibit feed, and `pointing` (what the human is pointing at right now: "this") — read it to see what the human flagged in the app before your next edit. Open pins only; `resolved_count` is how many have been resolved |
| `resolve_pin` | Move one open pin into the resolved list in `pins.json` (`report`, `pin_id`, `note`). Writes only that file — never the report or the warehouse. A write, like `build_report` |
| `build_report` | The **publish step for the package lane**: `build_report(report=...)` builds `reports/<name>/` to one self-contained HTML + manifest (exploration stripped, every figure claim validated). Returns `output_path` (the HTML) and `manifest_path` — pass `manifest_path` as `verify_manifest(manifest=...)` and `output_path` as `fetch_artifact(path=...)`. Also returns the figure records, embedded fingerprints, and the `transform_contracts` join (per table its `status`, `writer`, `transform`, `checks`, `checked_at`; the manifest keeps what each run read); writes only its own artifact and manifest. `format="xlsx"` also writes `<name>.xlsx` and returns `xlsx_path` (pass that as `fetch_artifact(path=...)`). The spreadsheet carries no trace and is not verifiable; `spreadsheet_note` points at the HTML and manifest, which stay the checkable artifact. `format="pdf"` also writes `<name>.pdf` and returns `pdf_path` (pass that as `fetch_artifact(path=...)`). The PDF is a print of that built HTML; its last pages, "How these numbers were made", print each figure's query in one line and a short fingerprint, the sink contracts, the build time and git SHA, and the `tracebi verify` command, but the PDF itself is not verifiable; `pdf_note` points at the HTML and manifest |
| `fetch_artifact` | Read back an artifact a render or build tool wrote. The argument is `path`: `build_report`'s `output_path` or `manifest_path`, `render_report_spec`'s `html_path` or `manifest_path`, `build_report`'s `xlsx_path`, or `build_report`'s `pdf_path`. HTML and JSON come back as text. An `.xlsx` or a `.pdf` comes back base64-encoded (`encoding="base64"`) with its media type. Every other suffix stays refused |
| `verify_manifest` | Re-run every recorded query in a rendered manifest. The argument is `manifest`: pass `build_report`'s `manifest_path` (or `render_report_spec`'s `manifest_path`). Classifies `reproduces` / `source_drift` / `model_changed` / `unexplained` / `unverifiable`. Read the report-level `verdict`, not just `ok`: only `reproduces` means a number was re-run and matched — and it names any sections it could not check, so read `verdict_detail` too. `nothing_to_verify` (no data-bearing section — a broken manifest) and `refused_newer_schema` (written by a newer tracebi; not read at all) are not ok; `unverifiable` (every section hand-transformed) is ok but proves nothing |
| `list_drafts` | Your drafts under `drafts/<owner>/`: kind, path, url, and whether each differs from what is published |
| `start_draft` | Create a draft: `kind` is `reports` (a package) or `models` (one `models/<name>.yaml` or `.json`). A path that is published starts as a copy of the published one (`from_published` defaults to that; `false` starts empty); a new path starts empty. A published report with a `report.py` cannot be drafted remotely. Returns the draft's url |
| `read_draft` | The draft's files as `{name: text}` |
| `write_draft_file` | Replace one file of a draft with `content`. A report draft takes `report.json`, `template.html`, `style.css` or `script.js`; a model draft takes its `<name>.yaml` or `<name>.json` (writing the other form replaces it). Writes only under `drafts/` |
| `preview_draft` | Render the draft in memory against the published models plus your draft models. Returns `ok`, `errors`, and the url where the person sees it. Writes nothing |
| `delete_draft` | Delete one of your drafts (`kind`, `path`): its files under `drafts/` only; the published copy is unchanged. To start over, or to drop a what-if draft once `model_impact` has answered |
| `model_impact` | For a model draft (`path` = the model name): re-run the recorded queries of every published report that reads it against the draft and compare with each report's last build. Each report is `unchanged`, `moves` (figures, old and new), `breaks` (the error) or `not_built` (listed, never unchanged). Writes nothing |
| `publish_draft` | Validate and publish: a report must render against the published models, a model must compile. Keeps the version it replaces under `.tracebi/history/` and records a `publish` run. Changes what the app serves, so get the person's go-ahead first. A model that would move or break published reports is refused (`ok: false`, with `impact`) unless you pass `accept_impact=true`; a break needs accepting too, and the accepted impact is recorded in the run. A report goes to `folder` (a library path, created if needed; default its own path). With only Build on that folder the answer is `status: "requested"`: a request for someone with Publish there. A folder that `accepts: checkable` refuses a report whose numbers a query cannot re-run |
| `list_publish_requests` | Requests to publish a draft into a folder: yours, and those into folders where you hold Publish. `status` filters (`pending`, `approved`, `rejected`) |
| `decide_publish_request` | Approve (publishes what was requested, recording who approved and when) or reject (`note` required) a pending request. Needs Publish on the destination now; you cannot decide your own. Get the person's go-ahead first |
| `describe_project` (or `describe_workspace`, the same tool) | The workspace as a graph: every source, transform, table, model and report, what feeds what, and what you may read. The same graph as `GET /api/graph` and the app's Data overview, less the fields only the map draws (`lane`, `chip`, `sub`, `open`). A transform's `passport.agents` says whether you may propose a change; when a `-- source:` line names a table you may not read, `blocked` lists each such line and no change is offered. Call it first on a workspace you have not seen. For a table a SQL transform wrote, `columns_from` (also on `describe_table`) says which source columns each column is computed from, as DuckDB's parser proved it (`edge_facts` draws them); `null` with a reason where it could not follow, nothing for pandas |
| `downstream` | Every built report figure that depends on `node`: `table:<warehouse>.<table>` or `source_table:<connection>.<table>` (`describe_project`'s ids), or `measure:<model>:<measure>`, read from each report's last build (a figure counts only when its binding's query loaded the table, or asked for the measure or one defined from it). Each report carries its figures (with what the page printed), `manifest_path` and `trust`, its verify verdict (re-run here unless one is kept); `not_built` lists reports that read it with no build. "What breaks if this goes" from the builds, and "which report shows this number"; `model_impact` on a what-if model draft proves it. The same answer as the app's Depends on this (`GET /api/graph/downstream`). Writes nothing |
| `list_connections` | The workspace's connections (`connections/<name>.yaml`), each with its `type` and `agent_tables`: the tables a person allowed agents to read (`agents: {tables: [a, b] \| "*"}`; none when absent). Credentials are never shown |
| `list_source_tables` | One connection's allowed tables, with columns and row estimates. Other tables are not listed. A connection that cannot be reached answers `ok: false` with `reason` (and `variable`), `snapshots` (the committed files the transforms' `-- source:` lines read in a table's place, `fallback: inputs/<file>.csv`), `unread_inputs` (files in `inputs/` no transform reads yet) and a `note` on what you can do meanwhile; `describe_source_table` answers the same |
| `describe_source_table` | One allowed table: columns, a profile, and `sample` rows (default 20, at most 500). A table agents may not read is "not found", as a missing one is |
| `read_transform` | One transform in `transforms/` (`name`): its file `text` and `contract_yaml`, its `form` (sql, python, notebook), the `tables` it writes, `last_run` (when its sink last satisfied its contract, and the `sources` that run read, each with `method` and `snapshot`) and its column `lineage` (SQL only), `other_forms` (another file of the same transform, such as a pandas twin declaring the same contract: a proposed change does not reach it, and `propose_transform`'s note says so), and `change`: the `propose_transform` call to make, or, while a `-- source:` line names a table agents may not read, why not, naming each such line. A name not in `transforms/` is "not found". Code, never rows |
| `propose_transform` | `transforms/<name>.sql` + `<name>.contract.yaml` as one code request (`name`, `sql`, `contract_yaml`, `note`; `change=true` for a change to an existing SQL transform, diffed against the published files on review). Checked first: SQL that parses (when it does not, that is the only error returned), the name, every `-- source:` a table you may read, a contract with at least one check; a change must keep writing every table a model reads (else refused naming the model and table: change the model first as a draft), and a Python transform is refused (a person changes it with `tracebi push`). Then it is **dry-run** once against a throwaway copy — a scratch DuckDB, the warehouse attached READ_ONLY, the `-- source:` tables loaded as the real run loads them, external access locked, a `-- sink:` line and `COPY` not run — and `dry_run` says per created table its columns, rows, `state` against the warehouse's table of that name (`new`, `changed` or `unchanged`) and, for a new or changed one only, its first 20 rows (`sample`), per check `passed` and `failing_rows`, the column lineage, `elapsed_ms` and any error with its statement. Nothing real is written. A proposal whose dry run fails is stored but cannot be approved: fix it and propose again. An admin approves it at `review_url`; approving runs it once and, in a git workspace, commits exactly its files (you as author, a `TraceBi-Request` trailer, never pushed). `docs/agents/sop-onboarding.md` walks connection → transform → model → report |
| `export_table` | Admin: write a warehouse table or view (`source`, `table`) to `to`, a connection's name or an object prefix (`<prefix>/<table>.parquet`). Records an `export` run. Get the person's go-ahead first |

Every tool returns **structured output** (a typed `outputSchema` and
`structuredContent`, not JSON inside a text blob), so the stamp and the verdict
arrive machine-typed. The read tools carry a `readOnlyHint` **annotation** — the
"read-and-compute only" promise, visible in the protocol before you call.

### Resources and prompts

The gateway also exposes reference material as MCP **resources** — pull them
into context rather than guessing:

- `tracebi://guide` — the authoring rules (this SOP, on the surface itself).
- `tracebi://spec-schema` — the ReportSpec JSON Schema. Read it before writing
  a spec instead of guessing the grammar.
- `tracebi://models/{name}` — one model's full schema as a document.
- `tracebi://knowledge/{slug}` — one lesson body, the same text as
  `tracebi knowledge <slug>`. Slugs are `get_context`'s
  `analyst_knowledge.lessons`.

And three **prompts**, the fastest way to start correctly:

- `author_report(question)` — the whole loop for a question: context, query,
  a `reports/<name>/` package (paste each `query_model` `binding` object
  under `data.<name>`), `build_report`, `verify_manifest`. Without file
  access it takes the gateway route to the same package:
  `start_draft(kind='reports')` → `write_draft_file` → `preview_draft` →
  `publish_draft`, then `build_report` and `verify_manifest` (a measure the
  model lacks is a model draft, published first). A spec and
  `render_report_spec` stay the simpler lane for a fixed layout.
- `answer_question(question, model="")` — `describe_model` (with no model
  named, `list_models` first: each model's description), then `query_model`;
  answer in plain words with each number beside its fingerprint and measure.
  Never estimate; say so when the model can't answer; no report unless asked.
  Asked whether a number is checked, it answers two claims, never blended:
  `downstream(node='measure:<model>:<measure>')` and `verify_manifest` (a
  built figure re-run and matched, the same fingerprint as yours), and
  `describe_table`'s `contract` (the sink satisfied its contract).
- `address_pins(report)` — read `workbench_state`, act on each open pin in
  order (in place with files, or as a report draft over the gateway; a pin
  that doubts a number is checked with `query_model` before anything
  changes), `build_report`, then `verify_manifest(manifest=<manifest_path>)`,
  then `resolve_pin` each with a one-line note.

The server's own instructions lead with the package lane (`build_report`)
and name the spec lane (`render_report_spec`) as the simpler alternative.

### The canonical loop

1. **Discover** — `get_context`, then `list_models` / `describe_model`.
2. **Explore** — `query_model` to probe the data before deciding what to write.
3. **Author** — write a ReportSpec using only vocabulary the gateway showed you.
4. **Validate** — `validate_report_spec`; fix pathed errors until clean. Then
   fix the `design —` warnings too (unsorted bars, more than five KPIs, a
   wide table with no `columns`, an oversized pie): they never block, and each
   names the `design-` lesson that explains the fix.
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

## Drafts over a remote gateway

An agent without server access drafts a report or a declarative model through
the gateway. A draft is a private working copy under `drafts/<owner>/`, and
nothing a draft holds goes live until `publish_draft`.

1. `start_draft(kind, path)`. `kind` is `reports` (a package) or `models` (one
   `models/<name>.yaml` or `.json`, see `docs/reference/model-json.md`). A path
   that is published starts from the published copy; a new one starts empty.
2. `write_draft_file(kind, path, file, content)` for each file the draft needs.
3. `preview_draft(kind, path)`, then give the person the `url` it returns. They
   see the draft rendered in the app.
4. `publish_draft(kind, path, note)` once they agree. For a model, run
   `model_impact(path)` first and show the person which published reports
   move or break; `publish_draft` is refused until you pass
   `accept_impact=true`, and a break needs accepting too. A model may name
   `owners`: if you are not one (and not an admin), `publish_draft` is refused
   with the owners named. Draft it, show `model_impact`, and ask an owner to
   publish; do not try to add yourself to `owners` in the draft (the published
   file decides).
5. A report can go to a chosen folder: `publish_draft(kind, path, folder="finance/q3")`.
   With Publish there it is published. With only Build there the answer is
   `status: "requested"`: a request, not a publish. Tell the person it waits for
   someone with Publish on that folder, who approves or rejects it with
   `list_publish_requests` / `decide_publish_request` (or in the app, under
   Review); you
   cannot decide your own. A folder whose `_folder.yaml` says
   `accepts: checkable` refuses a report whose numbers a query cannot re-run,
   at publish and at request, and the message names why.
   A signed-in person has a folder of their own, `my-published/<sign-in name>`
   (My published in the app), where they hold Publish: publishing there is
   direct, and only they see it unless a `_folder.yaml` inside it grants View.
   With no sign-in identity (the shared token, the CLI) there is none.

**Dev to prod: publish a model before a report that uses it.** A report is
checked against the published models only, so a report that names a model not
yet published does not publish. Python (`report.py`, `models/*.py`,
transforms, pipelines) cannot be drafted remotely; those change through git.

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
  changes belong in `models/*.yaml` (and friends) through git — the definition
  plane. The gateway has no write surface, on purpose.
- **Never page raw rows to dodge the cap.** More than 500 rows means you are
  building a table; do it through a report spec.
