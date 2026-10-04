# Hosted MCP gateway (demo)

Same `ghcr.io/saltyscott0521/tracebi` image as the web demo, with a
different command. It serves the portfolio + bundled demo models over
streamable HTTP so a Cursor / Claude client with only a URL and a bearer
token can query the demos.

Public URL (proxied by `site/nginx.conf`):

```
https://tracebi.com/mcp
```

Internal Traefik host (no public DNS): `mcp.tracebi.com`.

## Coolify

1. New resource in project **TraceBi** → Docker Image
   `ghcr.io/saltyscott0521/tracebi:main`.
2. Ports: expose **8765**.
3. Domains: `http://mcp.tracebi.com` (internal — same pattern as
   `demo.tracebi.com`; the site nginx proxies `/mcp` with that Host).
4. Custom command:

   ```
   tracebi mcp --transport http --host 0.0.0.0 --port 8765
   ```

5. Environment:

   | Var | Value |
   |---|---|
   | `TRACEBI_MCP_TOKEN` | long random secret (Coolify secret) |
   | `TRACEBI_APP` | `tracebi.web.demo_app` |
   | `TRACEBI_MCP_ACTOR` | `demo` (optional) |

6. Health check: disable Coolify's HTTP probe on `/api/health`, or point
   it at a TCP check on 8765 — this process is not the web app.

Redeploy when `:main` moves (same cadence as `tracebi-demo`), or add the
Coolify deploy webhook next to `COOLIFY_WEBHOOK` in
`.github/workflows/publish-demo.yml`.

## Cursor client (other machine)

```bash
tracebi mcp config --client cursor --http 'https://tracebi.com/mcp'
```

```json
{
  "mcpServers": {
    "tracebi": {
      "type": "http",
      "url": "https://tracebi.com/mcp",
      "headers": {
        "Authorization": "Bearer ${env:TRACEBI_MCP_TOKEN}"
      }
    }
  }
}
```

Set `TRACEBI_MCP_TOKEN` in that Cursor environment to the same secret as
the Coolify env. No local TraceBi install required.
