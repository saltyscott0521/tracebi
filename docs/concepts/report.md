# Reports

A report is a folder in `reports/`, usually inside a project
(`reports/<project>/<report>/`, [[workspace-and-projects]]), whose every
figure is a query against a model. One command builds it into a single HTML file and a [[trace]]:

```
reports/my_report/
  report.json      the data the report reads           → [[report-json]]
  app.jsx          a dashboard built from the kit       → [[app-jsx]]
  template.html    or a page written in HTML            → [[template-html]]
  style.css        optional: your CSS
  script.js        optional: your JavaScript
  report.py        optional: Python for numbers the model cannot express
```

A dashboard (`tracebi new-dashboard`) is an `app.jsx` made of kit components
such as `<Kpi>`, `<Chart>`, `<Table>` and `<Filter>`. A page
(`tracebi new-report`) is a `template.html` of ordinary HTML, where
`data-tb-*` attributes turn elements into figures. You own the layout and the
styles.

## Build it

```bash
tracebi report build my_report
```

This writes `output/my_report.html`, with its CSS, JavaScript, data and
charting library inlined, a strict content security policy and no CDN, and
`output/my_report.html.manifest.json`, the trace. With the `pdf` extra
(Playwright and Chromium) the build also writes `my_report.cover.png`, a
picture of the first screen that the library uses as a cover. The cover is
not part of the trace.

Check the file later, offline:

```bash
tracebi verify --file output/my_report.html
```

## How a figure gets its number

A figure never holds a typed-in number. It names a **binding**, a query
declared in `report.json`. The build runs the query, fingerprints the result,
embeds the rows in the page and fills the figure from them. So:

- A typed-in number cannot pass as a figure. A number with no query must be
  marked `data-tb-unverified`. There is no third state.
- The page and the trace cannot disagree, because both come from the same
  fingerprinted rows.
- Rebuilding takes milliseconds. The model's tables already exist, and no
  transform runs.

There is one renderer: a report is always built from its package. A
`reports/<name>.json` spec is shorthand that compiles into a package.

## Filters and interactivity

Filters, search, tabs, scrolling tables and CSV download all work in the
built file. The rule: a figure's number is only ever a query result.

The built page carries a slice of the model (the rows its figures and filters
need) and each binding's query as a calc plan. A filter changes the page's
selection, and the page re-runs each figure's own query under it. Values,
tables, charts and sparklines all recompute, and the chip reads Local.
`tracebi verify --local` replays the same plans on the server. Nothing sums the
rows on screen. Search only narrows the rows shown. See [[template-html]].

## When the model cannot express a number

Add `report.py` with a `build(inputs) -> {name: DataFrame}` function. Its
inputs are stamped queries and can still reproduce. Its outputs are stamped
`verifiable: false` and never read green. Use it only when the model cannot
express the number, because everything it computes leaves the checkable path.
See [[trace]].

## Next

- Build one step by step: [[your-first-report]]
- Style it: [[styling-a-report]]
