### Added — the workbench in the app

- The **Point** button is now **Build**. It opens the workbench beside the
  report (the report list steps aside to give it room):
  - **Pointing**, with a box to pin a note on what you point at, for the agent.
  - **Pins**: yours, and the resolved ones with the agent's answer.
  - **From your agent**: what it shows while it works (`tracebi.workbench.show`).
  - **Needs a look**: a binding that is broken right now, or a package that
    fails to render, while the last good render stays up.
- The report in the pane is the working state, rendered in memory (no build, no
  receipt), and refreshes on its own when the agent saves the package, its
  model or the feed. Another process (the agent, over MCP) writes the files;
  the pane polls a cheap fingerprint and re-fetches only when it moves.
- API (dev mode only): `GET /api/reports/<name>/workbench/{version,state,
  preview}`, `POST …/workbench/pins`, `DELETE …/workbench/pins/<id>`. A pin on an
  area (not a figure) carries a `target` saying where; `workbench_state` lists
  it.
- The dev server and the app share one implementation of adding and removing
  pins (`workbench.add_pin` / `remove_pin`).
