### Added — MCP client config from init

- `tracebi init` writes `.mcp.json` (Claude Code) and `.cursor/mcp.json`
  (Cursor). Both run `tracebi mcp` over stdio. A second init without
  `--force` does not overwrite them.
- `tracebi mcp config --client claude-code|cursor|claude-desktop` prints
  that client's snippet. `--http URL` prints the streamable-HTTP form
  with `Authorization: Bearer ${TRACEBI_MCP_TOKEN}`, never a token value.
  Claude Desktop's stdio snippet uses an absolute path to `tracebi`.
