---
slug: design-cut-the-chrome
title: Cut the decoration — the telltale marks of a generated report
when: a report looks "AI-made", or before calling any report page finished
---
**The pitfall.** A report can be correct, well-bound and fully receipted, and
still look machine-made at a glance. The marks are consistent enough to list,
and each one makes the reader trust the page a little less — the opposite of
what a receipted report is for.

**Remove these on sight:**

- **Emoji as section markers** (📊 Overview, 💰 Revenue). Headings do that job.
- **Gradients, glows and glassy cards**; a drop shadow on every box. Cards are a
  grouping device — a hairline border (`.tb-card`) is enough.
- **Every number badged.** Badges are off by default for a reason: mark only the
  exceptions (an estimate, a python-derived figure). The receipt drawer already
  carries provenance for everything else.
- **Every KPI in a same-sized card in one long row** — see
  [[design-kpis-with-context]].
- **Decorative color** — see [[design-color-with-meaning]].
- **Filler prose**: "This dashboard provides a comprehensive overview of…".
  Delete the sentence; if the page needs an intro, it's the answer
  ([[design-lead-with-the-answer]]).
- **Centered everything.** Left-align text and labels; right-align numbers so
  digits line up.
- **Numbered section markers (01 / 02 / 03)** on sections that aren't a sequence.

**What to keep instead.** Whitespace, a consistent grid (`.tb-cols-2`,
`.tb-cols-3`), one type size per role, and the design tokens rather than new
colors. Restraint reads as confidence.

**The tell.** Show the page to someone for five seconds and ask what it says.
If they describe the styling instead of the finding, cut until they don't.
