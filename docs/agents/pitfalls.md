# Pitfalls: bugs we hit, and the rule that prevents each

**Every entry here happened while working on this repo. Read it before
changing the report runtime, the stylesheet, the spec compiler or the CLI.**
Each one has a rule for authors (agents and people) and, where one exists, a
framework change that would make the mistake impossible.

Add to this page whenever you hit a new one.

---

## Styling and the report runtime

**1. An undefined CSS variable fails silently.**
The Reports page's main download button used `var(--accent)`, which was never
defined. It rendered white on white, invisible.
- *Rule:* use only tokens defined in `tracebi.css` (or your own `:root`).
  Search for the definition before you use a `var(--…)`.
- *Framework:* a lint that flags `var(--name)` with no definition in the stack.

**2. A modifier class can lose to a more specific rule.**
`.tb-num { text-align: right }` never applied, because
`.tb-table td { text-align: left }` is more specific. Every numeric column was
left-aligned.
- *Rule:* when a class modifies a component, match the component rule's
  specificity (`.tb-table .tb-num`), then look at the result.

**3. A chart default must allow for the space it gets.**
Forcing every category label to show made labels overlap in narrow cards.
- *Rule:* defaults that add content (labels, legends, values) must check the
  available width. `polishOption` now rotates labels when each category gets
  less than about 80px.

**4. A wide table must not widen the page on a phone.**
- *Rule:* check new layouts at 390px wide. The stylesheet now makes tables
  scroll inside their card on narrow screens.

**5. A server-only feature must detect when there is no server.**
A report with live filtering tried to reach its server when opened from disk
(`file://`) and logged an error in the console.
- *Rule:* anything that calls the server takes the documented offline path
  when `location.protocol` is `file:`.

**6. Two formatters mean two places to change.**
Numbers are formatted in JavaScript (`applyNamedFormat`) and again in Python
(`_ssr_format`) for the no-JavaScript view. Fixing negative money
(`-$1,234`, not `$-1,234`) needed both.
- *Rule:* change them in the same commit. The parity test catches a
  mismatch.

## The spec compiler and emitters

**7. Emit one element per logical block.**
The compiler emitted each chart's title and card as siblings. In a
side-by-side row, the title took one grid cell and the chart was squashed
into the next.
- *Rule:* a title belongs inside its card. Emitters return one element that
  a layout can place.

**8. "Warn and drop" still ships a broken page.**
The compiler dropped a table's column labels and currency formats with a
warning nobody read, so spec reports showed raw numbers.
- *Rule:* if the runtime can express a setting, pass it through. Warn only
  for what truly has no equivalent.

## Concurrency and state

**9. Context variables don't cross into worker threads.**
`tracebi schedule serve` set the audit actor in the main thread; APScheduler
runs jobs on worker threads, which don't inherit it, so runs were recorded with
no actor.
- *Rule:* set context (`with actor(...)`) inside the job, where it runs.

**10. Two downloads are two renders.**
The web app re-renders a report on each download, so a receipt saved earlier
can fail to match an HTML file downloaded later.
- *Rule:* hand out a report and its receipt from the same render.

## Docs and claims

**11. A claim about behaviour must be run, not remembered.**
The docs said `tracebi verify --file` needs "only the .html". It also needs the
`.manifest.json` beside it.
- *Rule:* before writing what a command does, run it.

**12. Check where a document will be published.**
The repo is public, and `site/docs/` publishes `docs/` to the website.
Business strategy almost went out with it.
- *Rule:* before committing pricing, revenue, competitor or hiring material,
  check the repo's visibility. Keep internal documents out of the public
  site (`HIDDEN` in `site/build_docs.py`) or out of the repo.

**13. Generated files must be regenerated.**
`site/docs/` is committed. After editing `docs/`, run
`python site/build_docs.py`, or `test_docs_site.py` fails.

## Tests

**14. Don't pin presentation in tests.**
Tests pinned hex colours, CSS text, SVG hashes and file sizes. None caught a
bug; every design change broke them. They were removed (see
[[test-suite-review]]).
- *Rule:* test behaviour: the data is unchanged, honesty rules hold, two
  implementations agree, security holds. Not how it looks.

**15. Tests must write to temporary folders.**
Some tests write receipts into the repo's `output/` folder, leaving untracked
files in every contributor's checkout.
- *Rule:* use `tmp_path`.

**16. A failing test run may be the environment.**
In a fresh container, 12 tests failed because the system `cryptography`
package was broken and `tzdata` was missing.
- *Rule:* read the traceback before touching code. Install the missing
  package (`pip install --ignore-installed cryptography cffi tzdata`) and
  rerun.

## Editing files

**17. Rewriting JSON with a library reformats the whole file.**
`json.load` then `json.dump` turned a three-line change into an 80-line diff.
- *Rule:* edit JSON as text for small changes, so the diff shows only what
  changed.

**18. Bound numbers only in report prose.**
The final build fails when a template's text contains a typed-in number of
two or more digits (a single digit, as in "Q3", is allowed). Bind the number
(`data-tb-figure="value"`) or leave it out of the prose.

## Assets and licences

**19. Everything must be inlined.**
The report's security policy blocks web fonts, CDN scripts and remote images.
- *Rule:* put fonts and images in the package's `assets/` folder; the build
  inlines them.

**20. Ship the licence with a font.**
Open-licence fonts (SIL OFL) may be embedded, but the licence must travel with
them. The showcase keeps `Inter-OFL.txt` and `Fraunces-OFL.txt` beside the font
files.
