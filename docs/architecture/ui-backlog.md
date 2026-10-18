# UI backlog

The loop in `ui-quality.md` takes the top open item. Done items move to the
bottom with the change that closed them.

## Open

1. **Words a reader doesn't use**: "semantic contract", "DuckDBConnector"
   as a badge, "STEP / never run" in the Refresh flow.
2. **"Checks stale" items name no model**: a stale sink check shows only
    under All models. Attribute warehouse tables to the models that read them.
3. **Bundle is 1.1 MB of JS.** Split routes (React Flow, Markdown, Recharts
    load only on the pages that use them).
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

Left by Step 2 of the UX plan ([[ux-plan-2026-10-17]]), app side:

14. **Re-run the ui-audit baselines**: the committed findings still name the
    addresses before R-1 (`/m/<model>/…`, `/reports?r=`), so item 13 cannot
    be retriaged against them.
15. **The Data page's Reports-stage preview keeps its Preview/Config switch**
    (R-4 moved Config into Files on the report page); Step 3 (D-1) retires
    that preview.
16. **Docs still say reports are served "on the model's Overview"**: about
    nine lines in `CLAUDE.md`, `the-three-phase-workflow.md`,
    `report-json.md`, `analyst-guide.md` and `notebook-guide.md` (and the
    `site/docs` twins). For D-3.
17. **`demo-script.md` points at "the green badges above the report"**, which
    R-3 removed; the chip in the masthead is what to point at.
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

## Done

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
