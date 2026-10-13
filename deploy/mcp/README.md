# Hosted MCP gateway (demo)

The demo web app serves the agent gateway itself, at `/mcp`, when
`TRACEBI_MCP_TOKEN` is set on it. One process: what an agent drafts over the
gateway is what the app shows.

Public URL (proxied by `site/nginx.conf` to the demo container):

```
https://tracebi.com/mcp                 the gateway (bearer token)
```

## Coolify (the existing `tracebi-demo` resource)

Add to its environment:

| Var | Value |
|---|---|
| `TRACEBI_MCP_TOKEN` | long random secret (Coolify secret) |
| `TRACEBI_PUBLIC_URL` | `https://tracebi.com/app`, so links the gateway hands out are full URLs |
| `TRACEBI_MCP_ACTOR` | `demo` (optional) |

Redeploy it (its log says `mcp gateway: /mcp`), then redeploy the site so
nginx sends `/mcp` to the demo, and check `https://tracebi.com/mcp` answers
401 without the token. Set the token **before** the site redeploys: until the
demo has it, the demo serves no `/mcp`.

The separate `tracebi mcp --transport http` resource (internal host
`mcp.tracebi.com`) is no longer needed once nginx points at the demo; stop it
after the switch. `tracebi mcp --transport http` itself still works for anyone
who wants a gateway with no web app;
`docker-compose.yml` here is that stand-alone container.

## claude.ai and ChatGPT custom connectors (built-in sign-in)

Those connectors need OAuth, not a static token. With no identity provider,
the demo can serve its own sign-in page (`docs/guides/connect-chatgpt-and-claude.md`).
Add to the same Coolify environment, **before** redeploying the site:

| Var | Value |
|---|---|
| `TRACEBI_DEMO_LOGIN` | the role the one-click demo user gets (`viewer` for a safe public demo); anyone with the address can sign in |
| `TRACEBI_OAUTH_SECRET` | `openssl rand -hex 32` (a Coolify secret; signs the sign-in in flight) |
| `TRACEBI_PUBLIC_URL` | `https://tracebi.com/app` is fine: the connector address is its origin plus `/mcp`, i.e. `https://tracebi.com/mcp` |

No `TRACEBI_OIDC_*` may be set (they are exclusive). nginx forwards the OAuth
addresses (`/authorize`, `/token`, `/register`, `/revoke`, `/oauth/`,
`/.well-known/`) to the demo along with `/mcp`. Check:

```bash
curl -i https://tracebi.com/mcp                                    # 401 with WWW-Authenticate
curl -s https://tracebi.com/.well-known/oauth-authorization-server # JSON naming /authorize and /token
```

Then in claude.ai: Settings → Connectors → Add custom connector →
`https://tracebi.com/mcp`, and sign in with the demo button.

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
