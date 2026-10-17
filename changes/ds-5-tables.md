### Changed — tables: right-aligned numbers, a thin data bar, one totals row

- `data-tb-bars` draws a thin (6px) bar in a lane of its own after the
  number, in the accent at full strength (the dark accent on a dark ground,
  `--tb-bad` for a negative), instead of a translucent wash behind the text.
  The lane is inside the cell, so the bar follows its row on sort, filter and
  search, the CSV download is unchanged, and the header, the total and a
  blank keep the lane empty so the numbers stay in one column. The scale is
  as before: zero at the left, or in the middle when the column has
  negatives, over every stamped row. The no-JS view draws the same bars.
- A header inside a scroll box (`.tb-scroll`, the kit's `<Table>`) stays put
  with its rule while the rows scroll.
- One totals style, for a `<tfoot>` row or a `.tb-total`: a 2px rule at 60%
  ink above, weight 600.
- Headers are `--tb-text-xs`, cells `--tb-text-sm`, both in tabular
  numerals; density is `--tb-cell-pad` alone (`.tb-table--compact` no longer
  shrinks the type).
