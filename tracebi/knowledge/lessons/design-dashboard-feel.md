---
slug: design-dashboard-feel
title: Make a dashboard feel like a dashboard — ask how it should look, then lay it out to be scanned, not read
when: building a dashboard (several figures someone checks often), choosing its title, navigation, mode or density, or when a page "reads like a document"
---
**The pitfall.** A dashboard built like an essay: a big title, a paragraph, then
one wide card per figure down a long scroll. Every number is right and traced,
and the reader still has to read top to bottom to find the one they came for.
The other half of the pitfall is guessing the look: a dark sidebar dashboard for
someone who prints it, a banner for a page that lives in a tab all day.

**Ask, once.** With a person in the loop, before you build, ask in one short
message: the title and where it sits (left, centred, a banner, or at the top of a
sidebar); one page, top tabs or a sidebar; light, dark or the reader's choice;
comfortable or compact. Offer the look of their last report first and skip what
they already said. With nobody in the loop, use the defaults. Each answer is one
attribute (`presentation.layout.look` in `tracebi context`):

- `data-tb-mode="dark"` or `"light"` on `<html>` (unset is `"auto"`, which
  follows the reader's system), `data-tb-density="compact"`, `data-tb-width="full"`;
- `<div class="tb-tabs" data-tb-nav="side">` for a sidebar, with the whole page
  inside it so the column runs top to bottom;
- `<header class="tb-masthead" data-tb-title="…" data-tb-period="…">` with
  the `<h1>` and a `.tb-standfirst`; the runtime adds the meta line (the
  period, the build time from the trace and the verdict chip). Never type a
  date.

`tracebi new-dashboard "<Name>" --mode … --density … --nav … --title-at …` writes
it.

**Then lay it out to be scanned.**

- **The numbers are the headline.** A slim title, then a KPI strip of three to
  five values, each with its comparison ([[design-kpis-with-context]]). The
  answer sentence ([[design-lead-with-the-answer]]) sits under it, short.
- **One strip with an anchor, not a row of equal boxes.** A `.tb-grid` of
  `.tb-kpi` cells is one panel with hairlines between them. Mark the number the
  page is about `.tb-kpi--lead` (larger, not wider). A row of three
  identical cards is the most recognisable sign of a generated dashboard.
- **Trends under their numbers.** A KPI that changes over time gets a
  `class="tb-spark"` line or area chart bound to the by-period query: the
  shape alone, no axes. It stays zero-based; never crop it to make a flat line
  look steep.
- **Panels side by side, not cards down a page.** A wide panel beside a narrow
  one (a `.tb-grid` whose panels are `.tb-span-8` and `.tb-span-4`: the trend
  beside its ranking) reads as a dashboard; two
  equal halves read as a document. One figure per `.tb-card`, the most
  important top-left ([[design-layout-by-importance]]). Give a panel a
  one-line `.tb-note` subtitle under its `<h2>`. The first screen holds the
  overview; detail goes on a second tab, not further down.
- **Small labels, big values.** Card titles short and plain ("Fair value by
  sector"), controls (a filter, "top 10") beside the figure they change.
- **Quiet chrome.** No gradients, shadows or icons for decoration
  ([[design-cut-the-chrome]]). Colour stays meaning: one accent, and the
  problem tones only where something needs a look ([[design-color-with-meaning]]).
- **Dark is a choice, not a style.** Use it when the reader asked or the page
  lives on a wall screen. Charts and tables follow the tokens; check your own
  `style.css` uses tokens too ([[design-theme-with-tokens]]).

**The tell.** Can someone glance at the first screen for five seconds and say
what is up, what is down and what needs a look? If they have to scroll or read
a paragraph first, it is still a document.
