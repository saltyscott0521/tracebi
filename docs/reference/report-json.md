# `report.json`

**The package declaration: what data a report binds, and which figures the
framework builds for it.**

Every report package is a directory under `reports/`:

```
reports/my_report/
  report.json      ← this page
  template.html    the page you draw          → [[template-html]]
  style.css        optional, your CSS
  script.js        optional, your JS
  report.py        optional escape hatch      → [[receipts#Unverifiable figures]]
```

---

## Minimal example

```json
{
  "name": "Portfolio Overview",
  "data": {
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

## Keys

### `name` — string

The report's display title. Defaults to the directory name.

### `author` — string, optional

Recorded in the manifest as `rendered_by`.

### `description` — string, optional

Shown on the Reports page in the web UI.

### `data` — object, **required**

Maps a **binding name** to a query. A binding is the unit of trust: it is
resolved once, fingerprinted, embedded in the artifact, and recorded in the
receipt.

```json
"data": {
  "<binding_name>": {
    "model": "<model name>",
    "query": { ... }                  → [[queries]]
  }
}
```

Must be a non-empty object. Each entry must have `model` and `query`.

Figures refer to bindings by name — see [[template-html]] and [[figure-helper]].

### `figures` — object, optional

Figures the framework builds for you, placed in `template.html` with
`{{ figure("name") }}`. Full page: [[figure-helper]].

```json
"figures": {
  "total":  {"kind": "value", "binding": "totals", "cell": "revenue",
             "label": "Revenue", "format": "currency"},
  "detail": {"kind": "table", "binding": "by_sector"}
}
```

Omit it entirely if you hand-write your figure markup — both styles work, and
they produce the same bytes.

### `libs` — array, optional

Charting libraries to inline into the self-contained file. Currently only
`"echarts"`.

```json
"libs": ["echarts"]
```

**A package with charts must opt in**, or every chart panel renders
permanently blank. A data-only report omits it and ships smaller. An unknown
value is refused at load.

---

## What is checked, and when

Checked when the package **loads** (before any query runs):

| Rule | Refusal |
| --- | --- |
| top level is an object | `the top level must be an object` |
| `data` is a non-empty object | `needs a non-empty 'data' object mapping…` |
| each binding is an object with `model`/`query` | `data binding 'x' must be an object…` |
| `libs` ⊆ known libraries | `'libs' must be a list drawn from ['echarts']` |
| `figures` is an object | `'figures' must be an object mapping…` |
| a figure's `kind` is known | `has kind 'x'; expected one of [...]` |
| a figure's `binding` exists in `data` | `names binding 'x', which is not declared in 'data'` |
| a `value` figure has `cell` | `is a value figure and needs 'cell'` |

Checked when the report **builds**:

- every declared figure is placed in `template.html` exactly once
  ([[figure-helper#Refusals]])
- every figure's binding resolves against a registered model
- the query is valid against the model's grain and [[measures]]

> **Known gap.** Unknown keys are currently **ignored, not rejected** — a typo
> like `"figure"` for `"figures"` loads quietly with no figures declared, and a
> typo inside a figure entry falls back to a default. The `.json` spec format
> does reject unknown keys with a suggestion; the package format does not yet.

## Related

- [[template-html]] — the markup side
- [[figure-helper]] — declaring figures instead of hand-writing them
- [[queries]] — what goes inside `query`
- [[report]] — the concept
