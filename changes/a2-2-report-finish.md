### Changed — report finish (A2-2)

- **Hosted mastheads.** The app's report page already shows when a build was
  made and its verdict in its own header, so the frame no longer repeats them:
  the app's `tracebi:verdict` message now carries `hosted: true`
  (`web/ui/src/frameBridge.js`), and on it `tracebi.js` hides the masthead
  meta's build time and verdict chip (the `hidden` attribute). The period and
  the Receipt link stay; the editorial hero keeps its byline; the receipt's own
  chip still says the verdict. Opened on its own (a file, `/r/`, an email) the
  masthead is whole, as before.
- **Links on a hero ground.** A masthead with a filled background (the
  editorial hero, a banner, a report's own hero such as `affordability`'s) is
  marked `data-tb-ground="filled"` by the runtime, and its Receipt link and
  unstyled links take the masthead's ink. An author's own link colour still
  wins. `affordability`'s Receipt link was accent blue on its green hero.
- **More to scroll.** A box that scrolls a table (`.tb-scroll`, the kit's
  `<Table>`, and on a phone a table or card that scrolls itself) gets
  `data-tb-more="x|y|xy"` while there is more of it to the right or below, and
  that edge fades. The fade is a CSS mask (`mask-image: linear-gradient(...)`):
  **the one gradient the system allows**, because it fills nothing and changes
  no colour; it goes when the last column is in view and does not print. A mask
  is not a `background-image`, so `scripts/ui_audit.py`'s gradient count does
  not see it and needs no exclusion. Kept current on scroll, resize, and when
  the table inside changes size.
- **`mrr_dashboard`** (reference and `saas-metrics` template, byte-identical):
  the trend and "Ending MRR by plan" are equal halves, so the plan table shows
  all four columns at 1440 (it cut Logo churn to "LO…").
- **Showcase.** The lead KPI, its delta and the standfirst's fair value are
  `currency_compact` ("$285.9M", "-$6.3M"), as on every other page. The
  typed-in "Est. Q3 deployments" card says so where it is read: "typed in, not
  a query · not re-run" (it is a `data-tb-unverified` figure, not a
  `report.py` one; the python-derived figure is the cumulative-share chart,
  which already says so). The scatter sits beside the top-issuers bars in a
  half-width panel, and the issuer curve takes the full row, so the scatter is
  no longer mostly empty space at 1440.
