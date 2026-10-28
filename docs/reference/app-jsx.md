# `app.jsx`

A report package can hold `app.jsx` instead of `template.html`: a React
component for dashboards people work in, built into the same single offline
file with the same trace.

```
reports/sales_model/revenue_app/
  report.json     # the bindings, as for any package
  app.jsx         # export default a component
```

```bash
tracebi new-dashboard "Revenue App"               # --nav top|side, --title-at
tracebi report build sales_model/revenue_app
```

- The data works as for any package: `report.json` bindings are queried,
  stamped and fingerprinted at build ([[report-json]]).
- There is no Node and no server. The page carries React and the kit and
  compiles `app.jsx` when it opens. The strict CSP still refuses `eval`, and
  nothing is fetched.
- Mode and density go in `report.json` `"look"`, a shipped theme in
  `"theme"`. The project's house style is `reports/_style.md`, which agents
  read before building.

## `template.html` or `app.jsx`

| `template.html` ([[template-html]]) | `app.jsx` |
|---|---|
| Briefs, long reads, emailed and printed reports | Dashboards people work in |
| Every number on the page is a checked claim | Kit figures are claims; the app's own numbers are not |
| Reads with JavaScript off (charts fall back to a picture) | Needs JavaScript |
| Suits agents writing at volume with no reviewer | Suits a page a person will use |

## Imports

`app.jsx` can import only these:

| Module | What it is |
|---|---|
| `react` | React's hooks and components (`useState`, `useMemo`, …). Every page runs on TanStack Redact, a drop-in React runtime with the same API |
| `react-dom` | `createPortal`, `flushSync` |
| `echarts` | Apache ECharts' module (`echarts.graphic`, `echarts.getInstanceByDom`), for what `<EChart>` hands you; the chart itself is `<EChart>` from `tracebi` |
| `recharts` | Recharts 2, which also works (Recharts 3 does not run on Redact) |
| `lucide-react` | Lucide icons, imported by name (`import { TrendingUp } from "lucide-react"`); only those are embedded |
| `tracebi` | The figure components and data hooks below |

Any other import fails the build and names the list.

Tailwind classes work everywhere, generated in the page. The TraceBi tokens
are Tailwind colours, so an app follows the page's mode and
`reports/_theme.css`: `bg-page`, `bg-card`, `bg-surface`, `text-ink`,
`text-muted`, `border-rule`, `bg-accent`, `text-accent-text`, `text-on-accent`,
`text-good`, `text-bad`, `chart-1` … `chart-8`, `font-sans`, `font-mono`,
`rounded-panel`. The `tb-*` classes ([[styling-a-report]]) work too. A
`style.css` beside `app.jsx` is a theme preset, tokens only (the accent pair
for each ground, a display face as `--tb-font-display`).

## Figures

```jsx
import { Kpi, Value, Chart, Spark, Table, EChart, Filter, Search, Download,
         useBinding, useSelection, fmt } from "tracebi";
```

Each figure renders the element a template would hold, and the runtime fills
it from the stamped rows: formatted, traced and filterable.

| Component | Props |
|---|---|
| `<Kpi>` | `binding`, `cell`, `format`, `label`, `context`, `lead` (a step larger), `id`. `deltaBinding`, `deltaCell`, `deltaFormat` and `deltaGood` (`"up"` or `"down"`) show a stamped change first on the context line, with arrow, sign and colour. Children (a `<Spark>`) sit on the card's bottom edge. |
| `<Value>` | `binding`, `cell`, `format`, `id`: a number inside a sentence |
| `<Chart>` | `binding`, `type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`), `x`, `y` (a string or a list), `color`, `valueFormat`, `stack`, `mark`, `annotate`, `facet`, `unit`, `xTitle`, `yTitle`, `palette`, `height`, `id` |
| `<Spark>` | As `<Chart>` (default `type="area"`): the trend's shape alone, under a KPI |
| `<Table>` | `binding`, `columns`, `labels`, `formats`, `sort`, `bars`, `totals`, `rows` (default 10; `"all"`), `selectRows` (or `selectRows="dim_issuer.issuer"`: the columns a row click writes), `id` |

