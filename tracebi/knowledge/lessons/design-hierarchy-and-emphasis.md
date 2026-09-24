---
slug: design-hierarchy-and-emphasis
title: Emphasis works only by contrast — one thing per view is loud, everything else is quiet
when: styling a page's headings, KPI values, highlights or callouts, or when every element on the page looks equally important
---
**The pitfall.** Every card has the same weight, every heading is bold, three
callouts are tinted, two KPIs are highlighted and the chart uses five saturated
colors. Nothing is emphasized because everything is. The reader scans the whole
page to find the one fact that matters, which is the work the design should have
done.

**The correct pattern in TraceBi.**

- **One loud element per view.** Usually that is the answer: the `.tb-lede`
  sentence under the title (see [[design-lead-with-the-answer]]) or the one KPI
  the question turns on. Something stands out only when the things around it are
  uniform, so keep the other cards identical and let the one differ.
- **Size and weight set the order before color does.** `tracebi.css` already
  steps this down: title → lede → KPI value → section heading → body → the muted
  `.tb-note` and `.tb-kpi-context`. Use those classes rather than a new font
  size. If you need a new level, the page probably has too many.
- **Use more than one signal on the element that matters**: position (top-left),
  size and weight. A color change alone is missed by a colorblind reader (see
  [[design-accessible-by-default]]).
- **Mute the rest on purpose.** Secondary figures take the muted ink; a
  highlighted bar or row goes in the accent while its neighbors stay grey (see
  [[design-color-with-meaning]]).
- **Whitespace is emphasis too.** A figure with room around it reads as more
  important than one packed between others. Space the page from the tokens (see
  [[design-grid-and-spacing]]), not with ad-hoc margins.

**The tell.** Squint at the page, or view it zoomed out to 25%. The one thing
you still see should be the answer. If you see a grid of equal boxes, or three
competing bright spots, the hierarchy is flat.
