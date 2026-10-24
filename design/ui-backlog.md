# UI backlog

The loop in `ui-quality.md` takes the top open item. An item keeps its number
for good (`NOTES.md` cites them); a closed one is deleted, and the change that
closed it says so in `CHANGELOG.md`. Checked against the app on 2026-10-24:
what the board, the table page, the Transforms tab, the role tiers, the
theme's OS default and the Steps table's chips closed is gone from this list.

## Open

The app:

3. **Bundle is 1.2 MB of JS** (364 KB gzipped). The bundler already drops
   what nothing imports; split routes instead (React Flow, Markdown,
   Recharts load only on the pages that use them). Build into an empty
   `dist` before an audit, or a stale second bundle is counted.
4. **Hard-coded colours in JSX** (ten left, mostly React Flow's `nodeColor`,
   handle borders and arrow markers in `Models.jsx`, `Pipelines.jsx`,
   `Lineage.jsx`, `ReportLineage.jsx`): each is a dark-mode bug waiting.
   Move them to tokens.
6. **`Btn` drops a caller's colours**: its variant styles are applied after
   `style`, so `style={{ background }}` is silently overridden.
21. **The phone header is translucent**: a scrolled list shows through it
    (History's sticky day header sits under it).
24. **The Transform flow zooms in two steps** only (D-1).
27. **`scripts/ui_audit.py`'s `scope-mismatch` detail still says "the model
    switcher"**; it means the model chip.
32. **A pipeline run in History goes by its identifier** (`portfolio_model`):
    `/api/runs` gives a report run a `display_name` and a pipeline run none.
    Give it its model's label.
33. **History's "N older runs" counts what `/api/runs` returned** (the last
    50 runs, default `limit`), not every run the store holds.
35. **Links inside a page still point past the role**: a viewer's report
    panel and Ask can link to History or a model's Data page, which then shows
    the plain "for analysts / admins" page. Hide those links by the same
    `mayUse` rule the sidebar uses.

Ask:

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
37. **Ask's "Keep this" does not carry a selection into the page.** A kept
    answer opens a one-figure draft; it could instead open the report it came
    from with the selection in the frame's hash (`#sel=`), so the reader lands
    on the same cut, Local, without a draft.

Reports:

7. **Affordability is a second bespoke look**: Inter, a green accent, its own
   paper ground, resting shadows and gradients, pinned light. Move it onto
   the system, or name it beside `aum_by_branch` as a bespoke example.
8. **The reference project has more than one look**: `portfolio_book` (navy)
   and `portfolio_showcase` (teal, Fraunces) carry their own accent presets
   (`report_accents`, `report_looks` in the baseline). Decide whether a project
   is one accent, and ratchet the count down.
9. **Small multiples are dense on a phone** (DS-4).
10. **The showcase's striped frozen column keeps a light shade in dark** (DS-5).
12. **A line's end label is cut at the plot's top edge on a phone**
    (`portfolio_concentration`'s cumulative share at 390px).
18. **`site/sample/portfolio_showcase.html` predates the report design
    system** (built 2026-10-03): rebuild it with the current runtime.
38. **The page engine keys slices by fact name.** `tracebiCalc.load(fact, …)`
    holds one slice per fact name, so a page reading two models that each
    have a fact of the same name would load one over the other. Key by
    `model.fact` (the calc payload already records both).

Not UI, found on the way:

19. **A report build records no finish time** (`record_report_build`), so
    History shows how long only for background runs, schedules and pipeline
    runs. Record the build's start and finish.
20. **`tracebi migrate model` drops `owners`.** `model_yaml._document` puts
    `owners` in the document, but `model_to_yaml` writes only `label` and the
    `_SECTIONS` keys, so a migrated model loses who may publish it.
36. **The code still says "receipt".** Readers see *trace* everywhere; the
    identifiers kept the old word so the artifact contract did not move: the
    `tracebi-receipt` block id, `.tb-receipt*` classes, `data-tb-receipt-*`
    attributes, `tracebi.renderReceipt` / `receiptFileName`, Python
    `receipt_*` names, `ReceiptFrame.jsx`, the panel's `receipt` tab key and
    the `receipt_drawer` key in `tracebi context`. Rename them together, with
    a reader for the old block id so files built before the rename still open
    their drawer (and `verify --file` still reads them).

The committed audit baselines (`ui-audit-baseline-*.json`) hold the
mechanical findings still counted (on an open report: `blank-page`,
`no-focus-ring` into the frame, `one-h1`, `small-target`; and `slow-page`);
`scripts/ui_audit.py` fails on a new one.
