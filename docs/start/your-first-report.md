# Your first report

Change the query behind one number in the sample report, rebuild it, and see
the trace follow. Then start a report of your own.

## Before you begin

- The workspace from the [[quickstart]], with its transform run once

## 1. Open the report's data

Open `reports/sample_model/sample_dashboard/report.json`. The `measures` block
holds calculations that belong to this report. `big_orders` is the revenue of
orders of 10 units or more:

```json
"big_orders": {
  "column": "revenue",
  "agg": "sum",
  "filters": {"qty": {"gte": 10}},
  "format": "currency0"
}
```

The **Large orders** card on the page reads it through the `split` binding.

## 2. Change the query

Raise the threshold to 20 units:

```json
"filters": {"qty": {"gte": 20}}
```

Make the same change to `small_orders`, so the two still add up to revenue:

```json
"filters": {"qty": {"lt": 20}}
```

## 3. Rebuild

```bash
tracebi report build sample_model/sample_dashboard
```

Open `output/sample_model/sample_dashboard.html`. The **Large orders** card
shows the new number. Click it: the trace opens at that figure, with this
build's query and fingerprint.

## 4. Check it

```bash
tracebi verify output/sample_model/sample_dashboard.html.manifest.json
```

Every figure reads `REPRODUCES`, because the manifest now records the new
query. An older manifest would not match the new numbers.

## 5. Watch it live

```bash
tracebi dev sample_model/sample_dashboard
```

The app opens the report in Build mode. Edit `report.json` or `app.jsx` and
the page reloads. The panel beside it lists what changed on each save, the
data each figure reads, and **Checks**: figures with no data, bindings no
figure reads, and numbers typed outside figures.

## Start a report of your own

### 1. Create the package

```bash
tracebi new-report "Portfolio Book"
```

This creates `reports/portfolio_book/` with `report.json` and `template.html`,
bound to the first model it finds. Use `tracebi new-dashboard` instead for an
`app.jsx` dashboard ([[app-jsx]]): it lands in the project folder of the model
it reads, `reports/<model>/<name>/`, and says which; with more than one model,
name it with `--model <name>`.

### 2. Declare the data

Each entry under `data` is a binding: a named query against a model. The build
runs it once, fingerprints the result and records it in the trace.

```json
{
  "name": "Portfolio Book",
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

`totals` has no dimensions, so it returns one row. A KPI needs a one-row
binding.

### 3. Declare the figures

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

The build adds the chart library (Apache ECharts) when the page has a chart. See
[[figure-helper]] for every key.

### 4. Place them on the page

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body>
<main class="tb-page">
  <header class="tb-masthead">
    <h1>Portfolio Book</h1>
    <p class="tb-standfirst">The book at fair value, by sector.</p>
  </header>

  <div class="tb-grid">
    {{ figure("kpi_value") }}
    {{ figure("kpi_count") }}
  </div>

  <div class="tb-grid">
    <div class="tb-card tb-span-8">
      <h2>Fair value by sector</h2>
      {{ figure("sector_mix") }}
    </div>
    <div class="tb-card tb-span-4">
      <h2>Detail</h2>
      <input data-tb-search data-tb-binding="by_sector" placeholder="Search…">
      {{ figure("sector_tbl") }}
    </div>
  </div>

  <footer class="tb-footer" data-tb-methodology>
    <p>Source: the funds' Schedules of Investments.</p>
  </footer>
</main>
</body></html>
```

Place each declared figure exactly once. The build fails if one is missing or
placed twice. You can also write the `data-tb-*` attributes by hand
([[template-html]]); both produce the same page.

### 5. Bind the numbers in your prose

```html
<p>The book stands at
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="fair_value" data-tb-format="compact"
         id="prose-fv"></span>
   across
   <span data-tb-figure="value" data-tb-binding="totals"
         data-tb-cell="positions" data-tb-format="comma"
         id="prose-pos"></span>
   positions.</p>
```

A number typed into a sentence has no trace. A bound one gets its own row in
the trace.

### 6. Build, check and review

```bash
tracebi report build portfolio_book
tracebi verify output/portfolio_book.html.manifest.json
tracebi verify --file output/portfolio_book.html
tracebi report status portfolio_book
```

`tracebi report status` lists each figure as verified, python-derived or
unverified, then unused and failing bindings. It exits 1 on any binding error,
so CI can use it as a gate.

Wrap scratch work in `data-tb-stage="exploration"` while you iterate. The
final build removes it.

## If the build refuses

| Message | Fix |
| --- | --- |
| *a value figure needs a one-row binding* | Aggregate the query, or use a table figure. |
| *names binding 'x', which is not declared in 'data'* | Fix the typo, or add the binding. |
| *declares 'x' … but template.html never places it* | Add `{{ figure("x") }}`, or remove the declaration. |
| *figure('x') is placed more than once* | Declare a second figure. One id addresses one number. |
| A chart stays blank | Check `data-tb-x` and `data-tb-y` name columns of the binding. |
| *limit without order_by is refused* | Add an `order_by`. See [[queries]]. |

## Next

- Style the page: [[styling-a-report]]
- Add a measure to the model: [[measures]]
- Send or schedule the report: `tracebi report send` and `tracebi schedule` in [[cli]]
