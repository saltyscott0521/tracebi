# Number formats

The named formats you can give a figure, and the defaults TraceBi picks when
you give none.

```html
<span data-tb-figure="value" data-tb-binding="totals"
      data-tb-cell="fair_value" data-tb-format="currency0"></span>
```

Use a name as `format` in [[figure-helper]], or as `data-tb-format` or
`data-tb-value-format` in [[template-html]].

## Named formats

| Name | `1705495.22` renders as |
| --- | --- |
| `currency` | `$1,705,495.22` |
| `currency0` | `$1,705,495` |
| `comma` | `1,705,495` |
| `decimal` | `1,705,495.22` |
| `percent` | For a fraction: `0.069` → `6.9%` |
| `compact` | `1.7M` (`550.7B` at scale). Good for chart axes and tooltips. |
| `currency_compact` | `$1.7M` (`-$6.3M` for a loss). Good on a KPI card or in a sentence. |

## Defaults

With no format set, TraceBi derives one: `dim_branch.region` renders as
**Region**, and `1705495.2200000002` as **1,705,495.22**. The first match
wins:

1. the format set on the figure;
2. a format the model declares on the measure;
3. a column-name hint: a `_pct` suffix;
4. the value's shape: whole numbers get separators, fractions two decimals.

Columns named like `year`, `id` or `*_key` get no format, so 2024 never
renders as `2,024`.

A text column whose every value is a month (`2024-01`, as a model's month
grain writes it) reads **Jan 2024** in tables, on chart axes and readouts, and
in a range's pickers. Only the words change: the value stays the row's own, so
it sorts, filters, selects and fingerprints as built.

A pie's or a funnel's legend names each slice's value, the row's own number in
the chart's format. A share is shown only when the binding returns one (a
`share` measure); the page never works one out.

This applies to table columns and value figures alike. A KPI with no
`data-tb-format` reads `4,846.10`, not `4846.1`. The server and the browser
use the same rule, so the number doesn't change when the page finishes
loading.

## The `_pct` hint

A presentation default must never change the number it presents. Real data
stores percentages two ways: a declared ratio holds `0.069`, a hand-computed
`pct_change().mul(100)` holds `12.5`. So the `_pct` hint applies only when
every non-null value is fraction-shaped (`|v| <= 1.5`). Otherwise the column
falls through to the shape default and keeps its own magnitude, with no `%`.

A format the model declares still wins over this check: `format="percent"` on
a measure is a statement, not a guess.

The check looks only at the values, so it cannot spot a pre-scaled column
whose values happen to be small: a fee of `0.0945` meaning 0.0945% looks like
a fraction. Store such a column in a unit its name states, e.g.
`expense_ratio_bps`.

## Other renderers

| Renderer | Behaviour |
| --- | --- |
| `ExcelRenderer` | Applies only explicit formats and derives nothing. A convention chosen for the HTML page lands unformatted in the spreadsheet; check both when you change data. |
| `HTMLRenderer(derive_defaults=False)` | Turns derivation off and shows raw values. |
