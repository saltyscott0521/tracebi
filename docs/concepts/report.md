# Report — phase ③

**A package where every figure is a live query. One command turns it into a
single self-contained HTML file plus a [[receipts|receipt]].**

Lives in `reports/`.

---

## The shape

```
reports/my_report/
  report.json      what data this report binds        → [[report-json]]
  template.html    the page you draw                  → [[template-html]]
  style.css        optional — your CSS
  script.js        optional — your JS
  report.py        optional escape hatch
```

**You own the page.** The framework does not impose a layout, a component set,
or a stylesheet you must work around. `template.html` is ordinary HTML; a
handful of `data-tb-*` attributes turn elements into figures.

There is exactly one renderer: a report is always built from its package. (A
`reports/<name>.json` spec is a shorthand that compiles into exactly this.)

## What "every figure is a live query" means

A figure never contains a typed-in number. It names a **binding** — a query
declared in `report.json` — and the framework resolves it, fingerprints the
result, embeds the bytes, and fills the figure from them.

The consequences are the point:

- **A hard-coded number cannot be a figure.** There is no way to bind a literal
  to a figure and have it read as governed — the honest mark
  (`data-tb-unverified`) is the only alternative, and there is no third state.
- **The page and the receipt cannot disagree**, because the page draws from the
  same fingerprinted bytes the receipt covers.
- **Re-rendering is milliseconds**, because the [[model]] is already
  materialized. No pandas runs.

## Build it

```bash
tracebi report build my_report
```

Produces one offline HTML — CSS, JS, data and charting library all inlined, a
strict CSP, no CDN — plus `my_report.html.manifest.json`.

Email it, archive it, open it on a plane. Then:

```bash
tracebi verify --file output/my_report.html
```

## Interactivity, and its one rule

Filters, search, tabs, scrolling tables and CSV download all ship. They
**subset which stamped rows a figure displays. They never compute new numbers.**

Client-side aggregation would mint numbers nobody can re-run, so a filtered KPI
needs its own binding, and value figures never react to controls. See
[[template-html#Interactivity]].

## When the query surface isn't enough

Add `report.py` with a `build(inputs) -> {name: DataFrame}` function. Its
**inputs** stay stamped and green-eligible; its **outputs** are permanently
`verifiable: false` and never read green.

That asymmetry is deliberate — see [[receipts#Unverifiable figures]]. Reach for
it only when the [[model]] genuinely cannot express the number, because
everything you compute here leaves the receipted lane.

## Related

- [[report-json]] · [[template-html]] · [[figure-helper]]
- [[styling-a-report]] — the CSS stack
- [[your-first-report]] — the walkthrough
