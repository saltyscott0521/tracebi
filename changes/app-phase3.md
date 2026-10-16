### Added — app pages read without JavaScript; app behaviour; dashboards by job

- An `app.jsx` page carries a static view of its kit figures (labelled KPIs,
  the charts' static pictures, tables), filled by the build, so an email
  preview or a phone's file viewer shows the numbers; the app replaces it.
- The kit: `<Filter column>` with no binding is a page-wide filter (KPIs stay
  the stamped totals); `<Segmented>` picks which figure shows;
  `useUrlState` keeps a view or period in the URL. The dashboard scaffold
  keeps its view in the URL.
- `tracebi new-dashboard --job overview|trend|leaderboard`.
- Fix: the table cell-bar style no longer resizes a static chart picture's bars.
