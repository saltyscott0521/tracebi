# UI backlog

The loop in `ui-quality.md` takes the top open item. Done items move to the
bottom with the change that closed them.

## Open

1. *Closed by D-1 (see Done).*
2. **"Checks stale" items name no model**: a stale sink check shows only
    under All models. Attribute warehouse tables to the models that read them.
3. **Bundle is 1.2 MB of JS** (1,243,903 bytes, 364 KB gzipped, after D-3).
    D-3's dead-code pass did not move it: the bundler already dropped what
    nothing imported. Split routes (React Flow, Markdown, Recharts load only
    on the pages that use them). The Step 1 baselines' `bundle_js_kb` 2,345
    counted a stale second bundle left in `dist/assets/`; build into an empty
    `dist` before an audit.
4. **90 hard-coded colours in JSX** — each is a dark-mode bug waiting.
    Move them to tokens.
5. **The theme ignores the OS setting**: a first visit is always light. Follow
   `prefers-color-scheme` until the viewer picks one.
6. **`Btn` drops a caller's colours**: its variant styles are applied after
    `style`, so `style={{ background }}` is silently overridden.

Left by Step 1 of the UX plan ([[ux-plan-2026-10-17]]), report side:

7. **Affordability is a second bespoke look**: Inter, a green accent, its own
   paper ground, resting shadows and gradients (all of the reference
   project's `report_box_shadows` and `report_gradients`), pinned light. Move
   it onto the system, or name it beside `aum_by_branch` as a bespoke example.
8. **The reference project has more than one look**: `portfolio_book` (navy)
   and `portfolio_showcase` (teal, Fraunces) carry their own accent presets
   (`report_accents`, `report_looks` in the baseline). Decide whether a project
   is one accent, and ratchet the count down.
9. **Small multiples are dense on a phone** (DS-4).
10. **The showcase's striped frozen column keeps a light shade in dark** (DS-5).
11. *Closed by L-5 (see Done): there is no handshake left.*
12. **A line's end label is cut at the plot's top edge on a phone**
    (`portfolio_concentration`'s cumulative share at 390px).

Recorded in the committed audit baselines, not caused by Step 1 (which touched
no app code), to retriage with Step 2's library and report page (R-1, R-4):

13. **App crawl findings since the 2026-10-13 Reports page**: `scope-mismatch`
    and `nav-you-are-here` were the audit's selectors (R-1: it now reads the
    library's `[data-report]` rows at `/?model=<m>` and counts the rail's
    current entry on an open report; the committed baselines still name the
    old addresses until the next run), `blank-page` / `one-h1` / `small-target` on an open report,
    `no-focus-ring` into the report frame, eleven `slow-page`, and the
    segmented bar's `repeating-linear-gradient` (`global.css:1188`,
    `theme-decoration`). Some are the audit's selectors, some the app.
    *Retriaged after D-3's re-run:* `scope-mismatch`, `nav-you-are-here` and
    `theme-decoration` are gone. Left, on an open report only: `blank-page`,
    `no-focus-ring` into the frame and `one-h1` (affordability; the demo's
    medallion_revenue), and `small-target` on the rail's "Reports" crumb and
    the header's verdict chip; plus `small-target` on Review's "All history →"
    and thirteen `slow-page`.

Left by Step 2 of the UX plan ([[ux-plan-2026-10-17]]), app side:

14. *Closed by D-3 (see Done).*
15. *Closed by D-1 (see Done).*
16. **`CLAUDE.md` still says "on the model's Overview"** (four lines: the
    phase ③ paragraph, the run-command comment, How to Add Things twice) and
    does not say where `tracebi dev` opens. D-3 fixed every other file; the
    project instructions are the owner's to edit (the proposed wording is in
    D-3's report).
17. *Closed by D-3 (see Done).*
18. **`site/sample/portfolio_showcase.html` predates Step 1**: rebuild it with
    the current runtime.
19. **A report build records no finish time** (`record_report_build`), so
    History shows how long only for background runs, schedules and pipeline
    runs. Record the build's start and finish.
