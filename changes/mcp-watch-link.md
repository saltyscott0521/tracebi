### Added

- The web app serves the agent gateway at `/mcp` when `TRACEBI_MCP_TOKEN` is set: one process, with the same bearer token. Each MCP session there gets a **private watch link**. `get_context` returns it as `watch.url`, the agent hands it to the person, and the page at `/live/<id>` shows the agent's queries (as tables) and builds (with a link to the report) as they happen. One link per session, kept 24 hours, no receipts. `GET /api/live/{watch}` serves it. The run store gains a `tracebi_live_events` table (Alembic revision 0003).
- On tracebi.com, `/mcp` now goes to the demo app. Set `TRACEBI_MCP_TOKEN` and `TRACEBI_PUBLIC_URL` on the demo before the site redeploys (`deploy/mcp/README.md`).
