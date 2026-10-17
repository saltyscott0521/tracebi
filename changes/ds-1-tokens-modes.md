### Changed — one type scale, one accent, auto mode by default

- A report follows the reader's system: the build gives a page whose `<html>`
  names no `data-tb-mode` (and an app with no `look.mode`) `auto`. Pin a page
  with `data-tb-mode="light"` or `"dark"`; `--mode` on `new-report` /
  `new-dashboard` now defaults to `auto`.
- `tracebi.css` gains a seven-step type scale (`--tb-text-xs` … `--tb-text-3xl`,
  12–40px, body 14px), `--tb-tracking-tight`, weights 400/500/600, and
  tabular numerals on every figure.
- `--tb-chart-1` is the accent (no second blue). The dark ground has its own
  series and its own accent pair (`--tb-dark-accent`, `--tb-dark-accent-text`).
- The shipped themes are accent presets for both grounds. `midnight` is a navy
  accent, no longer "always dark": use `data-tb-mode="dark"` for that. `sand`
  no longer repaints the page ground.
- The editorial hero is the flat accent: no hatch, gradient or glow. Cards,
  KPI strips and the article sheet draw no resting shadow; `--tb-shadow`
  defaults to `none`.
