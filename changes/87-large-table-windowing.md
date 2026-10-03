### Changed — Large tables render only the visible rows

- A table figure with more than 500 rows paints the visible window (plus a
  small overscan) inside its scroll box. Sort, filter, search, bars, totals,
  and a selection recompute all go through that same row set. Printing and
  download still use every row. Find-in-page cannot see rows outside the
  window; `data-tb-search` can. A table of 500 rows or fewer is unchanged.
