### Changed — the standard report stylesheet matches the app

- **A report looks like the product.** `tracebi.css` now leads with **Hanken Grotesk**
  (the web app's face), on neutral grounds (`#fafafa` page, white cards,
  `#e5e5e5` hairlines) with one cobalt accent. Cards are a hairline instead of a
  shadow, the radius is 8px, headings are a touch tighter, KPI numbers are a
  touch lighter, and inline code in prose is a quiet chip.
- **The face travels in the file.** It is inlined (Latin subset, about 45 KB), so a
  report still needs nothing installed and fetches nothing; the strict CSP is
  unchanged. Set `--tb-font` to use your own face. Hanken Grotesk is SIL OFL 1.1; its
  licence is in `NOTICE` and credited in each report's source comment.
- **Finished controls:** the filter box, dropdown and Download CSV button share a
  height, hover and focus; the dropdown arrow is drawn so every browser matches.
- **New tokens:** `--tb-accent-text` (the accent deepened to read as small text:
  links, hovers) and `--tb-mono`. Projects that override `--tb-accent` should
  override `--tb-accent-text` too; the old defaults (`#1f63b8`, warm greys) are
  gone, so a project that relied on them will look different.
- `scripts/ui_audit.py` checks the report stylesheet at the source (Hanken Grotesk first,
  every text token at 4.5:1), since axe cannot see inside a report's iframe.
