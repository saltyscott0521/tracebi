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
  `[axe:*]`, in light *and* dark (contrast is checked in both).
- **It fits.** No sideways scrolling at 390px or 1440px `[h-overflow]`.
  Tap targets are at least 24×24 on a phone `[small-target]`. Text that is
  cut off has a tooltip with the rest `[truncated-no-title]`.
- **No blank half-pages.** A list-and-detail page opens on something, not on
  "Select an item" `[empty-detail-pane]`.
- **It is quick.** Every page settles within 2.5s on the reference project
  `[slow-page]`.

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
