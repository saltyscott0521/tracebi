# Environment variables

**Every `TRACEBI_*` variable the framework reads.**

TraceBi does **not** auto-load `.env`. `python-dotenv` ships with the
`analyst`/`all` extras, but a transform script calls `load_dotenv()` itself.

---

## Project layout

Where each phase of [[the-three-phase-workflow]] lives. Each has a CLI flag
equivalent where it matters.

| Variable | Default | Used by |
| --- | --- | --- |
| `TRACEBI_TRANSFORMS_DIR` | `transforms` | `new-transform`, `run-transform` |
| `TRACEBI_MODELS_DIR` | `models` | `validate`, `new-model`, `verify`, discovery |
| `TRACEBI_REPORTS_DIR` | `reports` | `new-report`, `report`, discovery. Ignored when `TRACEBI_LIBRARY_MOUNTS` is set. |
| `TRACEBI_LIBRARY_MOUNTS` | — | Comma-separated `label:/absolute/path` roots for the report Library. Each label is a top-level folder; report identity is `label/relative_path`. When set, this is authoritative over `TRACEBI_REPORTS_DIR`. |
| `TRACEBI_PIPELINES_DIR` | `pipelines` | `run-pipeline`, discovery |
| `TRACEBI_CONNECTIONS_DIR` | `connections` | declarative sources (`connections/<name>.yaml`), `tracebi connect`, discovery |
| `TRACEBI_DRAFTS_DIR` | `drafts` | Remote drafts: each owner's drafts live under `drafts/<owner>/`. The `/mcp` draft tools and `/api/drafts` read and write there. Publishing copies a draft into the library. |
| `TRACEBI_SCHEDULED_DIR` | `scheduled` | discovery. **Deprecated.** The folder is still imported if it exists, and a script in it logs one deprecation line. It never ran reports. Use a `"schedule"` block in `report.json` (`tracebi schedule`). |
| `TRACEBI_WORKBENCH_DIR` | `.tracebi/workbench` | `dev`, `session` |
| `TRACEBI_OUTPUT_ROOT` | `output` | build outputs |
| `TRACEBI_DOCS_DIR` | — | the served docs browser |

## Application

| Variable | Meaning |
| --- | --- |
| `TRACEBI_APP` | app module to import at startup. Default: none. `tracebi serve` sets it to empty so the bundled demo is never dragged into your project — set it yourself to opt in. |
| `TRACEBI_DEV_MODE` | enables `POST /api/_dev/reload`, **and** allows tracebacks in API error payloads |
| `TRACEBI_DISCOVERY_INTERVAL` | Seconds between live-discovery scans. A running server picks up report packages, specs, model files and pipeline files added to `reports/`, `models/` and `pipelines/` (and drops deleted reports) without a restart. Default `5`; `0` turns it off, so new reports need a restart. Python report modules are still found only at startup. |
| `TRACEBI_STATE_URL` | The shared run store. Default `sqlite:///data/tracebi.db` beside the working directory. Point every worker at the same Postgres URL so polls, last builds, and schedule ticks share one database. |
| `TRACEBI_SCHEDULES_IN_SERVER` | `1` runs each report package's `schedule` block inside the web server (the same job as `tracebi schedule serve`). Off by default. On Postgres a tick takes one advisory lock per report. On SQLite the lock is a no-op, so several workers would each send the email. |
| `TRACEBI_DEBUG` | `run-transform` re-raises a `ContractViolation` with the full traceback instead of the clean message |

> **`TRACEBI_DEV_MODE` is security-relevant.** Without it, API error responses
> carry a message and exception type but an **empty traceback** — a traceback
> leaks file paths, the server username and package versions. Do not set it in
> production.

## Authentication and roles

| Variable | Meaning |
| --- | --- |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | HTTP Basic credentials |
| `TRACEBI_AUTH_REALM` | the Basic auth realm |
| `TRACEBI_AUTH_PROXY_HEADER` | header carrying the authenticated user, when a proxy sets it |
| `TRACEBI_AUTH_PROXY_TRUSTED_IPS` | CIDRs allowed to assert that header |
| `TRACEBI_AUTH_ROLE_HEADER` | header carrying the caller's role |
| `TRACEBI_AUTH_ROLE_MAP` | `alice:admin,bob:analyst` |
| `TRACEBI_AUTH_DEFAULT_ROLE` | fallback role for principals the map omits |
| `TRACEBI_ALLOWED_ORIGINS` | CORS allowlist |

> **Enforcement is opt-in, and the default is permissive.** With no usable role
> source — no `TRACEBI_AUTH_ROLE_MAP`, and no `TRACEBI_AUTH_ROLE_HEADER` —
> **every principal resolves to `admin`**, including on the pipeline routes that
> write to the warehouse. This is deliberate, so adding authorization could not
> lock a running deployment out of its own pipelines.
>
> `TRACEBI_AUTH_DEFAULT_ROLE` is **not a role source on its own**: set by itself
> it names a fallback but leaves enforcement off. It switches enforcement on
> only alongside `TRACEBI_AUTH_ROLE_HEADER`.

Roles: `viewer` (read, and run queries that persist nothing) → `analyst`
(+ execute reports) → `admin` (+ run pipeline layers, which write, and keep
a selection cut, which writes the published report).

## Delivery

