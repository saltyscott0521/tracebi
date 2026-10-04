# UI backlog

The loop in `ui-quality.md` takes the top open item. Done items move to the
bottom with the change that closed them.

## Open

1. **Lists are clickable divs** `[click-not-keyboard]`: `ListItem` and the
   Verify drop zone can't be reached by keyboard. Make them buttons.
2. **Phone header button has no name** `[axe:button-name]`, and the header
   is outside any landmark `[axe:region]`.
3. **Contrast** `[axe:color-contrast]`: diagram node labels, report list
   meta text, badges in dark mode.
4. **Reports opens on "Pick a report"** `[empty-detail-pane]`: half the page
   blank on desktop. Show what needs attention and the latest builds there.
5. **The phone hides which model you are in.** The switcher lives in the
   drawer; the header says only "TraceBi". Show the model in the header.
6. **Diagram edges take keyboard focus with no ring** `[no-focus-ring]`, and
   a keyboard user tabs through every edge before reaching anything useful.
7. **Code blocks scroll but can't be focused**
   `[axe:scrollable-region-focusable]` on Get Started and Workflow.
8. **Learn has three pages telling one story** (Get Started, Docs,
   Workflow), and Workflow is in no menu `[nav-you-are-here]`. Fold
   Workflow into Get Started.
9. **Words a reader doesn't use**: "semantic contract", "DuckDBConnector"
   as a badge, "STEP / never run" in the Refresh flow.
10. **"Checks stale" items name no model**: a stale sink check shows only
    under All models. Attribute warehouse tables to the models that read them.
11. **Bundle is 1.1 MB of JS.** Split routes (React Flow, Markdown, Recharts
    load only on the pages that use them).
12. **113 hard-coded colours in JSX** — each is a dark-mode bug waiting.
    Move them to tokens.

## Done

- **Model switcher as the frame of the app** — one control at the top of the
  sidebar narrows every page (Data model, Explore, Refresh, Reports, Sources,
  Runs) to a model; `/m/<model>/<page>` and an all-models `/<page>`; the last
  pick is remembered; old addresses redirect. "Contract" is "Data model"
  again. Removed the dead nav code from earlier designs.
- **"You are here" on every page** `[nav-you-are-here]` — every frame page
  marks its sidebar entry.
- **Unknown URLs render a real "Page not found"** `[blank-page]`.
- **Sources opens on its first source**, not a blank pane; the model page no
  longer repeats the model's name or stacks two rows of tabs.
