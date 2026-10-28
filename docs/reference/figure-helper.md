# `{{ figure("name") }}`

Declare a figure in [[report-json]] and place it in your page with one call.
TraceBi builds the element; you keep the layout.

```json
"figures": {
  "total": {"kind": "value", "binding": "totals", "cell": "revenue",
            "label": "Revenue", "format": "currency"}
}
```

```html
<section class="my-own-card">
  {{ figure("total") }}
</section>
```

The element it writes is identical to what a compiled `.json` spec produces
for the same declaration, and to the `data-tb-*` markup you could write by
hand ([[template-html]]). Mix both styles freely.

## `value`

A single number.

```json
{"kind": "value", "binding": "totals", "cell": "revenue",
 "label": "Revenue", "format": "currency"}
```

| Key | Meaning |
| --- | --- |
| `cell` | Required. The column to read from the binding's one row. |
| `label` | The caption beside the number. |
| `format` | A named format ([[number-formats]]). |

The binding must be a one-row binding. Over a multi-row binding the build
fails: *"a value figure needs a one-row binding (aggregate the query, or use a
table figure)."*

## `chart`

```json
{"kind": "chart", "binding": "by_sector", "chart_type": "bar",
 "x": "dim_issuer.sector", "y": "fair_value", "value_format": "compact"}
```

| Key | Meaning |
| --- | --- |
| `chart_type` | `bar`, `barh`, `line`, `area`, `pie` or `scatter`. Default `bar`. |
| `x` | The category column. |
| `y` | The value column, or a list for several series. |
| `color` | The series column. |
| `palette` | A list of colours. |
| `value_format` | Format for labels, axes and tooltips ([[number-formats]]). |
| `renderer` | `svg` (the default) or `canvas`, for thousands of marks ([[report-json]] `charts`). |

The build inlines ECharts automatically when the page has a chart.

## `table`

```json
{"kind": "table", "binding": "holdings", "columns": ["issuer", "fair_value"],
 "style": "striped"}
```

| Key | Meaning |
| --- | --- |
| `columns` | Which columns, in order. |
| `style` | `striped` or `compact`. |
| `labels` | `{column: header}`, replacing the derived header. |
| `formats` | `{column: format}`: `compact`, `comma`, `currency`, `currency0`, `percent` or `decimal`, replacing the derived format. |

A `custom` figure has no generated markup: your `script.js` draws it. Write
and mark it yourself ([[template-html]]).

## Figure ids

The declared name becomes the id: `total` → `fig-total`. The trace uses the id
as the figure's address, and a reviewer uses it to point at a number ("fix
`fig-total`"), so choose names that say what the number is.

## Refusals

| You did | Result |
| --- | --- |
| Named a binding that isn't in `data` | Fails when the package loads. |
| Declared a figure and never placed it | Fails the build. A declared number must not vanish. |
| Placed the same figure twice | Fails. One id addresses one number. |
| Called `figure("typo")` | Fails, listing the declared names. |

Jinja evaluates `{{ figure(...) }}` even inside an HTML comment, so never put
one in a comment.
