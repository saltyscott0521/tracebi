# Style a report

Give a report your colours, fonts and layout by setting design tokens, using
the shipped components, and adding your own CSS and JavaScript.

## Before you begin

- A report package (`tracebi new-report` or `tracebi new-dashboard`)
- `tracebi dev <name>` running, so you see each change

Styles stack in three layers, and the later one wins:

```
1. tracebi.css            the shipped design system (Ledger)
2. the house theme        report.json "theme", else tracebi.yaml brand.theme
3. the brand              tracebi.yaml brand: accent, palette, font, logo
4. reports/_theme.css     your workspace's own tokens (optional)
5. style.css              this report (optional)
```

## 1. Pick a house theme

Three, each a whole look ([[chart-style]]): `ledger` (calm, institutional, the
default), `nightdesk` (dark, dense, monospaced numbers, for a desk or an
operations screen) and `signal` (bold, big numbers, for a board pack or a wall
screen). The workspace picks one in `tracebi.yaml` (`brand: {theme: signal}`,
[[tracebi-yaml]]); a single report in `report.json`: `"theme": "nightdesk"`
([[report-json]]). Your colours go in the brand (`brand: {accent: …, palette:
[…]}`), which layers over whichever theme. `tracebi theme list` shows them.

## 2. Set your own tokens

Override tokens in `reports/_theme.css` or a report's `style.css`. Don't copy
the stylesheet: a copy misses every later fix.

```css
:root {
  --tb-accent:      #2e74b5;
  --tb-accent-text: #1f5a96;   /* the same blue, dark enough for small text */
  --tb-ink:         #0a1628;
  --tb-bg:          #eef2f8;
}
```

By default a report uses Geist on neutral grounds, one cobalt accent and
hairline cards, like the web app. The font is inlined in the file (about
45 KB, Latin subset). Set `--tb-font` to use your own.

| Token | Controls |
| --- | --- |
| `--tb-font` / `--tb-mono` | The text font, and the font for code |
| `--tb-ink` / `--tb-muted` | Text colours |
| `--tb-page` / `--tb-bg` / `--tb-surface` | The page, cards and tables, raised tints |
| `--tb-accent` / `--tb-accent-text` | The accent (focus ring, bars, first chart series, editorial hero) and a darker shade for small text such as links. Set both. |
| `--tb-dark-accent` / `--tb-dark-accent-text` | The same pair on the dark ground. Without them dark mode keeps the default cobalt. |
| `--tb-text-xs` … `--tb-text-3xl` | Type scale: 12, 13, 14 (body), 16, 20, 28, 40px; `--tb-tracking-tight` from 28px up |
| `--tb-good` / `--tb-bad` | Better and worse |
| `--tb-rule` | Borders and rules |
| `--tb-shadow` | None by default (cards use a hairline); available to your own CSS |
| `--tb-radius`, `--tb-space-1..4` | Corner radius and spacing |
| `--tb-cell-pad` | Table density |
| `--tb-measure` | The editorial reading column: 68 characters of its serif body |
| `--tb-chart-1..8` | Chart palette; `--tb-chart-1` is the accent |

The accent pairs are usually all a house style needs. The first chart series,
links, the hero and the active tab follow them.

**Light and dark.** A page follows the reader's system by default
(`data-tb-mode="auto"`). Set `data-tb-mode="light"` or `"dark"` on `<html>` to
fix it; an app sets `report.json` `"look"`. If your `style.css` paints a light
background, set `light` until you style the dark one too.

## 3. Use the components

```
.tb-page                     the page width, 1,200px
.tb-masthead                 opens the page: .tb-kicker, <h1>, .tb-standfirst,
                             .tb-masthead-meta (period, build time, .tb-verdict)
.tb-footer                   ends the page: your sources, then the build's line
.tb-grid   .tb-card
.tb-span-4 / -6 / -8 / -12   the 12-column grid
.tb-lede                     the answer sentence under the masthead
.tb-kpi  (.tb-kpi-label / .tb-kpi-value / .tb-kpi-context)
.tb-kpi--lead                the main number: larger, not wider
.tb-kpi-delta                a stamped change at the start of the context line
.tb-spark                    a line or area chart inside a KPI
.tb-table  (.tb-table--striped / .tb-table--compact / .tb-table--freeze)
.tb-callout   .tb-note   .tb-badge
.tb-good / .tb-bad           better and worse; pair with a sign or a word
.tb-cols-2 / .tb-cols-3      equal columns, one column under 720px
.tb-tabs                     with data-tb-tab sections
```

