---
slug: design-consistency-over-variety
title: The same kind of data looks the same everywhere — variety for its own sake costs the reader
when: a page has several charts or KPIs, or a report series will be read month after month
---
**The pitfall.** Four trends drawn as a line, an area, a column and a stepped
chart "so it isn't boring"; revenue blue in one chart and orange in the next;
currency with cents on one card and in millions on another. Each switch makes
the reader relearn how to read the page, and invites them to find meaning in
differences that mean nothing. A page of five sorted bar charts is easier to
read than five different chart types.

**The correct pattern in TraceBi.**

- **Same question, same chart.** Every trend is a `line`; every ranking is a
  sorted `barh`. Change the chart type only when the question changes
  ([[design-choose-the-chart]]).
- **A measure keeps one color across the page.** If revenue is the accent in
  the first chart, it's the accent everywhere. Keep series in the same order in
  every chart so each keeps its color.
- **A measure keeps one format everywhere.** Declare the format on the measure
  (`format="currency0"`) rather than per figure, so every card, axis and table
  agrees ([[design-format-for-reading]]).
- **One notation for scenarios.** Pick a convention for actual vs. plan vs.
  prior period and keep it everywhere — for example, actual in the accent,
  prior period in grey, plan in a lighter tint. The business reporting standard
  IBCS makes exactly this its "unify" rule: the same thing always looks the
  same.
- **Consistent across issues, too.** A monthly report should look the same
  every month, so readers spot what changed in the data, not in the layout.
  Put shared choices in `reports/_theme.css` rather than in each report.

**The tell.** Point at two figures of different types and ask why. If the
answer is "variety", make them the same.
