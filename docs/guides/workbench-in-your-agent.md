# The workbench in your agent

When your agent works on a report over MCP, the workbench opens in the
conversation: the report itself, live, beside what the agent is saying. You
click a figure and pin a note on it ("this looks off"), and the agent reads
it before its next edit. Nothing to install: it is part of the gateway.

## Before you begin

- An agent connected to the gateway (`tracebi mcp`, or the app's `/mcp`; see
  [[connect-chatgpt-and-claude]]).
- A host that shows MCP Apps (the `io.modelcontextprotocol/ui` extension).
  The MCP Apps specification lists ChatGPT, Claude, VS Code, Goose, Postman
  and MCPJam among the hosts that render them. Claude Code is not one of
  them: Claude Code users get a link instead; see
  [Without MCP Apps](#without-mcp-apps).

## What you see

The panel opens when the agent calls `preview_draft` (a report draft),
`workbench_state` (a report in the library) or `build_report`. It shows:

- **The report**, as itself, in its own sandboxed frame: filters, clicks, the
  selection bar and the trace all work, and every number on it is the
  report's own query result. A draft reads **Draft**; the chips say Local or
  Fixed as they do anywhere else.
- **Figures**: each figure's id and kind and where its number comes from
  (model query, python-derived, marked unverified, or no data behind it).
- **Open pins**: what you have asked for that the agent has not resolved yet.
- **What your agent did**: each file it wrote, each query and build, newest
  first, while the panel is open.

It follows the agent: after every `write_draft_file` or build the page and
the lists refresh by themselves, in a second or two. On a narrow panel the
report comes first and the workbench under it; a wide one puts them side by
side. It tells the host how tall it would like to be, so an inline panel grows
with the report. It follows the host's light or dark theme. **Expand** asks the host for
the full window where it offers one; **Open in the app** opens the same
report in TraceBi.

## Pin a note

1. Click a figure in the report. The panel says *Pinning on* and its id.
2. Type what is wrong or what you want, then **Pin on figure**. With no figure
   chosen, **Leave note** leaves a note for the whole report.
3. The pin is saved where the agent reads pins (`workbench_state`, the
   `address_pins` prompt), and the panel tells the agent in the conversation:
   *Pinned on kpi-revenue in the draft of sales/weekly: this looks off*.

The agent acts on it, edits, and resolves the pin with a note. The panel only
pins, selects and asks: it cannot write the report, publish or approve
anything.

## Without MCP Apps

A host that does not show MCP Apps gets the same tools and results as before,
plus a link to open: `preview_draft` returns the draft's `url`, and
`workbench_state` and `build_report` return `workbench_url`, the report's page
in the app (`/reports/<name>`), where Build mode shows the same workbench.

- **Claude Code:** start the app with `tracebi dev <name>` (it opens
  `http://127.0.0.1:8000/reports/<name>` with Build on) and keep it beside the
  terminal; the Claude desktop app's preview pane can open that address. A
  draft's link needs the app running too (`tracebi serve`).
- Set `TRACEBI_PUBLIC_URL` on a hosted server so the links are full addresses.

## Next

- How an agent authors a report: [[sop-authoring]]
- The same pins from the terminal: `tracebi report pins <name>` ([[cli]])
