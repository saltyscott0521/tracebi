# The UI quality bar

What "top tier" means for the TraceBi web app, written so a script can check
most of it and a reviewer can check the rest in ten minutes.

`python scripts/ui_audit.py` serves the reference project, crawls every page
it can reach in desktop and phone widths, light and dark, and writes
`findings.json` plus a contact sheet of screenshots. It then opens every
report as delivered (`/r/<name>`) at 1440 and 390 wide, light and dark, into
one `report-sheet.png` (beside `findings.json`; `report-sheet.html` is the same
tiles, browsable), and counts what makes a project look like more than one
system. Run it with `--baseline <old findings.json>` and any new finding fails
the run: a fix can never quietly undo another. The open work lives in
`ui-backlog.md`.

The baselines are committed: `ui-audit-baseline-reference.json` (the
reference project) and `ui-audit-baseline-demo.json` (`--app
tracebi.web.demo_app`), both in this folder. The sheets are not committed (they
are megabytes); a run prints where it wrote them.

```bash
python scripts/ui_audit.py --out /tmp/a --baseline docs/architecture/ui-audit-baseline-reference.json
python scripts/ui_audit.py --app tracebi.web.demo_app --out /tmp/d \
    --baseline docs/architecture/ui-audit-baseline-demo.json
```

A change that fixes findings, or deliberately changes a count, commits the new
`findings.json` over the baseline in the same change.

## How the loop works

1. Audit (`--baseline` the committed baseline), and look at the contact
   sheet. Before each release, look at the report sheet too: every report,
   both modes, both widths, side by side.
2. Take the top item in `ui-backlog.md`. Fix it in the smallest change that
   fixes it everywhere it occurs, not just on the page where it was seen.
3. If the bug is a *kind* of bug, add a check for that kind to
   `scripts/ui_audit.py` in the same change. Then it stays fixed.
4. Build, run `pytest tests/`, run the audit against the baseline. Commit.
5. Record what was learned here, under "Rules learned", so the next pass
   starts from it.

## The bar

Checked by the script (rule name in brackets):

- **Nothing breaks.** No console errors, page errors or failed API calls on
  any page `[browser-error]`. No blank page `[blank-page]`, no raw
  `undefined` / `NaN` / traceback shown to a reader `[raw-garbage]`, no
  "not found" except on a page that does not exist `[not-found]`.