## Controls

A figure's number is only ever a query result. On a live page (the default) a
`<Filter>` recomputes every figure it reaches by re-running each binding's own
query over the data the file carries. `<Search>` only narrows the rows shown.
With `"embed": "none"` a filter subsets stamped rows and KPIs keep the stamped
totals.

| Component | Props |
|---|---|
| `<Filter>` | `binding`, `column`, `label`, `multiple` |
| `<Range>` | `column`, `label`, `min`, `max`, `step` (`data-tb-range`) |
| `<SelectionBar />` | `className`: where the selection bar goes (`data-tb-selection`) |
| `<Search>` | `binding`, `placeholder`, `label` |
| `<Download>` | `binding`, `label`: the stamped CSV, unchanged |

Every gesture on a live page writes the same selection:

| Gesture | Selects |
|---|---|
| Click a bar, pie slice, line category or legend entry | That value of the chart's `x` (or `color`) column, with no `<Filter>` needed. Click again to clear; shift-click adds. A `<Spark>` does not select. |
| Click a row of a `<Table selectRows>` | The row's dimension values |
| Move a `<Range>` | `{gte, lte}`: two handles on a number column, or from/to pickers on a time grain's labels |

- A chart keeps its own field's other values and dims them
  (cross-highlighting). `data-tb-highlight="off"` on it or an ancestor makes
  it narrow like other figures.
- `<SelectionBar />` shows one chip per value, Clear, and "Download what I
  see". Without it the runtime puts the bar above the app.
- Escape clears the selection. In print it is one line ("Filtered to: …").
- `window.tracebi.onSelection(fn)` hears every change.

## App behaviour

