---
slug: design-words-on-the-page
title: Every word on a report page is interface — titles state findings, labels name units, blanks say why
when: writing a report's title, headings, figure titles, labels, captions, notes, control labels or empty-state text
---
**The pitfall.** A title "Portfolio Analytics Dashboard", section headings
"Overview" and "Insights", a chart titled "Fair Value", a caption that restates
the chart ("This chart shows fair value by sector"), a search box whose only
label is its placeholder, and a table that silently shows nothing after a filter.
Every word is generic, and it could sit on any report.

**The correct pattern in TraceBi.**

- **Titles state the finding, headings name the question.** The page title or
  its `.tb-lede` says what was found, with the numbers bound (see
  [[design-lead-with-the-answer]]). A chart title says what to see, like
  "Software holds a third of fair value", rather than repeating its axes.
- **Labels carry unit and period**: "Fair value, $ · end of Aug", "Spread, bps".
  A number whose unit the reader has to guess gets misquoted. Write in sentence
  case. The only capitals are the small uppercase KPI and table-header labels
  that `tracebi.css` already styles, so never type text in capitals.
- **Captions add what the chart can't show**: the source, a definition ("mark =
  fair value ÷ cost"), or a caveat. Use `.tb-note` for them. Never narrate the
  picture.
- **Controls get real labels.** Wrap each filter and search box in a `<label>`
  ("Search", "Sector"). A placeholder disappears as soon as someone types and
  isn't read reliably by screen readers.
- **An empty state says what happened.** A value figure keeps the text you write
  inside it when its binding comes back empty, so write "no trades this period"
  there, not "—". A note beside a figure that might be empty should say why it
  might be (see [[design-plan-every-state]]).
- **Plain words over system words.** Write "Download CSV", not "Export dataset".
  Write "Fair value", not `fair_value`. Leave out filler adjectives such as
  "powerful", "comprehensive" or "seamless" (see [[design-cut-the-chrome]]).
- **Honesty words are locked.** Don't rephrase a receipt's wording in your
  prose. "The sink satisfied its contract" stays as written, and nothing on the
  page calls the transform "verified".

**The tell.** Read only the words on the page, with no numbers and no charts.
If the page could belong to any company's report, the words aren't doing their
job.
