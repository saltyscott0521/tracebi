### Added — stacked, marked, annotated, zoomable and faceted charts

New chart attributes for the D3 engine. None of them computes a number:
- `data-tb-stack` (bar, barh, area) stacks the series into one slot per
  category. The rows are laid end to end and no total is written; the tooltip
  lists each row's own value.
- `data-tb-x-title` / `data-tb-y-title` title the axes.
- `data-tb-mark="max,last"` (also `min`, `first`) circles and labels a series'
  own high, low, first or last row ("High 6.81").
- `data-tb-annotate="2008=Financial crisis; 2020=Pandemic"` draws a dashed
  rule and the author's note at each category.
- `data-tb-facet="column"` draws small multiples: one panel per value, on one
  shared scale and one category axis. The keyboard walk crosses every panel.

Line and area charts with 8 or more categories zoom by dragging across the
plot; double-click or **Reset zoom** returns. Scatter charts zoom the same
way on x. Long category axes (more than 16 categories) label every k-th one
flat instead of rotating them all, and area fills fade with a gradient.

The D3 bundle adds `d3-brush` (163 KB in all). The showcase's Overview tab
gains a small-multiples card.
