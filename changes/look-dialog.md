### Added — ask how a report should look, once, before building it

- `tracebi.css` page look on `<html>`: `data-tb-mode` (dark / auto),
  `data-tb-density="compact"`, `data-tb-width="full"`; a sidebar nav
  (`.tb-tabs[data-tb-nav="side"]`); a standard title block (`.tb-title`,
  `data-tb-title` left / center / banner / nav, `data-tb-built` filled from
  the receipt).
- `tracebi new-report --mode --density --nav --title-at`.
- The `author_report` prompt, both agent guides and `presentation.layout.look`
  tell an agent to ask the look once; new lesson `design-dashboard-feel`.