| Piece | What it does |
|---|---|
| `<Filter column label>` with no `binding` | A page-wide filter. On a page with a slice (the default `"embed"`), every filter writes one selection, and every figure whose fact reaches the column recomputes from the embedded data, including figures mounted later. The chip reads Local, and the selection rides in the URL hash beside `useUrlState`'s keys. A figure that cannot recompute carries `data-tb-fixed`; one the field does not reach, `data-tb-unfiltered-by`. With `"embed": "none"`, or on a column no slice carries, it subsets the stamped rows of every binding with the column, and KPIs keep the stamped totals. |
| `<Filter column multiple>` | A list box: the reader picks several values. |
| `<Segmented options value onChange label>` | One choice of a few: a view, a period. Use it to pick which figure shows, one literal-binding figure per option (`{p === "YTD" ? <Kpi binding="kpis_ytd" …/> : <Kpi binding="kpis_mtd" …/>}`), so each number keeps its trace. |
| `useUrlState(key, initial)` | `useState` kept in the URL (`#view=Detail&period=YTD`), so a reload or a shared link opens where the reader was. |
| `usePrinting()` | `true` while the page prints (Ctrl+P, and `tracebi report build --format pdf`). Render every view then, so the PDF holds the whole report: `{printing ? <><Overview /><Detail /></> : <View />}`. Give navigation `print:hidden`. |
| `<Masthead title kicker period mark>` | Opens the page: an optional `mark` (a node, or size `.tb-masthead-mark` in `style.css`), a `kicker` (unset: the model's label; `kicker={null}` shows none), the `title` (a string, or text with `<Value>`s: `title={<>Marked at <Value binding="kpis" cell="mark" /> of cost</>}`), the standfirst as children, and a meta line with the `period` (a label such as `"Q3 2026"`), the build time and the verdict chip. The runtime fills the chip from the file: `not-checked` on a built file, `draft` on a preview, never green on its own. Other props go on the `<header>`: `data-tb-title="center|banner|nav"`. A literal `title` is checked for typed numbers; `kicker` and `period` are labels. |
| `<Footer />` | Where the build's footer goes: when the file was built, from which model (by its label), that the page does not claim the numbers are right, then "How these numbers were made", which opens the trace drawer. Put it at the end of the main column; without it the footer follows the app. |
| `<Built>` | When the file was built, from its trace (`<Masthead>` already shows it). |
| `tb-page`, `tb-grid` + `tb-span-4/6/8/12` | The page width (`<main className="tb-page space-y-8 px-6 py-8">`, 1,200px) and the 12-column grid (`<div className="tb-grid"><section className="tb-card tb-span-8">…`). |

## Charts

`<EChart>` is the chart: Apache ECharts, drawn into its own canvas (or SVG),
for everything from a bar to a treemap, a sankey or 100,000 points. Whether a
chart is a checked figure follows its data, not who wrote it.

```jsx
<EChart binding="by_sector" type="treemap" x="dim_issuer.sector" y="fair_value"
        format="currency_compact" height={300} />
```

| Prop | What it does |
|---|---|
| `binding`, `x`, `y` | The binding and its columns: `x` the category (a number on a scatter), `y` one measure or a list. Literal strings make the chart a claim, as for `<Chart>`. |
| `type` | `bar` (default), `barh`, `line`, `area`, `pie`, `scatter`, or any ECharts series type that takes name/value items (`funnel`, `treemap`, `sunburst`, …) |
| `series` | A column whose values split the rows into series (`<Chart color>`) |
| `format`, `unit`, `stack` | The values' named format, a unit suffix, stacked series |
| `option` | An ECharts option, or a function of the rows, deep-merged on top: the escape hatch for anything the props do not say |
| `renderer` | `"canvas"` (default: large data, smooth hover) or `"svg"` (crisp text, small charts, prints sharp) |
| `theme` | `"auto"` (default): the page's tokens and palette, following its mode; or an ECharts theme |
| `selects`, `onSelect` | On an option-only chart, the column a click selects; `onSelect(params)` returns the value a click picks (null: none) |
| `highlight` | `"off"`: a selection narrows the chart instead of dimming its own field's other values |
| `onEvents`, `ariaLabel`, `height`, `id`, `className` | ECharts events (`{click: (p) => …}`), the description (ECharts' aria is on by default, so a canvas chart has one), size, id |

- **A chart of a binding's columns is a claim.** With `binding`, `x` and `y`
  literal, `<EChart>` renders the same `data-tb-figure="chart"` element as
  `<Chart>`, the build records it and refuses an unknown binding or column,
  and the trace names it. `option` styles it and cannot replace its numbers
  (series data, a dataset or category labels in it are dropped).
- **A chart of numbers the page computed is not.** `<EChart option={…}>`
  alone (sankey links summed in the app, a ratio you work out) carries
  `data-tb-computed` and is the app's presentation, not a checked figure; the
  page's footer says so.
- **Every chart is live.** Its rows are its binding's query re-run under the
  page's selection, and a click on a mark selects that value of its `x` (shift
  adds, again removes), as on `<Chart>`; the chart keeps its own field's other
  values and dims them.
- **Recharts also works.** `import { BarChart, Bar } from "recharts"` (Recharts
  2) draws with `useBinding` rows; to select on click, `<Bar onClick={(d, i, e) =>
  window.tracebi.pick("dim_region.region", d.payload["dim_region.region"], e)} />`.
  A Recharts chart is presentation, like an option-only `<EChart>`.

**Data for your own components.** `useBinding("name")` returns copies of the
binding's rows as the page has them now: on a live page its query re-run
under the selection, re-rendering when the selection changes; on an `"embed":
"none"` page, or for a binding the page cannot re-run (SQL, `report.py`), the
stamped rows. What you draw from them is live, not a checked figure.
`useSelection()` returns the selection (`{"dim_region.region": ["East"]}`).
`fmt(value, "currency0")` formats a number with the named formats
([[number-formats]]).

## What the trace covers

The build reads every kit figure's props from `app.jsx` without running it,
records each as a claim in the manifest, and refuses a binding or column that
does not exist.

- `binding`, `cell`, `x`, `y`, `deltaBinding` and `deltaCell` must be literal
  strings. `<Kpi binding={b}>` fails the build.
- Two kit figures of the same binding and column need an `id` each. An id is
  the trace's address for one number.
- A `<Kpi>`'s delta is a claim of its own (`fig-delta-<binding>-<cell>`). It
  reads a measure the model computes, such as fair value less cost; the kit
  never computes one. No comparison measure, no delta.
- A number typed into the app's text (`<p>Up 1250 units</p>`) fails the build,
  as in a `template.html`. Bind it with `<Value binding="…" cell="…" />`, or
  say it in words. A single digit ("Q3") is not a number here.
- Anything the app computes or draws itself (an `<EChart option={…}>`, a
  Recharts chart, a sum, a number in your own markup) is presentation, not a
  checked figure. The page's footer
  says so: *"This page is an app. The figures it shows through the TraceBi kit
  carry that trace; anything else it draws is the app's own presentation and
  is not checked."*

`tracebi verify` re-runs the bindings as for any report.

## Example

```jsx
import { useState } from "react";
import { LayoutDashboard, CreditCard } from "lucide-react";
import { Masthead, Footer, Kpi, Spark, Chart, Table, Filter } from "tracebi";

const NAV = { Overview: LayoutDashboard, Plans: CreditCard };

export default function App() {
  const [view, setView] = useState("Overview");
  return (
    <div className="flex min-h-screen bg-page text-ink">
      <aside className="w-56 border-r border-rule bg-card p-3">
        {Object.entries(NAV).map(([label, Icon]) => (
          <button key={label} onClick={() => setView(label)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm">
            <Icon size={16} />{label}
          </button>
        ))}
      </aside>
      <main className="min-w-0 flex-1 space-y-8 px-6 py-8">
        <Masthead title="Recurring revenue" period="Monthly">
          Ending MRR and customers, month by month.
        </Masthead>
        {view === "Overview" ? (
          <div className="tb-grid">
            <Kpi lead binding="kpis" cell="ending_mrr" format="currency0" label="Ending MRR">
              <Spark binding="by_month" x="dim_month.month" y="ending_mrr" />
            </Kpi>
            <Kpi binding="kpis" cell="customers" format="comma" label="Customers" />
          </div>
        ) : (
          <section className="tb-card">
            <h2>Plans</h2>
            <Filter binding="by_plan" column="dim_plan.plan" label="Plan" />
            <Table binding="by_plan" sort bars="ending_mrr" />
          </section>
        )}
        <Footer />
      </main>
    </div>
  );
}
```

## Without JavaScript

An email preview or a phone's file viewer runs no script. The build writes
the kit figures into the app's mount point as a static view (labelled KPIs,
each chart's static picture, the tables), so those readers still see the
numbers. The app replaces that view when it starts. `tracebi report build
--format pdf` prints the app's first view.

## Starting points

`tracebi new-dashboard "Name" --job …`:

| Job | Starts with |
|---|---|
| `overview` (default) | A KPI strip with a lead, a chart beside its ranking, a filterable detail. |
| `trend` | The latest period with its sparkline, and the series as a chart or a table (a `<Segmented>` kept in the URL). Needs a time dimension. |
| `leaderboard` | The leader, a top-ten bar chart, the full ranking with search. |
| `scorecard` | Every measure the fact runs (up to four) as a KPI, each with its trend when the model has a time dimension, then all of them by category. |
| `monitor` | The latest period of every measure (up to four) with its sparkline, the series, and a watch list, lowest first. Needs a time dimension; without one it starts as a scorecard. |
| `funnel` | The fact's count measures (not money, not rates) as stages, widest first, each with its share of the first. Conversions are report-level ratios in `report.json` `"measures"`, so the trace names them; reorder the stages there. Needs two count measures; with one it starts as an overview. |

A broken app shows its error on the page. The vendored bundles and their
licences are listed in `tracebi/reports/assets/REACT_NOTICE.md`.
