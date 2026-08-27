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
- `data-tb-format` — see [[number-formats]]

The runtime fills a `.tb-kpi-value` child when one exists, otherwise the
element itself.

### Chart figures

`data-tb-type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`),
`data-tb-x`, `data-tb-y` (comma-list for multi-series), `data-tb-color`,
and `data-tb-value-format` for labels, axes and tooltips.

Requires `"libs": ["echarts"]` in [[report-json]].

### Table figures

`data-tb-columns` — a column allowlist and order. Classes
`tb-table--striped` / `tb-table--compact` restyle it.

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
one attribute, and each bound span becomes a verified figure in the receipt.

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

## Layout

- **Tabs** — `<div class="tb-tabs"><section data-tb-tab="Label">…</section></div>`;
  the runtime builds the tab bar from the labels.
- **Columns** — `.tb-cols-2` / `.tb-cols-3`, collapsing to one column under 720px.

## Stage blocks

```html
<section data-tb-stage="exploration"> … </section>
```

Exploration content is **deleted** at final build. Use it to keep scratch
queries beside the page while iterating with `tracebi dev`.

## Stated methodology

```html
<section data-tb-methodology> your own notes … </section>
```

One per page. Your children stay first; the build appends the pipeline's
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
