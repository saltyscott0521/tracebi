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
| `--tb-ink` / `--tb-bg` / `--tb-muted` | text and ground |
| `--tb-accent` | the accent |
| `--tb-rule` | borders and rules |
| `--tb-radius`, `--tb-space-1..4` | shape and rhythm |
| `--tb-chart-1..8` | the chart palette |

Setting `--tb-chart-1..8` in `reports/_theme.css` is usually all a house style
needs: charts follow it automatically.

## Components

```
.tb-page   .tb-grid   .tb-card
.tb-kpi  (.tb-kpi-label / .tb-kpi-value)
.tb-table  (.tb-table--striped / .tb-table--compact)
.tb-callout   .tb-note   .tb-badge
.tb-cols-2 / .tb-cols-3      responsive, collapse under 720px
.tb-tabs                     with data-tb-tab sections
```

Use them or ignore them — [[template-html|`template.html`]] is your page, and
nothing requires these classes.

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
  moves the ordering out of the receipt.
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

## Related

- [[template-html]] — the markup
- [[web-customization]] — theming the served web UI (a different surface)
- [[number-formats]] — display defaults
