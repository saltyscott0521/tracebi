---
slug: design-color-with-meaning
title: Color is for meaning — one accent, quiet greys, and the verdict colors left alone
when: choosing chart colors, styling cards or badges, or writing style.css / _theme.css
---
**The pitfall.** Every series a different saturated color; a gradient on each
card; green and red used for decoration. Color then carries no information, so
the one thing that *should* stand out can't. Worse, green and red already mean
something in a TraceBi report — reproducible and altered — and decorative use
muddies the receipt's own language.

**The correct pattern in TraceBi.**

- **One accent, used to point.** Neutral grey for the context, the accent for the
  thing the title is about — the sector that grew, the fund that missed. Set it
  once with the design tokens (`--tb-accent`, `--tb-chart-1..8` in
  `reports/_theme.css`) so every chart follows.
- **Categorical color only when the category is the point** (`data-tb-color` on
  a chart), and then at most five or six. Past that, colors stop being
  distinguishable; sort and label instead (see [[design-choose-the-chart]]).
- **Green, amber and red belong to the verdict.** The receipt's badges use them
  for *reproducible / derived / unverified*. Don't reuse them for "good / bad"
  styling, and never restyle a badge to change what it says — provenance
  chooses the badge class, presentation cannot.
- **Sequential data gets one hue, light to dark.** A rainbow scale for "low to
  high" reads as categories.
- **Check it in both themes and in greyscale.** If the point disappears in
  greyscale, it was carried by hue alone; add a label or position.

**The tell.** Count the colors on the page. More than an accent, a grey, and the
series you genuinely need to tell apart means color is decoration. See
[[design-cut-the-chrome]].
