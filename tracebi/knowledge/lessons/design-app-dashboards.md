---
slug: design-app-dashboards
title: Build an app dashboard people work in — kit numbers, tokens for colour, views instead of scroll
when: writing or reviewing an app.jsx (the React lane), or deciding whether a page should be an app at all
---
**The pitfall.** Full React makes anything possible, and the generated version
shows it: a gradient hero, eight equal cards, a chart library's default
colours, a number computed in a `.reduce()` and printed in a `<div>` — the
receipt cannot see it, and the reader cannot tell it from a checked one. Or the
opposite: an app built for a page that only needed to be read, now blank in an
email client.

**First, is it an app?** An app earns its weight when someone works in the page:
switches views, drills into a row, toggles a period. A page that is read once,
emailed or printed is a `template.html` — it reads with JavaScript off.

**Numbers through the kit, always.** Every number a reader might act on is a
`<Kpi>`, `<Value>`, `<Chart>`, `<Spark>` or `<Table>` with literal `binding` and
`cell`/`x`/`y`. That is what makes it a claim the receipt names. `useBinding`
rows are for layout and interaction — a list of names to navigate, which row is
selected — not for new totals. If a figure needs arithmetic, it belongs in the
model or in `report.json` `"measures"` (a report-level measure), where it is
stamped. A number you do draw yourself, say so beside it.

**Colour from tokens, never hex.** `bg-page`, `bg-card`, `bg-surface`,
`text-ink`, `text-muted`, `border-rule`, `bg-accent`, and `chart-1`… for series.
They follow the page's mode, the project theme and the house style; a hex code
does not, and breaks dark mode silently ([[design-theme-with-tokens]]). Status
colours stay meaning: `text-bad` for a problem, never for decoration
([[design-color-with-meaning]]).

**Lay it out as a tool.**

- **Views, not one long scroll.** A rail or top tabs with two to five views;
  the first view answers "how are we doing?" on one screen.
- **One KPI strip with a lead** (`.tb-grid` of `<Kpi>`, one `lead`), then a wide
  panel beside a narrow one (`tb-grid`, `tb-span-8` and `tb-span-4`). Panels are
  `.tb-card`; a `.tb-note` under the `<h2>` is the subtitle
  ([[design-dashboard-feel]]).
- **Controls next to what they change**, in one row above the table: `<Search>`,
  `<Filter>`, `<Download>`. They choose rows; they never compute.
- **Drill-down opens beside, not instead.** A selected row opens a side panel
  or drawer; the list stays where it was.
- **Plain chrome.** Icons only where they label navigation; no gradients, glass
  or shadows ([[design-cut-the-chrome]]). Open with `<Masthead>` and end with
  `<Footer />`.

**Every state, not just the happy one.** An empty binding renders "No rows", a
filter that matches nothing says so, and a view with no data says why
([[design-plan-every-state]]).

**The tell.** Open the receipt drawer and look at the page: every number you
would quote should be in the drawer's list. If one is not, it is either the
app's own arithmetic — move it into the model — or it should say it is not
checked.
