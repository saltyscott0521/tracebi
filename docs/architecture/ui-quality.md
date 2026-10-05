# The UI quality bar

What "top tier" means for the TraceBi web app, written so a script can check
most of it and a reviewer can check the rest in ten minutes.

`python scripts/ui_audit.py` serves the reference project, crawls every page
it can reach in desktop and phone widths, light and dark, and writes
`findings.json` plus a contact sheet of screenshots. Run it with
`--baseline <old findings.json>` and any new finding fails the run: a fix can
never quietly undo another. The open work lives in `ui-backlog.md`.

## How the loop works

1. Audit (`--baseline` the last run), and look at the contact sheet.
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
- **You always know where you are.** Exactly one sidebar entry is marked
  as the current page `[nav-you-are-here]`. Exactly one `h1`, naming the
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
- **Picking a model shows exactly what belongs to it**: each model's Reports
  and Sources list what the API says it owns `[scope-mismatch]`; every model a
  report reads is one the switcher lists `[report-model-unlisted]`; nothing
  appears or vanishes while the audit runs `[registry-drift]`.
- **No model is a dead end**: every model has at least one report
  `[model-without-reports]`. (The live demo showed three models with none:
  see the discovery fix under Rules learned.)
- **Every model has a pipeline** `[model-without-pipeline]`: something its
  Refresh page can run. A pipeline belongs to the models it names
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

Run it on both projects: the reference project, and the demo app
(`--app tracebi.web.demo_app`: its own models, reports folder and pipelines,
registered by an app module rather than found under `reports/`). Each has caught what the other could not.

Checked by eye, from the contact sheet:

- **One idea per page.** The title says what the page is, the subtitle says
  what to do on it, in words a reader uses (no "sink", "contract",
  "connector" unless the page explains them).
- **The model is the frame.** With more than one model, every list says
  which model each row belongs to, and the model switcher narrows every page.
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
  from the same data: the Runs page shows the verdict the Reports page shows
  (`/api/desk`) on a report's newest build, and a neutral "Not checked" on every
  older one. A build row stores no verdict, so it never reads green by itself.
- A row of seven buttons is a grouping problem, not a wrapping problem: one
  primary action, the rest quiet, and a menu for the family (Download holds
  HTML, Excel and PDF, each with its one-line caveat). An open item gets the
  page's full width; its list is one click away.
- Focus that sits inside a report's frame belongs to the element inside it, so
  the audit judges that element; the frame draws no ring of its own.
