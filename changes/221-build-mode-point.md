### Added — Build mode: point at a figure, and the agent knows what "this" means

- In the web app, with the server in dev mode (`TRACEBI_DEV_MODE=1`), a report package gets a **Point** button. Hover outlines what
  you can address; click a figure or an area and the app records it as what
  you are pointing at. Esc, or leaving Point mode, stops.
- The agent reads it with the MCP tool `workbench_state`: `pointing` is a
  figure (`id`, `binding`, `cell`) or an element (`selector`, `text`,
  `section`). "Make this a line chart" now means a specific figure.
- It is dev-state under `.tracebi/workbench/<report>/pointing.json`, shared by
  the web server and the MCP server (two processes). It never reaches a build
  or a receipt, the app calls no model, and the endpoints (`/api/reports/
  <name>/workbench/pointing`) refuse unless the server is in dev mode.
- Design and order of work: `docs/architecture/design-direction.md`.
