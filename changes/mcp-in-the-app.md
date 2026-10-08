### Added

- The web app serves the agent gateway at `/mcp` when `TRACEBI_MCP_TOKEN` is set: one process, the same bearer token, outside the app's Basic/proxy auth. On tracebi.com, `/mcp` now goes to the demo app; set `TRACEBI_MCP_TOKEN` on the demo before the site redeploys (`deploy/mcp/README.md`).
