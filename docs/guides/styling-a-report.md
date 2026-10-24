# Styling a report

**Your CSS and JS, unrestricted — plus a design system you can lean on instead
of fighting.**

---

## The stack

Three layers, later wins:

```
1. tracebi.css            the shipped design system
2. reports/_theme.css     your project brand layer   (optional)
3. style.css              this report                (optional)
```

**Override tokens; don't fork the sheet.** Redefining a token restyles every
component coherently; copying the stylesheet means inheriting every future fix
by hand.

## Design tokens

```css
:root {
  --tb-accent:      #2e74b5;
  --tb-accent-text: #1f5a96;   /* the same blue, deep enough for small text */
  --tb-ink:         #0a1628;
  --tb-bg:          #eef2f8;
}
```

Out of the box a report is Hanken Grotesk on neutral grounds with one cobalt
accent and hairline cards: the same look as the web app. The face is inlined into
the file (about 45 KB, Latin subset), so nothing is fetched and nothing needs installing;
set `--tb-font` to use your own face instead.

| Token | Controls |
| --- | --- |
| `--tb-font` / `--tb-mono` | the type family, and the one for code |
| `--tb-ink` / `--tb-muted` | text |
| `--tb-page` / `--tb-bg` / `--tb-surface` | the page, cards and tables, raised tints |
| `--tb-accent` / `--tb-accent-text` | the accent (focus ring, bars, the first chart series, the editorial hero), and the same blue deepened for small text (links, hovers): override both |
| `--tb-dark-accent` / `--tb-dark-accent-text` | the same pair for the dark ground; set them too, or dark mode keeps the default cobalt |
| `--tb-text-xs` … `--tb-text-3xl` | the type scale: 12, 13, 14 (body), 16, 20, 28, 40px; `--tb-tracking-tight` from 28px up |
| `--tb-good` / `--tb-bad` | direction: better and worse |
| `--tb-rule` | borders and rules |
| `--tb-shadow` | none; the sheet draws no resting shadow (cards are a hairline). Left for a report's own CSS |
| `--tb-radius`, `--tb-space-1..4` | shape and rhythm |
| `--tb-cell-pad` | table density, in one place |
| `--tb-measure` | the editorial's reading column: 68ch of its serif body |
| `--tb-chart-1..8` | the chart palette; `--tb-chart-1` is the accent |

Setting the accent pairs in `reports/_theme.css` is usually all a house style
needs: the first chart series, links, the hero and the active tab follow it.
The shipped themes (`tracebi theme list`) are exactly that, an accent preset
for each ground.

**Modes.** A page follows the reader's system by default: the build gives a
`<html>` with no `data-tb-mode` the value `auto`. Set `data-tb-mode="light"`
(or `"dark"`) to pin it; an app sets `report.json` `"look"`. A report whose own
`style.css` paints a light ground (a fixed paper colour, a light-only palette)
should pin `light` until it styles the dark ground too.

## Components

```
.tb-page                     the page measure, 1,200px
.tb-masthead                 opens the page: .tb-kicker, <h1>, .tb-standfirst,
                             .tb-masthead-meta (period, build time, .tb-verdict)
.tb-footer                   ends the page: your sources, then the build's line
.tb-grid   .tb-card
.tb-span-4 / -6 / -8 / -12   the 12-column grid: a .tb-grid's panels name a span
.tb-lede                     the answer sentence under the masthead
.tb-kpi  (.tb-kpi-label / .tb-kpi-value / .tb-kpi-context)
.tb-kpi--lead                the strip's main number: larger, not wider
.tb-kpi-delta                a stamped change leading the context line
.tb-spark                    a line/area chart in a KPI: the trend's shape alone
.tb-table  (.tb-table--striped / .tb-table--compact / .tb-table--freeze)
.tb-callout   .tb-note   .tb-badge
.tb-good / .tb-bad           direction tones; pair with a sign or a word
.tb-cols-2 / .tb-cols-3      shorthands: equal columns, one under 720px
.tb-tabs                     with data-tb-tab sections
```

Use them or ignore them — [[template-html|`template.html`]] is your page, and
nothing requires these classes.

A typical top of page, built only from these:

```html
<header class="tb-masthead" data-tb-period="End of August">
  <h1>Fund book</h1>
  <p class="tb-standfirst">The book at fair value, by sector and fund.</p>
</header>
<p class="tb-lede">
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="dim_issuer.sector" id="top-sector">—</span>
  is the largest sector, at
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="fv_share" data-tb-format="percent" id="top-share">—</span>
  of the book.</p>

<div class="tb-grid">
  <div class="tb-kpi tb-kpi--lead">
    <span class="tb-kpi-label">Fair value</span>
    <span class="tb-kpi-value" data-tb-figure="value" data-tb-binding="kpis"
          data-tb-cell="fair_value" data-tb-format="compact" id="kpi-fv"></span>
    <span class="tb-kpi-context">
      <span class="tb-kpi-delta" data-tb-figure="value" data-tb-binding="kpis"
            data-tb-cell="fv_growth" data-tb-format="percent" data-tb-direction="up-good"
            id="kpi-fv-growth"></span> vs last month</span>
  </div>
</div>
```

