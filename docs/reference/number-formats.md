# Number formats

**Named formats you apply to a figure, plus the defaults TraceBi derives when
you don't.**

---

## The named formats

Use these as `format` in [[figure-helper]], or `data-tb-format` /
`data-tb-value-format` in [[template-html]].

| Name | Renders `1705495.22` as |
| --- | --- |
| `currency` | `$1,705,495.22` |
| `currency0` | `$1,705,495` |
| `comma` | `1,705,495` |
| `decimal` | `1,705,495.22` |
| `percent` | applies to a fraction: `0.069` → `6.9%` |
| `compact` | `1.7M` (`550.7B` at scale) |

`compact` is the right default for chart axes and tooltips, where space is
tight.

## Derived defaults

If you set no format, TraceBi fills one in from what the query already knows —
so `dim_branch.region` renders as **Region** and `1705495.2200000002` renders
as **1,705,495.22**.

Preference order, first match wins:

1. the format **you** set on the figure
2. a format the **model declares** on that measure
3. a **column-name hint** — a `_pct` suffix
4. **shape** — whole numbers get separators, fractional ones two decimals

Columns named like `year`, `id`, or `*_key` get **no** format: a separator
would render 2024 as `2,024`.

## The percent guard

The `_pct` name hint is unit-aware, and it is the only rung that is.

Both conventions exist in real data — a declared ratio measure holds `0.069`,
a hand-computed `pct_change().mul(100)` holds `12.5`. So the hint applies
**only when every non-null value is fraction-shaped** (`|v| <= 1.5`).
Otherwise the column falls through to the shape default and keeps its own
magnitude with no `%`.

A format the model declares still wins over this guard, because a model saying
`format="percent"` is a statement, not a guess.

> **The rule underneath:** a presentation default must never change the number
> it presents.

The guard is shape-based, so it cannot see a pre-scaled column whose values
happen to be small — a fund fee of `0.0945` meaning 0.0945% is
indistinguishable from a fraction. Store such a column in a unit its **name**
states, e.g. `expense_ratio_bps`.

## Two things worth knowing

- **Excel derives nothing.** `ExcelRenderer` applies only explicit formats, so a
  stored convention chosen to please the HTML renderer lands unformatted in the
  spreadsheet. Check both if you change data.
- **Opt out entirely** with `HTMLRenderer(derive_defaults=False)` for raw output.

## Why this exists

Raw defaults are a trap that scales badly. A human authoring one report sees
`DIM_BRANCH.REGION` and fixes it; an agent composing at volume, with nobody
reading the output, does not.

## Related

- [[figure-helper]] — where `format` is declared
- [[measures]] — declaring a format on a measure
