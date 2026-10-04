# Design direction

**Status: proposed (2026-10-04), agreed in conversation.** What the builder
experience is, and what the app looks like. The quality bar and the audit that
checks it are in [[ui-quality]]; the work queue is [[ui-backlog]].

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
   receipt only reads green for what was built and checked, never for a draft.

You can also leave a note on a selection (a **pin**) for the agent to pick up
later: `address_pins` already does that.

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

Hard rules, kept from the workbench's design ([[report-architecture-v2]] §2.5):
everything here is dev-state; none of it enters a build or a manifest; no
receipt is minted. Build mode exists only on loopback with dev mode on. The
point-mode script is injected by the server at serve time, never into a built
file.

### Where it is today, and the gap

`tracebi dev` already serves a live preview and a workbench page, with pins,
exhibits and the MCP tools `workbench_state`, `resolve_pin` and the
`address_pins` prompt. The gaps: the preview and the workbench are separate
pages on a separate server, you cannot click the report itself (pinning is a
browser pop-up from a list), and the agent cannot tell what you are pointing
at. Build mode closes those, in the app.

## The look: Vercel's restraint, Supabase's console

Both are developer tools that trust the reader with density and use colour
sparingly. Take what they share and add what TraceBi needs.

**Rules** (each is checkable; the audit gains a check for the ones marked ◆):

- **Monochrome first.** Neutrals carry the interface. The primary button is
  inverted (near-black on light, near-white on dark). There is no brand
  accent colour. ◆
- **Colour means something, and only that.** Green is *reproduces*. Amber is
  *needs a look* (source changed, checks stale). Red is *does not reproduce*
  or failed. Blue is a link or the focus ring. Supabase's signature green is
  deliberately not borrowed as a brand colour: green is already spoken for.
  ◆ (a colour token used for decoration, outside status, fails)
- **Dark and light are both designed.** Follow the OS setting until the viewer
  chooses. Dark is near-black with 1px borders and no glow (Supabase's
  craft); light is white with 1px borders (Vercel's).
- **Borders, not boxes.** 1px hairlines separate regions; no cards inside
  cards, no gradients, no backdrop blur, no resting shadows (a menu or popover
  may have one). ◆
- **Type: Geist Sans and Geist Mono** (both SIL OFL), replacing Source Sans,
  Inter and Source Code Pro. 14px body, 13px in dense lists, tabular numerals
  for every figure, mono for every identifier (model, table, binding, id). ◆
- **Radius 6px, sidebar the same ground as the page**, not a separate navy
  slab. Page header small (20px): the page is the content, not the title.
- **Density with hierarchy.** Lists read like a console table: one line per
  row, status as a small dot or chip, secondary text quiet. Progressive
  disclosure (Linear): the detail opens when you ask for it.
- **The reader's report** follows Mercury and Plausible: one big number, then
  its context, then the receipt on demand. Report templates keep their own
  style; the default theme (`tracebi.css`) takes the same tokens.

## Order of work

1. This brief.
2. **Build mode, slice one** (done): click-to-select in the app's report
   preview, the pointing in `workbench_state`. Agent guides and the generated
   vocabulary name it in the same change, as every authoring-surface feature
   must.
3. **The workbench in the app** (done): the Build button opens it beside the
   report: pointing, a pin from it, the pins and what the agent answered, the
   agent's exhibits, broken bindings, and a preview of the working state that
   refreshes when the agent saves. Still to do: the before/after view with
   keep and revert, and `tracebi dev <name>` opening the app at that report.
4. **The theme pass,** one surface at a time through the audit loop: tokens
   and type first (every page changes at once and the audit shows what broke),
   then the sidebar, then lists, then the report defaults.
