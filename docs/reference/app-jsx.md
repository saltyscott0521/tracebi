# `app.jsx` — the React lane

**A report package can hold `app.jsx` in place of `template.html`: a React
component for app-like dashboards (navigation, drawers, drill-downs, toggles),
built into the same single offline file, with the same trace.**

The data does not change: `report.json` bindings are queried, stamped and
fingerprinted at build ([[report-json]]). What changes is how the page is
written. There is no Node and no server: the page carries React and the kit,
and compiles `app.jsx` when it opens. The report's strict CSP still refuses
`eval`; nothing is fetched.

```
reports/sales_model/revenue_app/
  report.json     # the bindings, as for any package
  app.jsx         # export default a component
```

`tracebi new-dashboard "Revenue App"` writes one (`--nav top|side` adds
navigation, `--title-at` places the title).
`tracebi report build sales_model/revenue_app` builds it, and the app serves
it like any other report. Its mode and density go in `report.json` `"look"`
and a shipped theme in `"theme"` ([[report-json]]); the project's house style
is `reports/_style.md`, which agents read before building.

## When to use which

| `template.html` ([[template-html]]) | `app.jsx` |
|---|---|
| Briefs, long-form, emailed and printed reports | Dashboards people work in |
| Checkable without running anything; every number is a claim | Kit figures are claims; the app's own numbers are not |
| Reads with JavaScript off (charts fall back to a picture) | Needs JavaScript: a blank page without it |
| Written at volume by an agent with nobody reviewing | Written for a person who will use it |

## Imports — the kit

A report is one offline file, so `app.jsx` can import only:

| Module | What it is |
|---|---|
| `react` | React 18: hooks, components (`useState`, `useMemo`, …) |
| `react-dom` | `createPortal`, `flushSync` |
| `recharts` | Recharts 3, for charts of your own |
| `lucide-react` | Lucide icons. Import by name (`import { TrendingUp } from "lucide-react"`); only those are embedded |
| `tracebi` | The figure components and data hooks below |

Any other import fails the build and names the list. Tailwind classes work
everywhere, generated in the page. The TraceBi tokens are Tailwind colours, so
an app follows the page's mode and the project's `reports/_theme.css`:
`bg-page`, `bg-card`, `bg-surface`, `text-ink`, `text-muted`, `border-rule`,
`bg-accent`, `text-accent-text`, `text-on-accent` (text on an accent fill), `text-good`, `text-bad`, `chart-1` … `chart-8`,
`font-sans` / `font-mono`, `rounded-panel`. The `tb-*` classes
([[styling-a-report]]) work too. A `style.css` beside `app.jsx` is a theme
preset as for a template (the accent pair for each ground, a display face);
its `:root` tokens give way to the dark ground as a template's do.

## The `tracebi` module

```jsx
import { Kpi, Value, Chart, Spark, Table, Filter, Search, Download,
         useBinding, fmt } from "tracebi";
```

**Figures — numbers with a trace.** Each renders the element a template would
hold, and the runtime fills it from the stamped rows: formatted, traced,
filterable, exactly as in a template.

| Component | Props |
|---|---|
| `<Kpi>` | `binding`, `cell`, `format`, `label`, `context`, `lead` (a step larger), `id`; `deltaBinding`, `deltaCell`, `deltaFormat`, `deltaGood` (`"up"` or `"down"`: which way is good) show a stamped change first on the context line, with its arrow, sign and colour; children (a `<Spark>`) sit on the card's bottom edge |
| `<Value>` | `binding`, `cell`, `format`, `id` — a number inside a sentence |
| `<Chart>` | `binding`, `type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`), `x`, `y` (a string or a list), `color`, `valueFormat`, `stack`, `mark`, `annotate`, `facet`, `unit`, `xTitle`, `yTitle`, `palette`, `height`, `id` |
| `<Spark>` | as `<Chart>` (default `type="area"`): the trend's shape alone, under a KPI |
| `<Table>` | `binding`, `columns`, `labels`, `formats`, `sort`, `bars`, `totals`, `rows` (default 10; `"all"`), `selectRows`, `id` |

**Controls.** A figure's number is only ever a query result. On a live page (the
default) a `<Filter>` recomputes every figure it reaches by re-running each
binding's own query over the data the file carries; `<Search>` only narrows the
rows shown. On a page built with `"embed": "none"` a filter subsets stamped rows
and KPIs stay the stamped totals.

| Component | Props |
|---|---|
| `<Filter>` | `binding`, `column`, `label`, `multiple` |
| `<Range>` | `column`, `label`, `min`, `max`, `step` — `data-tb-range` |
| `<SelectionBar />` | `className` — where the selection bar goes (`data-tb-selection`) |
| `<Search>` | `binding`, `placeholder`, `label` |
| `<Download>` | `binding`, `label` — the stamped CSV, verbatim |

