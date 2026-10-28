# `template.html`

A report page is ordinary HTML you control. `data-tb-*` attributes turn any
element, even a `<span>` inside a sentence, into a live figure backed by a
binding in [[report-json]].

```html
<div data-tb-figure="chart" data-tb-binding="by_sector"
     data-tb-type="bar" data-tb-x="dim_issuer.sector"
     data-tb-y="fair_value" id="chart-sector"></div>
```

To skip the attributes, declare figures in `report.json` and place them with
`{{ figure("name") }}` ([[figure-helper]]). Both produce the same markup.

## Every figure

| Attribute | Meaning |
| --- | --- |
| `data-tb-figure` | `value`, `chart`, `table` or `custom` |
| `data-tb-binding` | The binding that feeds the element |
| `id` | Give every figure one. It is the trace's address for the number. |
| `data-tb-unverified` | Required on a figure with no binding. A number is either backed by a re-runnable query or marked as not being one; there is no third state. |

## Value figures

```html
<span data-tb-figure="value" data-tb-binding="totals"
      data-tb-cell="revenue" data-tb-format="currency" id="kpi-rev"></span>
```

| Attribute | Meaning |
| --- | --- |
| `data-tb-cell` | The column to read from a one-row binding. A multi-row binding fails the build. A text cell (the top sector's name) shows as text. |
| `data-tb-format` | A named format ([[number-formats]]). Unset, a number takes the model's declared format, then a readable default. |
| `data-tb-direction` | `up-good` or `down-good`, for a change. Draws ▲ or ▼ from the sign and colours it `--tb-good` or `--tb-bad`. The text stays the formatted number. Any other value fails the build. |

The runtime fills a `.tb-kpi-value` child when there is one, else the element
itself. On a KPI, put the change first on the context line as a
`.tb-kpi-delta` (a rise draws `▲ +`; zero is neutral). Use it only where the
model measures a comparison:

```html
<span class="tb-kpi-context"><span class="tb-kpi-delta" data-tb-figure="value"
  data-tb-binding="gain" data-tb-cell="unrealized" data-tb-format="compact"
  data-tb-direction="up-good" id="kpi-gain"></span> vs cost</span>
```

**Bind the numbers in your prose.** A number typed into a sentence has no
trace. A bound one gets its own row:

```html
<p>Fair value grew to
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="fair_value" data-tb-format="compact"></span>
   this quarter.</p>
```

## Chart figures

| Attribute | Meaning |
| --- | --- |
| `data-tb-type` | `bar`, `barh`, `line`, `area`, `pie` or `scatter` |
| `data-tb-x` | The category column |
| `data-tb-y` | The value column; a comma list for several series |
| `data-tb-color` | The series column |
| `data-tb-value-format` | The format for labels, axes and tooltips |
| `data-tb-renderer` | `svg` (the default) or `canvas`, for thousands of marks; a canvas chart prints as SVG |

Every chart is drawn by Apache ECharts, in one style:

- Bars carry their values in that format at their free end: one to three
  series of few bars, none on stacks or in small multiples; a label that
  would sit on another is left out.
- A line or area ends with its last value, unless `data-tb-mark` already
  labels it.
- Category names wrap to two lines or turn, and are never cut. Value ticks
  are short (`$20M`).
- The tooltip shows the category, the value, the measure's description and a
  "Trace →" link to that figure's row in the trace.

The build inlines ECharts automatically when the page has a chart.

**More than the attributes say.** `tracebi.configureChart(id, patch)` in
`script.js` deep-merges a raw ECharts option into the chart's own:
`dataZoom` (a slider under a long series), `brush`, `visualMap`, `markArea`
(a shaded period), a `toolbox`, a series' `smooth` or `symbol`. It restyles
and never re-sources: every series keeps the data built from the stamped rows,
a patch's own `series[i].data` or `dataset` is dropped, and a series past the
chart's own is not drawn. The plan's `data-tb-type` may also name any ECharts
series type that takes name/value items (`funnel`, `treemap`, `sunburst`),
drawn from the binding's rows the same way.

```js
tracebi.configureChart("fig-flows", {
  dataZoom: [{ type: "slider", height: 18, bottom: 0 }],
  series: [{ smooth: true }],
});
```

## Table figures

```html
<table data-tb-figure="table" data-tb-binding="holdings"
       data-tb-labels="dim_issuer.issuer=Issuer; mark=Mark (FV / cost)"
       data-tb-formats="fair_value=currency0; mark=percent"
       data-tb-totals="holdings_total" data-tb-sort
       data-tb-bars="fair_value" class="tb-table--freeze"></table>
```

| Attribute or class | Meaning |
| --- | --- |
| `data-tb-columns` | Which columns, in order. |
| `data-tb-labels` | Header text per column, as `col=value` pairs separated by `;` (so a label may hold a comma). |
| `data-tb-formats` | Format per column, same syntax: `compact`, `comma`, `currency`, `currency0`, `percent`, `decimal`. A missing column or unknown format fails the build. |
| `data-tb-totals="<binding>"` | A totals row from a one-row binding (the same query with no dimensions). The model computes each total, so a ratio's total is the ratio of the totals. Hidden while a filter or search is on. |
| `data-tb-sort` | Headers become buttons: ascending, descending, then the query's order. Blanks sort last; `aria-sort` reports the order. Only reorders the stamped rows; the totals row stays. |
| `data-tb-bars="col, col2"` | A thin bar after each value in those numeric columns, in its own lane, proportional to the value. Zero is the left edge, or the middle when the column has negatives. The scale covers every stamped row, so filtering never rescales it. A non-numeric column fails the build. |
| `data-tb-rows` | Rows shown before the table scrolls. Default 10; `"all"` turns scrolling off. |
| `tb-table--striped`, `tb-table--compact` | Restyle the table. |
| `tb-table--freeze` | Keeps the first column in view while a wide table scrolls. |

A table past 500 rows renders only the visible rows. Printing and download
still use every row. The browser's find cannot see rows outside the window;
`data-tb-search` is the in-page find.

## Filters and selection

A figure's number is only ever a query result. On a page built with a slice
(`report.json` `"embed"`, the default), a filter writes the page's selection,
and the page re-runs each binding's own query (its calc plan) over the
embedded slice. Values, tables, charts and sparklines recompute.

| Mark | Meaning |
| --- | --- |
| `data-tb-unfiltered-by` | The selected field cannot reach this figure; it keeps its number. |
| `data-tb-fixed` | The page engine cannot run this figure (a SQL binding, a `report.py` output); it stays as built. |

With `"embed": "none"`, filters subset the stamped rows of tables and charts,
and value figures never change: a sum of the rows on screen would be a number
no query produced. Search only narrows the rows shown.

| Control | Markup |
| --- | --- |
| Dropdown filter | `<select data-tb-filter data-tb-binding="B" data-tb-column="C">` |
| Range | `<span data-tb-range data-tb-column="C" data-tb-label="…">` (optional `data-tb-min`, `data-tb-max`, `data-tb-step`) |
| Row selection | `data-tb-select-rows` on a table figure (`="dim_issuer.issuer"` names the columns a row writes) |
| Selection bar | `<div data-tb-selection></div>` (optional: where the bar goes) |
| Search | `<input data-tb-search data-tb-binding="B">` |
| Download | `<button data-tb-download data-tb-binding="B" data-tb-label="…">` |

Filters combine with AND, and search with them. Download exports the
binding's stamped CSV unchanged: always the full binding, never the filtered
view. Under a selection its first line says `# selection: none (full binding)`.

**Every gesture writes the same selection.**

| Gesture | Selects |
|---|---|
| Click a bar, pie slice, line category or legend entry | That value of the chart's `data-tb-x` (or `data-tb-color`) column, whenever a slice carries it, with no filter needed. Click again to remove; shift-click adds. |
| Click a row of a `data-tb-select-rows` table | The row's values of the dimension columns the table shows. |
| Move a range | `{gte, lte}`: two handles on a number column (a dimension attribute, or a fact's own column, which keeps that fact's slice at base grain), or from/to pickers on a time grain's labels. It lets go when both ends are back at the domain (the column's values under the rest of the selection). |

