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
27. **`scripts/ui_audit.py`'s `scope-mismatch` detail still says "the model
    switcher"**; it means the model chip.
39. **Inline paddings in JSX are off the 4px grid** (about 150 values of 6,
    10, 14, 18px in `style={{…}}`, mostly the React Flow nodes, the palette
    and the sidebar). global.css is on the grid (UI-4A); move these as each
    page is touched, into a class where the style is shared.
40. **Diagram node labels now use the eyebrow step** (10.5px, was 8.5–10px
    inside the ERD and step nodes): check the ERD's column rows at a narrow
    canvas still fit their 300px node, and move the node styles into classes.

Ask:

28. **An Ask answer carries no fingerprint.** `POST /api/models/{name}/query`
    returns lineage, not the stamp `query_model` gives an agent, so the
    answer cannot quote one beside its number.
29. **Ask's filters are equality on dimension values.** Ranges, a measure
    threshold (`having`) and fact columns are Advanced only; the sentence
    shows them in words but offers no token for them.
37. **Ask's "Keep this" does not carry a selection into the page.** A kept
    answer opens a one-figure draft; it could instead open the report it came
    from with the selection in the frame's hash (`#sel=`), so the reader lands
    on the same cut, Local, without a draft.

Reports:

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
