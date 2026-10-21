# API routes

**The HTTP surface served by `tracebi serve`.** Everything reads from the
registry; nothing is app-specific.

Roles in the table are the minimum required when authorization is enabled — see
[[environment-variables#Authentication and roles]].

---

## Health and discovery

| Method | Path | Role | Returns |
| --- | --- | --- | --- |
| `GET` | `/api/health` | — | liveness: `{"status": "ok", "version": "<installed version>"}` |
| `GET` | `/api/status` | viewer | `{"version", "checks": [{"name", "ok", "detail"}]}` — output writable, discovery failures, models loaded, SMTP configured, in-server schedules, auth posture |
| `GET` | `/api/schema` | viewer | the machine-readable vocabulary (same source as `tracebi context`) |
| `GET` | `/api/discovery` | viewer | per-file registered / skipped / failed, **with the reason** |

`/api/discovery` is the first place to look when something you wrote doesn't
appear: auto-discovery is convention-based and quiet, and this is where the
silence gets a reason.

`/api/status` is the operator page: one check per thing that is usually
wrong. `email_configured.detail` is the SMTP variable names and whether each
is set. It never includes a URL, host, user, or password.
`schedules_in_server.detail` is `{"on", "count"}`. `auth.detail` is the
posture line. Beside the checks, `build_mode` says the app runs in dev mode and
`gateway` that it serves the agent gateway at `/mcp`; Ask points at the agent
when either is true.

## Models

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/models` | viewer |
| `GET` | `/api/models/{name}` | viewer |
| `GET` | `/api/models/{name}/tables/{table}/preview` | viewer |
| `GET` | `/api/models/{name}/tables/{table}/export.csv` | viewer |
| `POST` | `/api/models/{name}/query` | viewer |
| `GET` | `/api/models/{name}/dimensions/{dim.attr}/values` | viewer |
| `GET` | `/api/models/{name}/source` | viewer |

`GET /api/models` and `GET /api/models/{name}` carry each model's `label` (what a list
shows; see [[model-json]]) beside `name`, the identifier every other route takes.

`/source` returns the model's file, read-only (the **Code** tab). A model registered in
Python code has no file and says so. `/query` takes a [[queries|QuerySpec]] and returns the result plus a lineage
graph. It computes but persists nothing, which is why `viewer` may call it.

`/dimensions/{dim.attr}/values` (`dim_issuer.sector`; `?limit=`, default 200,
at most 1,000) lists one dimension attribute's distinct values, sorted, from the
dimension's own table: `{"values", "total", "truncated"}`. It is what Ask offers
to filter on. An unknown attribute is 404; one derived when a query runs (a time
grain, a bin) has no stored values and is 422.

`/query` returns each row twice: `data` holds the raw values (what a CSV download
uses) and `display` holds the same cells as text, written the way a built report's
table writes them: a numeric column takes the model's declared format on that
measure (`currency0`, `percent`, …), else the shape-derived default, and anything
else stays plain text. A value JSON cannot carry (NaN from an empty total, infinity
from a division by zero) is `null` in `data` and an empty string in `display`, never
an error. `GET /api/models/{name}` lists, on each fact,
`runnable_measures`: the declared measures whose columns exist on that fact's table,
so a UI offers only what will run. When the connector cannot describe the table (the
warehouse is not built yet), every declared measure is listed and a run reports the
real error.

## Reports

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/reports` | viewer |
| `POST` | `/api/reports/{name}/run` | analyst |
| `POST` | `/api/reports/{name}/runs` | analyst |
| `GET` | `/api/reports/{name}/runs` | viewer |
| `GET` | `/api/reports/{name}/runs/{run_id}` | viewer |
| `GET` | `/api/reports/{name}/built` | viewer |
| `GET` | `/api/runs` | viewer |
| `GET` | `/api/reports/{name}/download?format=xlsx\|html\|pdf` | analyst |
| `GET` | `/api/reports/{name}/lineage` | viewer |
| `GET` | `/api/reports/{name}/mermaid` | viewer |
| `GET` | `/api/reports/{name}/source` | viewer |

`GET /api/reports` gives each report a `form`: `spec` (a `reports/<name>.json`
in the default style), `package` (a `reports/<name>/` with its own template
and style) or `code`. `/source` returns the files that define the report —
the spec, or the package's `report.json`, `template.html`, `style.css`,
`script.js` and `report.py` — read-only, and only the files discovery
registered for it. It also gives each report `models` (the models its data
bindings read) and `measures` (the declared measure names they ask for, read
from the file, never from a warehouse); Data's Map draws both. `display_name` is
`report.json`'s `name` (what a list or title shows); `name` stays the path
identifier the routes take. `GET /api/runs` rows and the `report` entries of
`GET /api/desk` carry `display_name` beside `target` / `report` (a model
publish carries the model's `label`; a pipeline run carries `null`).

`/run` returns `{name, html, manifest}` — the **real artifact render**, so what
the browser shows is what `verify --file` can check. `POST /runs` starts the
same work in the background and returns a `run_id` to poll.

> **Folders can hide reports.** With a `_folder.yaml` ([[folder-yaml]]) a person
> without `view` on a report's folder sees it nowhere: it is not in
> `GET /api/reports`, `/api/runs` or `/api/discovery`, and every route above,
> and `/r/{name}`, answers as for a name that does not exist (`404`; an empty
> list for `GET .../runs`). A report they can see but may not act on (`build` to
> start a draft in its folder, `publish` to publish into it) is `403` with
> `detail.required_permission`.

> **There is one renderer.** A registered report with no package is refused with
> `422` naming the fix, never served through a weaker path. See [[report]].

`/built` is what the app opens for a report: the **last build**, from
`output/<name>.html` or, when that file is not there, the path recorded in
the run store. A report never built on this server is built once on first
open and kept. Opening never re-queries after that; fresh data comes from
`/run`, `/runs` (Rebuild) or a schedule.

`GET /api/runs` lists rows from that store, newest first. Query params:
`kind`, `target`, `limit`. A viewer may read it. The HTML of a report stays
on disk; the row holds the output path. The **History** list (`/runs`) is this list.
A build row stores no verdict (a build is not a check), so the page shows the
`/api/desk` re-check, the one the Reports list shows, on a report's newest
build, and "Not checked" on the older ones.

The `html` download is that last build, the file the reader is looking at.
`pdf` is a print of that same file (headless Chromium, so charts render). It
carries no trace; the HTML file is what `verify --file` checks.
`xlsx` goes through the Excel renderer, which derives no
[[number-formats|formats]], and runs the report to do so.

## Drafts

Remote drafts (design: `docs/strategy/remote-authoring.md`). `{kind}` is `reports` or `models`.
A draft's owner is the acting principal; `{owner}` is that name slugged to
`[a-z0-9._-]`.

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/drafts` | owner (their own); admin (everyone's) |
| `POST` | `/api/drafts` | analyst: start your own draft of a published report or model |
| `PUT` | `/api/drafts/{owner}/{kind}/{path}/files/{file}` | analyst, and owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/files` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/version` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/preview` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/impact` | owner or admin |
| `POST` | `/api/drafts/{owner}/{kind}/{path}/publish` | analyst, and owner or admin |
| `DELETE` | `/api/drafts/{owner}/{kind}/{path}` | analyst, and owner or admin |

| `GET` | `/api/folders` | viewer: the folders the caller may see, with their level and whether a publish there is direct or a request. `personal` is the caller's own `my-published/<sign-in name>` (null with no sign-in identity). `permissions` (read-only, `editable: false`) only for `manage` and for the owner of a personal folder |
| `GET` | `/api/drafts/{owner}/reports/{path}/destinations` | owner or admin: where the draft may be published, each `mode: publish` or `request` |
| `GET` | `/api/publish-requests?status=` | viewer: the caller's own requests, and those into folders where they hold `publish` |
| `POST` | `/api/publish-requests/{id}/approve` | analyst, and `publish` on the destination |
| `POST` | `/api/publish-requests/{id}/reject` | analyst, and `publish` on the destination; body `{"note"}` (required) |
| `POST` | `/api/code-requests` | analyst: Python from `tracebi push`, body `{"files": {path: text}, "note"}` (note required) |
| `GET` | `/api/code-requests?status=` | viewer: the caller's own; an admin sees every one |
| `GET` | `/api/code-requests/{id}` | the requester or an admin: each file with its diff, and the runs an approval started |
| `POST` | `/api/code-requests/{id}/approve` | admin: copy the files in, run the pipelines they touch once |
| `POST` | `/api/code-requests/{id}/reject` | admin; body `{"note"}` (required) |
| `POST` | `/api/library/sync` | outside sign-in: `TRACEBI_LIBRARY_SYNC_SECRET` as `X-Hub-Signature-256` or `X-TraceBi-Sync-Token`; 404 when unset |

`POST /api/drafts` takes `{"kind": "reports"|"models", "path", "from_published"}`
and answers `201` with the new draft, or `200` with the one the caller already
has; a Python model, or a report with a `report.py`, is `422` and the message
says to edit it from a laptop. `PUT .../files/{file}` takes `{"content"}` and
answers with the draft's new `version`.

A draft of a report is also checked against its folder's `_folder.yaml`
([[folder-yaml]]): starting one needs `build` there. `/publish` takes
`{"note", "folder"}`; `folder` is a library path to publish into (default: the
draft's own path). With `publish` on the destination it answers `200`,
`"status": "published"`; with only `build` it answers `202`,
`"status": "requested"` and the request, for someone with `publish` there to
approve or reject; with less, `403`. A folder with `accepts: checkable` refuses
(`422`) a report that is not made of re-runnable numbers, at publish and at
request. Approving answers `200` with the request, now `approved`; deciding a
request already decided is `422`; one the caller may not see is `404`.

`/preview` renders the draft in memory against the published models plus the
owner's draft models, and writes nothing. `/publish` validates the draft first,
keeps the version it replaces under `.tracebi/history/`, copies it into the
library and records a `publish` run. The draft is kept. `DELETE` removes the
draft only, never the published copy.

`/impact` is for a model draft (a report draft is `422`). It re-runs the
recorded queries of every published report that reads the model, from each
report's last build, against the draft, and answers
`{reports: [{report, status, detail, moved, broken}], summary, needs_acceptance}`.
`status` is `unchanged`, `moves` (`moved[].figures` carry `id`, `old`, `new`),
`breaks` (`broken[].error`), `not_built` (no last build to compare; listed,
never unchanged) or `not_checkable`. It writes nothing. `/publish` of a model
whose impact has a `moves` or `breaks` is `409` with the same `impact` in
`detail`, unless the body carries `"accept_impact": true`; a break needs
accepting too. The accepted impact is stored in the `publish` run's `detail`.
The MCP tool `model_impact(path)` is the same check, and `publish_draft` (also `folder`; with only Build there it returns `status:
requested`) and `list_publish_requests` / `decide_publish_request` (approve or
reject; Publish on the destination) are the same flow for an agent. `publish_draft` takes
`accept_impact`.

A model that names `owners` in its published file may be published only by one
of them or an admin; anyone else gets `403` (MCP `ok: false`) naming the owners,
checked before the impact. They can still draft and read `/impact`. Names only,
no groups; no owners means any analyst.

## Report specs

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/spec/schema` | viewer |
| `POST` | `/api/spec/validate` | viewer |
| `POST` | `/api/spec/render` | analyst |

`/render` compiles the spec to a package and renders it like a hand-authored
one — same figures, same trace drawer, same schema-2 manifest.

## Verify

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/api/verify/file` | viewer |

The offline file check over HTTP: embedded bytes against the manifest. No model
needed. See [[trace]].

## Pipelines

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/pipelines` | viewer |
| `POST` | `/api/pipelines/{name}/run` | **admin** |
| `POST` | `/api/pipelines/{name}/layers/{layer}/run` | **admin** |
| `GET` | `/api/pipelines/{name}/layers/{layer}/history` | viewer |
| `POST` | `/api/pipelines/{name}/runs` | **admin** |
| `GET` | `/api/pipelines/{name}/runs` · `/api/pipelines/{name}/runs/{id}` | viewer |
| `GET` | `/api/pipelines/{name}/runs/{id}/log` | analyst |
| `GET` | `/api/pipelines/{name}/source` | viewer |

`GET /api/pipelines` lists each pipeline with its `layers` and last run of each,
the `model`(s) it feeds, and, from its `pipelines/<name>.yaml`, the `transform`
it runs (the phase ① script; `null` for a hand-built runner) and its
`description`; a model's Data page (its line and Transform tab) and the Map (`/data/map`) show them.

These **write to the warehouse**, which is why they require `admin` — the split
in the role model is by side effect, not by resource.

`POST …/runs` is what **Refresh data** (the primary action on a model's Transform tab, shown only to an admin) and
per-step **Run** use. It
starts the run in the background and returns at once (`202`; `?layer=` runs one
step, `?refresh=true` adds what it depends on). A pipeline already running
returns that run with `already_running: true`. The run's output is a log:
`GET …/runs/{id}/log?after=<offset>` returns the new lines, a `next` offset to
ask from, and `done`. Reading a log needs `analyst` because it is whatever the
steps printed, not only their status. Logs are files under
`data/logs/pipelines/<name>/`, the newest 30 per pipeline.

`GET …/runs` lists every recorded run of the pipeline, newest first, whether it
started from the app or from `tracebi run-pipeline` (those carry
`actor_role: "cli"`). A run has `layers` (the steps it ran) and `reports` (the
reports its build step rebuilt, only those it actually built).

## Connectors, docs, dev

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/connectors` · `/api/connectors/{name}` | viewer. Each carries `read_by`: `{transforms: [{name, tables}], layers: [{pipeline, layer}], models}`, read from the transform files (`-- source:` lines, `load_source(...)`), the pipelines' layers and the models |
| `GET` | `/api/connectors/{name}/source` | viewer |
| `GET` | `/api/connectors/{name}/tables` | viewer. What the source holds, read now: `{connected: true, tables: [{name, columns: [{name, type}], rows}]}` (`rows` for a DuckDB file, and a SQL database's first 20 tables; else null), or `{connected: false, reason, variable?}` with status 200 when its `${VAR}` is unset or it refuses. The connection is resolved on this request only and released before it returns |
| `GET` | `/api/connectors/{name}/warehouse` | viewer. Tables, row counts, column profiles and sink-contract status of a file-backed DuckDB source; the file is opened read-only and closed within the request |
| `GET` | `/api/inputs` | viewer. The project's `inputs/` folder: `{folder, exists, files: [{path, size, modified, read_by: [transform]}]}`; `read_by` is found by reading each transform for a literal path into `inputs/` |
| `GET` | `/api/warehouse` | viewer. `{warehouses: [{name, tier, where, exists, size, engine_version, read_by, tables: [{name, rows, columns, written_by: {transform, contract, at} \| null, read_by, contract: {status, checks, checked_at}, fed_from: [{ref, connection, table, fingerprint, rows, loaded_at, snapshot}]}]}]}`, one per warehouse-kind connector, read-only |
| `GET` | `/api/docs` · `/api/docs/{name}` | viewer |
| `POST` | `/api/_dev/reload` | **admin**, and only with `TRACEBI_DEV_MODE` |
| `POST` · `GET` · `DELETE` | `/mcp` | the agent gateway, only when `TRACEBI_MCP_TOKEN` is set. Bearer token, outside the app's Basic/proxy auth |
| `GET` | `/api/_dev/discovered` | admin |

## The SPA

`GET /` serves the built React bundle. When it has not been built, the page
says so and names the build command rather than 404ing.

The app's addresses, five places in the sidebar (`web/ui/src/nav.js`):

| Place | Addresses |
| --- | --- |
| Reports | `/` the library (`?model=<m>` narrows it); `/reports/<folder>/<name>` one report (`?build=1` turns Build mode on) |
| Ask | `/ask` (`?model=<m>` picks the model) |
| Data | four tabs, the chain left to right: `/data` Models (a chain row per model), `/data/sources` Sources (every connection and the `inputs/` folder), `/data/warehouse` Warehouse (every table: who wrote it, who reads it, its checks), `/data/map` Map; `?model=<m>` narrows the last three. `/data/<m>` one model, then `/transform`, `/sources`, `/runs` |
| Review | four tabs: `/review` Attention, `/review/drafts` Drafts, `/runs` History, `/verify` Verify; `/drafts/<owner>/<kind>/<path>` one draft |
| Docs | `/docs` the handbook; `/docs/get-started` first, then `/docs/<section>/<page>` per file of `docs/` |

The sidebar shows the places a role uses (`placesFor` in `web/ui/src/nav.js`):
everyone Reports, Ask and Docs, an analyst also Review, an admin also Data. With no
sign-in `/api/me` names everyone admin, so all five show. An address above the
role renders a plain page saying who it is for; the API enforces the roles.

Older addresses redirect, keeping their query (`movedTo`): `/m/<m>/…` to the
same thing under Data, Ask, History or the library; `/models` to `/data`;
`/explore` to `/ask`; `/sources` and `/connectors` to `/data/sources`; `/map`
and `/data?view=map` to `/data/map`; `/handbook` (and `/handbook/<page>`) to `/docs`;
`/getting-started` and `/workflow` to `/docs/get-started`; `/drafts` and `/review#drafts`
to `/review/drafts`; `/reports?r=<name>` to `/reports/<name>`.

FastAPI's interactive API reference is at `/api-docs` (ReDoc at `/api-redoc`):
`/docs` is the app's Docs place.

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
