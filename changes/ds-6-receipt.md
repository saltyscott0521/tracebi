### Changed — the receipt reads as a certificate

- The drawer opens on what matters: the report, when it was built and from
  which model, the verdict chip, "The receipt does not claim the numbers are
  right.", and how to check the file (`tracebi verify --file <name>.html`,
  with Copy). Then one row per figure in page order: the value as the page
  shows it (or "table, 13 rows" / "chart, 6 rows"), its label, the measure's
  definition from the model, the query in one line in the model's names
  (`fair_value by dim_issuer.sector · order fair_value desc` — only the
  ordering keys the author wrote; the engine's tie-break stays in the raw
  query) and the fingerprint's first 8 characters with Copy. "Raw" holds the
  ids, the query exactly as run and the full fingerprint; "About this build"
  holds the sink contracts, the stated methodology, who built it, the render
  stamp and git.
- Ways in: a "Receipt" button after the masthead's verdict chip (the chip
  opens it too), "Open the receipt" on the footer's line, a click on any value
  figure (opens at its row, highlighted), and a chart tooltip's "Receipt →".
  Escape closes it. A page with no masthead keeps the floating button, so
  nothing floats over a chart on a phone.
- 420px on the right; a full-height sheet on a phone; prints as an appendix
  with every disclosure open.
- The `tracebi-receipt` block also carries `cell` per figure and `bindings`
  (per binding: `query` as run, `rows`, `order_stated`), copies of what the
  manifest records, so the drawer needs no page to state a query.
- For the web app: `tracebi.renderReceipt(mount, receipt, options)` renders
  the certificate into any element (options: `contracts` — the parsed
  `tb-semantic-contract-*` blocks, for definitions; `verdict` — one of
  `draft`, `not-checked`, `reproduces`, `needs-a-look`, `does-not-reproduce`,
  default what the file says of itself; `page` — the document whose figures
  show the values, `null` when out of reach; `file` — the name in the "how to
  check" line). The drawer chrome (`.tb-receipt-drawer`, its close button and
  the triggers) is separate; the certificate is `.tb-receipt`. Note that
  loading `tracebi.js` also boots its page hydration on that document.
