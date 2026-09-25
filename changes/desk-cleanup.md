### Changed

- The Desk page now answers two questions: does anything need you, and what
  state is each report in? It shows:
  - a one-line status;
  - **Needs attention**: open review notes, receipts that no longer reproduce,
    failed data refreshes, and data checks that are stale or missing;
  - **Reports**: when each one was last built and whether its receipt still
    reproduces;
  - **Recent data refreshes**.

  The workflow diagram, count cards, "How the receipt works", quick start and
  connector list are gone from the Desk; each already has its own page. An
  empty project gets one pointer to Get Started instead. Reports that contain
  working-notes blocks are no longer flagged as drafts needing attention.
- `GET /api/desk` adds `builds`: every built report on disk, with its build
  time and receipt verdict, newest first.

### Fixed

- Correct reports could read "not reproduced" when several requests checked
  receipts at once. A DuckDB connector shared one connection across the web
  server's threads, and a second query could consume the first one's result,
  so a load returned nothing. The connector now runs one query at a time.
