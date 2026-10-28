# Customize the web app

Point the web server at your own workspace, add resources in code when files
are not enough, restyle or extend the React UI, and deploy it.

## Before you begin

- A TraceBi workspace (`tracebi init`), or the reference workspace
- `pip install -e ".[all]"`, and Node.js 22 for UI work

The server is a FastAPI app (`tracebi/web/api/main.py`). It serves a JSON API
under `/api` and the built React app (`tracebi/web/ui/dist/`) at `/`. Every
route reads connectors, models, reports and pipelines from one shared registry
(`tracebi/registry.py`), which is filled at startup:

```
your workspace folders ──discovery──▶ registry ◀──reads── API routes ◀── React UI
your app module      ──registers──▶ (shared)            (request time)
```

## 1. Add resources as files

The server finds these folders at the workspace root, and picks up changes
while it runs:

| Folder | File | Appears in the app as |
|---|---|---|
| `connections/` | `<name>.yaml`: a type and its fields, secrets as `${NAME}` ([[connections-yaml]]) | **Data → Sources**, and a card in the map's first lane. Secrets resolve only when used. |
| `transforms/` | `<name>.sql` (with its `.contract.yaml`), `.py` or `.ipynb` | **Data → Transforms**. Runs only when a pipeline or `tracebi run-transform` asks. |
| `models/` | `<name>.yaml` or `.json`; a `.py` with a `model` variable | The model's **Data** page and **Ask** |
| `pipelines/` | `<name>.yaml`; a `.py` with a `runner` variable | The model's **Transform** tab |
| `reports/` | A `<name>/` package (`report.json` plus `app.jsx` or `template.html`), or a `.json` spec compiled into one (a package beats a spec of the same name) | **Reports**, under its model |

Scaffold them with the CLI:

```bash
tracebi connect crm --kind postgres  # connections/crm.yaml (secret to .env, or --store secret)
tracebi new-transform "Sales"        # transforms/sales.sql + sales.contract.yaml
tracebi new-model "Sales Model"      # models/sales_model.yaml
tracebi new-pipeline "Sales ETL"     # pipelines/sales_etl.yaml
tracebi new-dashboard "Weekly"       # reports/weekly/ (report.json + app.jsx)
tracebi new-report "Weekly Report"   # reports/weekly_report/ (report.json + template.html)
```

Set `TRACEBI_CONNECTIONS_DIR`, `TRACEBI_TRANSFORMS_DIR`, `TRACEBI_MODELS_DIR`,
`TRACEBI_PIPELINES_DIR` or `TRACEBI_REPORTS_DIR` to move a folder. Scripts and
notebooks read the same folders without a server:

```python
from tracebi.model_registry import get_model
from tracebi.pipeline_registry import get_runner

model = get_model("sales_model")
runner = get_runner("sales_etl")
```

A `.py` in `reports/` that registers a report with `@register.report(...)` is
still imported at startup, but a report with no package is refused (HTTP 422
naming the fix). The package is the only renderer.

## 2. Add resources in code (optional)

Most workspaces need no code. Use an app module for wiring the files cannot
express, such as a connector type of your own or medallion layers built in
Python. The bundled demo app (`tracebi/web/demo_app/`) is the example:

```
myapp/
  __init__.py        # imports registry (one line)
  model.py           # connectors and a DataModel (optional if you use models/)
  pipeline.py        # PipelineRunner and layers (optional if you use pipelines/)
  registry.py        # the registration calls
```

```python
# myapp/registry.py
import os
from tracebi.registry import registry
from myapp.model import connector, model

registry.add_connector(connector)
registry.add_model(model, default=True)
```

```bash
TRACEBI_APP=myapp python -m tracebi.web.run
```

| Resource | Call | Appears as |
|---|---|---|
| Connector | `registry.add_connector(conn)` | **Data → Sources** |
| Model | `registry.add_model(model, default=False)` | The model's **Data** page and **Ask** |
| Report | `@registry.report("name", description="…")` on a zero-argument factory, with a package to render it | **Reports** |
| Pipeline | `registry.add_pipeline("name", runner)` | The model's **Transform** tab: steps, run buttons, a live log, history |
| Scheduled report | Deprecated: `@registry.scheduled(...)` warns and only registers. Use a `"schedule"` block in `report.json`. | **Reports** |

