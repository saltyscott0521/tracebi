# `template.html` — the figure grammar

**Ordinary HTML you fully control. A handful of `data-tb-*` attributes turn an
element into a live figure backed by a [[report-json#`data` — object, **required**|binding]].**

Nothing here is a component library. Any element can be a figure — including a
`<span>` mid-sentence.

> Prefer not to write these by hand? Declare the figure instead and place it
> with `{{ figure("name") }}` — see [[figure-helper]]. Both produce identical
> markup; mix freely.

---

## Claiming a figure

```html
<div data-tb-figure="chart" data-tb-binding="by_sector"
     data-tb-type="bar" data-tb-x="dim_issuer.sector"
     data-tb-y="fair_value" id="chart-sector"></div>
```

| Attribute | Meaning |
| --- | --- |
| `data-tb-figure` | `value` \| `chart` \| `table` \| `custom` |
| `data-tb-binding` | which stamped binding feeds this element |
| `id` | **give every figure one** — it is the receipt's address, and how a human redirects you |

A figure with no binding must carry `data-tb-unverified`. **There is no third
state:** a number is either backed by a re-runnable query or honestly marked as
not being one.

### Value figures

```html
<span data-tb-figure="value" data-tb-binding="totals"
      data-tb-cell="revenue" data-tb-format="currency" id="kpi-rev">—</span>
```

- `data-tb-cell` — the column to read, from row 0
- `data-tb-format` — see [[number-formats]]. Leave it off and a numeric cell
  takes the model's declared format, then a readable default, the same way a
  table column does.
- `data-tb-direction` — `up-good` or `down-good`, for a figure that shows a
  change. The runtime draws ▲ or ▼ from the value's sign and colors it with
  `--tb-good` or `--tb-bad` depending on whether that direction is good. The
  text stays the formatted number. Anything else fails the build. On a KPI,
  the change goes first on the context line as a `.tb-kpi-delta` (a rise is
  drawn `▲ +`, zero is neutral):

```html
<span class="tb-kpi-context"><span class="tb-kpi-delta" data-tb-figure="value"
  data-tb-binding="gain" data-tb-cell="unrealized" data-tb-format="compact"
  data-tb-direction="up-good" id="kpi-gain"></span> vs cost</span>
```

  Only where the model measures a comparison; no comparison measure, no delta.

The runtime fills a `.tb-kpi-value` child when one exists, otherwise the
element itself. The `binding` must return one row; a value figure over a
multi-row binding fails the build.

### Chart figures

`data-tb-type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`),
`data-tb-x`, `data-tb-y` (comma-list for multi-series), `data-tb-color`,
and `data-tb-value-format` for labels, axes and tooltips.

Every chart is drawn in one style, with no setting to learn: bars carry
their own values in that format (inside the bar when the label fits, past
its end when not; none on bars under 14px wide, on stacks or in small
multiples), a line or area ends in its last value (unless `data-tb-mark`
already labels the last), category names wrap to two lines or turn and are
never cut, and value ticks thin to what fits. The tooltip shows the
category, the value, the measure's description from the model and a
"Receipt →" link that opens the receipt drawer at that figure.

The build inlines D3 automatically when the page contains a chart
figure. `"libs"` in [[report-json]] is optional.

### Table figures

`data-tb-columns` — a column allowlist and order. Classes
`tb-table--striped` / `tb-table--compact` restyle it, and `tb-table--freeze`
keeps the first column in view while a wide table scrolls sideways.

`data-tb-labels` and `data-tb-formats` — header text and number format per
column, written as `col=value` pairs separated by `;` (so a label may contain
a comma). They win over the derived header and format for the columns they
name; the others keep their defaults.

```html
<table data-tb-figure="table" data-tb-binding="holdings"
       data-tb-labels="dim_issuer.issuer=Issuer; mark=Mark (FV / cost)"
       data-tb-formats="fair_value=currency0; mark=percent"></table>
```

Formats: `compact`, `comma`, `currency`, `currency0`, `percent`, `decimal`.
A column that isn't in the binding, or an unknown format, fails the build
and names the fix.

`data-tb-totals="<binding>"` — a totals row, filled from a one-row binding:
the same query with no dimensions. The model computes each total, so a ratio's
total is the ratio of the totals, never a sum of ratios. The row steps aside
while a filter or search is on, because a grand total would no longer match
the rows shown.

`data-tb-sort` (no value) — the headers become buttons. Clicking one sorts
ascending, then descending, then back to the query's own order. Blanks sort
last, and `aria-sort` tells screen readers the current order. Sorting only
reorders stamped rows; the totals row stays.

`data-tb-bars="col, col2"` — a thin bar after each value in the named numeric
columns, in a lane of its own inside the cell, proportional to the value; the
number stays right-aligned and the bar follows its row on sort and filter. Zero is the left edge; when a column holds
negative values, zero moves to the middle so neither side is exaggerated. The
scale covers every stamped row, so filtering never rescales it. A column that
isn't numeric fails the build.

```html
<table data-tb-figure="table" data-tb-binding="holdings"
       data-tb-totals="holdings_total" data-tb-sort
       data-tb-bars="fair_value" class="tb-table--freeze"></table>
```

---

## Bind prose numbers

The single highest-value habit in this file:

```html
<p>Fair value grew to
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="fair_value" data-tb-format="compact">—</span>
   this quarter.</p>
```

Narrative prose is where hard-coded numbers hide. Here the honest path costs
one attribute, and each bound span gets its own entry in the receipt.

## Interactivity

**Controls subset which stamped rows a figure displays. They never compute new
numbers** — client-side aggregation would mint numbers nobody can re-run, so a
filtered KPI needs its own binding, and value figures never react to controls.

| Control | Markup |
| --- | --- |
| Dropdown filter | `<select data-tb-filter data-tb-binding="B" data-tb-column="C">` |
| Search | `<input data-tb-search data-tb-binding="B">` |
| Download | `<button data-tb-download data-tb-binding="B" data-tb-label="…">` |

Filters on one binding AND-combine, and search ANDs with them. Download exports
the binding's **stamped CSV verbatim** — a receipt-preserving export, always the
full binding, never the filtered view.

Tables scroll past `data-tb-rows` (default 10); `data-tb-rows="all"` opts out.
Tables past 500 rows render only the visible rows; printing and download still
use every row. Find-in-page cannot see rows outside that window — `data-tb-search`
is the in-page find.

## Layout

- **Tabs** — `<div class="tb-tabs"><section data-tb-tab="Label">…</section></div>`;
  the runtime builds the tab bar from the labels.
- **Page measure** — `<main class="tb-page">` (and the page itself) is
  1,200px wide at most.
- **12-column grid** — the layout: give a `.tb-grid`'s panels `.tb-span-4`,
  `.tb-span-6`, `.tb-span-8` or `.tb-span-12` (a third, a half, two thirds,
  the row): the grid becomes twelve columns, and every span is the full row
  under 720px. A wide panel beside a narrow one:
  `<div class="tb-grid"><section class="tb-card tb-span-8">…</section><section
  class="tb-card tb-span-4">…</section></div>`.
- **Columns** — `.tb-cols-2` / `.tb-cols-3`, and `.tb-cols-2-1` / `.tb-cols-1-2`,
  still work as shorthands for equal or 2:1 columns; they collapse to one
  column under 720px.
- **KPI strip** — a `.tb-grid` of `.tb-kpi` cells renders as one panel with
  hairlines between the cells. `.tb-kpi--lead` sets the page's main number a
  step larger (not wider); a `.tb-kpi-delta` leads its context line.
- **Sparkline** — a line or area chart with `class="tb-spark"` inside a
  `.tb-kpi` draws the trend's shape alone (no axes, grid or legend; 32px tall
  on the card's bottom edge; zero-based); hovering still reads each value.
- **Panels** — a `.tb-note` straight after a `.tb-card`'s first `<h2>` is the
  panel's subtitle; a table that ends a card runs edge to edge.
- **Sidebar** — `<div class="tb-tabs" data-tb-nav="side">` lays the same tab
  bar out as a left column (a top bar again under 720px).

### The look

Set on `<html>`; ask the person once, before you build, and leave unset what
they didn't ask for (`tracebi context` → `presentation.layout.look`).

| Attribute | Values |
|---|---|
| `data-tb-mode` | `dark` or `light`; unset is `auto` (follows the reader's system, set at build) |
| `data-tb-density` | `compact`; unset is comfortable |
| `data-tb-width` | `full` drops the reading-width cap (a sidebar wants it) |

**The masthead** — every page opens with one:

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

The kicker is the model's label: leave it out and the build adds
`<p class="tb-kicker">` with the label of the model the bindings read; write
one to say something else. The `<h1>` is the report's name or its finding.
`data-tb-title` is `left`, `center`, `banner` (accent band) or `nav` (moved
to the top of a sidebar). `data-tb-period` names what the numbers cover; it
is a label, so it may hold a year. The runtime fills the meta line: the
period, the build time from the receipt (never type a date) and the verdict
chip; whichever the template leaves out, it adds.

The chip's state is `data-tb-verdict`, set by the runtime from the file
itself, never from the page's markup: `draft` on a working preview (no
receipt), `not-checked` on a built file — nothing has re-run its queries;
`tracebi verify` does, and says whether each figure reproduces. The four
verdicts, everywhere TraceBi shows one, are `reproduces` (green, `--tb-good`),
`needs-a-look` (amber, `--tb-warn`), `does-not-reproduce` (red, `--tb-bad`)
and `not-checked` (neutral). A page never makes it green. In a built file the
runtime puts a "Receipt" button after the chip and makes the chip open the
receipt too (the receipt drawer, below).

The mark is empty by default. To show a logo, put the file in the package's
`assets/` and size it in `style.css`:
`.tb-masthead-mark { width: 120px; height: 28px; margin-bottom: 16px;
background: url(assets/logo.svg) left / contain no-repeat; }`. A look for every
report in the project goes in `reports/_theme.css`. (`.tb-title`, the older
title block, still works.)

A report's look beyond that is a theme preset: `tracebi theme use <name>`, or
in `style.css` the accent pair for each ground (`--tb-accent` /
`--tb-accent-text` and `--tb-dark-accent` / `--tb-dark-accent-text`) and at
most one display face for the headline and the lead number. The showcase's
`style.css` is exactly that: Fraunces from `assets/fonts/` on
`.tb-masthead h1` and `.tb-kpi--lead .tb-kpi-value`, and a teal accent. No
gradient, no shadow, no second set of components.

**The footer** — every page ends with one:

```html
<footer class="tb-footer" data-tb-methodology>
  <p>Source: the funds' Schedules of Investments.</p>
</footer>
```

Your sources come first. The build adds one line — when the file was built and
from which model, by its label ("Built 18 Oct 2026 · Direct Lending Portfolio."),
and *"The receipt does not claim the numbers are right."* —
then "How these numbers were made" behind a `<details>`: what the receipt is
for, and the stated methodology (below). A template with no
`data-tb-methodology` gets the whole footer at the end of the page. The
runtime adds "Open the receipt" to that line.

**The receipt drawer** — every built page carries one; you write nothing for
it. It opens from the masthead's "Receipt" button or its verdict chip, the
footer's line, a click on any value figure (at that figure's row), or a
chart tooltip's "Receipt →"; Escape closes it. A page with no masthead keeps
a floating "Receipt" button instead. It reads as a certificate: the report,
when it was built and from which model, the verdict chip, *"The receipt does
not claim the numbers are right."*, how to check the file
(`tracebi verify --file <name>.html`, with its `.manifest.json` beside it),
then one row per figure in page order — the value as the page shows it (or
"table, 13 rows" / "chart, 6 rows"), its label, the measure's definition from
the model, the query in one line (`fair_value by dim_issuer.sector · order
fair_value desc`, only the ordering keys you wrote), the fingerprint's first
8 characters with Copy — and "Raw" (the query exactly as run, the full
fingerprint) behind a disclosure. "About this build" closes it: the sink
contracts, the stated methodology, who built it, the render stamp and git.
It is 420px on the right, a full-height sheet on a phone, and prints as an
appendix with every disclosure open. Its badges keep their own tones; a theme
never recolours them.

