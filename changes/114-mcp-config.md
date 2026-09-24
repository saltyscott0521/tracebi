### Added — MCP client config from init

- `tracebi init` writes `.mcp.json` (Claude Code) and `.cursor/mcp.json`
  (Cursor). Both run `tracebi mcp` over stdio. A second init without
  `--force` does not overwrite them.
- `tracebi mcp config --client claude-code|cursor|claude-desktop` prints
  that client's snippet. `--http URL` prints the streamable-HTTP form.
  The Authorization placeholder differs by client:
  `Bearer ${TRACEBI_MCP_TOKEN}` for Claude Code,
  `Bearer ${env:TRACEBI_MCP_TOKEN}` for Cursor, never a token value.
  The `--http` form is not offered for Claude Desktop (add the URL as a
  custom connector under Settings → Connectors). Claude Desktop's stdio
  snippet uses an absolute path to `tracebi`.
