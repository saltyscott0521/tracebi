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
| `TRACEBI_REPORTS_DIR` | `reports` | `new-report`, `report`, discovery |
| `TRACEBI_PIPELINES_DIR` | `pipelines` | `run-pipeline`, discovery |
| `TRACEBI_SCHEDULED_DIR` | `scheduled` | discovery |
| `TRACEBI_WORKBENCH_DIR` | `.tracebi/workbench` | `dev`, `session` |
| `TRACEBI_OUTPUT_ROOT` | `output` | build outputs |
| `TRACEBI_DOCS_DIR` | — | the served docs browser |

## Application

| Variable | Meaning |
| --- | --- |
| `TRACEBI_APP` | app module to import at startup. Default: none. `tracebi serve` sets it to empty so the bundled demo is never dragged into your project — set it yourself to opt in. |
| `TRACEBI_DEV_MODE` | enables `POST /api/_dev/reload`, **and** allows tracebacks in API error payloads |
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
(+ execute reports) → `admin` (+ run pipeline layers, which write).

## Delivery

| Variable | Meaning |
| --- | --- |
| `TRACEBI_SMTP_URL` | `smtp://user:pass@host:587` (STARTTLS) or `smtps://` (implicit TLS) |
| `TRACEBI_SMTP_FROM` | sender address |
| `TRACEBI_SLACK_WEBHOOK` | optional ping after a successful `report send` |

Both SMTP variables are required by `tracebi report send`. A Slack failure is
reported but does not fail the command — the report already went out.

## Agent gateway

| Variable | Meaning |
| --- | --- |
| `TRACEBI_MCP_TOKEN` | bearer token for `tracebi mcp --transport http` |
| `TRACEBI_MCP_ACTOR` | audit attribution for gateway work (default `agent`) |

The http transport **refuses to start** until you either set the token or pass
`--insecure` deliberately.

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
`TRACEBI_SCHEDULED_DIR` is documented only in a module docstring.

Conversely `TRACEBI_WAREHOUSE_URL` appears in `.env.example` and **no code reads
it** — it is a leftover.

## Related

- [[cli]] — the flags that override these
- [[deploy-vercel-supabase]] — hosting configuration