## Editorial

A report written to be read — what `tracebi new-report` writes by default.
A sheet on the page, opened by the hero; the prose in one serif column of
about 68 characters (a system face; nothing is fetched; `--tb-measure`), and
figures, tables and a KPI strip (`.tb-grid` of `.tb-kpi`) at the sheet's full
width. With no `style.css` this is the page: one accent, no texture, no
shadow.

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

The hero is the masthead in the editorial's register: the project's accent,
flat, with a serif headline (on a dark ground, a deep band of the accent with
the page's ink). A number in the prose is bound and set in weight 600, in the
prose's own ink. Charts, tables, the KPI strip, the pull-stat and the footer
keep the sans face, so numbers read as data; the methodology is in the
receipt, behind the footer's link. To restyle it, set the accent pairs
(`--tb-accent` / `--tb-dark-accent` and their `-text`), not a colour of its own. The writing advice is `tracebi knowledge
design-editorial-report`.

## Stage blocks

```html
<section data-tb-stage="exploration"> … </section>
```

Exploration content is **deleted** at final build. Use it to keep scratch
queries beside the page while iterating with `tracebi dev`.

## Stated methodology

```html
<footer class="tb-footer" data-tb-methodology> your sources … </footer>
```

One per page, on any container. Your children stay first; the build appends
the footer's line and, behind "How these numbers were made", the pipeline's
stated methodology — transform notes, per-check rationale, measure
descriptions. It is an appendix, never a claim: no badge, no status.

## Reading data in `script.js`

```js
tracebi.ready(function (data) { /* … */ });
```

**Never call `tracebi.data()` at the top level.** A large-detail artifact
decodes its data in a worker *after* `script.js` runs, so a bare call returns
`[]` there and rows on a small report. `ready(fn)` behaves the same on both.

Sorting and slicing belong in the query (`order_by` + `limit`, see
[[queries]]), never in JS — that moves ordering out of the receipt.

## Related

- [[figure-helper]] — declare figures instead of writing this
- [[styling-a-report]] — the CSS stack and design tokens
- [[report-json]] — where bindings are declared
