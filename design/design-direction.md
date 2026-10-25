# Design direction

**Status: agreed (2026-10-04); the theme pass below is done.** What the builder
experience is, and what the app looks like. The quality bar and the audit that
checks it are in [The UI quality bar](ui-quality.md); the work queue is [UI backlog](ui-backlog.md).

## Who it is for

Two people, two surfaces, and one rule between them.

| | The reader | The builder |
|---|---|---|
| Who | someone opening a finished report | an analyst or agent making one |
| Where | the report page, the share link, the emailed file | the app running locally, with an agent beside it |
| Asks for | one number they can trust, then the context | a change to a figure, a layout, a query |

**Ask is for the builder, not the reader.** A reader looks at the report and
verifies it; they do not edit it. The reader-facing "ask a question of the
model" path stays what it is. Everything below is the builder's.

## The builder loop

Run TraceBi locally and the app opens beside the agent: chat on one side, the
app on the other. In the app, open a report in **Build mode** (local only).

1. **Point.** Hover outlines what you can address; click selects it. A figure
   resolves to its id, binding and cell (the report already carries
   `data-tb-figure`, `data-tb-binding`, `data-tb-cell`); any other element
   resolves to its selector and text.
2. **Ask.** In the agent's chat: "make *this* a line chart by plan." The agent
   asks the app what *this* is (`workbench_state` returns the selection) and
   edits the package: `report.json` and `template.html`.
3. **See.** The report rebuilds in the pane, the change marked against the
   previous version. A change to a number is shown as old value, new value.
4. **Keep.** You accept or revert. Nothing is kept until you say so, and the
   trace only reads green for what was built and checked, never for a draft.

You can also leave a note (a **pin**) for the agent to pick up later, from
the panel's note box: `address_pins` already does that.

### One workbench, two clients

The workbench's state is files under `.tracebi/workbench/<report>/`
(selection, pins, exhibits). The app and the MCP server are separate processes
that both read and write them, so:

- what you click reaches the agent (`workbench_state` returns the selection);
- what the agent does shows up in the pane live (exhibits from
  `tracebi.workbench.show`, pins it resolves, the rebuilt preview);
- the app does not call a model. Your connected agent does the editing, so
  there is no server-side key, no bill, and no web page with the power to
  write files on its own.

Hard rules, kept from the workbench's design ([Report Architecture v2 — the one-lane reshape](report-architecture-v2.md) §2.5):
everything here is dev-state; none of it enters a build or a manifest; no
trace is minted. Build mode exists only on loopback with dev mode on. The
point-mode script is injected by the server at serve time, never into a built
file.

### Where it is today, and the gap

`tracebi dev` already serves a live preview and a workbench page, with pins,
exhibits and the MCP tools `workbench_state`, `resolve_pin` and the
`address_pins` prompt. The gaps: the preview and the workbench are separate
pages on a separate server, you cannot click the report itself (pinning is a
browser pop-up from a list), and the agent cannot tell what you are pointing
at. Build mode closes those, in the app.

## The look: Vercel's restraint, Supabase's console, one blue

Both are developer tools that trust the reader with density and use colour
sparingly. Take that restraint (type, hairlines, no gloss) and spend one blue in
few places. (First pass went black and white, then back to the old navy, which
read heavy: sleek is blue as an accent, not as a field. Cobalt on neutral
grounds was picked from six side-by-side options.)

**Rules** (each is checkable; the audit gains a check for the ones marked ◆):

- **Quiet colour: one cobalt, used where you act or are.** Cobalt (`#2f5bea`)
  is the brand: the primary button, the selected row, the active tab, links,
  focus, the logo tile; a lighter cobalt on dark and for the active nav icon.
  Grounds are neutral (`#fafafa` / `#0a0a0a`) with hairline borders, and the
  sidebar is a near-black slab in both themes. The brand stays in its blue
  family. ◆
- **Beyond the brand, colour means something.** Four verdict states, one chip
  in the report and in the app: green is *Reproduces*; amber is *Needs a look*
  (source changed since the build, checks stale); red is *Does not reproduce*
  or failed; *Not checked* is neutral. Supabase's signature green is deliberately not borrowed as a brand
  colour: green is already spoken for. A decorative amber chip reads as a
  warning.