20. **Bug, not UI: `tracebi migrate model` drops `owners`.**
    `model_yaml._document` puts `owners` in the document, but `model_to_yaml`
    writes only `label` and the `_SECTIONS` keys, so a migrated model loses
    who may publish it.
21. **The phone header is translucent**: a scrolled list shows through it
    (History's sticky day header sits under it).

Left by Step 3 of the UX plan ([[ux-plan-2026-10-17]]):

22. *Closed by A2-3 (see Done).*
23. *Closed by A2-3 (see Done).*
24. **The Transform flow zooms in two steps** only (D-1).
25. *Closed by Step 4 (see Done): `AskCut` deleted.*
26. **`notebook-guide.md`'s `@register.report` section predates the one
    renderer**: a factory with no package is listed but refused (422). Point
    it at a package.
27. **`scripts/ui_audit.py`'s `scope-mismatch` detail still says "the model
    switcher"**; it means the model chip.

Left by Step 4 (Ask):

28. **An Ask answer carries no fingerprint.** `POST /api/models/{name}/query`
    returns lineage, not the stamp `query_model` gives an agent, so the
    answer cannot quote one beside its number.
29. **Ask's filters are equality on dimension values.** Ranges, a measure
    threshold (`having`) and fact columns are Advanced only; the sentence
    shows them in words but offers no token for them.
30. **A measure's label is its humanised name** ("Fv share"): models have no
    measure `label`, so Ask reads `fv_share` as "Fv share" beside its
    description.
31. **Keep this cannot pick a folder**: the draft starts at
    `<model>/<slug>`; the folder is chosen when it is published.

Left by A2-3 (the app, audit pass 2):

32. **A pipeline run in History goes by its identifier** (`portfolio_model`):
    `/api/runs` gives a report run a `display_name` and a pipeline run none.
    Give it its model's label, as the Transform card now reads.
33. **History's "N older runs" counts what `/api/runs` returned** (the last
    50 runs, default `limit`), not every run the store holds.
34. **The Steps table's status is an upper-case badge** ("SUCCESS"), not the
    verdict-shaped `Chip` the table checks now use.

Left by A2-6 (role-aware navigation):

35. **Links inside a page still point past the role**: a viewer's report
    panel and Ask can link to History or a model's Data page, which then shows
    the plain "for analysts / admins" page. Hide those links by the same
    `mayUse` rule the sidebar uses.

Left by A2-4 (receipt → trace):

36. **The code still says "receipt".** Readers see *trace* everywhere; the
    identifiers kept the old word so the artifact contract did not move: the
    `tracebi-receipt` block id, `.tb-receipt*` classes, `data-tb-receipt-*`
    attributes, `tracebi.renderReceipt` / `receiptFileName`, Python
    `receipt_*` names, `ReceiptFrame.jsx`, the panel's `receipt` tab key and
    the `receipt_drawer` key in `tracebi context`. Rename them together, with
    a reader for the old block id so files built before the rename still open
    their drawer (and `verify --file` still reads them).

Left by the live-reports round ([[live-reports-plan]], L-5):

37. **Ask's "Keep this" does not carry a selection into the page.** A kept
    answer opens a one-figure draft; it could instead open the report it came
    from with the selection in the frame's hash (`#sel=`), so the reader lands
    on the same cut, Local, without a draft.
38. **The page engine keys slices by fact name.** `tracebiCalc.load(fact, …)`
    holds one slice per fact name, so a page reading two models that each
    have a fact of the same name would load one over the other. Key by
    `model.fact` (the calc payload already records both).