None are required. A typical top of page:

```html
<header class="tb-masthead" data-tb-period="End of August">
  <h1>Fund book</h1>
  <p class="tb-standfirst">The book at fair value, by sector and fund.</p>
</header>
<p class="tb-lede">
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="dim_issuer.sector" id="top-sector"></span>
  is the largest sector, at
  <span data-tb-figure="value" data-tb-binding="top" data-tb-cell="fv_share" data-tb-format="percent" id="top-share"></span>
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

`fv_share` is a `share=` measure and `fv_growth` a `growth=` measure
([[measures]]), so the comparison has its own trace. `data-tb-direction` draws
▲ or ▼ and picks `--tb-good` or `--tb-bad` from the number's sign. The
attributes are in [[template-html]].

## 4. Add fonts and images

Put them in the package's `assets/` folder and reference them by relative
path. The build inlines each one, so the file still fetches nothing:

```css
@font-face {
  font-family: "Fraunces";
  font-weight: 600;
  src: url(assets/fonts/fraunces-latin-600-normal.woff2) format("woff2");
}
:root { --tb-font-display: "Fraunces", var(--tb-font-serif); }   /* headline and lead number */
.tb-masthead-mark { width: 120px; height: 28px; background: url(assets/logo.svg) left / contain no-repeat; }
```

```html
<img src="assets/logo.svg" alt="Company">
```

Allowed types: woff2, woff, ttf, otf, svg, png, jpg, webp, gif, avif. A missing
file, another type, or a path outside `assets/` fails the build with the file
named. Every byte ships inside the report, so keep images small. Check that a
font's licence allows embedding (SIL OFL fonts do; ship the licence text too).

## 5. Add JavaScript

```js
tracebi.ready(function (data) {
  // data is the stamped rows, already decoded
});
```

Don't call `tracebi.data()` at the top level. A large report decodes its data
after `script.js` runs, so a top-level call returns `[]` there. `ready(fn)`
works on every report.

Two things belong in the query, not in JavaScript:

- **Sorting and slicing.** Use `order_by` and `limit` ([[queries]]). For a
  table readers can re-sort, add `data-tb-sort`: the query's order stays the
  default and clicks only reorder the stamped rows.
- **Totals.** A figure's number is only ever a query result. A sum in your
  script is a number nobody can re-run.

## What happened

You get these without writing CSS:

- Numbers right-align in tables, use tabular digits and never wrap.
- A value with no `data-tb-format` gets the model's format, or a readable
  default ([[number-formats]]).
- Keyboard focus is visible, headings wrap evenly, and text stops at a
  readable line length.
- An empty table or chart says "no data".
- Printing keeps the trace, the badges and every tab's content.
- The trace drawer doesn't animate for readers who turned motion off.

## Rules

- **Styles never change a number.** A stylesheet can restyle a `.tb-badge`,
  but the badge class (`--verified`, `--derived`, `--unverified`) comes from
  the figure's provenance, and CSS cannot move a figure between them. Number
  formats change how a number is shown, never its value.
- **Nothing loads from outside the file.** The page has a strict content
  security policy and works offline: no CDN scripts, stylesheets, fonts or
  images, and no `fetch` or XHR (`connect-src 'none'`). The build inlines the
  chart library (Apache ECharts) when the page has a chart ([[report-json]]
  `libs` and `charts`).

## Design advice

`tracebi knowledge` lists TraceBi's lessons; the design ones start with
`design-`. Read one with `tracebi knowledge design-lead-with-the-answer`. They
cover leading with the answer, KPIs with context, choosing a chart, colour,
number formats, tables, layout, hierarchy, wording, themes, empty states and
accessibility. Agents that load skills get the same review from the
`tracebi-designer` skill. `tracebi spec validate` warns about common design
problems in a JSON spec, such as unsorted bar charts or more than five KPI
cards.

## Next

- See it all in one report: `examples/portfolio_project/reports/portfolio_model/portfolio_showcase/`
  uses a tokens-only `style.css` (one inlined display face, its own teal
  accent) with every chart type, a KPI delta, data bars, sortable columns,
  filters, a scenario and a custom D3 figure. `reports/wealth_model/aum_by_branch`
  has its own fonts, palette and hero artwork on the same frame.
- Restyle the web app itself: [[web-customization]]