- **Dark and light are both designed.** Follow the OS setting until the viewer
  chooses. Dark is near-black with 1px borders and no glow (Supabase's
  craft); light is white with 1px borders (Vercel's).
- **Borders, not boxes.** 1px hairlines separate regions; no cards inside
  cards, no gradients, no backdrop blur, no resting shadows (a menu or popover
  may have one). The library is the exception, on purpose (2026-10-24): its
  tiles, covers, pills and a folder's hero rest on `--shadow`, a folder's tile
  and hero carry its hue as a tint, and page titles are set in Instrument
  Serif (`--font-display`). ◆
- **Type: Hanken Grotesk and IBM Plex Mono** (both SIL OFL), replacing Source
  Sans, Inter and Source Code Pro. A clean, tightly set grotesque in the spirit
  of Vercel's and Supabase's faces, without copying one. 14px body, 13px in dense lists, tabular numerals
  for every figure, mono for every identifier (model, table, binding, id). ◆
- **Radius 6px, sidebar the same ground as the page**, not a separate navy
  slab. Page header small (20px): the page is the content, not the title.
- **Density with hierarchy.** Lists read like a console table: one line per
  row, status as a small dot or chip, secondary text quiet. Progressive
  disclosure (Linear): the detail opens when you ask for it.
- **The reader's report** follows Mercury and Plausible: one big number, then
  its context, then the trace on demand. It is one system, below; a report's
  own `style.css` is a theme preset on it, not a second look.

### The mark

A trace: one stroke rising through two open points to a filled one, the
number you arrived at. White on the cobalt tile (`--ink`, `#2f5bea`, radius
6px), flat: no gradient, no second blue, so `theme-brand-colour` holds it as it
holds every brand token. It is drawn once, on a 20-unit grid with a 1.6 stroke,
and holds at 16px (the browser tab), 18px in its 28px tile (the sidebar, the
56px rail on a report page, the phone header) and 32px. Its `title` is the
tagline, *Every number, traced.*, which also opens the sign-in page and Get
started; it is never set under the logo. The wordmark beside it is "TraceBi"
in the app's sans at 15px/600, tracking -0.01em.

Where it lives: `BrandMark` in `web/ui/src/components/Art.jsx` (the trace
draws point to point, replayed on hover), `web/ui/public/favicon.svg`, the
gateway's sign-in page (`_MARK_SVG` in `tracebi/mcp_oauth.py`) and the site
header and favicon (`site/index.html`; `site/build_docs.py` copies the
favicon). It is never put on a report: `.tb-masthead-mark` is the customer's
slot. The illustrations speak the same language: `ReportArt`'s trend is a
cobalt line ending on a filled point.

## The report's system

The bar (the 2026-10-17 plan, decision 2): type and restraint as Stripe's
dashboard, density and chrome as Linear, the editorial register as a fund's
quarterly letter. A report with no `style.css` is the page we would show.
Everything here is `tracebi.css`, `tracebi.js` and the kit; the reference is
`portfolio_showcase`, which carries every figure kind and interaction on it.

- **Type.** One scale of seven steps (`--tb-text-xs` … `--tb-text-3xl`:
  12/13/14/16/20/28/40px), weights 400/500/600, tight tracking from 28px,
  tabular numerals on every figure. Hierarchy is size and weight, never
  colour. The editorial and the dashboard share the scale and use different
  steps (the editorial's prose is a 68-character serif column).
- **Modes.** `auto` by default: a built page follows the reader's system, as
  the app does. Dark has its own grounds, series and accent pair
  (`--tb-dark-accent`), not light inverted.
- **One accent.** `--tb-chart-1` is the accent; the other seven series are
  checked against it for colour-blind separation. A theme
  (`tracebi theme use`) is an accent preset: the pair for each ground and
  nothing structural. A report's `style.css` may add one display face (the
  showcase sets its headline and lead number in Fraunces).
- **The frame.** Every page opens with a masthead (kicker, the `<h1>` that
  states the finding, the standfirst, and a meta line: the period, the build
  time, the verdict chip and the Trace button) and ends with a footer (the
  author's sources, one line on who built it from which model with "The
  trace does not claim the numbers are right.", and "How these numbers were
  made" behind a disclosure). The page measure is 1,200px with a 12-column
  grid (`.tb-span-4/6/8/12`). No methodology in the body.
- **The verdict chip.** Reproduces (green), Needs a look (amber), Does not
  reproduce (red), Not checked (neutral). A file only ever calls itself Not
  checked or Draft; the other three come from a host that re-ran its queries.
- **A KPI is a number with a signal.** The lead is larger, not wider; a delta
  is a stamped change with its arrow, sign and good/bad tone, and with no
  comparison measure there is no delta.
- **One chart style.** Bars at 55% of the band with a 2px end radius and their
  own values; category names wrap, never "…"; ticks thin to what fits;
  gridlines at 6% ink, a baseline, no axis lines; lines 1.5px ending in their
  last value; an area at 10%; a tooltip with the measure's definition and
  "Trace →".
- **Tables.** Numbers right-aligned in tabular numerals, a sticky header in a
  scroll box, a thin data bar in its own lane after the number, one totals
  style (a 2px rule, weight 600), density from `--tb-cell-pad`.
- **The trace is a certificate.** The verdict and the honesty line first,
  then one row per figure: the value as shown, the definition in words, the
  query in one line and an 8-character fingerprint, the raw detail behind a
  disclosure.
- **Nothing decorates.** No gradient, hatch, glow or resting shadow; a menu,
  popover, tooltip and the trace drawer may lift. The one bespoke example is
  the demo app's `aum_by_branch`: its own faces (Inter, Fraunces), a pine and
  brass palette and a flat hero band with inlined artwork, on the system's
  masthead, KPI strip, grid, footer and trace.

## Order of work

1. This brief.
2. **Build mode, slice one** (done): click-to-select in the app's report
   preview, the pointing in `workbench_state`. Agent guides and the generated
   vocabulary name it in the same change, as every authoring-surface feature
   must.
3. **The workbench in the app** (done): the Build button opens it beside the
   report: pointing, a pin from it, the pins and what the agent answered, the
   agent's exhibits, broken bindings, and a preview of the working state that
   refreshes when the agent saves. You instruct the agent in chat; the panel
   also takes a note for later. A timeline of what each save changed, and
   flip back to the version before. `tracebi dev <name>` opens it in one
   command, and is the default now that the app has the classic workbench's
   per-binding data and lint (Data, Checks) and the project feed before a
   report exists (`tracebi dev --classic` keeps the old preview server).
4. **The theme pass,** one surface at a time through the audit loop.
   - Foundation (done): Hanken Grotesk and IBM Plex Mono; cobalt as the one brand colour on
     neutral grounds that follow the OS; a near-black sidebar slab; hairline
     borders; no gradients, blur or resting shadows. The nav is four places,
     Reports, Data, Review, Docs (it was Build, then Use, before the 2026-10 IA;
     Docs joined on 2026-10-21; Ask left on 2026-10-24, into a folder's page and
     a model's).
     The audit enforces it: `theme-font`, `theme-brand-colour`,
     `theme-dark-ink`, `theme-shadow`, `theme-decoration`.
   - Report defaults (done): `tracebi.css` takes the same type, grounds and
     cobalt, so a report matches the app. Hanken Grotesk is inlined into the file
     (`stack.font_face_css`); controls and inline code are finished.
   - Report design system v2 (done, the 2026-10-17 plan's Step 1): the
     report's system above, the scaffolds, the reference reports and the demo
     app on it.
   - The app on the four places (done, the same plan's Steps 2 and 3):
     Reports as home, the report page, Data and Review, the verdict chip
     everywhere; the report contact sheet in the audit (DS-9).
   - Ask (done, Step 4); since then Docs is a fifth place and Data opens on
     the board ([Navigation v3 — Docs as a place, Data as the chain](nav-v3.md), [Data as a flow: the board](data-flow-board.md)). Still to do: lists as
     console rows throughout, and illustrations beyond the mark.
