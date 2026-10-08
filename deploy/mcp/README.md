# Hosted MCP gateway (demo)

The demo web app serves the agent gateway itself, at `/mcp`, when
`TRACEBI_MCP_TOKEN` is set on it. One process: what an agent does over the
gateway reaches the app, so each MCP session gets a **private watch link**
(`get_context` returns it as `watch.url`) where the person watches the
agent's queries and builds as they happen.

Public URLs (proxied by `site/nginx.conf` to the demo container):

```
https://tracebi.com/mcp                 the gateway (bearer token)
https://tracebi.com/app/live/<id>       a session's watch link
```

## Coolify (the existing `tracebi-demo` resource)

Add to its environment:

| Var | Value |
|---|---|
| `TRACEBI_MCP_TOKEN` | long random secret (Coolify secret) |
| `TRACEBI_PUBLIC_URL` | `https://tracebi.com/app`, so watch links are full URLs |
| `TRACEBI_MCP_ACTOR` | `demo` (optional) |

Redeploy it (its log says `mcp gateway: /mcp`), then redeploy the site so
nginx sends `/mcp` to the demo, and check `https://tracebi.com/mcp` answers
401 without the token. Set the token **before** the site redeploys: until the
demo has it, the demo serves no `/mcp`.

The separate `tracebi mcp --transport http` resource (internal host
`mcp.tracebi.com`) is no longer needed once nginx points at the demo; stop it
after the switch. `tracebi mcp --transport http` itself still works for anyone
who wants a gateway with no web app (it has no watch links);
`docker-compose.yml` here is that stand-alone container.

Run one worker (the demo does). MCP sessions live in the process that opened
them; several workers need a load balancer that keeps a session on one worker.

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
