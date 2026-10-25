# Environment variables

Every `TRACEBI_*` variable TraceBi reads.

```bash
TRACEBI_STATE_URL=postgresql+psycopg://tracebi@db/tracebi_state
TRACEBI_SCHEDULES_IN_SERVER=1
TRACEBI_SMTP_URL=smtp://user:password@host:587
```

TraceBi does not load `.env` on its own. `python-dotenv` ships with the
`analyst` and `all` extras; a transform script calls `load_dotenv()` itself.
The exception is a `${NAME}` in a connection file or the warehouse block,
which is looked up in `.env` when the connection is used ([[credentials]]).

## Project layout

| Variable | Default | Used by |
| --- | --- | --- |
| `TRACEBI_TRANSFORMS_DIR` | `transforms` | `new-transform`, `run-transform` |
| `TRACEBI_MODELS_DIR` | `models` | `validate`, `new-model`, `verify`, discovery |
| `TRACEBI_REPORTS_DIR` | `reports` | `new-report`, `report`, discovery. Ignored when `TRACEBI_LIBRARY_MOUNTS` is set. |
| `TRACEBI_LIBRARY_MOUNTS` | none | Comma-separated `label:/absolute/path` roots for the report library. Each label is a top-level folder; a report's identity is `label/relative_path`. Overrides `TRACEBI_REPORTS_DIR`. |
| `TRACEBI_PIPELINES_DIR` | `pipelines` | `run-pipeline`, discovery |
| `TRACEBI_CONNECTIONS_DIR` | `connections` | Connection files, `tracebi connect`, discovery |
| `TRACEBI_DRAFTS_DIR` | `drafts` | Remote drafts, under `drafts/<owner>/`. The `/mcp` draft tools and `/api/drafts` read and write here; publishing copies a draft into the library. |
| `TRACEBI_SCHEDULED_DIR` | `scheduled` | Deprecated. Still imported if the folder exists, with one deprecation line per script. It never ran reports; use a `"schedule"` block in `report.json`. |
| `TRACEBI_WORKBENCH_DIR` | `.tracebi/workbench` | `dev`, `session` |
| `TRACEBI_OUTPUT_ROOT` | `output` | Build outputs |
| `TRACEBI_DOCS_DIR` | none | The folder the app's Docs place serves |

## Application

| Variable | Meaning |
| --- | --- |
| `TRACEBI_APP` | App module to import at startup. Default: none. `tracebi serve` sets it empty so the bundled demo never loads into your project; set it yourself to opt in. |
| `TRACEBI_DEV_MODE` | Turns on `POST /api/_dev/reload` and puts tracebacks in API errors. Don't set it in production: a traceback shows file paths, the server's user name and package versions. |
| `TRACEBI_DISCOVERY_INTERVAL` | Seconds between scans of `reports/`, `models/` and `pipelines/` for added or deleted files. Default `5`; `0` turns scanning off. Python report modules are found only at startup. |
| `TRACEBI_SECRET_KEY` | The Fernet key for the credential store ([[credentials]]). Unset, `.tracebi/secret.key` is generated on the first write. Several workers must share one. |
| `TRACEBI_STATE_URL` | The shared run store. Default `sqlite:///data/tracebi.db`. Point every worker at the same Postgres URL. |
| `TRACEBI_SCHEDULES_IN_SERVER` | `1` runs each package's `schedule` block inside the web server (the same job as `tracebi schedule serve`). Off by default. On Postgres a run takes one advisory lock per report; on SQLite the lock does nothing, so several workers would each send the email. |
| `TRACEBI_COVERS` | `0` takes no cover at build ([[report]]): no Chromium launch per build, and the library draws every cover. On by default where Playwright and Chromium are installed. |
| `TRACEBI_DEBUG` | `run-transform` re-raises a `ContractViolation` with the full traceback instead of the short message. |

## Sign-in and roles

