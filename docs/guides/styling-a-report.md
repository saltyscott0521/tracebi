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
  --tb-accent: #2e74b5;
  --tb-ink:    #0a1628;
  --tb-bg:     #eef2f8;
}
```

| Token | Controls |
| --- | --- |
| `--tb-font` | the type family |
| `--tb-ink` / `--tb-muted` | text |
| `--tb-page` / `--tb-bg` / `--tb-surface` | the page, cards and tables, raised tints |
| `--tb-accent` | the accent |
| `--tb-good` / `--tb-bad` | direction: better and worse |
| `--tb-rule` | borders and rules |
| `--tb-radius`, `--tb-space-1..4` | shape and rhythm |
| `--tb-cell-pad` | table density, in one place |
| `--tb-chart-1..8` | the chart palette |

Setting `--tb-chart-1..8` in `reports/_theme.css` is usually all a house style
needs: charts follow it automatically.

## Components

```
.tb-page   .tb-grid   .tb-card
.tb-lede                     the answer sentence under the title
.tb-kpi  (.tb-kpi-label / .tb-kpi-value / .tb-kpi-context)
.tb-table  (.tb-table--striped / .tb-table--compact / .tb-table--freeze)
.tb-callout   .tb-note   .tb-badge
.tb-good / .tb-bad           direction tones; pair with a sign or a word
.tb-cols-2 / .tb-cols-3      responsive, collapse under 720px
.tb-tabs                     with data-tb-tab sections
```

Use them or ignore them — [[template-html|`template.html`]] is your page, and
nothing requires these classes.

A typical top of page, built only from these:

```html
<h1>Fund book, end of August</h1>
<p class="tb-lede">
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="dim_issuer.sector" id="top-sector">—</span>
  is the largest sector, at
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="fv_share" data-tb-format="percent" id="top-share">—</span>
  of the book.</p>

<div class="tb-grid">
  <div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpis"
       data-tb-cell="fair_value" data-tb-format="compact" id="kpi-fv">
    <span class="tb-kpi-label">Fair value</span>
    <span class="tb-kpi-value"></span>
    <span class="tb-kpi-context">
      <span data-tb-figure="value" data-tb-binding="kpis" data-tb-cell="fv_growth"
            data-tb-format="percent" data-tb-direction="up-good" id="kpi-fv-growth"></span>
      vs last month</span>
  </div>
</div>
```

The `data-tb-*` attributes are covered in [[template-html]]. Here `fv_share` is
a `share=` measure and `fv_growth` a `growth=` measure ([[measures]]), so the
comparison is a governed number with its own receipt. `data-tb-direction` draws
the ▲/▼ and picks `--tb-good` or `--tb-bad` from that number's sign.

## What you get without writing CSS

- Numbers right-align in table columns, in tabular digits, and never wrap.
- A value figure with no `data-tb-format` gets the model's declared format, or
  a readable default ([[number-formats]]).
- Keyboard focus is always visible, headings wrap evenly, and running text
  stops at a readable line length.
- An empty table or chart says "no data" instead of showing a blank.
- Printing keeps the receipt, the badges and every tab's content.
- The receipt drawer doesn't animate for people who've turned motion off.

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
  moves the ordering out of the receipt. If readers should re-sort a table,
  add `data-tb-sort` to it: the query's order stays the default, and the
  reader's clicks only reorder the stamped rows.
- **Aggregation** — never. Client-side aggregation mints numbers nobody can
  re-run; a filtered KPI needs its own binding.

## What you cannot load

The artifact ships with a strict CSP and is meant to work offline, on a plane,
from an email attachment. So:

- **no CDN scripts, stylesheets, fonts or images**
- **no `fetch`/XHR** — `connect-src 'none'`

Everything must be inlined at build time. That constraint is what makes the file
self-contained and the offline `verify --file` check meaningful.

Charting is already inlined for you — opt in with `"libs": ["echarts"]` in
[[report-json]].

## Fonts and images

Put them in the package's `assets/` folder and reference them by relative path.
The build inlines each one as a `data:` URI, so the file still fetches nothing:

```css
@font-face {
  font-family: "Inter";
  src: url(assets/fonts/inter-latin-400-normal.woff2) format("woff2");
}
.hero { background: url(assets/contours.svg) center / cover, linear-gradient(125deg, #0a1330, #1b2f7a); }
```

```html
<img src="assets/logo.svg" alt="Company">
```

Allowed types: woff2, woff, ttf, otf, svg, png, jpg, webp, gif, avif. A missing
file, any other type, or a path outside `assets/` fails the load with the file
named. Keep images small: every byte ships inside the report. Check a font's
licence allows embedding (SIL OFL fonts do; ship the licence text alongside).

`examples/portfolio_project/reports/showcase/portfolio_showcase/` shows it all: two
typefaces, a hero with inlined artwork, pill tabs, in-cell bars, sortable
columns, and chart styling through `tracebi.configureChart`.

## Related

- [[template-html]] — the markup
- [[web-customization]] — theming the served web UI (a different surface)
- [[number-formats]] — display defaults
