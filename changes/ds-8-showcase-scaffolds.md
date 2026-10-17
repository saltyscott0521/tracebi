### Changed — the showcase, the scaffolds and the demo app on the system

- `portfolio_showcase` is the system's reference: the masthead, a KPI strip
  with a lead and a delta, the 12-column grid (`.tb-span-4/6/8`), every chart
  type, the tables and the footer, in both modes. Its `style.css` (196 lines
  to 36) is a theme preset: a teal accent pair and one display face
  (Fraunces, from `assets/fonts/`) for the headline and the lead number. The
  gradient hero, the drop shadows, the pill tabs, Inter, the hero artwork, the
  light-only table header and the pie's own palette are gone. The treemap
  uses the charts' readout and leaves out a label that does not fit instead
  of cutting it.
- The `new-dashboard --html` row, both `init --template` bundles, the demo
  app's reports and `portfolio_concentration` lay panels out on the 12-column
  grid (`tb-grid` + `tb-span-*`) instead of Tailwind grid columns or
  `.tb-cols-2-1`.
- `aum_by_branch` stays the one bespoke example (Inter and Fraunces, pine and
  brass, a hero band with its rings artwork), now a flat band with no
  gradient or shadow, on the system's KPI strip, grid, footer and receipt,
  and with a dark accent of its own.
- Fixed: on an app page, a theme's or a `style.css`'s `:root` tokens beat the
  dark ground (tracebi.css sits in a cascade layer there), so a dark reader
  got near-black text on dark cards and the light accent. The dark-mode
  token blocks now apply over them, as on a template page.
- The share link (`/r/<name>`) makes no request: a page built since the
  selection moved to the host never fetched the API. The CORS errors came
  from builds made before that, whose runtime posted to
  `/api/reports/<name>/selection`; rebuild such a report. The reference test
  now checks the built page names no API path and calls no `fetch`.
- `design-direction` describes the report's system; the template, app and
  styling references, the design lessons, the vocabulary and both agent
  guides teach the 12-column grid and the theme-preset rule for `style.css`.
