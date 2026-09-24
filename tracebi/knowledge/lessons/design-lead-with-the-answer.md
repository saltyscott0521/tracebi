---
slug: design-lead-with-the-answer
title: A report page answers one question, and its title says the answer
when: starting a report page or section — writing its title, ordering its figures
---
**The pitfall.** A page titled "Portfolio Dashboard" over a grid of eight equal
cards. Every figure is correct and none of them tells the reader anything: they
have to work out what matters, in what order, and what it means. This is the
most common shape of generated reports — the layout is a *list of available
data*, not an *answer*.

**The correct pattern in TraceBi.** Decide the one question the page answers
before binding anything, then let the page read top to bottom as the answer:

1. **The title states the finding**, not the topic. "Tech is now 41% of the
   book, up from 33%" — not "Sector Allocation". Bind the numbers in it
   (`<span data-tb-figure="value" …>`) so the headline is a live, receipted
   figure rather than typed-in text.
2. **The first figure is the evidence for that sentence** — the one chart or KPI
   that proves it. Detail comes after, never before.
3. **Everything else earns its place** by supporting the answer. A figure that
   doesn't is a second question; it belongs on another page or a tab
   (`data-tb-tab`), not squeezed onto this one.

**The tell.** If you could swap the title onto a different month's data and it
would still be true, it's a label, not an answer. If two figures on the page
answer different questions, split the page.

See [[design-kpis-with-context]] for the numbers that usually sit under the
headline, and [[design-cut-the-chrome]] for what to remove once the answer is
clear.
