### Added — Resolve a workbench pin

- `tracebi report pins <name>` lists open pins. `--resolve <id> --note "..."`
  moves one into the resolved list in `pins.json` (kept, with a timestamp,
  the actor, and the note). An unknown id is an error.
- The MCP tool `resolve_pin` does the same and writes only `pins.json`.
  `workbench_state` shows open pins only, plus how many are resolved.
- The workbench timeline shows a resolved pin as a quiet "done · <note>" line.
