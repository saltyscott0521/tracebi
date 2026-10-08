### Added — Drafts: write a report or declarative model remotely, publish when it renders

- `tracebi/drafts.py` keeps private working copies under `drafts/<owner>/`
  (`TRACEBI_DRAFTS_DIR`): a report package (`report.json`, `template.html`,
  `style.css`) or a model `<name>.json`. Nothing else is accepted: no
  `report.py`, no `script.js`, 512 KB per file. A published report with a
  `report.py` cannot be drafted remotely.
- Six MCP tools (`list_drafts`, `start_draft`, `read_draft`,
  `write_draft_file`, `preview_draft`, `publish_draft`) and `/api/drafts`
  routes. Reading a draft is for its owner or an admin; publishing needs
  `analyst`.
- Publishing renders the package first, keeps the version it replaces under
  `.tracebi/history/`, copies the draft into the library and records a
  `publish` run with the actor. The draft is kept.
