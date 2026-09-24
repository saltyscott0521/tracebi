---
slug: design-grid-and-spacing
title: Align to one grid and space from the scale — distance tells the reader what belongs together
when: arranging figures on a page, choosing columns and widths, or setting margins, gaps and padding in style.css
---
**The pitfall.** Cards of slightly different widths, a chart whose left edge sits
6px off the table below it, 13px here and 20px there, and a filter floating
halfway between the table it controls and the chart above. None of it is wrong on
its own. Together it reads as unfinished, and the reader can't tell which pieces
belong together.

**The correct pattern in TraceBi.**

- **Use the layout classes, not hand-made columns.** `.tb-grid` (KPI rows that
  wrap on their own), `.tb-cols-2` and `.tb-cols-3` (side-by-side figures that
  stack on a phone), and `.tb-card` for each figure. They share one gap, so
  edges line up across rows without any extra work.
- **Pick proportions, not pixel widths.** Two related charts share a row
  equally. A chart with its detail table can go 1:2 in your `style.css`
  (`grid-template-columns: 1fr 2fr`). Don't mix three different splits on one
  page.
- **Space from the scale.** `--tb-space-1` to `--tb-space-4` (4 / 8 / 16 / 32px)
  cover almost everything. Things that belong together sit close (a control
  directly above its table, a caption directly under its chart); separate
  groups get the larger step. If you type a raw pixel value, it is probably one
  of these tokens.
- **Group with a boundary when distance can't do it.** A `.tb-card` puts a chart
  and its note in one region. Don't nest cards inside cards: one level of
  container is enough.
- **Break the grid only on purpose.** A full-width chart after a row of halves is
  a choice. A card that is 40px narrower than its neighbors is an accident.
- **Check at phone width.** The layout classes collapse to one column under
  720px. A custom grid in `style.css` must do the same.

**The tell.** Draw vertical lines down the page in your head: every left edge
should land on one of a few lines. And the gap between a control and its table
should be smaller than the gap between that table and the next section. See also
[[design-layout-by-importance]].
