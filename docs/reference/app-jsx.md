# `app.jsx` — the React lane

**A report package can hold `app.jsx` in place of `template.html`: a React
component for app-like dashboards (navigation, drawers, drill-downs, toggles),
built into the same single offline file, with the same receipt.**

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
([[styling-a-report]]) work too.

## The `tracebi` module

```jsx
import { Kpi, Value, Chart, Spark, Table, Filter, Search, Download,
         useBinding, fmt } from "tracebi";
```

**Figures — numbers with a receipt.** Each renders the element a template would
hold, and the runtime fills it from the stamped rows: formatted, receipted,
filterable, exactly as in a template.

| Component | Props |
|---|---|
| `<Kpi>` | `binding`, `cell`, `format`, `label`, `context`, `lead` (twice as wide), `id`; children (a `<Spark>`) go under the number |
| `<Value>` | `binding`, `cell`, `format`, `id` — a number inside a sentence |
| `<Chart>` | `binding`, `type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`), `x`, `y` (a string or a list), `color`, `valueFormat`, `stack`, `mark`, `annotate`, `facet`, `unit`, `xTitle`, `yTitle`, `palette`, `height`, `id` |
| `<Spark>` | as `<Chart>` (default `type="area"`): the trend's shape alone, under a KPI |
| `<Table>` | `binding`, `columns`, `labels`, `formats`, `sort`, `bars`, `totals`, `rows` (default 10; `"all"`), `id` |

**Controls** subset the rows the figures of one binding show; they never compute.

| Component | Props |
|---|---|
| `<Filter>` | `binding`, `column`, `label` |
| `<Search>` | `binding`, `placeholder`, `label` |
| `<Download>` | `binding`, `label` — the stamped CSV, verbatim |

**App behaviour.**

| Piece | What it does |
|---|---|
| `<Filter column label>` with no `binding` | A page-wide filter: it subsets every binding that has the column — tables and charts, including ones mounted later. KPIs and values stay the stamped totals (a filtered KPI needs its own binding, or `report.json` `"selection"`). |
| `<Segmented options value onChange label>` | One choice of a few — a view, a period. Use it to pick *which* figure shows: one literal-binding figure per option (`{p === "YTD" ? <Kpi binding="kpis_ytd" …/> : <Kpi binding="kpis_mtd" …/>}`), so each number keeps its receipt. |
| `useUrlState(key, initial)` | `useState` kept in the URL (`#view=Detail&period=YTD`): a reload or a shared link opens where the reader was. |
| `<Built>` | When the file was built, from its receipt. |

**Data for your own components.** `useBinding("name")` returns the binding's
stamped rows (copies), and `fmt(value, "currency0")` formats a number with the
named formats ([[number-formats]]).

## What the receipt covers

The build reads every kit figure's props from `app.jsx` without running it,
records each one as a claim in the manifest, and refuses a binding or a column
that does not exist. So `binding`, `cell`, `x` and `y` must be literal strings:
`<Kpi binding={b}>` fails the build. Two kit figures of the same binding and
column need an `id` each — an id is the receipt's address for one number.

Anything the app computes or draws itself — a Recharts chart, a sum, a number
in your own markup — is the app's presentation, not a checked figure. The page's
About block says so: *"This page is an app. The figures it shows through the
TraceBi kit carry that receipt; anything else it draws is the app's own
presentation and is not checked."* `tracebi verify` re-runs the bindings as for
any report.

## An example

```jsx
import { useState } from "react";
import { LayoutDashboard, CreditCard } from "lucide-react";
import { Kpi, Spark, Chart, Table, Filter } from "tracebi";

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
      <main className="flex-1 space-y-6 p-8">
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

A broken app shows its error on the page instead of a blank one. The vendored
bundles and their licences are listed in `tracebi/reports/assets/REACT_NOTICE.md`.