- **You always know where you are.** Exactly one sidebar entry (one of the
  five places; on an open report, the rail's) is marked as the
  current page `[nav-you-are-here]`. Exactly one `h1`, naming the
  page `[one-h1]`.
- **Everything works from a keyboard.** Anything that looks clickable is a
  link or a button `[click-not-keyboard]`. Focus is always visible
  `[no-focus-ring]`. axe-core finds no serious or critical violations
  `[axe:*]`, in light *and* dark (contrast is checked in both). Every text
  colour token reads at 4.5:1 on every surface token, and every diagram tag
  on its own background, in both themes `[token-contrast]`.
- **It fits.** No sideways scrolling at 390px or 1440px `[h-overflow]`.
  Tap targets are at least 24×24 on a phone `[small-target]`. Text that is
  cut off has a tooltip with the rest `[truncated-no-title]`.
- **No blank half-pages.** A list-and-detail page opens on something, not on
  "Select an item" `[empty-detail-pane]`.
- **A row of actions fits** `[action-row-wraps]`: three or more buttons in a
  flat row do not wrap onto a second line at desktop width.
- **It is quick.** Every page settles within 2.5s on the reference project
  `[slow-page]`. The JS bundle and the count of hard-coded colours never grow
  against the baseline `[metric:*]`.
- **Picking a model shows exactly what belongs to it**: the library filtered
  to a model (`/?model=<m>`) lists what the API says it owns
  `[scope-mismatch]`; every model a report reads is one the model chips list
  `[report-model-unlisted]`; nothing
  appears or vanishes while the audit runs `[registry-drift]`.
- **No model is a dead end**: every model has at least one report
  `[model-without-reports]`. (The live demo showed three models with none:
  see the discovery fix under Rules learned.)
- **Every model has a pipeline** `[model-without-pipeline]`: something its
  Transform tab can run. A pipeline belongs to the models it names
  (`runner.models`), else the one `model_pipeline` stamped, else its own name.
- **The look** ([[design-direction]]): Hanken Grotesk loads `[theme-font-loaded]`
  `[theme-font]`; the brand is cobalt and stays in its blue family, and other
  colour means something (green reproduces, amber needs a look, red does not
  reproduce) `[theme-brand-colour]`; the dark theme
  sets its own ink `[theme-dark-ink]`; resting shadows are none
  `[theme-shadow]`; no decorative gradients or blur `[theme-decoration]`.
- **A report carries the same look** `[report-style]`: `tracebi.css` leads with
  Hanken Grotesk (inlined, not fetched) and every report text token reads at 4.5:1 on
  every surface a report puts text on.
- **No colour tricks that break themes**: no `${colour}22` hex-alpha gluing
  `[hex-alpha-concat]`.
- **One set of parts.** A state is a sentence-case chip: nothing styled as a
  pill (filled or outlined, rounded, inline) is upper case `[uppercase-state]`.
  The app writes a moment in at most two shapes across the whole crawl, the
  stamp ("Oct 23 · 11:48") and the recency ("2 h ago"), both from
  `web/ui/src/when.js` `[date-formats]`; values in a data table, code and the
  Docs pages are not the app's words and are not counted.
- **Every report renders as delivered** `[report-unrendered]`, with no browser
  error `[browser-error]`, laid out at the phone's own width
  `[report-phone-layout]` and without sideways scrolling `[h-overflow]`.
- **A project's reports are one system** `[metric:report_*]`, counted from the
  rendered pages and never allowed to grow against the baseline:
  `report_font_families` (the first family of the computed font on every
  visible text node), `report_accents` (the computed `--tb-accent` light/dark
  pair per report), `report_box_shadows` and `report_gradients` (elements with
  a resting shadow that has blur or spread, or a gradient background or SVG
  gradient; the chart tooltip, a menu or popover and the trace drawer may
  keep theirs), and `report_looks` (display face + accent; a look not in the
  baseline fails the run even if the count does not grow). The target is one
  look per project, plus a named bespoke example.
- **A live page stays light and quick** ([[live-reports-plan]], decision 10):
  the page engine, `tracebi-calc.js`, is at most 50 KB gzipped
  `[engine-size]` and never grows against the baseline
  `[metric:engine_gz_kb]`; each delivered report's file grows at most 10%
  against its own baseline `[metric:report_html_kb]`; and on every live page
  the slowest single plan run, at load and after picking its first filter's
  first value, is at most 100 ms `[calc-slow]` `[metric:calc_ms_max]`. The
  runtime writes that time to `data-tb-calc-ms` on `<html>` after each
  recompute (a measurement, never shown).

Run it on both projects: the reference project, and the demo app
(`--app tracebi.web.demo_app`: its own models, reports folder and pipelines,
registered by an app module rather than found under `reports/`). Each has caught what the other could not.

Checked by eye, from the contact sheet:

- **One idea per page.** The title says what the page is, the subtitle says
  what to do on it, in words a reader uses (no "sink", "contract",
  "connector" unless the page explains them).
- **The model is a filter, not the frame.** Four places (Reports, Ask, Data,
  Review); with more than one model, the library groups reports under their
  model's name and a chip narrows it to one.
- **The sidebar shows what the role uses.** Everyone sees Reports, Ask and
  Docs; an analyst also Review and Data (with no sign-in, all five). Data is
  read-only below admin: Refresh data, a step's Run and the credential forms
  show for an admin only, because they write the warehouse or point the
  server's connections. A viewer meets no instruction they cannot follow (no
  My published, a never-built report says who builds it). A place
  the role cannot use is hidden, not disabled, in the sidebar, the rail, the
  phone's drawer and ⌘K alike; its address shows a plain page saying who it
  is for. Review's tabs (Attention, Drafts, History, Verify) each keep an
  address, and Review is the current entry on all of them.
- **Hierarchy is visible.** The first thing the eye lands on is the thing
  the page is for. Secondary things are quieter, not merely smaller.
- **Empty states teach.** An empty list says what would fill it and how
  (the command, the folder).
- **Light and dark are both designed.** Neither looks like the other inverted.
- **A phone is a first-class screen**, not a squeezed desktop.

## Rules learned

Each fix that taught something general adds a line here.

