# Customizing the TraceBi Web App

How to point the web server at your own data, add your own reports and
restyle or extend the React UI, and deploy. Written for the
person who has outgrown the reference project.

---

## Architecture in one paragraph

The web layer is a FastAPI app ([tracebi/web/api/main.py](../../tracebi/web/api/main.py)) that
serves a JSON API under `/api` and serves the built React SPA
(`tracebi/web/ui/dist/`) at `/`. Everything the API exposes — connectors, models,
reports, pipelines — is read from a **singleton registry**
([tracebi/registry.py](../../tracebi/registry.py), also re-exported as
`tracebi.web.api.registry` for older code) that your *app module*
populates once at startup. Routes never construct resources themselves;
they only read the registry. That seam is what makes the whole web layer
swappable onto your data.

```
your app module ──populates──▶ registry ◀──reads── API routes ◀── React UI
(import time)                 (singleton)          (request time)
```

## The three-phase workflow this serves

The server front-ends the analyst workflow described in
[[the-three-phase-workflow]]: phase ① `transforms/` writes clean star-schema
tables into the warehouse `tracebi.yaml` names, phase ② `models/` declares a
thin `DataModel` over that warehouse, and phase ③ `reports/` holds report
packages (`reports/<model>/<name>/`) pointed at the model.
Phases ② and ③ are auto-discovered directories (below): a model lands
under **Data** (its page, Model tab) and a report in **Reports**, the library, under its
model. Phase ① runs explicitly (`tracebi run-transform`, a pipeline, or
**Refresh data** on the model's Transform tab); the server lists the
transforms (Data → Transforms) but runs one only when asked — the sink it
produces is the input the model reads.

## Step 1: Project-root directories (recommended)

The server auto-discovers these directories at the project root. This is the
lowest-friction way to add resources — no app module configuration needed:

| Directory | Convention | What the server does |
|---|---|---|
| `connections/` | each `<name>.yaml` declares a source: a type and its fields, secrets as `${NAME}` ([[connections-yaml]]) | lists it under Data → Sources; resolves its secrets only when it is used |
| `transforms/` | each `.sql` (with its `.contract.yaml`), `.py` or `.ipynb` is one phase ① transform | lists it under Data → Transforms; runs it only when a pipeline or `run-transform` asks |
| `models/` | each `<name>.yaml` (or `.json`) is one model; a `.py` exposes a `model` variable (a `DataModel`) | registers it via `registry.add_model()` |
| `pipelines/` | each `<name>.yaml` names a transform, models and reports; a `.py` exposes a `runner` variable (a `PipelineRunner`) | registers it via `registry.add_pipeline()` |
| `reports/` | a `<name>/` **report package** (`report.json` + `app.jsx` or `template.html`), or a `.json` `ReportSpec` compiled into one at discovery (a package directory shadows a same-named spec) | registered as a report, listed in the library under its model |

A `.py` in `reports/` that registers a report with `@register.report(...)` is
still imported at startup, but a report with no package is refused (HTTP 422
naming the fix): there is one renderer, the package. The `requests/` lane was
removed in 0.8.

Scaffold files with the CLI, then edit and commit them:

```bash
tracebi connect crm --kind postgres  # → connections/crm.yaml (the secret to .env, or --store secret)
tracebi new-transform "Sales"        # → transforms/sales.sql + sales.contract.yaml
tracebi new-model "Sales Model"      # → models/sales_model.yaml
tracebi new-pipeline "Sales ETL"     # → pipelines/sales_etl.yaml
tracebi new-dashboard "Weekly"       # → reports/weekly/ (report.json + app.jsx)
tracebi new-report "Weekly Report"   # → reports/weekly_report/ (report.json + template.html)
```

These directories also work without the web server — notebooks and scripts
can import from them directly:

```python
from tracebi.model_registry import get_model
from tracebi.pipeline_registry import get_runner

model = get_model("sales_model")    # no server needed
runner = get_runner("sales_etl")
```

Override any directory path via env var (`TRACEBI_CONNECTIONS_DIR`,
`TRACEBI_TRANSFORMS_DIR`, `TRACEBI_MODELS_DIR`, `TRACEBI_PIPELINES_DIR`,
`TRACEBI_REPORTS_DIR`).

## Step 1b: An app module (optional, Python wiring)

Most projects need none: a source is a `connections/<name>.yaml`, and its
secret resolves from the environment, the project `.env` or the encrypted
store ([[credentials]]). An app module is for wiring the declarative files
cannot express, such as a connector type of your own or medallion layers
built in code. The bundled demo app
([tracebi/web/demo_app/](../../tracebi/web/demo_app/)) is the example, opt-in
and never the demo tracebi.com serves — copy its layout:

```
myapp/
  __init__.py        # imports registry module (one line, like demo_app)
  model.py           # connectors + DataModel construction (optional if using models/)
  pipeline.py        # PipelineRunner + layer setup (optional if using pipelines/)
  registry.py        # THE wiring file — connector registration lives here
```

`registry.py` is the only file with registration side effects:

```python
import os
from tracebi.registry import registry
from myapp.model import connector, model

registry.add_connector(connector)
# Models and pipelines in models/ and pipelines/ are auto-discovered;
# register here only if you build them inside the app module.
registry.add_model(model, default=True)
```

Then point the server at it:

```bash
TRACEBI_APP=myapp python -m tracebi.web.run
```

`TRACEBI_APP` defaults to none — a serve shows your project's discovered
directories; set `TRACEBI_APP=tracebi.web.demo_app` for the bundled demo app (the example of Python wiring). If
the named module fails to import, the
server emits a `UserWarning` and starts with an **empty registry** — no
connectors, no models — rather than refusing to boot, so check the startup log
after changing it. `/api/health` returns 200 either way, which means a
healthcheck alone will not tell you the app module loaded.

The one exception is a `TRACEBI_APP` still naming the old top-level `web`
package (`web.demo_app`): that is refused outright with the replacement
spelling, because it is an unfinished upgrade rather than a broken module.

**Rules that keep you out of trouble** (enforced by convention, violated at
your peril):

- Register everything at import time; never mutate the registry inside a
  route handler.
- Construct connectors in your app module and pass credential-bearing URLs
  via `os.environ[...]` explicitly. The framework never reads connector
  URLs from env vars implicitly. See [.env.example](../../.env.example).

## Step 2: Add resources

**Preferred — project-root directories (auto-discovered, no registration code):**

| Directory | File convention | Result |
|---|---|---|
| `connections/` | `<name>.yaml` | **Data → Sources**, and a card in the board's first lane |
| `transforms/` | `<name>.sql` (+ `.contract.yaml`), `.py` or `.ipynb` | **Data → Transforms** |
| `models/` | `<name>.yaml` (or a `.py` with a `model` variable) | the model's **Data** page (Model tab) + **Ask** |
| `pipelines/` | `<name>.yaml` (or a `.py` with a `runner` variable) | the model's **Transform** tab on **Data** |
| `reports/` | a `<name>/` **report package** (shadows a same-named `.json` spec), or a `.json` `ReportSpec` | **Reports** (the library), under its model |

**Or register explicitly** (in your app module's `registry.py`, or the notebook facade `tracebi.web.register`):

| Resource | Call | Appears in UI as |
|---|---|---|
| Connector | `registry.add_connector(conn)` | **Data → Sources** (`/data/sources`) |
| Model | `registry.add_model(model, default=False)` | a model chip on **Reports**, the model's **Data** page (its Model tab) + **Ask** |
| Report | `@registry.report("name", description="…")` on a zero-arg factory, with a package to render it | **Reports** (the library), under its model |
| Scheduled report | **Deprecated**: `@registry.scheduled(...)` warns and only registers; a schedule is a `"schedule"` block in `report.json` | **Reports** |
| Pipeline | `registry.add_pipeline("name", runner)` | the model's **Transform** tab under **Data** (DAG, run buttons, a live run log, history) |

**History** is not a folder. It reads `GET /api/runs`: what ran, when,
for whom, and whether it reproduced. It lives under **Review**;
`/runs?model=<model>` narrows it to one model.

## Step 3: The development loop

```bash
python -m tracebi.web.run                       # uvicorn with hot-reload, port 8000
python -m tracebi.web.run --port 9000           # different port
TRACEBI_DEV_MODE=1 python -m tracebi.web.run    # adds POST /api/_dev/reload
```

Hot-reload restarts the server on Python file changes. Dev mode additionally
mounts `POST /api/_dev/reload`, which re-imports every auto-discovered
module *without* a restart — useful when iterating on Python models and
pipelines. Packages, specs, YAML models and pipelines need neither: live
discovery picks them up every `TRACEBI_DISCOVERY_INTERVAL` seconds.

For UI work, run Vite's dev server alongside the API (see below).

## Step 4: Customize the React UI

The UI lives in [web/ui/](../../web/ui/) — React 18 + Vite, React Query for
data, React Flow for lineage/ERD graphs, Recharts for charts.

```bash
cd web/ui
npm install
npm run dev      # Vite dev server on :5173, proxies /api to the API server
npm run build    # writes tracebi/web/ui/dist/ — FastAPI serves it at / when present
```

Layout of `src/`:

```
api.js               # all API hooks (React Query) — one hook per endpoint
nav.js               # the four places, Data's tabs, their addresses, movedTo (old addresses)
folders.js           # the library's folders: one list, its order, a hue per folder
components/
  Layout.jsx         # sidebar, theme toggle, ⌘K trigger
  Scope.jsx          # page header, one-model routes, redirects from old addresses
  Shared.jsx         # Card, Badge, Btn, Tabs, toasts, skeletons…
  Lineage.jsx        # React Flow lineage graph renderer
  CommandPalette.jsx # ⌘K navigation
pages/               # one file per route
styles/global.css    # ALL design tokens — start here for theming
```

**Theming:** every color in the UI is a CSS variable defined at the top of
[global.css](../../web/ui/src/styles/global.css). Light theme under `:root`,
dark under `[data-theme="dark"]`. To rebrand, edit the tokens (`--blue`,
`--bg`, `--card`, the `--op-*` lineage-node palette) — components never
hard-code colors. The brand gradient is `--brand`.

**Adding a nav page:** the sidebar is four places, `PAGES` in `nav.js`
(Reports `/`, Data `/data`, Review `/review`, Docs `/docs`; Ask `/ask` is a
page inside Reports), drawn
by `Layout.jsx`; Data's own tabs are `DATA_TABS` (Flow, Sources, Transforms,
Warehouse, Models). A new page lives inside one of them: give it a route in
`App.jsx` under that place's address and teach `whereAmI` in `nav.js` which
place it belongs to, so its sidebar entry reads as current. A model is a
filter, not a frame: pass it in the query (`?model=<name>`) or, on Data, the
path (`/data/<model>/<tab>`: `pages/Overview.jsx` draws that page, the line from
`components/TheLine.jsx` with its three stations, then the tabs in `TABS`,
`model`, `transform`, `sources`, `runs`). An
address that moves gets an entry in `movedTo` so old links keep working. Use
the hooks in `api.js` for data and the primitives in `Shared.jsx` for visual
consistency.

## Step 5: Extend the API

New endpoints follow one pattern: a router file under
[tracebi/web/api/routers/](../../tracebi/web/api/routers/), included in `main.py` with the
`/api` prefix, reading **only from the registry** — never importing your
app module directly. Failed runs should return the structured error shape
(`{message, exception_type, traceback}`) via `tracebi/web/api/errors.py`; the UI
knows how to render it.

## Auth

Optional, enabled entirely by env vars (see
[tracebi/web/api/auth.py](../../tracebi/web/api/auth.py) and `.env.example`):

```bash
# Basic auth — single shared credential
TRACEBI_AUTH_USER=admin
TRACEBI_AUTH_PASS=changeme

# OR reverse-proxy header trust (Authelia, oauth2-proxy, Cloudflare Access)
TRACEBI_AUTH_PROXY_HEADER=X-Forwarded-User
TRACEBI_AUTH_PROXY_TRUSTED_IPS=10.0.0.0/8,172.16.0.0/12

# OR the app's own sign-in through your identity provider (see the Sign-in guide)
TRACEBI_OIDC_ISSUER=https://login.example.com
```

No auth vars set ⇒ the app is open (fine on localhost, not on a network).
OIDC sign-in, and named local users (`TRACEBI_LOCAL_USERS`), are in
[[sign-in]]; folder permissions narrow what a role allows, per folder
([[folder-yaml]]).

**Roles.** Authentication says who a caller is; authorization says what they
may do. Three ordered roles, split by side effect: `viewer` (read models,
reports, lineage; run Ask queries and spec validation — they compute
but persist nothing), `analyst` (viewer + execute report and request code),
`admin` (analyst + run pipeline layers, which write to the warehouse,
`/api/_dev/reload`, keeping a selection cut, which writes the published
`report.json`, approving code requests, and setting a connection's
credential, which also needs a role a sign-in or role source gave). Assign roles per principal with
`TRACEBI_AUTH_ROLE_MAP=alice:admin,bob:analyst` or, **in proxy mode only**,
from the proxy's group claim with
`TRACEBI_AUTH_ROLE_HEADER=X-Forwarded-Groups` — your proxy must *replace*
that header on client requests, not append to it; TraceBi reads the last
occurrence, so an appending proxy still wins over a client copy, but a proxy
that does neither hands the role to the caller. Under Basic auth there is no
upstream, so the header would be self-asserted by the caller it promotes: it
is ignored there, with a startup warning. Unlisted principals get
`TRACEBI_AUTH_DEFAULT_ROLE` (default `viewer`), but it is not a role source on
its own: set by itself it names the fallback and leaves enforcement off, and
it switches enforcement on only alongside `TRACEBI_AUTH_ROLE_HEADER`. With *no
usable* role source set, every authenticated principal is `admin` — role
enforcement is opt-in so enabling auth cannot lock a deployment out of its own
pipelines.

**The MCP gateway authenticates separately.** `tracebi mcp --transport http`
is not behind the web app's auth — it requires its own bearer token
(`TRACEBI_MCP_TOKEN`; every request sends `Authorization: Bearer <token>`)
and refuses to start without one unless `--insecure` is passed explicitly.
With `TRACEBI_MCP_TOKEN`, `TRACEBI_OIDC_ISSUER` or the built-in sign-in set,
the web app also serves the gateway at `/mcp` ([[connect-chatgpt-and-claude]]).

## Deployment

```bash
# Bare uvicorn
uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker — multi-stage build compiles the React UI, then runs the API
docker compose up --build
```

> **More than one worker requires Postgres.** Each process gets its own
> in-process layer lock, so the lock that counts is the database one: on
> Postgres a `pg_try_advisory_lock` per layer refuses a concurrent run with a
> clear error, while on SQLite the cross-process lock is a no-op and two
> workers will both execute the same layer — interleaving writes to the sink
> and leaving two "running" rows in the run history. Point
> `TRACEBI_STATE_URL` (and any `PipelineRunner(db_url=...)` that keeps its own
> database) at Postgres, and share one `TRACEBI_SECRET_KEY`, before scaling
> past one process.


## Environment variable reference

| Variable | Default | Effect |
|---|---|---|
| `TRACEBI_APP` | *(none)* | App module imported at startup; `tracebi.web.demo_app` opts into the bundled demo |
| `TRACEBI_CONNECTIONS_DIR` | `connections` | Folder scanned for `<name>.yaml` sources |
| `TRACEBI_TRANSFORMS_DIR` | `transforms` | Folder of phase ① transforms |
| `TRACEBI_MODELS_DIR` | `models` | Folder scanned for model files (`.yaml`, `.json`, `.py`) |
| `TRACEBI_PIPELINES_DIR` | `pipelines` | Folder scanned for pipeline files (`.yaml`, `.py`) |
| `TRACEBI_REPORTS_DIR` | `reports` | Folder scanned for report packages and `.json` `ReportSpec`s (phase ③); all served in the app, in the library under each model |
| `TRACEBI_SCHEDULED_DIR` | `scheduled` | **Deprecated.** Still scanned if the folder exists. `@register.scheduled()` never ran anything; use a `"schedule"` block in `report.json` |
| `TRACEBI_DEV_MODE` | unset | `1` mounts `POST /api/_dev/reload` |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | unset | HTTP Basic auth |
| `TRACEBI_AUTH_PROXY_HEADER` / `TRACEBI_AUTH_PROXY_TRUSTED_IPS` | unset | Proxy-header auth |
| `TRACEBI_AUTH_REALM` | `TraceBi` | Basic-auth realm string |
| `TRACEBI_AUTH_ROLE_MAP` | unset | `principal:role` pairs (e.g. `alice:admin,bob:analyst`) |
| `TRACEBI_AUTH_ROLE_HEADER` | unset | Read roles from the proxy's group header (e.g. `X-Forwarded-Groups`) — proxy mode only; ignored under Basic auth |
| `TRACEBI_AUTH_DEFAULT_ROLE` | `viewer` | Role for principals not covered above. Not a role source by itself — set alone it leaves enforcement off and everyone `admin`; it switches enforcement on only alongside `TRACEBI_AUTH_ROLE_HEADER` |
| `TRACEBI_DOCS_DIR` | `docs` | Folder the Docs place (`/docs`) serves the handbook from |
| `TRACEBI_MCP_TOKEN` | unset | Bearer token for `tracebi mcp --transport http` (gateway, not the web app — required unless `--insecure`) |
| `TRACEBI_MCP_ACTOR` | `agent` | Audit attribution for gateway work (recorded as `mcp:<actor>`) |

Every variable, with sign-in, the state store and the credential store, is in
[[environment-variables]].
