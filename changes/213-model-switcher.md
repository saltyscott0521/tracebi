### Changed — the web app is framed by a model switcher

- One control at the top of the sidebar picks a model, or "All models".
  Beneath it, the same six pages for every model: **Data model**,
  **Explore**, **Refresh** (was Pipelines), **Reports**, **Sources** and
  **Runs**, each narrowed to the picked model. With all models, every row
  names its model. One model: no switcher.
- Addresses are `/m/<model>/<page>` (one model) and `/<page>` (all models);
  the last pick is remembered and `/` reopens it. Old addresses
  (`/models/<name>?tab=…`, `/connectors`, `/pipelines`, `/explore?model=…`)
  redirect. An unknown address shows "Page not found" instead of a blank page.
- The "Contract" tab is "Data model" again. Sources opens on its first source.

### Added — `scripts/ui_audit.py`

- Serves the reference project and crawls every reachable page at desktop
  and phone widths, light and dark: browser errors, failed API calls,
  sideways scroll, axe-core violations, keyboard reach and focus rings, tap
  targets, "you are here", blank panes, slow pages. Writes `findings.json`
  and a screenshot contact sheet; `--baseline` fails on any new finding.
  The bar is `docs/architecture/ui-quality.md`; the work is
  `docs/architecture/ui-backlog.md`.
