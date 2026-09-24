---
slug: design-fewer-columns
title: Detail tables show the few columns the job needs, with search first
when: adding a table figure — especially a detail or holdings table
---
**The pitfall.** A table that shows every column the query returned — twelve of
them, IDs and keys included — because that's what the binding had. The reader
scrolls sideways hunting for the two columns they came for. Filtering sits in a
dropdown they have to discover. This is how an export looks, not a report.

**The correct pattern in TraceBi.**

- **Choose the columns, in reading order**, with `data-tb-columns` (or `columns`
  on a declared figure). Aim for about five: the thing's name, the measure the
  page is about, and the one or two that explain it. Drop IDs, keys and anything
  the reader won't act on.

```html
<table data-tb-figure="table" data-tb-binding="holdings"
       data-tb-columns="dim_issuer.issuer,fair_value,fv_growth,dim_issuer.sector"></table>
```

- **Put the question's column first-left or sort by it.** If the page is about
  size, sort by size in the query (`order_by`), largest first.
- **Search first on a long table.** When a table runs past a screen, put a
  `data-tb-search` box directly above it. Finding a row by name is the most
  common thing a reader does with a detail table; don't make them open a menu.
  Add `data-tb-filter` dropdowns only for the one or two columns people actually
  slice by.
- **Let the table scroll, not the page.** Tables longer than `data-tb-rows`
  (default 10) scroll inside their card; keep that rather than setting
  `data-tb-rows="all"` on a 500-row table.
- **Keep the full data one click away.** `data-tb-download` exports the
  binding's full stamped CSV, every column — so trimming the view costs the
  reader nothing.

**The tell.** If the table is wider than the page, or has a column you'd have to
explain, it has too many columns. See [[design-format-for-reading]] for the
headers.