Every gesture on a live page writes the same selection state: a click on a
bar, a pie slice, a line's category or a legend entry selects that value of the
chart's `x` (or `color`) column, no `<Filter>` needed (again, it clears it;
shift-click adds one; a `<Spark>` does not select); a click on a row of a
`<Table selectRows>` selects the row's dimension values; a `<Range>` writes
`{gte, lte}` (two handles for a number column, from/to pickers for a time
grain's labels). A chart keeps its own field's other values and draws them back
(cross-highlighting); `data-tb-highlight="off"` on it, or on an ancestor, makes
it narrow like every other figure. `<SelectionBar />` shows one chip per picked
value, Clear and "Download what I see"; without it the runtime puts the bar
above the app. Escape clears; printed, the bar is one line ("Filtered to: …").
`window.tracebi.onSelection(fn)` hears every change.

**App behaviour.**

| Piece | What it does |
|---|---|
| `<Filter column label>` with no `binding` | A page-wide filter. On a page built with a slice (the default `"embed"`) every filter, page-wide or bound, writes one selection state and every figure whose fact reaches the column recomputes from the embedded data — values, tables, charts, sparks, including ones mounted later; the chip reads Local, the state rides in the URL hash beside `useUrlState`'s keys, and a figure that cannot recompute carries `data-tb-fixed` (one the field does not reach, `data-tb-unfiltered-by`). With `"embed": "none"`, or on a column no slice carries, it subsets the stamped rows of every binding that has the column and KPIs stay the stamped totals. |
| `<Filter column multiple>` | A list box: the reader picks several values; the selection holds all of them. |
| `<Segmented options value onChange label>` | One choice of a few — a view, a period. Use it to pick *which* figure shows: one literal-binding figure per option (`{p === "YTD" ? <Kpi binding="kpis_ytd" …/> : <Kpi binding="kpis_mtd" …/>}`), so each number keeps its trace. |
| `useUrlState(key, initial)` | `useState` kept in the URL (`#view=Detail&period=YTD`): a reload or a shared link opens where the reader was. |
| `usePrinting()` | `true` while the page prints (the browser's Ctrl+P, and `tracebi report build --format pdf`). An app with views renders every one then, so the PDF holds the whole report: `{printing ? <><Overview /><Detail /></> : <View />}`. Give navigation `print:hidden`. |
| `<Masthead title kicker period mark>` | Opens the page: an optional `mark` (a node; or leave it empty and size `.tb-masthead-mark` in `style.css`), a `kicker` (unset, the model's label; `kicker={null}` shows none), the `title` (a string, or text with `<Value>`s in it: `title={<>Marked at <Value binding="kpis" cell="mark" /> of cost</>}`), the standfirst as its children, and a meta line with the `period` (presentation, `"Q3 2026"`), the build time and the verdict chip, which the runtime fills from the file itself (`not-checked` on a built file, `draft` on a preview; never green on its own say-so). Other props go on the `<header>`: `data-tb-title="center|banner|nav"`. A literal `title` is checked for typed numbers like the app's text; `kicker` and `period` are labels. |
| `<Footer />` | Where the build's footer goes: one line on when the file was built, from which model (by its label), and that the page does not claim the numbers are right, then "How these numbers were made", which opens the trace drawer. Put it at the end of the main column (a sidebar layout's `<main>`); without it the footer follows the app. |
| `<Built>` | When the file was built, from its trace (`<Masthead>` already shows it). |
| `tb-page`, `tb-grid` + `tb-span-4/6/8/12` | The page measure (`<main className="tb-page space-y-8 px-6 py-8">`, 1,200px) and the 12-column grid (`<div className="tb-grid"><section className="tb-card tb-span-8">…`). |

**Data for your own components.** `useBinding("name")` returns the binding's
stamped rows (copies), and `fmt(value, "currency0")` formats a number with the
named formats ([[number-formats]]).

## What the trace covers

The build reads every kit figure's props from `app.jsx` without running it,
records each one as a claim in the manifest, and refuses a binding or a column
that does not exist. A `<Kpi>`'s delta is a claim of its own
(`fig-delta-<binding>-<cell>`); it reads a measure the model computes, such as
fair value less cost, and the kit never computes one: no comparison measure,
no delta. So `binding`, `cell`, `x` and `y` (and `deltaBinding`, `deltaCell`)
must be literal strings:
`<Kpi binding={b}>` fails the build. Two kit figures of the same binding and
column need an `id` each — an id is the trace's address for one number.

A number typed into the app's text (`<p>Up 1250 units</p>`) fails the build,
as it does in a `template.html`: bind it with `<Value binding="…" cell="…" />`,
or say it in words. A single digit ("Q3") is not a number here.

Anything the app computes or draws itself — a Recharts chart, a sum, a number
in your own markup — is the app's presentation, not a checked figure. The page's
footer says so: *"This page is an app. The figures it shows through the
TraceBi kit carry that trace; anything else it draws is the app's own
presentation and is not checked."* `tracebi verify` re-runs the bindings as for
any report.

## An example

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

An email client's preview or a phone's file viewer runs no script. The build
writes the kit figures into the app's mount point as a static view — labelled
KPIs, each chart's static picture, the tables — so those readers still see the
numbers; the app replaces that view when it starts. `tracebi report build
--format pdf` prints the app's first view.

## Starting points

`tracebi new-dashboard "Name" --job …`:

- `overview` (default) — a KPI strip with a lead, a chart beside its ranking, a filterable detail.
- `trend` — the latest period leading with its sparkline, the series as a chart or a table (a `<Segmented>` kept in the URL). Needs a time dimension in the model.
- `leaderboard` — the leader, a top-ten bar chart, the full ranking with search.
- `scorecard` — every measure the fact runs (up to four) as a KPI, each with its trend when the model has a time dimension, then all of them by category.
- `monitor` — is anything off right now: the latest period of every measure (up to four) with its sparkline, the series, and a watch list of the lowest members first. Needs a time dimension; without one it starts as a scorecard.
- `funnel` — the fact's count measures (not money, not rates) as stages, widest first as the warehouse stands, with each stage's share of the first. The conversions are report-level ratios in `report.json` `"measures"`, so the trace names them; reorder the stages to your funnel's in `report.json`. Needs two count measures; with one it starts as an overview.

A broken app shows its error on the page instead of a blank one. The vendored
bundles and their licences are listed in `tracebi/reports/assets/REACT_NOTICE.md`.
