### Changed — "receipt" is now "trace" (A2-4)

What every number carries is its **trace**: how it was made. The word
*receipt* is gone from the canon and from everything a reader sees; the
concept is traceability, the verb is "how this number was made".

- **MANIFESTO.md**: "The receipt" is "The trace" (every number drawn through
  the model has a trace; everything else must be marked as not having one),
  the opening's "mechanical receipt" is a mechanical trace, and the
  vocabulary, the assurance ladder (L1 traces) and the commitments say trace.
- **The built page**: the masthead's link reads **Trace**; the footer is one
  line, "Built … · <model>. This page does not claim the numbers are right.
  ▸ How these numbers were made", whose link opens the drawer (the footer's
  `<details>` stays in the file for a reader without JavaScript and hides
  once the runtime has a drawer; the drawer's About this build carries the
  same notes, now including the app note). The drawer is headed with the
  report's name and "How each number was made", and its honesty sentence is
  "This page does not claim the numbers are right; it records how each was
  made so it can be checked." A chart tooltip's link reads "Trace →".
- **The app**: About this build opens on **Trace**; the library reads "Every
  report, and whether its numbers still hold"; History, "Only a build that
  re-runs to the same numbers reads green"; Export, "HTML · the file with its
  trace"; Get started, the lineage panel and empty states follow.
- **Words everywhere else**: README, AGENTS.md and the scaffolded AGENTS.md,
  `tracebi context`, the MCP tool descriptions (`verify_manifest` is titled
  "Verify a manifest"), CLI help and output, `verify` verdict lines, the
  knowledge lessons, scaffolds and the reference reports.
  `docs/concepts/receipts.md` moved to `docs/concepts/trace.md`; the old page
  is a stub that points at it.
- **Kept internal**: the `tracebi-receipt` block, `.tb-receipt*` classes,
  `data-tb-receipt-*` attributes, `renderReceipt`, Python `receipt_*` names,
  manifest keys and API fields. Built files keep working unchanged.
- `tests/test_agent_guides.py` fails when either agent guide or `tracebi
  context` says "receipt" outside those identifiers.
