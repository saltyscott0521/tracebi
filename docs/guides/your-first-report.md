# Your first report

**Author a report package end to end — from `tracebi new-report` to a verified
artifact.**

Assumes you have a [[model]] over a warehouse. If not, start with
[[quickstart]].

---

## 1. Scaffold

```bash
tracebi new-report "Portfolio Book"
```

Creates `reports/portfolio_book/` with `report.json` and `template.html`, bound
to the first model it finds.

There is deliberately **no `script.js` or `style.css`** yet. The runtime draws
every figure from the stamped bytes, so hand-rolling a CSV parser and a chart is
the classic wasted afternoon. Add them when you actually need them.

## 2. Declare the data

Open `report.json`. Each entry under `data` is a **binding** — the unit of
trust, resolved once, fingerprinted, and recorded in the receipt.

```json
{
  "name": "Portfolio Book",
  "libs": ["echarts"],
  "data": {
    "totals": {
      "model": "portfolio_model",
      "query": {"fact": "fact_holdings", "measures": ["fair_value", "positions"]}
    },
    "by_sector": {
      "model": "portfolio_model",
      "query": {
        "fact": "fact_holdings",
        "measures": ["fair_value"],
        "dimensions": ["dim_issuer.sector"],
        "order_by": ["-fair_value"]
      }
    }
  }
}
```

Note `totals` has **no dimensions** — it returns one row. A KPI needs a one-row
binding; a value figure over a multi-row binding is refused.

`"libs": ["echarts"]` is required for charts, or the panel renders blank.

→ [[report-json]] · [[queries]]

## 3. Declare the figures

Add a `figures` block and let the framework build the markup:

```json
"figures": {
  "kpi_value":  {"kind": "value", "binding": "totals", "cell": "fair_value",
                 "label": "Fair value", "format": "currency0"},
  "kpi_count":  {"kind": "value", "binding": "totals", "cell": "positions",
                 "label": "Positions", "format": "comma"},
  "sector_mix": {"kind": "chart", "binding": "by_sector", "chart_type": "bar",
                 "x": "dim_issuer.sector", "y": "fair_value",
                 "value_format": "compact"},
  "sector_tbl": {"kind": "table", "binding": "by_sector"}
}
```

→ [[figure-helper]]

## 4. Draw the page

`template.html` is yours. Place each figure where it belongs:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body>
<main class="tb-page">
  <h1>Portfolio Book</h1>

  <div class="tb-cols-2">
    <div class="tb-card">{{ figure("kpi_value") }}</div>
    <div class="tb-card">{{ figure("kpi_count") }}</div>
  </div>

  <div class="tb-card">
    <h2>Fair value by sector</h2>
    {{ figure("sector_mix") }}
  </div>

  <div class="tb-card">
    <h2>Detail</h2>
    <input data-tb-search data-tb-binding="by_sector" placeholder="Search…">
    {{ figure("sector_tbl") }}
  </div>
</main>
</body></html>
```

Every declared figure must be placed **exactly once**, or the build fails —
a declared number must not silently vanish.

> Prefer writing the attributes yourself? Do — [[template-html]] documents the
> grammar, and both styles produce identical bytes. Mix them freely.

## 5. Bind the prose

The highest-value habit in the whole file:

```html
<p>The book stands at
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="fair_value" data-tb-format="compact"
         id="prose-fv">—</span>
   across
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="positions" data-tb-format="comma"
         id="prose-pos">—</span>
   positions.</p>
```

Narrative prose is where hard-coded numbers hide. Here the honest path costs one
attribute — and each bound span becomes a verified figure in the receipt.

## 6. Iterate live

```bash
tracebi dev portfolio_book
```

Edit and the page reloads. `/__workbench` shows what each figure is bound to and
what it has earned. Wrap scratch work in `data-tb-stage="exploration"` — it is
deleted at final build.

## 7. Build and verify

```bash
tracebi report build portfolio_book
tracebi verify output/portfolio_book.html.manifest.json
tracebi verify --file output/portfolio_book.html
```

You want `✓ REPRODUCES` per figure. See [[receipts]] for what that does and
does not claim.

## 8. Check what it earned

```bash
tracebi report status portfolio_book
```

Per figure: verified, python-derived, or unverified — plus unused and failing
bindings. Exits 1 on any binding error, so CI can gate on it.

---

## Common refusals, and what they mean

| Refusal | Fix |
| --- | --- |
| *a value figure needs a one-row binding* | aggregate the query, or use a table figure |
| *names binding 'x', which is not declared in 'data'* | typo, or you forgot the binding |
| *declares 'x' … but template.html never places it* | add `{{ figure("x") }}`, or drop the declaration |
| *figure('x') is placed more than once* | declare a second figure; one id addresses one number |
| chart renders blank | add `"libs": ["echarts"]` |
| *limit without order_by is refused* | state the ranking → [[queries]] |

## Next

- [[styling-a-report]] — your own CSS and JS
- [[measures]] — add a measure instead of computing in Python
- [[cli]] — `report send`, `snapshot`, `preview`
