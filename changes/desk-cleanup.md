### Changed — the Desk folds into Reports

- The Desk page is gone; the app opens on **Reports**. The one thing only the
  Desk did moved there: a **Needs attention** strip at the top of Reports
  lists open review notes, receipts that no longer reproduce, failed data
  refreshes, and data checks that are stale or missing. The strip only appears
  when something needs a person. `/` redirects to `/reports`, so old links
  still work.
- Each report in the Reports list now shows its last build time and whether
  its receipt still reproduces. This replaces the "verifiable" chip, which was
  green on every report and so told the reader nothing.
- `GET /api/desk` adds `builds`: every built report on disk, with its build
  time and receipt verdict, newest first.
- Long report descriptions in the Reports list are capped at two lines, and no
  longer push the status chips out of view.

### Fixed — correct reports read "not reproduced" under concurrent requests

- Correct reports could read "not reproduced" when several requests checked
  receipts at once. A DuckDB connector shared one connection across the web
  server's threads, and a second query could consume the first one's result,
  so a load returned nothing. The connector now runs one query at a time.
