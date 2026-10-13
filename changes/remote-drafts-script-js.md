### Changed — remote drafts may hold a `script.js`

- A report draft (over MCP or in the app) now accepts `script.js` beside
  `report.json`, `template.html` and `style.css`, and a published report with a
  `script.js` can be drafted. Python (`report.py`, models, transforms,
  pipelines) is still refused with the laptop line.
- This is safe because the browser is the boundary: every report frame and the
  share link are sandboxed (opaque origin, no network, no access to the app),
  and if a script changes a stamped figure's text the receipt says so. See
  `docs/strategy/analyst-freedom.md`.
