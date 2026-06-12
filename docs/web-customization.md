# Customizing the TraceBi Web App

How to point the web server at your own data, add your own reports and
dashboards, restyle or extend the React UI, and deploy. Written for the
person who has outgrown the demo app.

---

## Architecture in one paragraph

The web layer is a FastAPI app ([web/api/main.py](../web/api/main.py)) that
serves a JSON API under `/api`, mounts Dash dashboards as WSGI sub-apps
under `/dashboards/{name}/`, and serves the built React SPA
(`web/ui/dist/`) at `/`. Everything the API exposes — connectors, models,
reports, pipelines, dashboards — is read from a **singleton registry**
([web/api/registry.py](../web/api/registry.py)) that your *app module*
populates once at startup. Routes never construct resources themselves;
they only read the registry. That seam is what makes the whole web layer
swappable onto your data.

```
your app module ──populates──▶ registry ◀──reads── API routes ◀── React UI
(import time)                 (singleton)          (request time)
```

## Step 1: Create your app module

An app module is any importable Python module that registers resources at
import time. The demo ([web/demo_app/](../web/demo_app/)) is the reference —
copy its layout:

```
myapp/
  __init__.py        # imports registry module (one line, like demo_app)
  model.py           # connectors + DataModel construction
  pipeline.py        # PipelineRunner + layer registration (optional)
  dashboard.py       # Dash dashboard server (optional)
  registry.py        # THE wiring file — all register calls live here
  reports/           # auto-discovered report factories, one per file
```

`registry.py` is the only file with registration side effects:

```python
import os
from web.api.registry import registry
from myapp.model import connector, model
from tracebi.web.discovery import auto_discover

registry.add_connector(connector)
registry.add_model(model, default=True)     # default ⇒ used by request scripts

# Reports: each file in reports/ with a @registry.report(...) factory
auto_discover(os.path.join(os.path.dirname(__file__), "reports"))
```

Then point the server at it:

```bash
TRACEBI_APP=myapp python web/run.py
```

`TRACEBI_APP` defaults to `web.demo_app`. Import failure is fatal and loud —
a broken app module never half-starts.

**Rules that keep you out of trouble** (enforced by convention, violated at
your peril):

- Register everything at import time; never mutate the registry inside a
  route handler.
- Construct connectors in your app module and pass credential-bearing URLs
  via `os.environ[...]` explicitly. The framework never reads connector
  URLs from env vars implicitly. See [.env.example](../.env.example).

## Step 2: Add resources

All registration goes through the registry (or its notebook-friendly facade
`tracebi.web.register`, same methods minus the `add_` prefix):

| Resource | Call | Appears in UI as |
|---|---|---|
| Connector | `registry.add_connector(conn)` | **Connectors** page |
| Model | `registry.add_model(model, default=False)` | **Models** + **Explore** |
| Report | `@registry.report("name", description="…")` on a factory returning a `Report` | **Reports** page |
| Scheduled report | `@registry.scheduled("name", cron="0 7 * * *")` | **Reports** + scheduler metadata |
| Dashboard | `registry.add_dashboard("name", dash_server, description="…")` | **Dashboards** page + `/dashboards/name/` |
| Pipeline | `registry.add_pipeline("name", runner)` | **Pipelines** page (DAG, run buttons, history) |

Ad-hoc request scripts need no registration at all: any `.py` or `.ipynb`
in the requests directory (`TRACEBI_REQUESTS_DIR`, default `requests/`)
appears on the **Requests** page automatically — see the
[Analyst Guide](analyst-guide.md).

## Step 3: The development loop

```bash
python web/run.py                       # uvicorn with hot-reload, port 8000
python web/run.py --port 9000           # different port
TRACEBI_DEV_MODE=1 python web/run.py    # adds POST /api/_dev/reload
```

Hot-reload restarts the server on Python file changes. Dev mode additionally
mounts `POST /api/_dev/reload`, which re-imports auto-discovered request
modules *without* a restart — useful when iterating on report factories.

For UI work, run Vite's dev server alongside the API (see below).

## Step 4: Customize the React UI

The UI lives in [web/ui/](../web/ui/) — React 18 + Vite, React Query for
data, React Flow for lineage/ERD graphs, Recharts for charts.

```bash
cd web/ui
npm install
npm run dev      # Vite dev server on :5173, proxies /api to the API server
npm run build    # writes web/ui/dist/ — FastAPI serves it at / when present
```

Layout of `src/`:

```
api.js               # all API hooks (React Query) — one hook per endpoint
components/
  Layout.jsx         # sidebar, nav items, theme toggle, ⌘K trigger
  Shared.jsx         # Card, Badge, Btn, Tabs, toasts, skeletons…
  Lineage.jsx        # React Flow lineage graph renderer
  CommandPalette.jsx # ⌘K navigation
pages/               # one file per route
styles/global.css    # ALL design tokens — start here for theming
```

**Theming:** every color in the UI is a CSS variable defined at the top of
[global.css](../web/ui/src/styles/global.css). Light theme under `:root`,
dark under `[data-theme="dark"]`. To rebrand, edit the tokens (`--blue`,
`--bg`, `--card`, the `--op-*` lineage-node palette) — components never
hard-code colors. The brand gradient is `--brand`.

**Adding a nav page:** create `pages/MyPage.jsx`, add a route in
`App.jsx`, and an entry in the `NAV` array in `Layout.jsx`. Use the hooks
in `api.js` for data and the primitives in `Shared.jsx` for visual
consistency.

## Step 5: Extend the API

New endpoints follow one pattern: a router file under
[web/api/routers/](../web/api/routers/), included in `main.py` with the
`/api` prefix, reading **only from the registry** — never importing your
app module directly. Failed runs should return the structured error shape
(`{message, exception_type, traceback}`) via `web/api/errors.py`; the UI
knows how to render it.

## Auth

Optional, enabled entirely by env vars (see
[web/api/auth.py](../web/api/auth.py) and `.env.example`):

```bash
# Basic auth — single shared credential
TRACEBI_AUTH_USER=admin
TRACEBI_AUTH_PASS=changeme

# OR reverse-proxy header trust (Authelia, oauth2-proxy, Cloudflare Access)
TRACEBI_AUTH_PROXY_HEADER=X-Forwarded-User
TRACEBI_AUTH_PROXY_TRUSTED_IPS=10.0.0.0/8,172.16.0.0/12
```

No auth vars set ⇒ the app is open (fine on localhost, not on a network).

## Deployment

```bash
# Bare uvicorn
uvicorn web.api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker — multi-stage build compiles the React UI, then runs the API
docker compose up --build
```

Set `TRACEBI_EMBED_DASHBOARDS=0` to skip the in-process Dash WSGI mounts
and run dashboards as separate services instead — useful with multiple
uvicorn workers, since Dash apps hold in-process state.

## Environment variable reference

| Variable | Default | Effect |
|---|---|---|
| `TRACEBI_APP` | `web.demo_app` | App module imported at startup |
| `TRACEBI_REQUESTS_DIR` | `requests` | Folder scanned for request scripts |
| `TRACEBI_DEV_MODE` | unset | `1` mounts `POST /api/_dev/reload` |
| `TRACEBI_EMBED_DASHBOARDS` | `1` | `0` skips Dash WSGI mounts |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | unset | HTTP Basic auth |
| `TRACEBI_AUTH_PROXY_HEADER` / `TRACEBI_AUTH_PROXY_TRUSTED_IPS` | unset | Proxy-header auth |
| `TRACEBI_AUTH_REALM` | `TraceBi` | Basic-auth realm string |
