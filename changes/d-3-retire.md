### Changed — the old frame retired: dead code out, every old address checked, the words follow

- Code nothing referenced any more is gone: `StatTile` (`Shared.jsx`),
  `reviewNotes` (`Attention.jsx`), `modelOfPipeline` and `reportOpenPath`
  (`nav.js`), the report panel's unused `Section`, `Scope.jsx`'s re-export of
  `PAGES`, an unused `useMe` import on Review, and the stylesheet's dead rules
  (`.orb*`, `.gradient-text*`, `.cursor-blink` and its keyframes, `.grid-2`,
  `.grid-3`, `.concept-grid`, `.workflow-run-grid`, `.rp__model`). Every
  redirect and `movedTo` stay. `Overview.jsx` (the model's Data page),
  `Map.jsx` (Data's picture view) and `TheLine.jsx` were already reduced to
  what Data uses. The JS bundle is unchanged (the bundler had already dropped
  the unused exports); the CSS is 0.8 KB smaller.
- The smoke test's redirect table covers every old address `movedTo` knows
  (`/m/<m>/model|transform`, `/m/<m>?r=`, `/models/<m>?tab=…`, `/connectors`,
  `/pipelines?model=`, `/reports`, `/reports?r=`, `/?r=`,
  `/data/<m>/reports?r=`, `/workflow`), beside the ones already there. `/runs`
  and `/verify` keep their own pages under Review.
- Get started's "How the app fits together" is one entry per place, in the
  sidebar's order; step 5 says the app opens on Reports.
- The words: reports are served "in the library under its model", not "on the
  model's Overview"; Refresh data is "on the model's Transform tab"; the query
  builder is Ask; History and the library replace "the Runs page" and "the
  Reports page"; `tracebi push` says a code request waits "under Review";
  `tracebi dev` says it opens Data with no name, `/reports/<name>` with one.
  README (a Review entry in Web UI), the guides (the demo script follows the
  current app: the library, the verdict chip, the masthead Receipt link, Ask
  in the sidebar), concepts, `api-routes.md` (the app's addresses and its
  redirects), AGENTS.md and the `init` guide, the scaffolded pipeline's
  comment, and code comments. `remote-authoring.md` and `report-library.md`
  say at the top that they predate the 2026-10 layout.
- The ui-audit baselines are re-run against the four places.
