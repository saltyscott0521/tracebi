---
slug: design-layout-by-importance
title: Lay the page out by importance — overview first, related things side by side, detail last
when: arranging figures on a page, deciding what goes top-left, or splitting content into tabs
---
**The pitfall.** Figures placed in the order they were built, or to fill the
grid evenly. The logo and filter controls take the top-left; the one number
that matters is third row down; a chart and the table that explains it are on
opposite sides of the page. Readers scan a page in a predictable pattern —
across the top, then down the left — and a layout that ignores it hides its
own answer.

**The correct pattern in TraceBi.**

- **The top-left is the most valuable space. Give it the answer** — the title
  that states the finding and the one or two KPIs that prove it
  ([[design-lead-with-the-answer]]). Not a logo, not a filter bar.
- **Overview first, then narrow down, then detail on demand.** Top: the
  headline numbers. Middle: the charts that explain them. Bottom: the detail
  table, with search ([[design-fewer-columns]]). Controls sit directly above
  the figures they filter, not in a global bar far away.
- **Put things that should be compared next to each other.** A chart and the
  breakdown it summarises, or this period beside last, go in the same row
  (`.tb-cols-2`) so the eye can move between them. Things that would be
  compared but sit a scroll apart won't be compared.
- **The overview fits one screen.** The point of a report page is seeing it
  together. If the headline section doesn't fit a laptop screen, cut or move
  content — the second question goes on a tab (`data-tb-tab`), not below the
  fold.
- **Group with space, not boxes.** Whitespace between groups and consistent
  alignment on the grid do the grouping; a border around every figure adds
  noise ([[design-cut-the-chrome]]).

**The tell.** Blur your eyes and look at the page: the heaviest thing you see
first should be the answer. If it's a logo, a control or a decorative banner,
rearrange.