- Shell bugs (sidebar, phone header) are one bug, not one per page: the
  audit keys them as `(app shell)`.
- A finding is keyed by the element, not its words: ten report rows with the
  same bug are one bug, fixed in the one component that draws them.
- A block that must be clickable (a list row with badges, a drop zone) uses
  `pressable()` from `Shared.jsx`, never a bare `onClick` on a `div`.
- Focus has one look, `--focus-ring`, set once in `global.css`. A component
  moves the ring (offset) but does not remove it.
- A diagram fitted to a phone shrinks everything in it, buttons included. On a
  phone, open the list form of the same thing.
- axe-core cannot judge text on a blurred or layered background, and skips
  it silently. Colour is checked at the source too: the tokens, every pair.
- Dark mode is its own palette, not the light one with the ground swapped:
  every status colour needs a dark value.
- Audit the app people use, not the empty one: the harness builds every
  report before it crawls. Empty states are checked too, but they are not
  the product.
- A control inside a `<label>` is tapped through the label; the tap-target
  check measures the label.
- What a report belongs to is in its data bindings; its folder is a
  convention. Ask the API, never infer from a path.
- A check is only trusted once it has failed on the bug it was written for:
  revert the fix, watch it fail, restore.
- An app that wires its own reports folder (the demo app) fails differently
  from a project that uses `reports/`; a green audit on one says nothing about
  the other. The live site is a third thing: after a deploy, ask its own API.
- Data flows through more than one model (raw tables seeded from one, built into
  another), so a pipeline names the models it touches rather than owning one.
- A colour used for decoration steals its meaning from the status colours:
  the amber "Custom" chip read as "needs a look". How a report is authored is a
  fact, so it is neutral.
- A token with a hex-alpha suffix (`${accent}70`) turns into invalid CSS the
  moment the token becomes `var(--x)`: the pipeline edges silently lost their
  stroke. Use `var(--muted)` or `color-mix`, and check an edge renders.
- A theme token the dark block does not set silently inherits the light value:
  `--blue` stayed near-black and every active tab and row vanished in dark.
- A page that shows a fact another page shows uses the same words and chips,
  from the same data: every verdict is the `Verdict` chip, its state from
  `verdictOf` (`web/ui/src/verdict.js`). History shows the verdict the
  library shows (`/api/desk`) on a report's newest build, and a neutral
  "Not checked" on every older one. A build row stores no verdict, so it never
  reads green by itself.
- Forty rows of the same nine reports is a wall, not a history: a list of
  runs shows each report or pipeline once, its newest run, with "N older
  runs" folded under it (and how many of those failed, so a failure is never
  folded away unsaid). The flat list stays one toggle away, in the address.
  An empty cell's dash is quieter than any text in the row.
- A row of seven buttons is a grouping problem, not a wrapping problem: one
  primary action, the rest quiet, and a menu for the family (Export holds
  HTML, Excel and PDF, and one line saying which carries the trace). An open item gets the
  page's full width; its list is one click away. The report page's bar is
  what everyone may do on the left (Open, Share, Export) and what the role
  allows on the right (Rebuild, Edit as a draft, Build, then the one panel);
  a command the role cannot use is not rendered, never disabled. On a phone
  it is Open, Share and a "…" menu of the rest.
- Focus that sits inside a report's frame belongs to the element inside it, so
  the audit judges that element; the frame draws no ring of its own.
- Parts drift one caller at a time: four tab styles, two chips and seven date
  formats each began as one page's local helper. The parts live in
  `components/Shared.jsx` (`Segmented` for views inside a card, page tabs
  `.dtabs` for addresses; `Chip` for a state, `Badge` for a label that is not
  one; `Btn variant="outline"` and `BtnLink` for every secondary action;
  `ExportCsv`; `Empty`; `Time`), `when.js` (`stamp`, `ago`, `isoTitle`) and
  `format.js` (`count`, `plural`), and a list of things is a `.tb-list`
  table. Reach for them before writing a local one.
- A phone is not a narrow desktop window. The Step 1 captures were taken at
  390px in a desktop browser, where a page with no viewport meta still lays out
  at 390; a phone lays it out at 980 and shrinks it, and only affordability
  named one. The report pass opens reports as a phone does (`is_mobile`), and
  the build now adds the meta to any page that lacks it.
