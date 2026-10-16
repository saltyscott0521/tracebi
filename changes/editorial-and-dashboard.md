### Changed — `new-report` writes an editorial report; `new-dashboard` an app

- `tracebi new-report` now writes a page to be read: by default an editorial
  `template.html` (`.tb-article`: kicker, a headline that states the finding,
  standfirst, byline with the build time, prose with bound numbers, captioned
  figures, a pull-stat, "What to do", the methodology), set in a serif body.
  `--layout brief|tabbed|dashboard` remain.
- `tracebi new-dashboard` writes the app (`app.jsx`) people work in, with the
  look flags; `--html` writes the template dashboard.
- New lesson `design-editorial-report`; the vocabulary, both guides, the
  MCP authoring prompt and docs pick a report to read or a dashboard to work in.
