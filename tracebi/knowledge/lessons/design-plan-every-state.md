---
slug: design-plan-every-state
title: Design the empty and filtered-to-nothing states, not only the full one
when: a figure can be empty — a filter, a new period, a narrow segment, a live control
---
**The pitfall.** The report is designed against the one dataset the author had:
full, recent, every segment present. Then a reader picks a filter that matches
nothing, or a new month has no trades yet, and the page shows a lonely "no data"
under a confident headline, or a KPI card sits blank where "nothing to report
yet" was the truth. Nobody designed that state, so it looks broken.

**What TraceBi does for you.** A table or chart whose rows are empty says
**"no data"** instead of a blank box, both in the built file and after a filter
in the browser. You don't need to write empty markup for tables and charts.

**What it does not do.** A **value figure** over no rows is left **blank** — a
sum over nothing comes back empty, not 0 — and a blank card under a confident
label is the state that looks broken.

**What you still have to do.**

- **Say what the empty state means, next to the figure that can be empty.** A
  short note under a filterable table — "No positions match. Clear the filter or
  pick another sector." — turns a dead end into a next step.
- **Give a KPI that can be empty something to say.** If "no activity this
  period" is possible, put that sentence in the card's label or the text beside
  it, so a blank value reads as "nothing yet", not "broken". A comparison
  ([[design-kpis-with-context]]) also makes an empty period visible. And never
  type a 0 in by hand to fill the gap — that's an unbacked number.
- **Headlines must survive thin data.** A title that says "Tech leads the book"
  is wrong when the filter hides Tech. Bind headline numbers to a binding the
  controls don't touch — value figures never react to controls, by design.
- **Check the build against a quiet period.** Point the query at a narrow
  segment or an empty month once, and look at the page.

**The tell.** If you have only ever seen the report with every row present, you
haven't seen it the way its readers will.
