---
slug: design-format-for-reading
title: Format numbers and labels for the reader, not for the database
when: setting number formats, axis/column labels, or chart labelling on a figure
---
**The pitfall.** `DIM_ISSUER.SECTOR` as a column header, `1705495.2200000002` in
a cell, a y-axis reading 0 to 2,000,000 in steps of 250,000, and a legend
off to the side that the eye has to keep returning to. All correct, all tiring.
A generated report shows its plumbing unless someone formats it.

**The correct pattern in TraceBi.**

- **Let the derived defaults do the easy part** — TraceBi already turns
  `dim_issuer.sector` into "Sector" and gives numbers separators and sensible
  decimals. Don't undo it with raw overrides.
- **Declare the format on the measure, once**: `format="currency0"`,
  `"percent"`, `"compact"`. Every figure that uses the measure then agrees.
  Override per figure only when the context needs it (`data-tb-format`).
- **Compact on charts, precise in tables.** Axes and chart labels use
  `data-tb-value-format="compact"` ("1.7M"); the table beneath carries the
  exact figure. A reader scanning a chart doesn't need cents.
- **Consistent precision in a column.** One decimal place throughout, or none —
  never 12.5% next to 8%.
- **Units live in the label, not in every cell**: a header "Fair value ($M)"
  beats "$1.7M" repeated forty times.
- **Label directly where you can.** A two-series line with each line labelled at
  its end reads faster than a legend.

**The tell.** If a label contains a dot, an underscore or a table prefix, it's a
column name, not a label. If you have to count digits, the format is wrong. The
naming, formats and fraction guard are in the styling and number-format docs;
units that a column name can't state belong in the model (a `_bps` suffix,
not a bare decimal).