39. **A time grain reads two ways on one page.** As built, a binding grouped
    by a time grain shows the stamped label the model returned
    (`2025-03-01`); once the page recomputes it shows the slice's grain label
    (`2025-03`). The numbers agree; the axis labels change spelling on the
    first selection (the showcase's Cash flows chart). Stamp the grain label,
    or format it the same way on both paths.

## Done

- **The live page in the app** (L-5): a report's frame tells the app its
  selection (`tracebi-selection`, tagged like every bridge message); while it
  is not the authored one the header's chip reads **Local** with the page's
  own detail, and each selected field is a chip ("Sector: Technology ×")
  that clears it through the frame (`tracebi-set-selection`). The
  `selection-request` round trip is gone on both sides (item 11).

- **The sidebar is tiered by role** (A2-6): `nav.js` gives each place a
  `minRole` and `placesFor(role)` is the one list the sidebar, the phone's
  drawer, the report page's rail and ⌘K draw: everyone Reports and Ask, an
  analyst also Review, an admin also Data; with no sign-in (`/api/me` names
  admin) all four, and while the role loads only Reports and Ask. An address
  above the role shows a plain page in the frame ("This part of the app is
  for admins. You can read reports and ask questions."). Review is four tabs
  at their own addresses: Attention (`/review`), Drafts (`/review/drafts`;
  `/drafts` and `/review#drafts` land there), History (`/runs`) and Verify
  (`/verify`); its "All history →" link and the small Verify entry are gone.

- **The app, audit pass 2** (A2-3): the Model tab's views are one segmented
  row in its card's header with Edit as a draft at its right (no badge
  repeating the line; the grain in labels, identifiers in its title), sideways
  on a phone where Tables opens first; the Transform card goes by its model's
  label, its steps read "Transform · ran 2 h ago · wrote 3 tables" and
  "Build · 6 reports" in the sans at the app's size, table checks are
  sentence-case chips in the verdict's shape (`Chip`), and the phone's Steps
  table drops Schedule and Runs after; History is one row per report or
  pipeline with "N older runs" folded (Every run, `?all=1`, lists them flat;
  a fold says how many failed), the report panel's History folds older builds
  the same way, and an empty cell's dash is muted; the Map's models and
  reports go by their labels, measured in the sans; library descriptions
  wrap to two lines; the sidebar's tagline is gone. Closed items 22 and 23.

- **Ask** (Step 4): `/ask` is one sentence of the model's tokens ("Show
  [measure] by [dimension] for [filter], [order], top [n]"), typed or picked;
  the answer is the model's query drawn as a chart, table or number with each
  measure's definition in words, the query line and a Not checked chip; a
  Recent strip and `?q=` links; Keep this (analyst+) opens a one-figure draft
  holding the query; Advanced is the query builder on the same question.
  Closed item 25 (`AskCut` deleted, not reused: it cut a report's selection,
  where Ask asks a model).

- **The old frame retired** (D-3): dead components, helpers and CSS out
  (`StatTile`, `reviewNotes`, `modelOfPipeline`, `reportOpenPath`, the
  stylesheet's orb, gradient-text, grid and workflow-run rules, …); every old
  address checked to land (34 in a browser, the whole `movedTo` table in the
  smoke test); the words follow the four places in the README, guides,
  concepts, reference, agent guides, CLI and Get started ("How the app fits
  together" one entry per place). Closed items 14 (baselines re-run), 16 for
  every file but `CLAUDE.md`, and 17 (the demo script points at the masthead
  chip and its Receipt link).

- **Review is one page** (D-2): Needs attention first (failed runs and
  refreshes with what went wrong, builds that need a look, publish requests to
  decide in place, the person's own requests waiting on approvers), then
  Drafts (own first, an admin's Mine | Everyone's; an empty state written for
  a person, the MCP tool names under "For your agent"; decided requests
  folded under Requests), then Verify a file as a small drop zone that opens
  into the full one. `/drafts` lands on `/review#drafts`; a draft's page says
  Review › Drafts.

- **Data is one page per model** (D-1): the line as its header (three
  stations, the warehouse file and the measures between them, the reports'
  verdicts as chip counts), then tabs Model · Transform · Sources · Runs;
  `/data` lists the models one row each, and the Map is its picture view
  (`/data?view=map`) drawn with the line's nodes. Refresh data is the
  Transform tab's one primary action, and it and every run button render for
  an admin only. Closed item 1 ("DuckDBConnector" is "DuckDB file", "STEP /
  never run" is gone, sink checks read "checks passed when last written") and
  the Reports-stage preview with its Preview/Config switch (retired: the
  Reports station opens the library).

- **Model switcher as the frame of the app** — one control at the top of the
  sidebar narrows every page (Data model, Explore, Refresh, Reports, Sources,
  Runs) to a model; `/m/<model>/<page>` and an all-models `/<page>`; the last
  pick is remembered; old addresses redirect. "Contract" is "Data model"
  again. Removed the dead nav code from earlier designs.
- **"You are here" on every page** `[nav-you-are-here]` — every frame page
  marks its sidebar entry.
- **Unknown URLs render a real "Page not found"** `[blank-page]`.
- **Sources opens on its first source**, not a blank pane; the model page no
  longer repeats the model's name or stacks two rows of tabs.
- **Everything clickable works from a keyboard** `[click-not-keyboard]` —
  list rows and the Verify drop zone take Tab, Enter and Space
  (`pressable()` in `Shared.jsx`); one focus ring for the whole app
  (`--focus-ring`); diagram edges no longer take focus.
- **Phone header**: the menu button has a name, the header is a landmark, and
  it says which model you are in (tap it to switch).
- **Tap targets**: small buttons are 24px tall; the Refresh page opens on its
  list of steps on a phone, where the run buttons are full size.
- **Contrast in both themes** `[axe:color-contrast]` `[token-contrast]` — dark
  mode's status text (green / amber / red: whether a report reproduces) was at
  2:1, and its grey text at 3:1; both now pass on every surface. Unstyled
  links take the accent colour. The Docs page has one h1.
- **Reports opens on "At a glance"**, not a blank pane — how many reports,
  how many reproduce, what needs a look, the latest builds (each opens).
- **An open report names itself** on a phone (it is the page's h1 there).
- **Workflow folded into Get started** as "The three phases"; `/workflow`
  lands there. Its phase colours are theme tokens (`--phase-*`), readable in
  dark mode. Scrolling code blocks take keyboard focus.
- **The audit sees the populated app**: it builds every report before
  crawling, so verdicts, receipts and latest builds are checked, not only the
  never-built empty states.
- **A report belongs to the models it reads**, not the folder it sits in. The
  reports API returns `models` from each report's data bindings (by the name
  the switcher lists), so a model's Reports, Runs and attention items are
  right even when folder and model names differ (the demo app's are).
- **Live discovery no longer forgets an app module's own reports** five
  seconds after start; it forgets only what its own scan covers.
- **Diagram, Refresh and search colours are theme tokens** (`--role-*`,
  `--phase-*`): readable in dark mode, and no `${colour}22` alpha-gluing.
- **Every demo model has a pipeline.** `sales` and `wealth` now name the models
  they touch (`runner.models`), so SalesModel, SalesPipelineModel and
  WealthModel each show one on Refresh; a pipeline may belong to several.
  The audit flags any model with none.
- **Report design system v2 (Step 1)**: one type scale, accent and dark
  palette, `auto` mode, themes as accent presets (DS-1); masthead, footer,
  12-column grid (DS-2); KPI with a stamped delta (DS-3); one chart style
  (DS-4); tables (DS-5); the receipt as a certificate (DS-6); the editorial on
  the system (DS-7); showcase, scaffolds and demo app on it (DS-8).
- **The audit renders every report** (DS-9): both modes and widths into
  `report-sheet.png`, font families, accents, shadows, gradients and looks
  ratcheted per project against committed baselines
  `[metric:report_*]`; a page laid out wider than the phone
  `[report-phone-layout]` (every built report but one named no viewport; the
  build now adds it).
- **Reports home (Step 2)**: names, not identifiers, with a model `label`
  (R-2); one verdict chip and one rule for it (R-3); `/` is the library and
  the sidebar is four places, old addresses redirect (R-1); the report page is
  the artifact under one command bar with "About this build" (R-4); History
  rows as sentences, grouped by day, empty columns not drawn, cards on a
  phone; the library's two-line descriptions and the masthead receipt checked
  at 390 (R-5). Closes the audit's findings 12 and 15.