Rules for an app module:

- Register everything at import time. Never change the registry inside a
  route handler.
- Build connectors in your module and pass credential-bearing URLs from
  `os.environ[...]` yourself. TraceBi never reads a connector URL from the
  environment on its own. See `.env.example`.

`TRACEBI_APP` defaults to none. `TRACEBI_APP=tracebi.web.demo_app` serves the
bundled demo. If the module fails to import, the server logs a `UserWarning`
and starts with an empty registry, and `/api/health` still returns 200, so
check the startup log. A `TRACEBI_APP` that still names the old top-level
`web` package (`web.demo_app`) is refused with the new spelling.

## 3. Run the development server

```bash
python -m tracebi.web.run                       # hot reload, port 8000
python -m tracebi.web.run --port 9000
TRACEBI_DEV_MODE=1 python -m tracebi.web.run    # adds POST /api/_dev/reload
```

Hot reload restarts the server when a Python file changes. Dev mode adds
`POST /api/_dev/reload`, which re-imports discovered Python modules without a
restart. Packages, specs, YAML models and pipelines need neither: discovery
picks them up every `TRACEBI_DISCOVERY_INTERVAL` seconds.

## 4. Change the React UI

```bash
cd web/ui
npm install
npm run dev      # Vite on :5173, proxies /api to the API server
npm run build    # writes tracebi/web/ui/dist/, which FastAPI serves at /
```

The UI is React 18 and Vite, with React Query for data, React Flow for graphs
and its own SVG charts (`components/AnswerChart.jsx`, d3 for the scales). In
`web/ui/src/`:

```
api.js               one React Query hook per endpoint
nav.js               the four places, Data's folders, their addresses, movedTo for old addresses
folders.js           the library's folders: order and a hue per folder
components/
  Layout.jsx         sidebar, theme toggle, ⌘K
  Scope.jsx          page header, one-model routes, redirects from old addresses
  Shared.jsx         Card, Badge, Btn, Tabs, toasts, skeletons
  Lineage.jsx        the lineage graph
  CommandPalette.jsx ⌘K navigation
pages/               one file per route
styles/global.css    every design token
```

**Restyle it.** Every colour is a CSS variable at the top of
`styles/global.css`: light under `:root`, dark under `[data-theme="dark"]`.
Edit the tokens (`--blue`, `--bg`, `--card`, the `--op-*` lineage palette);
components never hard-code colours. The brand gradient is `--brand`.

**Add a page.** The sidebar has four places, `PAGES` in `nav.js`: Reports
`/`, Data `/data`, Review `/review` and Docs `/docs` (Ask, `/ask`, is a page
inside Reports). Data's folders are `DATA_FOLDERS`: its home (`/data`
itself, a status board, `pages/DataHome.jsx`), Lineage (`/data/lineage`,
the map, `pages/Map.jsx` over `GET /api/graph`), then Sources, Transforms,
Warehouse and Models, nested under Data in the sidebar (`SIDEBAR_FOLDERS`).
Every list under Data is a `ResourceTable` and every thing's page a
`ResourcePage` (`components/`), so a new kind of resource gets the same
columns, status pills (`statusWords` in `words.js`), actions and tabs.

1. Give the page a route in `App.jsx` under its place's address.
2. Teach `whereAmI` in `nav.js` which place it belongs to, so the sidebar
   marks it current.
3. Pass a model as a filter (`?model=<name>`), or on Data as the path of
   its page (`modelPath`: `/data/models/<model>`). Under Data, wrap the page
   in `DataFrame` (`pages/Data.jsx`): a folder's name as its h1, or a
   breadcrumb for one thing's page.
4. When an address moves, add it to `movedTo` so old links keep working.
5. Use the hooks in `api.js` for data and the parts in `Shared.jsx` for the
   look.