- A chart keeps its own field's other values and dims the ones not picked
  (cross-highlighting; its trace row says what it highlights).
  `data-tb-highlight="off"` on the figure or the page root makes it narrow
  like other figures.
- The selection bar (`.tb-selection-bar`) sits under the masthead, or where
  `data-tb-selection` says. It shows one chip per value with ×, Clear when
  there are two or more, and "Download what I see" (one CSV of each visible
  figure's current rows, the selection in its header and file name). It is
  hidden while the page is as built.
- Escape clears the selection, except while typing.
- In print and in the PDF the bar is one line, "Filtered to: Sector Software ·
  Fund Fund I", and the footer's built line adds " · filtered on this page".
- A field has one name everywhere the page shows it (chips, print line,
  download header, "Not filtered by" notes, trace): its control's
  `data-tb-label` or the `<label>` around it, else the table header or chart x
  title for the column, else a name derived from the column.
- `tracebi.onSelection(fn)` is called with `{selection, authored, figures}` on
  every change. `tracebi.result(id)` reads a figure's current answer.

## Layout

| Pattern | Markup |
| --- | --- |
| Tabs | `<div class="tb-tabs"><section data-tb-tab="Label">…</section></div>`. The runtime builds the tab bar. |
| Sidebar | `<div class="tb-tabs" data-tb-nav="side">`: the tab bar as a left column (a top bar under 720px). |
| Page width | `<main class="tb-page">`, 1,200px at most. |
| 12-column grid | Give a `.tb-grid`'s panels `.tb-span-4`, `-6`, `-8` or `-12`. Every span is the full row under 720px. `<div class="tb-grid"><section class="tb-card tb-span-8">…</section><section class="tb-card tb-span-4">…</section></div>` |
| Column shorthands | `.tb-cols-2`, `.tb-cols-3`, `.tb-cols-2-1`, `.tb-cols-1-2`: one column under 720px. |
| KPI strip | A `.tb-grid` of `.tb-kpi` cells renders as one panel with hairlines between. `.tb-kpi--lead` sets the main number a step larger (not wider); `.tb-kpi-delta` leads its context line. |
| Sparkline | A line or area chart with `class="tb-spark"` inside a `.tb-kpi`: the trend's shape alone, 32px tall on the card's bottom edge, zero-based. Hover still reads each value. |
| Panels | A `.tb-note` right after a `.tb-card`'s first `<h2>` is its subtitle. A table that ends a card runs edge to edge. |

### The look

Set on `<html>`. Ask the person once, before you build, and leave unset what
they didn't ask for (`tracebi context` → `presentation.layout.look`).

| Attribute | Values |
|---|---|
| `data-tb-mode` | `dark` or `light`. Unset: `auto`, following the reader's system. |
| `data-tb-density` | `compact`. Unset: comfortable. |
| `data-tb-width` | `full` removes the reading-width cap (a sidebar wants it). |

Beyond that, a look is a theme preset: `tracebi theme use <name>`, or in
`style.css` the accent pair for each ground (`--tb-accent` /
`--tb-accent-text`, `--tb-dark-accent` / `--tb-dark-accent-text`) and at most
one display face as `--tb-font-display`. The system applies the display face
to `.tb-masthead h1`, `.tb-kpi--lead .tb-kpi-value` and the trace drawer's
title; unset, a dashboard keeps the sans and an editorial headline the serif.
Tokens only: no rules of its own, no gradient, no shadow. The showcase's
`style.css` does exactly this, with Fraunces from `assets/fonts/` and the
project's accent. A look for every report goes in `reports/_theme.css`.

## The masthead

Every page opens with one:

```html
<header class="tb-masthead" data-tb-title="left" data-tb-period="Q3 2026">
  <div class="tb-masthead-mark"></div>              <!-- optional: your logo -->
  <p class="tb-kicker">Direct Lending Portfolio</p> <!-- optional: the model's label -->
  <h1>Portfolio Book</h1>
  <p class="tb-standfirst">One line on what this page is for.</p>
  <p class="tb-masthead-meta"><span data-tb-built></span>
    <span class="tb-verdict"></span></p>
</header>
```

| Part | Meaning |
|---|---|
| `.tb-kicker` | Leave it out and the build adds the label of the model the bindings read. Write one to say something else. |
| `<h1>` | The report's name or its finding. |
| `data-tb-title` | `left`, `center`, `banner` (accent band) or `nav` (moved to the top of a sidebar). |
| `data-tb-period` | What the numbers cover. A label, so it may hold a year. |
| `.tb-masthead-meta` | The runtime fills the period, the build time from the trace (never type a date) and the verdict chip, adding whichever you leave out. |
| `.tb-masthead-mark` | Empty by default. For a logo, put the file in `assets/` and size it in `style.css`: `.tb-masthead-mark { width: 120px; height: 28px; margin-bottom: 16px; background: url(assets/logo.svg) left / contain no-repeat; }`. |

`.tb-title`, the older title block, still works.

The chip's state is `data-tb-verdict`, set by the runtime from the file, never
from the page's markup: `draft` on a working preview (no trace), `not-checked`
on a built file. `tracebi verify` re-runs the queries and says whether each
figure reproduces. The four verdicts, everywhere TraceBi shows one:

| Verdict | Colour |
|---|---|
| `reproduces` | Green, `--tb-good` |
| `needs-a-look` | Amber, `--tb-warn` |
| `does-not-reproduce` | Red, `--tb-bad` |
| `not-checked` | Neutral |

A page never makes itself green. In a built file the runtime adds a "Trace"
link after the chip and makes the chip open the trace too.

## The footer

Every page ends with one:

```html
<footer class="tb-footer" data-tb-methodology>
  <p>Source: the funds' Schedules of Investments.</p>
</footer>
```

Your sources come first. The build adds one line: when the file was built and
from which model ("Built Oct 18, 2026 · Direct Lending Portfolio.", the date
in the reader's own format) and *"This page does not claim the numbers are
right."* Then "How these numbers were made", behind a `<details>`, with what
the trace is for and the stated methodology: transform notes, each check's
reason, measure descriptions. It is an appendix, never a claim: no badge, no
status.

- One `data-tb-methodology` per page, on any container. Without one, the
  whole footer goes at the end of the page.
- With the runtime, the line ends in a "How these numbers were made" link that
  opens the trace drawer, and the `<details>` hides. It stays for readers
  without JavaScript.

## The trace drawer

Every built page has one; you write nothing for it.

- **Opens from** the masthead's "Trace" link or verdict chip, the footer's
  link, a click on any value figure (at that figure's row), or a chart
  tooltip's "Trace →". A page with no masthead gets a floating "Trace" button.
  Escape closes it.
- **Header:** the report's name and *How each number was made*, when it was
  built and from which model, the verdict chip, *"This page does not claim
  the numbers are right; it records how each was made so it can be
  checked."*, and how to check the file (`tracebi verify --file <name>.html`,
  with its `.manifest.json` beside it).
- **One row per figure,** in page order: the value as shown (or "table, 13
  rows" / "chart, 6 rows"), its label, the measure's definition, the query in
  one line (`fair_value by dim_issuer.sector · order fair_value desc`, only the
  ordering keys you wrote), the fingerprint's first 8 characters with Copy,
  and "Raw" (the query as run, the full fingerprint) behind a disclosure.
- **About this build:** the sink contracts, the stated methodology, who built
  it, the build stamp and git.
- **Size:** 420px on the right, a full-height sheet on a phone. It prints as
  an appendix with every disclosure open. Its badges keep their own tones; a
  theme never recolours them.

## Editorial pages

What `tracebi new-report` writes by default: a report written to be read. A
sheet opened by a hero, prose in one serif column of about 68 characters
(`--tb-measure`, a system face), and figures, tables and a KPI strip at the
sheet's full width. With no `style.css` this is the page: one accent, no
texture, no shadow.

```html
<article class="tb-article">
  <header class="tb-masthead tb-article-head">  <!-- data-tb-title="center" to centre it -->
    <h1><span data-tb-figure="value" data-tb-binding="top" data-tb-cell="dim_region.region"></span>
        leads on revenue</h1>
    <p class="tb-standfirst">What this report finds, and why it matters.</p>
    <p class="tb-masthead-meta"><span data-tb-built></span> <span class="tb-verdict"></span></p>
  </header>
  <p class="tb-lede">… numbers bound as value figures …</p>
  <h2>A claim, not a topic</h2>
  <p>…</p>
  <figure class="tb-figure"> <div data-tb-figure="chart" …></div>
    <figcaption>Revenue by region, largest first.</figcaption></figure>
  <aside class="tb-pullstat">
    <span class="tb-pullstat-value" data-tb-figure="value" …></span>
    <span class="tb-pullstat-text">the one number to remember, explained</span></aside>
  <footer class="tb-footer" data-tb-methodology><p>Sources …</p></footer>
</article>
```

- The hero is the masthead in the project's accent, flat, with a serif
  headline (on a dark ground, a deep band of the accent with the page's ink).
- A bound number in the prose is set in weight 600, in the prose's ink.
- Charts, tables, the KPI strip, the pull-stat and the footer use the sans
  face, so numbers read as data.
- To restyle it, set the accent pairs, not a colour of its own.
- Writing advice: `tracebi knowledge design-editorial-report`.

## Exploration blocks

```html
<section data-tb-stage="exploration"> … </section>
```

Shown under `tracebi dev` and removed at the final build. Keep scratch work
here while you iterate.

## `script.js`

```js
tracebi.ready(function (data) { /* … */ });
```

Don't call `tracebi.data()` at the top level. A large report decodes its data
after `script.js` runs, so a top-level call returns `[]` there. `ready(fn)`
works on every report. Sort and slice in the query (`order_by` and `limit`,
[[queries]]), not in JavaScript, so the ordering stays in the trace.
