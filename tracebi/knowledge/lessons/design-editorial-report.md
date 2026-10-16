---
slug: design-editorial-report
title: Write a report like an editor — the headline is the finding, the prose carries the numbers
when: writing a report someone reads top to bottom (tracebi new-report's editorial page), or a report "reads like a data dump"
---
**The pitfall.** A report that is a dashboard with paragraphs in between: a
title that names the data ("Q3 Revenue"), a chart, a sentence describing the
chart ("This chart shows revenue by region"), another chart. The reader has to
do the analysis the writer skipped, and the one thing they needed to decide is
in the fourth section, if anywhere.

**The headline is the finding.** A verb and a direction: "Midwest leads on
revenue as the West slows", not "Revenue by region". Bind any number in it as a
value figure — the build refuses a typed one. The `.tb-kicker` above it names
the subject; the `.tb-dek` under it says in one or two sentences why it matters
to this reader ([[design-lead-with-the-answer]]).

**The first paragraph does the whole job.** A reader who stops after the
`.tb-lede` should know the answer, the size of it and the comparison that makes
it mean something. Everything below is evidence, in order of importance.

**One idea per section.** Each `<h2>` is a claim, not a topic ("The West's
slowdown is two accounts", not "Regional detail"). One to three short
paragraphs, then the figure that proves it.

**Say what to see before showing it.** The sentence above a figure tells the
reader what to look for; the `<figcaption>` says what the figure is and its
unit. A chart nobody is told to read is decoration ([[design-choose-the-chart]]).

**Numbers in sentences, not beside them.** Every number in the prose is a
`<span data-tb-figure="value">`, formatted for reading — rounded, with its unit
([[design-format-for-reading]]). One number per sentence where you can; never a
row of them. A `.tb-pullstat` is for the single number the reader should
remember, with the sentence that explains it.

**End with what to do.** The last section is the decision or the next step the
report supports — and who owns it. The methodology follows, small, for the
reader who checks.

**Words, not jargon.** Plain verbs, short sentences, the reader's names for
things, not the model's (`fact_orders` is never on the page)
([[design-words-on-the-page]]).

**The tell.** Read only the headline, the standfirst and each `<h2>`. If that
is not the story in full, the report is still a dump with paragraphs.