A model's page is `pages/Overview.jsx`, a `ResourcePage` whose Schema tab is
the data browser. The model page and Data's Warehouse (its Schema view) are one
component, `components/DataBrowser.jsx`, fed by `modelSchema` or
`warehouseSchema` in `components/modelGraph.js`.

## 5. Add an API route

1. Add a file under `tracebi/web/api/routers/`.
2. Include it in `main.py` with the `/api` prefix.
3. Read resources only from the registry. Never import your app module.
4. Return failures in the structured shape `{message, exception_type,
   traceback}` through `tracebi/web/api/errors.py`; the UI renders it.

## Turn on sign-in and roles

Sign-in is off until you set variables (see `tracebi/web/api/auth.py` and
`.env.example`):

```bash
# Basic auth: one shared credential
TRACEBI_AUTH_USER=admin
TRACEBI_AUTH_PASS=changeme

# Or trust a reverse proxy's header (Authelia, oauth2-proxy, Cloudflare Access)
TRACEBI_AUTH_PROXY_HEADER=X-Forwarded-User
TRACEBI_AUTH_PROXY_TRUSTED_IPS=10.0.0.0/8,172.16.0.0/12

# Or the app's own sign-in through your identity provider
TRACEBI_OIDC_ISSUER=https://login.example.com
```

With none set, the app is open: fine on localhost, not on a network. OIDC
sign-in and named local users (`TRACEBI_LOCAL_USERS`) are in [[sign-in]].
Folder permissions narrow what a role allows, per folder ([[folder-yaml]]).

Three roles, ordered by what they change:

| Role | May |
|---|---|
| `viewer` | Read models, reports and lineage. Run Ask queries and spec validation, which compute but save nothing. |
| `analyst` | Viewer, plus run reports and request code. |
| `admin` | Analyst, plus run pipeline layers (they write the warehouse), `/api/_dev/reload`, keep a selection cut (it writes the published `report.json`), approve code requests, and set a connection's credential (which also needs a role from a sign-in or a role source). |

Assign roles with `TRACEBI_AUTH_ROLE_MAP=alice:admin,bob:analyst`, or, in
proxy mode only, from the proxy's group header with
`TRACEBI_AUTH_ROLE_HEADER=X-Forwarded-Groups`.

- The proxy must replace that header on client requests. TraceBi reads the
  last copy, so an appending proxy still wins, but a proxy that does neither
  hands the role to the caller.
- Under Basic auth the header is ignored, with a startup warning: with no
  proxy, the caller would set its own role.
- People not in the map get `TRACEBI_AUTH_DEFAULT_ROLE` (default `viewer`).
  That variable alone does not turn enforcement on; it does so only with
  `TRACEBI_AUTH_ROLE_HEADER`.
- With no role source at all, every signed-in person is `admin`. Turning on
  sign-in can never shut a deployment out of its own pipelines.

The MCP gateway signs in separately. `tracebi mcp --transport http` needs its
own bearer token (`TRACEBI_MCP_TOKEN`; each request sends
`Authorization: Bearer <token>`) and refuses to start without one unless you
pass `--insecure`. With `TRACEBI_MCP_TOKEN`, `TRACEBI_OIDC_ISSUER` or the
built-in sign-in set, the web app also serves the gateway at `/mcp`
([[connect-chatgpt-and-claude]]).

## Deploy

```bash
# uvicorn
uvicorn tracebi.web.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker: builds the React UI, then runs the API
docker compose up --build
```

More than one worker needs Postgres. Each process has its own layer lock, so
the lock that counts is the database's. On Postgres, a `pg_try_advisory_lock`
per layer refuses a second run with a clear error. On SQLite that lock does
nothing, so two workers would both run the same layer, interleave writes to
the sink and leave two "running" rows in the history. Before running more
than one process, point `TRACEBI_STATE_URL` (and any
`PipelineRunner(db_url=...)` with its own database) at Postgres, and share one
`TRACEBI_SECRET_KEY`.

## Next

- Every variable the server reads: [[environment-variables]]
- Every route: [[api-routes]]
