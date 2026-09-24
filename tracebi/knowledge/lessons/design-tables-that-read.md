---
slug: design-tables-that-read
title: A table is for looking things up — identify rows on the left, align numbers on the right, one format per column
when: placing a table figure, choosing its columns, labels, formats, density or totals row
---
**The pitfall.** The first column is a surrogate key, numbers are left-aligned
so digits don't line up, one column mixes "$1.2M" and "1,204,331.5", headers say
`dim_issuer.issuer`, and a 400-row table pushes the rest of the page off the
screen. The data is right. The table is unusable.

**The correct pattern in TraceBi.** Most of this is already the default. Know it
so you don't undo it.

- **The first column says what the row is**: the issuer, the fund, the month.
  Put a readable name there, not an id. Choose and order the columns with
  `data-tb-columns` (see [[design-fewer-columns]]).
- **Numbers align right, in tabular figures, and never wrap.** The runtime tags
  numeric cells `tb-num`, and `tracebi.css` right-aligns them with tabular
  digits and `nowrap`. Don't override `text-align` on a numeric column.
- **One format per column, the same precision all the way down.** Declare it on
  the measure (`format="currency0"`), or per table with
  `data-tb-formats="fair_value=currency0"`. The shape default already gives a
  whole column the same decimals (see [[design-format-for-reading]]).
- **Headers a person would write**: `data-tb-labels="dim_issuer.issuer=Issuer"`.
  Put the unit in the header ("Fair value, $") rather than in every cell.
- **A total that the model computed.** `data-tb-totals` points at a one-row
  binding, so a ratio's total is the ratio of the totals, never a sum of ratios.
  It steps aside while a filter is on.
- **Density is one token.** The default is comfortable. Add
  `class="tb-table--compact"` for dense reference tables, or set
  `--tb-cell-pad` in the project theme. Use `tb-table--striped` for wide tables
  that are read across a row, and plain hairlines for short ones.
- **Long tables scroll inside themselves**: `data-tb-rows` caps the visible
  rows, the header sticks, and `data-tb-search` goes above it. The download
  button still exports every stamped row.
- **Never merge cells or put two values in one cell.** A screen reader and the
  CSV download both need one value per cell.

**The tell.** Cover every column except the first: can you still tell what each
row is? Run a finger down a numeric column: do the decimal points line up?
