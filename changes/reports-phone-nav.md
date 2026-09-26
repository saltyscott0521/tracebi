### Changed

- **Full screen** now opens the report over the app with a Close button (and
  Escape) instead of a new tab with no way back.
- On a phone, picking a report slides it in as its own screen with a
  "Reports / folder" breadcrumb back; the phone's back gesture works too.

### Fixed

- The share link works when the app is served under a path prefix (as on
  tracebi.com at `/app/`).
- A missing UI script now answers 404 instead of the app page. After a deploy,
  a CDN could cache that page under the script's address and show a blank app.
