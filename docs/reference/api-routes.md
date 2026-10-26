# API routes

The HTTP API `tracebi serve` provides. Every route reads from the registry.

```bash
curl -s http://127.0.0.1:8000/api/health
# {"status": "ok", "version": "0.7.0"}
```

- The role in each table is the minimum when roles are enforced
  ([[environment-variables]]).
- To try routes in the browser, open `/api-docs` on a running server
  (FastAPI's Swagger UI; ReDoc at `/api-redoc`). `/docs` is the app's handbook.
- A failed run returns `{"message": "...", "exception_type": "ValueError",
  "traceback": ""}` in `detail`. `traceback` is empty unless
  `TRACEBI_DEV_MODE` is set, because it would show file paths, the server's
  user name and package versions.

## Health and discovery

| Method | Path | Role | Returns |
| --- | --- | --- | --- |
| `GET` | `/api/health` | none | `{"status": "ok", "version": "<installed version>"}` |
| `GET` | `/api/status` | viewer | `{"version", "checks": [{"name", "ok", "detail"}]}`: output writable, discovery failures, models loaded, SMTP configured, in-server schedules, sign-in setup |
| `GET` | `/api/schema` | viewer | The vocabulary, from the same source as `tracebi context` |
| `GET` | `/api/discovery` | viewer | Each file: registered, skipped or failed, with the reason |
| `GET` | `/api/me` | viewer | `{actor, role, sign_in}`; `sign_in` is `oidc`, `basic`, `proxy` or `none` |

- `/api/discovery` is where to look when something you wrote doesn't appear.
- In `/api/status`, `email_configured.detail` lists the SMTP variable names and
  whether each is set, never a URL, host, user or password.
  `schedules_in_server.detail` is `{"on", "count"}`. `auth.detail` describes
  the sign-in setup. `build_mode` says the app runs in dev mode and `gateway`
  that it serves `/mcp`; Ask points at the agent when either is true.

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

| Route | Detail |
| --- | --- |
| `/api/models`, `/api/models/{name}` | Each model carries `label` ([[model-json]]) beside `name`, the identifier other routes take. Each fact lists `runnable_measures`: declared measures whose columns exist on its table. When the warehouse is not built yet, every declared measure is listed and a run reports the real error. TraceBi's own tables (`tracebi_*`, `alembic_version`) are left out and counted in `hidden_framework_tables`. |
| `/query` | Takes a [[queries]] spec; returns the result and a lineage graph. Computes but saves nothing, so a viewer may call it. Each row comes twice: `data` (raw values, used by CSV download) and `display` (text formatted as a built report would: the measure's declared format, else the shape default). NaN or infinity is `null` in `data` and an empty string in `display`. |
| `/dimensions/{dim.attr}/values` | One attribute's distinct values, sorted, from the dimension's table: `{"values", "total", "truncated"}`. `?limit=` default 200, at most 1,000. Unknown attribute: 404. A time grain or bin has no stored values: 422. Ask uses it for filters. |
| `/preview`, `/export.csv` | Read through the table API below: the first rows (`?rows=`, default 50, at most 500) with an exact total and engine types (`DOUBLE`, `DATE`), or the CSV streamed. A source the table API does not read (a `SELECT` source, a CSV folder, Snowflake, BigQuery) uses the connector's own load. A framework table is 404. |
| `/source` | The model's file, read-only (the Code tab). A model registered in Python has no file and says so. |

## Tables

One read-only API for every table, addressed as `(source, table)`. `source` is
a connector's name (a warehouse on any tier, a SQL connection, a
`MemoryConnector`) or `inputs`, where `table` is a file's path inside
`inputs/` (CSV, TSV, Parquet or JSON, read by DuckDB, confined to that
folder).

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/tables/{source}/{table}` | viewer |
| `GET` | `/api/tables/{source}/{table}/rows` | viewer |
| `GET` | `/api/tables/{source}/{table}/profile` | viewer |
| `GET` | `/api/tables/{source}/{table}/export.csv` | viewer |

| Route | Returns |
| --- | --- |
| `/{source}/{table}` | `{source, table, kind: "warehouse" \| "connection" \| "file", rows, rows_exact, columns: [{name, type}], written_by: {transform, contract, at} \| null, contract: {status, file, checks, note, checked_at} \| null, read_by: [model], used_by: [{report, display_name}], transform_read: [{ref, snapshot, fingerprint}]}`. `type` is the engine's spelling. `written_by`, `contract` and `transform_read` (what the writing run read from outside the warehouse; `snapshot` when a committed file stood in) come from the certificate, for warehouse tables only. `used_by` lists reports the caller may view whose bindings read a model in `read_by`. |
| `/rows` | `?offset=0&limit=100&sort=<col>&desc=1&q=<text>&where=<json>` → `{columns, rows, offset, limit, total, total_exact, elapsed_ms}`. `limit` at most 500 (more is 422). `q` matches text columns, ignoring case. `where` is a JSON list of `{column, op, value}`, `op` one of `eq ne lt le gt ge contains is_null not_null`, the value of the column's kind. Dates come back as ISO strings. `total` is exact, except an unfiltered SQL connection with a catalog estimate (`total_exact: false`). |
| `/profile` | `{rows, columns: {name: {type, nulls, null_share, distinct, min, max, mean?, top: [{value, count}]}}}`. `min`/`max` for numbers and dates, `mean` for numbers, `top` (the five commonest) for text and booleans. Past 50 columns nothing is profiled and `note` says so. |
| `/export.csv` | The same `sort`, `q` and `where`, streamed from the engine. |

- Nothing free-form reaches SQL. The table must be in the source's catalog and
  every column must be the table's. A quoted identifier, unknown op or column,
  or a value of the wrong kind is 422 before any statement is built. Values
  are bound.
- DuckDB reads use the read-only query connection. A SQL connection gets a
  short-lived engine for the request, stopped at `engine.query_timeout_s`
  (504 past it).
- An unreachable source answers `200 {connected: false, reason, variable?}`.
- A framework table (`tracebi_*`, `alembic_version`) is 404.
- Folder permissions do not apply: a table is not a report.

## Reports

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/reports` | viewer |
| `POST` | `/api/reports/{name}/run` | analyst |
| `POST` | `/api/reports/{name}/runs` | analyst |
| `GET` | `/api/reports/{name}/runs` | viewer |
| `GET` | `/api/reports/{name}/runs/{run_id}` | viewer |
| `GET` | `/api/reports/{name}/built` | viewer |
| `GET` | `/api/reports/{name}/cover` | viewer |
| `GET` | `/api/runs` | viewer |
| `GET` | `/api/runs/counts?kind=` | viewer |
| `GET` | `/api/desk[?fresh=1]` | viewer |
| `GET` | `/api/reports/{name}/download?format=xlsx\|html\|pdf` | analyst |
| `GET` | `/api/reports/{name}/lineage` | viewer |
| `GET` | `/api/reports/{name}/mermaid` | viewer |
| `GET` | `/api/reports/{name}/source` | viewer |
| `GET` | `/r/{name}` | viewer |

| Route | Detail |
| --- | --- |
| `GET /api/reports` | Each report has `name` (the path routes take), `display_name` (`report.json`'s `name`), `form` (`spec`, `package` or `code`), `made_from` (`app.jsx`, `template.html` or `null`), `folder`, `owner` (the last publisher, or a My published folder's owner), `models` (those its bindings read) and `measures` (the declared measure names they ask for, read from the file). |
| `/run` | `{name, html, manifest}`: the real build, which `verify --file` can check. |
| `POST /runs` | Starts the same build in the background and returns a `run_id` to poll. |
| `/built` | The last build: `output/<name>.html`, else the path in the run store. A report never built on this server is built once on first open and kept. Fresh data comes from `/run`, `/runs` (Rebuild) or a schedule. |
| `/cover` | The PNG of the last build's first screen, with an `ETag` of its write time (304 when unchanged). 404 when the build took none; it never builds. |
| `/api/runs` | Run rows, newest first; `kind`, `target`, `limit`. Rows carry `display_name` beside `target` (a model publish carries its `label`; a pipeline run `null`). The HTML stays on disk; the row holds its path. A build row stores no verdict, so History shows the `/api/desk` re-check on a report's newest build and "Not checked" on older ones. |
| `/api/runs/counts` | `[{kind, target, runs, failed}]` per target the caller may see. |
| `/api/desk` | Only reports the caller may view: pins, drafts, verdicts, builds (each with `values` [{id, label, text, delta, spark}], its KPIs as built), sinks. Each verdict or build row has `computed_at` and `cached`. A verdict is kept while its manifest, its models and their warehouse (and certificate) are unchanged; `?fresh=1` re-runs all. |
| `/download` | `html`: the last build. `pdf`: a print of it by headless Chromium, with no trace. `xlsx`: the Excel renderer, which derives no [[number-formats]] and runs the report to do so. |
| `/lineage` | Transform → tables → model → queries → figures, from the last build's manifest. `/mermaid` returns a diagram. |
| `/source` | The files that define the report (the spec, or `report.json`, `template.html`, `style.css`, `script.js`, `report.py`), read-only, and only files discovery registered. |
| `/r/{name}` | A share link: the last build as a full page. |

**Folders can hide reports.** With a `_folder.yaml` ([[folder-yaml]]), a
person without `view` on a report's folder finds it nowhere: not in
`/api/reports`, `/api/runs` or `/api/discovery`, and every route above,
including `/r/{name}`, answers 404 (an empty list for `GET .../runs`). A
report they can see but may not act on is 403 with
`detail.required_permission`.

**One renderer.** A registered report with no package is refused with 422
naming the fix ([[report]]).

## Drafts and publishing

`{kind}` is `reports` or `models`. A draft's owner is the acting principal;
`{owner}` is that name slugged to `[a-z0-9._-]`.

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/drafts` | The caller's own; an admin sees everyone's |
| `POST` | `/api/drafts` | analyst |
| `PUT` | `/api/drafts/{owner}/{kind}/{path}/files/{file}` | analyst, and owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/files` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/version` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/preview` | owner or admin |
| `GET` | `/api/drafts/{owner}/{kind}/{path}/impact` | owner or admin |
| `GET` | `/api/drafts/{owner}/reports/{path}/destinations` | owner or admin |
| `POST` | `/api/drafts/{owner}/{kind}/{path}/publish` | analyst, and owner or admin |
| `DELETE` | `/api/drafts/{owner}/{kind}/{path}` | analyst, and owner or admin |
| `GET` | `/api/folders` | viewer |
| `GET` | `/api/publish-requests?status=` | viewer |
| `POST` | `/api/publish-requests/{id}/approve` | analyst, and `publish` on the destination |
| `POST` | `/api/publish-requests/{id}/reject` | analyst, and `publish` on the destination |
| `POST` | `/api/code-requests` | analyst |
| `GET` | `/api/code-requests?status=` | viewer |
| `GET` | `/api/code-requests/{id}` | the requester or an admin |
| `POST` | `/api/code-requests/{id}/approve` | admin |
| `POST` | `/api/code-requests/{id}/reject` | admin |
| `POST` | `/api/library/sync` | outside sign-in (see below) |

| Route | Detail |
| --- | --- |
| `POST /api/drafts` | `{"kind", "path", "from_published"}`. 201 with a new draft, 200 with the one the caller has. A Python model, or a report with a `report.py`, is 422 and says to edit it from a laptop. Starting a report draft needs `build` on its folder. |
| `PUT .../files/{file}` | `{"content"}`; answers with the draft's new `version`. |
| `/preview` | Renders the draft in memory against the published models plus the owner's draft models. Writes nothing. |
| `/impact` | Model drafts only (a report draft is 422). Re-runs the recorded queries of every published report that reads the model, from each report's last build, against the draft: `{reports: [{report, status, detail, moved, broken}], summary, needs_acceptance}`. `status` is `unchanged`, `moves` (`moved[].figures` with `id`, `old`, `new`), `breaks` (`broken[].error`), `not_built` or `not_checkable`. Writes nothing. |
| `/destinations` | Where a report draft may go, each `mode: publish` or `request`. |
| `/publish` | `{"note", "folder", "accept_impact"}`; `folder` defaults to the draft's own path. Validates the draft, keeps the version it replaces under `.tracebi/history/`, copies it into the library and records a `publish` run. The draft is kept. With `publish` on the destination: 200, `"status": "published"`. With only `build`: 202, `"status": "requested"` and the request. Less: 403. A `checkable` folder refuses a report that is not all re-runnable numbers (422). A model whose impact `moves` or `breaks` is 409 with the impact until `"accept_impact": true`; the accepted impact is stored in the run's `detail`. A model naming `owners` may be published only by an owner or an admin (403 otherwise, checked before the impact). |
| `DELETE` | Removes the draft, never the published copy. |
| `/api/folders` | The folders the caller may see, with their level and whether a publish there is direct or a request. `personal` is the caller's `my-published/<sign-in name>` (null with no sign-in identity). `permissions` (read-only, `editable: false`) only for `manage` and a personal folder's owner. |
| `/api/publish-requests` | The caller's own requests and those into folders where they hold `publish`; each row carries `can_decide`. Approve answers 200 with the request, now `approved`. Reject needs `{"note"}`. Deciding a decided request is 422; one the caller may not see is 404. |
| `/api/code-requests` | Python from `tracebi push`: `{"files": {path: text}, "note"}` (note required). An admin sees all; others their own. `GET /{id}` gives each file's diff and the runs an approval started. Approve copies the files in and runs the pipelines they touch once. Reject needs `{"note"}`. |
| `/api/library/sync` | Exists only with `TRACEBI_LIBRARY_SYNC_SECRET`, sent as `X-Hub-Signature-256` or `X-TraceBi-Sync-Token` (404 otherwise). |

The MCP tools do the same: `model_impact(path)`, `publish_draft` (with
`folder` and `accept_impact`; `status: requested` with only Build there),
`list_publish_requests` and `decide_publish_request`.

## Report specs

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/spec/schema` | viewer |
| `POST` | `/api/spec/validate` | viewer |
| `POST` | `/api/spec/render` | analyst |

`/render` compiles the spec to a package and builds it like any other: the
same figures, trace drawer and schema-2 manifest.

## Verify

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/api/verify/file` | viewer |

The offline file check over HTTP: the embedded rows against the manifest. No
model needed ([[trace]]).

## Pipelines

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/pipelines` | viewer |
| `POST` | `/api/pipelines/{name}/run` | admin |
| `POST` | `/api/pipelines/{name}/layers/{layer}/run` | admin |
| `GET` | `/api/pipelines/{name}/layers/{layer}/history` | viewer |
| `POST` | `/api/pipelines/{name}/runs` | admin |
| `GET` | `/api/pipelines/{name}/runs` · `/api/pipelines/{name}/runs/{id}` | viewer |
| `GET` | `/api/pipelines/{name}/runs/{id}/log` | analyst |
| `GET` | `/api/pipelines/{name}/source` | viewer |

- Running a pipeline writes the warehouse, so it needs `admin`. Roles are
  split by what a route changes, not by resource.
- `GET /api/pipelines` lists each pipeline's `layers` with their last run, the
  `model`(s) it feeds, and from `pipelines/<name>.yaml` the `transform` it
  runs (`null` for a runner built in Python) and its `description`.
- `POST …/runs` is what **Refresh data** and a step's **Run** call. It returns
  202 at once (`?layer=` for one step, `?refresh=true` to add what it depends
  on). A pipeline already running returns that run with
  `already_running: true`.
- `GET …/runs/{id}/log?after=<offset>` returns new lines, a `next` offset and
  `done`. It needs `analyst` because it is whatever the steps printed. Logs
  live in `data/logs/pipelines/<name>/`, the newest 30 per pipeline.
- `GET …/runs` lists every run, from the app or `tracebi run-pipeline` (those
  carry `actor_role: "cli"`), each with `layers` (the steps it ran) and
  `reports` (the reports its build step rebuilt).

## Sources, transforms and the warehouse

| Method | Path | Role | Returns |
| --- | --- | --- | --- |
| `GET` | `/api/connectors` · `/api/connectors/{name}` | viewer | Each carries `read_by`: `{transforms: [{name, tables}], layers: [{pipeline, layer}], models}`, read from transform files (`-- source:` lines, `load_source(...)`), pipeline layers and models; also `warehouse` (bool), `label` and `dialect` (SQL). |
| `GET` | `/api/connectors/{name}/source` | viewer | The model files that declare it |
| `GET` | `/api/connectors/{name}/tables` | viewer | `{connected: true, tables: [{name, columns: [{name, type}], rows, rows_exact, agents}], hidden_framework_tables, agent_tables}` (`agents`: whether the connection file lets an agent read it), or `200 {connected: false, reason, variable?}` when its `${VAR}` is unset or it refuses. `rows` is exact for a DuckDB file or in-memory frames, the catalog estimate for a database that keeps one (Postgres `pg_class.reltuples`, `rows_exact: false`), else null. No table is counted row by row. The connection is opened for this request only. |
| `POST` | `/api/connectors/{name}/test` | admin | Opens the connection, lists its tables, closes it: `{ok: true, tables: n}` or `{ok: false, reason}`, with every resolved credential removed from the reason ([[credentials]]). |
| `GET` | `/api/connectors/{name}/warehouse` | viewer | Tables, row counts, column profiles and sink-contract status of a DuckDB file source, plus `hidden_framework_tables`. Each contract names the `file` that declares it and the transform's `note`. Opened read-only and closed within the request. |
| `GET` | `/api/connections/types` | viewer | The connection types and each one's fields (`name, label, kind: text\|secret\|url\|path, required, help`); the Add a connection form is drawn from it. |
| `POST` | `/api/connections` | admin, identified | `{name, type, fields: {…}, label?, agents?: {tables: [a, b] \| "*"}}` → writes `connections/<name>.yaml` (a secret typed in goes to the store; the file names it `${NAME}`) and answers 201 with the connection as `GET /api/connectors/{name}` describes it. 409 when the name is taken, 422 with the validator's `errors`. Without sign-in: 403 naming `tracebi connect`. |
| `POST` | `/api/connections/test` | admin, identified | The same body, tested before it is saved: `{ok, tables}` or `{ok: false, reason}`. Writes nothing. |
| `PUT` | `/api/connections/{name}` | admin, identified | Edits the file in place: the fields sent (a secret sent empty is kept), `label`, and `agents` when sent (null removes it). The type does not change. |
| `DELETE` | `/api/connections/{name}` | admin, identified | Removes the file: 204, or 409 with `read_by` while a transform, pipeline step or model reads it. |
| `POST` | `/api/inputs?name=x.csv[&replace=true]` | admin, identified | The body is one CSV or Parquet file, saved as `inputs/<name>` (at most 50 MB; 409 when it exists). |
| `GET` | `/api/credentials` | viewer | Every `${NAME}` the project references and where it is set, never a value ([[credentials]]). |
| `PUT` | `/api/credentials/{name}` | admin, identified | `{value}` → the status row: 201 new, 200 replaced, 422 for an unreferenced name. Without sign-in: 403 naming `tracebi secret set NAME`. Records a `credential` run row. |
| `DELETE` | `/api/credentials/{name}` | admin, identified | Removes the store's value: 204, or 404 when it holds none. Environment and `.env` values are untouched. |
| `GET` | `/api/inputs` | viewer | `{folder, exists, files: [{path, size, modified, read_by: [transform], table}]}`. `read_by` comes from each transform's literal paths into `inputs/`. |
| `GET` | `/api/transforms` | viewer | Every file in `transforms/`: `[{name, form: sql\|python\|notebook, file, contract_file, note, pipelines, models, tables, written_at}]`. `contract_file` is the `.contract.yaml` beside it, or the file itself when it holds a `with contract(...)` block. `models` are those its pipelines refresh, then those reading what it wrote. `tables` and `written_at` come from the certificate. |
| `GET` | `/api/transforms/{name}/source` | viewer | The transform's file and its contract (`{files, hint}`). `name` is a stem in `transforms/`, never a path (404 otherwise). |
| `GET` | `/api/warehouse` | viewer | `{warehouses: [{name, tier, where, exists, size, engine_version, read_by, tables: [{name, rows, columns, written_by, read_by, contract: {status, checks, checked_at}, fed_from: [{ref, connection, table, fingerprint, rows, loaded_at, snapshot}]}], hidden_framework_tables}]}`, one per warehouse connector; `writers` lists what each transform's run read, once per transform. Read-only; framework tables are never listed. |

## Docs, dev and the gateway

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/docs` · `/api/docs/{name}` | viewer |
| `POST` | `/api/_dev/reload` | admin, and only with `TRACEBI_DEV_MODE` |
| `GET` | `/api/_dev/discovered` | admin |
| `POST` · `GET` · `DELETE` | `/mcp` | Only with `TRACEBI_MCP_TOKEN`, `TRACEBI_OIDC_ISSUER` or the built-in sign-in (`TRACEBI_DEMO_LOGIN`, `TRACEBI_LOCAL_USERS`). A bearer token, outside the app's Basic or proxy auth ([[connect-chatgpt-and-claude]]). |
| `GET` | `/login?next=` · `/login/callback` · `POST /logout` | App sign-in through the OIDC provider ([[sign-in]]) |

## The app's addresses

`GET /` serves the built React app. When it has not been built, the page names
the build command.

| Place | Addresses |
| --- | --- |
| Reports | `/` the library (`?model=<m>` narrows it); `/?folder=<path>` one folder (one the caller may not see is not found); `/reports/<folder>/<name>` one report (`?build=1` turns Build mode on); `/ask` a question of one model (`?model=<m>`), reached by **Ask this model** on a folder's page or a model's page under Data |
| Data | `/data` Overview (the board: sources → transforms → warehouse → models → reports; `?model=<m>` lights that model's path), then four folders, each a page per thing: `/data/sources` (`/data/sources/<name>` one connection, `/data/sources/inputs` the folder, `/data/sources/<name>/<table>` one source table, `/data/sources/inputs/<path>` one input file); `/data/transforms` (`/data/transforms/<name>` one transform); `/data/warehouse` (`?table=<id>`, `?group=<id>` select in its browser; `/data/warehouse/<table>` one table); `/data/models` (`/data/models/<m>` one model: `?table=<t>`, `?measure=<name>`, `?view=measures\|relationships\|storage\|code\|agent`). Nothing under `/data` is narrowed to a model. |
| Review | `/review` Attention, `/review/drafts` Drafts, `/runs` History, `/verify` Verify; `/drafts/<owner>/<kind>/<path>` one draft |
| Docs | `/docs` the handbook in `docs/toc.yaml`'s order; `/docs/<section>/<page>` per file; the quickstart at `/docs/get-started`. A page that moved keeps its old address (the toc's `moved:`). |

- The sidebar shows the places a role uses (`placesFor` in
  `web/ui/src/nav.js`): Reports and Docs for everyone, Review and Data for
  analysts and admins (run buttons and credential forms for admins only).
  With no sign-in `/api/me` says everyone is admin, so all four show.
- An address above the caller's role shows a page saying who it is for. The
  API enforces the roles.
- Older addresses redirect, keeping their query (`movedTo`): `/m/<m>/…` to the
  same thing under Data, Ask, History or the library; `/models` to
  `/data/models` (`/models?m=<m>` to `/data/models/<m>`); `/explore` to `/ask`;
  `/sources` and `/connectors` to `/data/sources`; `/map`, `/data/map` and
  `/data?view=map` to `/data` (with `model=<m>`, to `/data/models/<m>`);
  `/data/<m>` and `/data/<m>/model` to `/data/models/<m>`,
  `/data/<m>/transform` to the transform its pipeline runs, `/data/<m>/sources`
  to `/data/sources`, `/data/<m>/runs` to `/runs?model=<m>`;
  `/data/tables/<source>/<table>` to the table's page under Sources or
  Warehouse; `/data/sources?source=<name>` to `/data/sources/<name>`, and a
  `?model=` on a Data folder is dropped; `/handbook`
  and `/handbook/<page>` to `/docs`; `/getting-started` to
  `/docs/get-started`; `/workflow` to
  `/docs/concepts/the-three-phase-workflow`; `/drafts` and `/review#drafts`
  to `/review/drafts`; `/reports?r=<name>` to `/reports/<name>`.

## Add a route

1. Add a file under `tracebi/web/api/routers/`.
2. Include it in `main.py`.
3. Read resources only from the registry. Never import app-specific objects.

Any write route the authorizer does not recognise requires `analyst`, so a new
route is guarded by default. Add an explicit rule when it needs `admin`.
