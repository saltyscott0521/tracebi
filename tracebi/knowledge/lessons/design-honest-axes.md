---
slug: design-honest-axes
title: A chart's shapes must be true to its numbers — bars from zero, no 3D, no area for size
when: choosing a chart for a comparison, or a reader might judge size by length, height or area
---
**The pitfall.** A bar chart whose axis starts at $500,000 makes one bar look
four times another when it's less than double. A 3D column hides its own top.
A bubble sized by radius makes a value twice as big look four times as big.
Readers judge the picture before they read the axis — so a chart whose shapes
misstate the ratios misleads even with every label correct. Truncated axes are
the most common device in deliberately misleading charts, and an accidental one
does the same damage.

**What TraceBi does for you.**

- **Every chart's value axis includes zero**, so bar and column lengths are
  always proportional to their values. There is no setting to truncate it.
- **There is no 3D chart type**, and pie charts refuse negative values.

**What you still have to do.**

- **A line whose movement is small is flattened by the zero baseline.** Don't
  go looking for an axis override — chart the change instead: a `growth`
  measure (percent change) or a variance around zero
  ([[design-show-the-difference]]) puts the movement on its own scale, honestly.
- **Never encode quantity by area** — no sized circles or icon arrays for
  amounts. Length on a common baseline (a sorted bar) is what people judge most
  accurately.
- **Compare on one scale.** Two charts meant to be compared side by side should
  show the same measure; if the ranges differ wildly, say so in the title rather
  than letting the reader assume equal scales.
- **Don't let precision imply accuracy.** An estimate plotted to the cent reads
  as exact. Round it, and mark it `data-tb-unverified` with the reason if it
  isn't query-backed.

**The tell.** Cover the axis labels. If what the shapes say differs from what
the numbers say, the chart is lying — even if every label is correct.
