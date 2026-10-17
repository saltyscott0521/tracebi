### Changed — one chart style

- Bars take 55% of their band, with a 2px radius on the free end, and carry
  their own values in the figure's format: inside the bar when every label
  fits (with 12px to spare, on a colour it reads on), past the end when not.
  None on bars under 14px wide, on stacks, in small multiples, or beside
  `data-tb-mark` points.
- Category names are never cut with "…": on `barh` they wrap to two lines
  and the margin grows to the longest line (up to 40% of the width); on
  `bar` they wrap while a band is 48px or wider and turn 30° below that. A
  name that still does not fit sets the whole axis smaller (to 9px).
- Value ticks thin to what fits (about one per 80px across, one per 50px
  up), in the same compact format. Gridlines are `--tb-grid` (6% ink, light
  and dark); no axis lines; one baseline at zero in `--tb-rule`.
- Lines are 1.5px with round joins and end in a dot and the last value
  (unless `data-tb-mark` labels the last); a point's dot shows under the
  pointer. An area is the series colour at 10%, no gradient.
- The tooltip adds the measure's description from the model and a
  "Receipt →" link that opens the receipt drawer at that figure's record. It
  waits a moment on leave so the link can be reached, and Tab from a
  focused chart reaches it.
- The showcase draws all six chart types (adds a `barh` of top issuers, an
  `area` of the governed cumulative share, and a `scatter` of size against
  mark).
