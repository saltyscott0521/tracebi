### Changed — every page is framed: a masthead, a footer, a 1,200px measure

- A page opens with a masthead: `<header class="tb-masthead">` (kicker,
  `<h1>`, `.tb-standfirst`, and `.tb-masthead-meta` holding the period, the
  build time and the verdict chip). `data-tb-period` names what the numbers
  cover; the runtime fills the meta and adds what a template leaves out.
  The kit's `<Masthead title kicker period mark>` renders it. The editorial
  hero is the same masthead (`tb-masthead tb-article-head`), and `.tb-dek` /
  `.tb-byline` give way to `.tb-standfirst` / `.tb-masthead-meta`.
- The verdict chip (`.tb-verdict`) is set from the file itself: "Not
  checked" on a built file (nothing has re-run its queries; `tracebi verify`
  does), "Draft" on a preview. It is never green on the page's say-so.
  `--tb-warn` joins `--tb-good` / `--tb-bad` for the amber verdict.
- The "About this report" block is gone from the page body. A footer ends
  the page instead (`<footer class="tb-footer" data-tb-methodology>`): your
  sources, then one line — who, when, which model, and "The receipt does
  not claim the numbers are right." — and "How these numbers were made"
  behind a disclosure, holding what the receipt is for and the stated
  methodology. The receipt block now also carries that text
  (`stated_methodology`) and `rendered_by`, for the drawer. In an app,
  `<Footer />` places it at the end of the main column.
- The page measure is 1,200px (`.tb-page`, and the page body); apps use
  `<main className="tb-page …">`. A `.tb-grid` whose panels carry
  `.tb-span-4/6/8/12` is a 12-column grid.