The `data-tb-*` attributes are covered in [[template-html]]. Here `fv_share` is
a `share=` measure and `fv_growth` a `growth=` measure ([[measures]]), so the
comparison is a governed number with its own trace. `data-tb-direction` draws
the ▲/▼ and picks `--tb-good` or `--tb-bad` from that number's sign.

## What you get without writing CSS

- Numbers right-align in table columns, in tabular digits, and never wrap.
- A value figure with no `data-tb-format` gets the model's declared format, or
  a readable default ([[number-formats]]).
- Keyboard focus is always visible, headings wrap evenly, and running text
  stops at a readable line length.
- An empty table or chart says "no data" instead of showing a blank.
- Printing keeps the trace, the badges and every tab's content.
- The trace drawer doesn't animate for people who've turned motion off.

## Design guidance

The framework ships design lessons next to its analysis lessons. List them with
`tracebi knowledge` (the design ones start `design-`) and read one with
`tracebi knowledge design-lead-with-the-answer`. They cover leading with the
answer, KPIs with context, choosing the chart, color, number formats, tables,
layout and spacing, hierarchy, the words on the page, theming with tokens,
empty states and accessibility. Agents that load skills get the same review as
the `tracebi-designer` skill.

`tracebi spec validate` also warns about common design problems in a JSON spec,
such as unsorted bar charts or more than five KPI cards, and names the lesson
that explains the fix.

## The one rule

**Presentation never changes a number.**

A stylesheet may restyle a `.tb-badge`; it may never re-colour honesty.
Provenance chooses the badge class — `--verified` / `--derived` /
`--unverified` — and CSS cannot move a figure between them.

Likewise [[number-formats|derived formats]] change how a number is *displayed*,
never its value.

## Writing `script.js`

```js
tracebi.ready(function (data) {
  // data is the stamped rows, already decoded
});
```

**Never call `tracebi.data()` at the top level.** On a large-detail artifact the
data decodes in a worker *after* `script.js` runs, so a bare call returns `[]`
there and rows on a small report. `ready(fn)` behaves identically on both.

Two things that belong in the query, not in JS:

- **Sorting and slicing** — `order_by` + `limit` ([[queries]]). Sorting in JS
  moves the ordering out of the trace. If readers should re-sort a table,
  add `data-tb-sort` to it: the query's order stays the default, and the
  reader's clicks only reorder the stamped rows.
- **Aggregation** — never in `script.js`. A figure's number is only ever a
  query result: a filter re-runs the binding's own query on the page; a sum in
  your script is a number nobody can re-run.

## What you cannot load

The artifact ships with a strict CSP and is meant to work offline, on a plane,
from an email attachment. So:

- **no CDN scripts, stylesheets, fonts or images**
- **no `fetch`/XHR** — `connect-src 'none'`

Everything must be inlined at build time. That constraint is what makes the file
self-contained and the offline `verify --file` check meaningful.

Charting is inlined for you when the page has a chart figure. `"libs":
["echarts"]` in [[report-json]] is optional.

## Fonts and images

Put them in the package's `assets/` folder and reference them by relative path.
The build inlines each one as a `data:` URI, so the file still fetches nothing:

```css
@font-face {
  font-family: "Fraunces";
  font-weight: 600;
  src: url(assets/fonts/fraunces-latin-600-normal.woff2) format("woff2");
}
.tb-masthead h1, .tb-kpi--lead .tb-kpi-value { font-family: "Fraunces", var(--tb-font-serif); }
.tb-masthead-mark { width: 120px; height: 28px; background: url(assets/logo.svg) left / contain no-repeat; }
```

```html
<img src="assets/logo.svg" alt="Company">
```

Allowed types: woff2, woff, ttf, otf, svg, png, jpg, webp, gif, avif. A missing
file, any other type, or a path outside `assets/` fails the load with the file
named. Keep images small: every byte ships inside the report. Check a font's
licence allows embedding (SIL OFL fonts do; ship the licence text alongside).

`examples/portfolio_project/reports/portfolio_model/portfolio_showcase/` shows it all on
the system: a `style.css` that is a theme preset (an accent pair and one
inlined display face), every chart type, a KPI delta, data bars, sortable
columns, filters, a scenario and a custom d3 figure. `reports/wealth_model/aum_by_branch`
is the one bespoke look (its own faces, palette and hero band
with inlined artwork) on the same masthead, grid, footer and trace.

## Related

- [[template-html]] — the markup
- [[web-customization]] — theming the served web UI (a different surface)
- [[number-formats]] — display defaults
