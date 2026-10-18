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
11. **The selection handshake with a parent that is not the app** (DS-8).
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

22. **The Map's labels are in mono** where the line's are in the sans (D-1).
23. **The Model tab has a second row of tabs inside it** (Diagram, Tables,
    Measures, …) and its **Edit as a draft** button floats alone above them
    (D-1).
24. **The Transform flow zooms in two steps** only (D-1).
25. **The report page's Ask box is off** (`SHOW_ASK = false` in
    `Reports.jsx`): `AskCut` is reachable in code but never shown. Step 4
    decides whether it returns or goes.
26. **`notebook-guide.md`'s `@register.report` section predates the one
    renderer**: a factory with no package is listed but refused (422). Point
    it at a package.
27. **`scripts/ui_audit.py`'s `scope-mismatch` detail still says "the model
    switcher"**; it means the model chip.

## Done

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
