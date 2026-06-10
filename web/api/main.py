"""
TraceBi Web API — FastAPI application.

Startup loads the app module (default: web.demo_app) which populates the
registry with connectors, models, reports, and pipeline runners. Set the
TRACEBI_APP environment variable to point at a different module.

    TRACEBI_APP=myproject.tracebi_config uvicorn web.api.main:app --reload

Environment switches:
    TRACEBI_APP                 — app module to import (default: web.demo_app)
    TRACEBI_REQUESTS_DIR        — folder scanned for request scripts (default: requests)
    TRACEBI_DEV_MODE=1          — mount /_dev/reload + /_dev/discovered
    TRACEBI_EMBED_DASHBOARDS=0  — skip the WSGI mount; run dashboards as a
                                  separate process via DashboardServer.run()
    TRACEBI_AUTH_USER / _PASS   — enable HTTP Basic auth
    TRACEBI_AUTH_PROXY_HEADER   — enable proxy header-trust auth
"""

import importlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware

from web.api.routers import connectors, models, reports, pipelines, dashboards
from web.api.auth import install_if_configured as _install_auth

app = FastAPI(
    title="TraceBi API",
    description="Code-first, traceable BI — REST interface to your TraceBi data layer.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # CRA / alternate dev port
        "http://localhost:8000",   # same-origin (prod static serving)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional auth — Basic or reverse-proxy header trust, depending on env.
_auth_mode = _install_auth(app)
if _auth_mode:
    print(f"[tracebi] auth mode: {_auth_mode}")
else:
    print(
        "[tracebi] WARNING: no auth configured — the API (including pipeline "
        "run endpoints) is open to anyone who can reach this server. Set "
        "TRACEBI_AUTH_USER/TRACEBI_AUTH_PASS or TRACEBI_AUTH_PROXY_HEADER "
        "before exposing it beyond localhost."
    )

app.include_router(connectors.router, prefix="/api")
app.include_router(models.router,     prefix="/api")
app.include_router(reports.router,    prefix="/api")
app.include_router(pipelines.router,  prefix="/api")
app.include_router(dashboards.router, prefix="/api")

# Dev-mode reload endpoint — opt-in via TRACEBI_DEV_MODE=1.
if os.environ.get("TRACEBI_DEV_MODE") == "1":
    from web.api.routers import dev
    app.include_router(dev.router, prefix="/api")
    print("[tracebi] dev mode: /api/_dev/reload mounted")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Load app module ────────────────────────────────────────────────────────

_app_module = os.environ.get("TRACEBI_APP", "web.demo_app")

try:
    importlib.import_module(_app_module)
except ImportError as exc:
    import warnings
    warnings.warn(
        f"TRACEBI_APP module '{_app_module}' could not be imported: {exc}. "
        "The API will start with an empty registry.",
        stacklevel=1,
    )

# Folder-based auto-discovery — scan requests/ and scheduled/ (or whatever
# TRACEBI_REQUESTS_DIR / TRACEBI_SCHEDULED_DIR point to). Both fire registry
# decorators as a side effect of import.
for _env, _default in (
    ("TRACEBI_REQUESTS_DIR", "requests"),
    ("TRACEBI_SCHEDULED_DIR", "scheduled"),
):
    _dir = os.environ.get(_env, _default)
    if os.path.isdir(_dir):
        from tracebi.web.discovery import auto_discover as _auto_discover
        _discovered = _auto_discover(_dir)
        if _discovered:
            print(f"[tracebi] auto-discovered {len(_discovered)} module(s) "
                  f"from {_dir}")


# ── Mount registered Dash dashboards ──────────────────────────────────────────

from web.api.registry import registry as _registry  # noqa: E402

_embed_dashboards = os.environ.get("TRACEBI_EMBED_DASHBOARDS", "1") != "0"
if _embed_dashboards:
    for _dash_name, _dash_entry in _registry._dashboards.items():
        _prefix = f"/dashboards/{_dash_name}/"
        try:
            _dash_app = _dash_entry["server"].get_app(requests_pathname_prefix=_prefix)
            app.mount(_prefix, WSGIMiddleware(_dash_app.server))
        except ImportError:
            pass  # dash not installed — skip silently
else:
    if _registry._dashboards:
        print(
            f"[tracebi] TRACEBI_EMBED_DASHBOARDS=0 — {len(_registry._dashboards)} "
            f"dashboard(s) registered but not mounted. Run them standalone "
            f"with DashboardServer.run() in a separate process."
        )


# ── Serve built React UI (production) ──────────────────────────────────────

_ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")

if os.path.isdir(_ui_dist):
    from starlette.exceptions import HTTPException as _StarletteHTTPException

    class _SPAFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except _StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", _SPAFiles(directory=_ui_dist, html=True), name="ui")
