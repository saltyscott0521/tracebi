# UI backlog

The loop in `ui-quality.md` takes the top open item. Done items move to the
bottom with the change that closed them.

## Open

1. **Words a reader doesn't use**: "semantic contract", "DuckDBConnector"
   as a badge, "STEP / never run" in the Refresh flow.
2. **"Checks stale" items name no model**: a stale sink check shows only
    under All models. Attribute warehouse tables to the models that read them.
3. **Bundle is 1.1 MB of JS.** Split routes (React Flow, Markdown, Recharts
    load only on the pages that use them).
4. **113 hard-coded colours in JSX** — each is a dark-mode bug waiting.
    Move them to tokens.
5. **The theme ignores the OS setting**: a first visit is always light. Follow
   `prefers-color-scheme` until the viewer picks one.
6. **`Btn` drops a caller's colours**: its variant styles are applied after
    `style`, so `style={{ background }}` is silently overridden.

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
- **Everything clickable works from a keyboard** `[click-not-keyboard]` —
  list rows and the Verify drop zone take Tab, Enter and Space
  (`pressable()` in `Shared.jsx`); one focus ring for the whole app
  (`--focus-ring`); diagram edges no longer take focus.
- **Phone header**: the menu button has a name, the header is a landmark, and
  it says which model you are in (tap it to switch).
- **Tap targets**: small buttons are 24px tall; the Refresh page opens on its
  list of steps on a phone, where the run buttons are full size.
- **Contrast in both themes** `[axe:color-contrast]` `[token-contrast]` — dark
  mode's status text (green / amber / red: whether a report reproduces) was at
  2:1, and its grey text at 3:1; both now pass on every surface. Unstyled
  links take the accent colour. The Docs page has one h1.
- **Reports opens on "At a glance"**, not a blank pane — how many reports,
  how many reproduce, what needs a look, the latest builds (each opens).
- **An open report names itself** on a phone (it is the page's h1 there).
- **Workflow folded into Get started** as "The three phases"; `/workflow`
  lands there. Its phase colours are theme tokens (`--phase-*`), readable in
  dark mode. Scrolling code blocks take keyboard focus.
- **The audit sees the populated app**: it builds every report before
  crawling, so verdicts, receipts and latest builds are checked, not only the
  never-built empty states.
