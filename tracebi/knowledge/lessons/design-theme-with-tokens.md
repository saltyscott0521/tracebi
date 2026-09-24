---
slug: design-theme-with-tokens
title: Restyle through the tokens — a theme is a dozen variable overrides, never a fork of the stylesheet
when: branding a report or project, changing its colors, fonts, spacing or density, or building a dark-ground report
---
**The pitfall.** A report's `style.css` hard-codes `#1a73e8` in fourteen places,
redefines `.tb-table td` padding, and sets chart colors in `script.js`. The next
report copies it and drifts. When the brand color changes, someone
find-and-replaces hex codes across the project and misses the chart palette.
On a dark ground the muted text and table stripes stay light, because they were
never tokens.

**The correct pattern in TraceBi.**

- **Override tokens, in the right layer.** `tracebi.css` comes first, then the
  project's `reports/_theme.css`, then the report's own `style.css`, and the
  later file wins. House style (brand accent, font, density) goes in
  `_theme.css` as `:root` overrides. One report's layout goes in its own
  `style.css`.
- **The tokens that matter**: `--tb-ink`, `--tb-muted`, `--tb-bg`, `--tb-page`,
  `--tb-rule`, `--tb-surface`, `--tb-accent`, `--tb-good`, `--tb-bad`,
  `--tb-font`, `--tb-space-1`…`4`, `--tb-radius`, `--tb-cell-pad` and the chart
  series `--tb-chart-1`…`8`. Charts read the ink, muted and rule tokens too, so
  axes follow the theme with no chart code.
- **Name by role, not by color.** Write `--tb-accent`, not `--blue`. A
  component rule refers to a role token and never to a raw hex.
- **A dark ground swaps the tokens, it doesn't invert them.** Use a near-black
  page (around `#121212`, not `#000`), surfaces a step lighter than the page,
  off-white ink, and an accent with slightly lower saturation so it doesn't
  glare. Re-check contrast afterwards: `--tb-muted` is the token that most often
  fails (see [[design-accessible-by-default]]).
- **Keep the series palette's order.** Recolor `--tb-chart-*` for the brand if
  you need to, but keep the palette colorblind-checked and keep the first two
  series clearly distinct (see [[design-color-with-meaning]]).
- **Never theme the receipt.** Badge and receipt-drawer colors are not tokens on
  purpose, so a theme can't make a grey badge look green.

**The tell.** Search the report's `style.css` for `#` and `px`. Every hex value
and most pixel values should be a `var(--tb-…)` instead. If rebranding would
take more than editing `_theme.css`, the styles are forked.