| Variable | Meaning |
| --- | --- |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | HTTP Basic credentials |
| `TRACEBI_AUTH_REALM` | The Basic auth realm |
| `TRACEBI_AUTH_PROXY_HEADER` | The header a proxy sets with the signed-in user |
| `TRACEBI_AUTH_PROXY_TRUSTED_IPS` | CIDRs allowed to set that header |
| `TRACEBI_AUTH_ROLE_HEADER` | The header carrying the caller's role (proxy mode only) |
| `TRACEBI_AUTH_GROUPS_HEADER` | The header carrying the caller's groups, comma separated, in proxy mode only; the proxy must set or replace it. Matched by `_folder.yaml` ([[folder-yaml]]). |
| `TRACEBI_AUTH_ROLE_MAP` | `alice:admin,bob:analyst` |
| `TRACEBI_AUTH_DEFAULT_ROLE` | The role for principals the map leaves out |
| `TRACEBI_ALLOWED_ORIGINS` | CORS allowlist |

Role enforcement is off until there is a role source. With no
`TRACEBI_AUTH_ROLE_MAP` and no `TRACEBI_AUTH_ROLE_HEADER`, every principal is
`admin`, including on the pipeline routes that write the warehouse. That way
adding sign-in cannot shut a running deployment out of its own pipelines.
`TRACEBI_AUTH_DEFAULT_ROLE` alone is not a role source: it turns enforcement
on only with `TRACEBI_AUTH_ROLE_HEADER`.

Roles, in order: `viewer` (read, and run queries that save nothing),
`analyst` (also run reports), `admin` (also run pipeline layers, which write,
and keep a selection cut, which writes the published report).

## Delivery

| Variable | Meaning |
| --- | --- |
| `TRACEBI_SMTP_URL` | `smtp://user:pass@host:587` (STARTTLS) or `smtps://` (TLS from the start). Required by `tracebi report send`. |
| `TRACEBI_SMTP_FROM` | The sender address. Required by `tracebi report send`. |
| `TRACEBI_SLACK_WEBHOOK` | A text ping after a successful `report send`, and with an owner's schedule alert. A failed ping is reported but does not fail the command. A webhook cannot upload a file. |
| `TRACEBI_SLACK_BOT_TOKEN` | A bot token (`files:write`) for scheduled file delivery. Needs `TRACEBI_SLACK_CHANNEL` too. |
| `TRACEBI_SLACK_CHANNEL` | The channel id (`C…`) or name a scheduled run uploads the HTML and manifest to. A failed upload is recorded on the run (`delivery.slack.error`) and not retried. |

## Agent gateway

| Variable | Meaning |
| --- | --- |
| `TRACEBI_MCP_TOKEN` | Bearer token for `tracebi mcp --transport http`. Set on the web app, it also serves the gateway at `/mcp` behind the same token. |
| `TRACEBI_MCP_ACTOR` | Who gateway work is recorded as (default `agent`). |
| `TRACEBI_MCP_LOG` | `1` appends one line per gateway tool call to `.tracebi/gateway_log.jsonl`: tool, ok or error, duration, actor, argument names. Never values or results. Read it with `tracebi agent log`. |

The http transport refuses to start until you set the token or pass
`--insecure`. The web app has no insecure mode: without a token or a sign-in
it serves no `/mcp`.

### Sign-in through your identity provider

`TRACEBI_OIDC_ISSUER` turns on a per-person sign-in for `/mcp`
([[connect-chatgpt-and-claude]]) and for the app at `/login` ([[sign-in]]),
which turns role enforcement on. The server refuses to start if it is combined
with `TRACEBI_AUTH_USER`/`TRACEBI_AUTH_PASS` or `TRACEBI_AUTH_PROXY_HEADER`.

