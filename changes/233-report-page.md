### Changed — an open report gets the whole page, and one Download menu

- Open a report and it has the full width of the page; the list steps aside and
  **← All reports** (at any screen size) brings it back. A three-card report's
  cards sit on one row.
- The report's buttons fit on one line: **Rebuild** (and **Build**, in dev mode),
  **Full screen**, **Share**, and one **Download** menu with HTML, Excel and PDF,
  each with its one-line caveat. On a phone they share a two-across grid.
- **Lineage** is always a tab and loads when you open it; the "View Lineage"
  button is gone.

### Changed — Runs agrees with Reports

- A report's newest build on the Runs page shows the verdict the Reports page
  shows for it. Every older build reads "Not checked" (it was "Not verified"):
  a build is not a check, and only a re-checked "Reproduces" is green.
- A refresh names its model on the Runs page, and a model's own Runs page lists
  its refreshes along with its report builds.

### Added — an audit check for crowded button rows

- `scripts/ui_audit.py` flags a row of three or more action buttons that wraps
  onto a second line at desktop width (`action-row-wraps`). Its focus-ring check
  now judges the element inside a report's frame rather than the frame.
