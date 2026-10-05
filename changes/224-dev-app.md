### Added — `tracebi dev <name> --app`: Build mode in one command

- Opens the web app on that report with Build mode already on: put your
  agent's chat beside it, watch the report re-render as it saves, see which
  figures each save changed, and click a figure to point at it. The server runs
  in dev mode on `127.0.0.1` only.
- Opt-in for now: plain `tracebi dev <name>` is still the classic preview and
  workbench page, which has per-binding data cards, lint and discovery mode
  that the app does not.
- Corrects earlier notes: only `tracebi dev <name> --app` (or a server started
  with `TRACEBI_DEV_MODE=1`) turns Build mode on; plain `tracebi dev` does not.