| Variable | Meaning |
| --- | --- |
| `TRACEBI_SMTP_URL` | `smtp://user:pass@host:587` (STARTTLS) or `smtps://` (implicit TLS) |
| `TRACEBI_SMTP_FROM` | sender address |
| `TRACEBI_SLACK_WEBHOOK` | optional text ping after a successful `report send`, and with an owner schedule alert. An incoming webhook cannot upload a file. |
| `TRACEBI_SLACK_BOT_TOKEN` | bot token (`files:write`) for scheduled file delivery. Does nothing unless `TRACEBI_SLACK_CHANNEL` is set too. |
| `TRACEBI_SLACK_CHANNEL` | channel id (`C…`) or name the scheduled HTML and manifest are uploaded to. |

Both SMTP variables are required by `tracebi report send`. A webhook ping
that fails is reported but does not fail the command — the report already
went out. A scheduled run also uploads the HTML and the manifest when both
`TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` are set. That upload
is separate from the webhook. A failed upload is recorded on the run
(`delivery.slack.error`) and is not retried. `--no-send` records the intent
and does not call Slack.

## Agent gateway

| Variable | Meaning |
| --- | --- |
| `TRACEBI_MCP_TOKEN` | bearer token for `tracebi mcp --transport http`. Set on the web app, it also serves the gateway at `/mcp` behind the same token. |
| `TRACEBI_MCP_ACTOR` | audit attribution for gateway work (default `agent`) |
| `TRACEBI_MCP_LOG` | `1` appends one line per gateway tool call to `.tracebi/gateway_log.jsonl`: tool, ok or error, duration, actor, argument **names**. Never argument values or results. Off by default; local only. Read it with `tracebi agent log`. |

### A sign-in per person

Set `TRACEBI_OIDC_ISSUER` and the web app serves `/mcp` with a sign-in per
person ([[connect-chatgpt-and-claude]]). Nothing is read from these variables
when it is unset.

| Variable | Meaning |
| --- | --- |
| `TRACEBI_OIDC_ISSUER` | the company identity provider's OIDC issuer URL (https). Turns per-person sign-in on. |
| `TRACEBI_OIDC_CLIENT_ID` / `TRACEBI_OIDC_CLIENT_SECRET` | the one app registration at the provider. Both required once the issuer is set. |
| `TRACEBI_OIDC_SCOPES` | scopes asked of the provider (default `openid email profile`; `openid` is always included) |
| `TRACEBI_OIDC_GROUPS_CLAIM` | the ID-token claim that lists the person's groups (default `groups`) |
| `TRACEBI_OIDC_ROLE_MAP` | `group:role` pairs, comma separated, e.g. `bi-admins:admin,bi-analysts:analyst`. The highest matching role wins. A bad entry stops startup. |
| `TRACEBI_OIDC_DEFAULT_ROLE` | role for a person in no mapped group (default `viewer`) |
| `TRACEBI_PUBLIC_URL` | the address people reach this server at. The MCP address is its origin plus `/mcp`. |
| `TRACEBI_PUBLIC_MCP_URL` | the public MCP address when it is not `<TRACEBI_PUBLIC_URL origin>/mcp`. Must equal what you give ChatGPT or Claude. |
| `TRACEBI_OAUTH_REDIRECTS` | extra exact redirect URIs a connector may return to, comma separated. Claude's and ChatGPT's callbacks and loopback addresses on any port are always allowed. |

`TRACEBI_MCP_TOKEN` keeps working beside it, for automation, acting as
`TRACEBI_MCP_ACTOR` with the `analyst` role.

The http transport **refuses to start** until you either set the token or pass
`--insecure` deliberately. The web app has no insecure mode: without the token
it serves no `/mcp`.

## Updates

How an install learns about a newer TraceBi ([[updating]]).

| Variable | Default | Effect |
| --- | --- | --- |
| `TRACEBI_UPDATE_CHECK` | on | `0` turns off the release check in `tracebi update` and the web app's "available" notice. Nothing else changes. |
| `TRACEBI_UPDATE_URL` | GitHub's `releases/latest` for this repo | Where to check: any URL that answers like GitHub's releases API, e.g. an internal mirror. |
| `TRACEBI_IN_DOCKER` | set in the image | Marks a container install, so the update command pulls a new image instead of upgrading in place. |

## Connector URLs

The framework never reads a connector URL implicitly. Construct connectors in
your own code and pass credential-bearing URLs explicitly:

```python
DuckDBConnector("warehouse", database=os.environ["MY_WAREHOUSE_PATH"])
```

`.env.example` shows the pattern with names like `TRACEBI_SALES_DB_URL` — those
are **yours to read**, not framework-read variables.

---

## Known drift

A handful of variables are read by the code but absent from `.env.example`:
`TRACEBI_DEBUG`, `TRACEBI_DEV_MODE`, `TRACEBI_AUTH_REALM`, `TRACEBI_DOCS_DIR`,
and the demo app's `TRACEBI_DEMO_DB_URL` / `TRACEBI_DEMO_DB_DIR`.
`TRACEBI_SCHEDULED_DIR` is deprecated (see the table above).

Conversely `TRACEBI_WAREHOUSE_URL` appears in `.env.example` and **no code reads
it** — it is a leftover.

## Related

- [[cli]] — the flags that override these
- [[one-server]] — hosting on one server
