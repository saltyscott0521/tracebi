# Live-view fonts (not in offline artifacts)

Source Sans 3 and Source Code Pro (SIL Open Font License 1.1) for
**server / `tracebi dev` preview only**.

`tracebi.reports.live_fonts.with_live_fonts` injects them as `data:` URIs
into HTML responses the browser views live. Built `output/*.html` files and
HTML downloads stay on the `system-ui` stack in `tracebi.css` — no font
bytes, so the offline file stays lean and CSP-self-contained.

| File | Face / weight |
|---|---|
| `source-sans-3-latin-400-normal.woff2` | body |
| `source-sans-3-latin-600-normal.woff2` | medium emphasis |
| `source-sans-3-latin-700-normal.woff2` | headings / KPIs |
| `source-code-pro-latin-400-normal.woff2` | receipts / fingerprints |

Licenses: `OFL-SourceSans3.txt`, `OFL-SourceCodePro.txt`.
