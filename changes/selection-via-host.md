### Changed — a report's cut is run by the app, not by the report page

- A report that opts into selection used to call `/api/reports/<name>/selection`
  from inside its own page (and its CSP said `connect-src 'self'` to allow it).
  The page is now sandboxed and has no network, so it asks the app by message
  and the app runs the cut as the signed-in viewer. Only the report being shown
  may ask, and only for filters. A page opted into selection now keeps
  `connect-src 'none'` like any other.
- A report opened on its own (the share link, a file from disk) has no app to
  ask, so a cut takes the page's embedded offline path, or is declined with
  "Further slices need the model", as a file from disk always did.
- The runtime now starts after everything it defines is in place, so a first
  hydrate that runs at once can no longer find a helper missing.
