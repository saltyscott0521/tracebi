# API routes

**The HTTP surface served by `tracebi serve`.** Everything reads from the
registry; nothing is app-specific.

Roles in the table are the minimum required when authorization is enabled — see
[[environment-variables#Authentication and roles]].

---

## Health and discovery

| Method | Path | Role | Returns |
| --- | --- | --- | --- |
| `GET` | `/api/health` | — | liveness |
| `GET` | `/api/schema` | viewer | the machine-readable vocabulary (same source as `tracebi context`) |
| `GET` | `/api/discovery` | viewer | per-file registered / skipped / failed, **with the reason** |

`/api/discovery` is the first place to look when something you wrote doesn't
appear: auto-discovery is convention-based and quiet, and this is where the
silence gets a reason.

## Models

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/models` | viewer |
| `GET` | `/api/models/{name}` | viewer |
| `GET` | `/api/models/{name}/tables/{table}/preview` | viewer |
| `GET` | `/api/models/{name}/tables/{table}/export.csv` | viewer |
| `POST` | `/api/models/{name}/query` | viewer |

`/query` takes a [[queries|QuerySpec]] and returns the result plus a lineage
graph. It computes but persists nothing, which is why `viewer` may call it.

## Reports

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/reports` | viewer |
| `POST` | `/api/reports/{name}/run` | analyst |
| `POST` | `/api/reports/{name}/runs` | analyst |
| `GET` | `/api/reports/{name}/runs` | viewer |
| `GET` | `/api/reports/{name}/runs/{run_id}` | viewer |
| `GET` | `/api/reports/{name}/download?format=xlsx\|html` | analyst |
| `GET` | `/api/reports/{name}/lineage` | viewer |
| `GET` | `/api/reports/{name}/mermaid` | viewer |

`/run` returns `{name, html, manifest}` — the **real artifact render**, so what
the browser shows is what `verify --file` can check. `POST /runs` starts the
same work in the background and returns a `run_id` to poll.

> **There is one renderer.** A registered report with no package is refused with
> `422` naming the fix, never served through a weaker path. See [[report]].

The `html` download is that same artifact. `xlsx` goes through the Excel
renderer, which derives no [[number-formats|formats]].

## Report specs

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/spec/schema` | viewer |
| `POST` | `/api/spec/validate` | viewer |
| `POST` | `/api/spec/render` | analyst |

`/render` compiles the spec to a package and renders it like a hand-authored
one — same figures, same receipt drawer, same schema-2 manifest.

## Verify

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/api/verify/file` | viewer |

The offline file check over HTTP: embedded bytes against the manifest. No model
needed. See [[receipts]].

## Pipelines

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/pipelines` | viewer |
| `POST` | `/api/pipelines/{name}/run` | **admin** |
| `POST` | `/api/pipelines/{name}/layers/{layer}/run` | **admin** |
| `GET` | `/api/pipelines/{name}/layers/{layer}/history` | viewer |

These **write to the warehouse**, which is why they require `admin` — the split
in the role model is by side effect, not by resource.

## Connectors, docs, dev

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/connectors` · `/api/connectors/{name}` | viewer |
| `GET` | `/api/docs` · `/api/docs/{name}` | viewer |
| `POST` | `/api/_dev/reload` | **admin**, and only with `TRACEBI_DEV_MODE` |
| `GET` | `/api/_dev/discovered` | admin |

## The SPA

`GET /` serves the built React bundle. When it has not been built, the page
says so and names the build command rather than 404ing.

---

## Error shape

A failed run returns a structured `detail`:

```json
{"message": "...", "exception_type": "ValueError", "traceback": ""}
```

**`traceback` is empty unless `TRACEBI_DEV_MODE` is set** — a traceback leaks
file paths, the server username and package versions. Keep it unset in
production.

## Adding a route

Add a file under `tracebi/web/api/routers/`, include it in `main.py`, and read
resources **only from the registry** — never import app-specific objects.

Any non-GET route the authorizer does not recognise requires `analyst` by
default, so a new write route is guarded rather than open. Add an explicit rule
when it needs `admin`.

## Related

- [[environment-variables]] — auth configuration
- [[cli]] — the same operations from the terminal