| Variable | Meaning |
| --- | --- |
| `TRACEBI_OIDC_ISSUER` | The provider's OIDC issuer URL (https). |
| `TRACEBI_OIDC_CLIENT_ID` / `TRACEBI_OIDC_CLIENT_SECRET` | The app registration at the provider. Both required once the issuer is set. |
| `TRACEBI_OIDC_SCOPES` | Scopes to ask for. Default `openid email profile`; `openid` is always included. |
| `TRACEBI_OIDC_GROUPS_CLAIM` | The ID-token claim listing the person's groups. Default `groups`. |
| `TRACEBI_OIDC_ROLE_MAP` | `group:role` pairs, comma separated, e.g. `bi-admins:admin,bi-analysts:analyst`. The highest match wins. A bad entry stops startup. |
| `TRACEBI_OIDC_DEFAULT_ROLE` | The role for a person in no mapped group. Default `viewer`. |
| `TRACEBI_PUBLIC_URL` | The address people reach the server at. The MCP address is its origin plus `/mcp`. |
| `TRACEBI_PUBLIC_MCP_URL` | The public MCP address when it is not `<TRACEBI_PUBLIC_URL origin>/mcp`. Must equal what you give ChatGPT or Claude. |
| `TRACEBI_OAUTH_REDIRECTS` | Extra exact redirect URIs a connector may return to, comma separated. Claude's and ChatGPT's callbacks and loopback addresses are always allowed. |

`TRACEBI_MCP_TOKEN` keeps working beside it for automation, acting as
`TRACEBI_MCP_ACTOR` with the `analyst` role.

### Built-in sign-in, with no identity provider

For a demo or a small team. The gateway signs people in on a page of its own
([[connect-chatgpt-and-claude]]). It covers `/mcp` only, cannot be combined
with `TRACEBI_OIDC_ISSUER`, and needs `TRACEBI_PUBLIC_URL` and
`TRACEBI_OAUTH_SECRET`. Run it as one worker.

| Variable | Meaning |
| --- | --- |
| `TRACEBI_DEMO_LOGIN` | A role (`viewer`, `analyst` or `admin`). Adds a **Continue as the demo user** button that signs anyone in as `demo` with that role. Use it only on a server with sample data. |
| `TRACEBI_LOCAL_USERS` | `name:role:password` entries, comma separated, e.g. `alice:analyst:a-long-password`. Groups for folder permissions follow the role after `@`, joined by `+`: `alice:analyst@finance+ops:a-long-password`. A password has at least 8 characters and may contain `:` but not `,`. Ten wrong passwords for one name in ten minutes stop that name for a while. |
| `TRACEBI_OAUTH_SECRET` | A random secret of at least 32 characters (`openssl rand -hex 32`). It signs the sign-in in flight, so every worker needs the same one. |

## Updates and sync

| Variable | Default | Effect |
| --- | --- | --- |
| `TRACEBI_LIBRARY_SYNC_SECRET` | unset | Turns on `POST /api/library/sync`, the git webhook that pulls each library checkout and rescans ([[push-from-a-laptop]]). GitHub signs with it (`X-Hub-Signature-256`); other senders put it in `X-TraceBi-Sync-Token`. |
| `TRACEBI_UPDATE_CHECK` | on | `0` turns off the release check in `tracebi update` and the app's "available" badge ([[updating]]). |
| `TRACEBI_UPDATE_URL` | GitHub's `releases/latest` for this repository | Any URL that answers like GitHub's releases API, such as an internal mirror. |
| `TRACEBI_IN_DOCKER` | set in the image | Marks a container install, so `tracebi update` pulls a new image instead of upgrading in place. |

## Connector URLs

TraceBi never reads a connector URL from the environment on its own. In
Python, build the connector and pass the URL yourself:

```python
DuckDBConnector("warehouse", database=os.environ["MY_WAREHOUSE_PATH"])
```

Names like `TRACEBI_SALES_DB_URL` in `.env.example` are yours to read, not
TraceBi's.

## Gaps in `.env.example`

- Read by the code but missing from `.env.example`: `TRACEBI_DEBUG`,
  `TRACEBI_DEV_MODE`, `TRACEBI_AUTH_REALM`, `TRACEBI_DOCS_DIR`, and the demo
  app's `TRACEBI_DEMO_DB_URL` and `TRACEBI_DEMO_DB_DIR`.
- In `.env.example` but read by nothing: `TRACEBI_WAREHOUSE_URL`.
