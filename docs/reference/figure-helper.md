# `{{ figure("name") }}`

**Declare a figure in [[report-json]]; the framework builds the element, you
keep the layout.**

The middle ground between writing the [[template-html|`data-tb-*` grammar]] by
hand and giving up control of the page.

---

## Use it

Declare the figure:

```json
"figures": {
  "total": {"kind": "value", "binding": "totals", "cell": "revenue",
            "label": "Revenue", "format": "currency"}
}
```

Place it anywhere in your own markup:

```html
<section class="my-own-card">
  {{ figure("total") }}
</section>
```

Your CSS, your JS, your layout — untouched. The framework supplies only the
element, and the element it emits is byte-identical to what a compiled `.json`
spec would produce for the same declaration.

## Kinds

### `value` — a single number

```json
{"kind": "value", "binding": "totals", "cell": "revenue",
 "label": "Revenue", "format": "currency"}
```

| Key | Meaning |
| --- | --- |
| `cell` | **required** — the column to read, from row 0 |
| `label` | the caption shown beside the number |
| `format` | a named format → [[number-formats]] |

The binding must be a **one-row** query. A value figure over a multi-row
binding is refused at build: *"a value figure needs a one-row binding
(aggregate the query, or use a table figure)."*

### `chart`

```json
{"kind": "chart", "binding": "by_sector", "chart_type": "bar",
 "x": "dim_issuer.sector", "y": "fair_value", "value_format": "compact"}
```

| Key | Meaning |
| --- | --- |
| `chart_type` | `bar`, `barh`, `line`, `area`, `pie`, `scatter` (default `bar`) |
| `x` | the category column |
| `y` | the value column, or a list for multi-series |
| `color` | series/colour column |
| `palette` | explicit colour list |
| `value_format` | formats labels, axes and tooltips → [[number-formats]] |

Requires `"libs": ["echarts"]` in [[report-json]], or the panel renders blank.

### `table`

```json
{"kind": "table", "binding": "holdings", "columns": ["issuer", "fair_value"],
 "style": "striped"}
```

| Key | Meaning |
| --- | --- |
| `columns` | allowlist and column order |
| `style` | `striped` or `compact` |

### Not `custom`

A `custom` figure has no framework markup by definition — your `script.js`
draws it. Write and mark that one yourself; see [[template-html]].

## Figure ids

The declared name becomes the figure id: `total` → `fig-total`.

That id is the receipt's stable address for the number, and it is how a human
redirects you — *"fix `fig-total`"*. Name figures accordingly.

## Refusals

The helper is strict, because each of these failures is otherwise silent:

| You did | What happens |
| --- | --- |
| named a binding that isn't in `data` | fails when the package **loads** |
| declared a figure, never placed it | fails the **build** — a declared number must not vanish |
| placed the same figure twice | fails — one id addresses one number |
| called `figure("typo")` | fails, listing the declared names |

> **Jinja parses inside HTML comments.** Never write a `{{ figure(...) }}` call
> in a comment — it is still evaluated and will error.

## Related

- [[report-json]] — where figures are declared
- [[template-html]] — the markup this emits, and the hand-written form
- [[number-formats]] — `format` and `value_format` values
