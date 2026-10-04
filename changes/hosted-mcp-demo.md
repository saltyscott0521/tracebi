### Hosted MCP gateway for the demos

`https://tracebi.com/mcp` reaches the portfolio + bundled demo models over
streamable HTTP (bearer `TRACEBI_MCP_TOKEN`). The site nginx proxies `/mcp`
to an internal `mcp.tracebi.com` service on the same image as the web demo.
See `deploy/mcp/README.md`.
