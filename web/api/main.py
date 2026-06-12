"""
TraceBi Web API — FastAPI application.

Startup loads the app module (default: web.demo_app) which populates the
registry with connectors, models, reports, and pipeline runners. Set the
TRACEBI_APP environment variable to point at a different module.

    TRACEBI_APP=myproject.tracebi_config uvicorn web.api.main:app --reload

Project-root directories are also auto-discovered at startup so you can define
artifacts outside of the app module package:

    models/       DataModel definitions (each file exposes a ``model`` variable)
    pipelines/    PipelineRunner definitions (each file exposes a ``runner`` variable)
    reports/      Named report factories (use @register.report() decorator)
    requests/     Ad-hoc report scripts with request_params() and run()
    scheduled/    Scheduled report scripts

Environment switches:
    TRACEBI_APP                 — app module to import (default: web.demo_app)
    TRACEBI_MODELS_DIR          — model definitions folder (default: models)
    TRACEBI_PIPELINES_DIR       — pipeline definitions folder (default: pipelines)
    TRACEBI_REPORTS_DIR         — named reports folder (default: reports)
    TRACEBI_REQUESTS_DIR        — request scripts folder (default: requests)
    TRACEBI_SCHEDULED_DIR       — scheduled scripts folder (default: scheduled)
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

from web.api.routers import connectors, models, reports, pipelines, dashboards, requests, docs
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
app.include_router(requests.router,   prefix="/api")
app.include_router(pipelines.router,  prefix="/api")
app.include_router(dashboards.router, prefix="/api")
app.include_router(docs.router,       prefix="/api")

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

# Folder-based auto-discovery — decorator-based artifacts fire registry side
# effects on import (reports use @register.report, requests expose run()).
for _env, _default in (
    ("TRACEBI_REQUESTS_DIR",  "requests"),
    ("TRACEBI_SCHEDULED_DIR", "scheduled"),
    ("TRACEBI_REPORTS_DIR",   "reports"),
):
    _dir = os.environ.get(_env, _default)
    if os.path.isdir(_dir):
        from tracebi.web.discovery import auto_discover as _auto_discover
        _discovered = _auto_discover(_dir)
        if _discovered:
            print(f"[tracebi] auto-discovered {len(_discovered)} module(s) "
                  f"from {_dir}")

# Models discovery — each models/<name>.py exposes a `model` variable.
_models_dir = os.environ.get("TRACEBI_MODELS_DIR", "models")
if os.path.isdir(_models_dir):
    from tracebi import model_registry as _model_reg
    _disc_models = _model_reg.auto_discover(_models_dir)
    for _mname in _disc_models:
        try:
            _m = _model_reg.get_model(_mname)
            from web.api.registry import registry as _registry_ref
            if _mname not in [t["name"] for t in _registry_ref.list_models()]:
                _registry_ref.add_model(_m)
        except Exception as _exc:
            import warnings
            warnings.warn(f"[tracebi] model '{_mname}' failed to load: {_exc}")
    if _disc_models:
        print(f"[tracebi] auto-discovered {len(_disc_models)} model(s) from {_models_dir}")

# Pipelines discovery — each pipelines/<name>.py exposes a `runner` variable.
_pipelines_dir = os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines")
if os.path.isdir(_pipelines_dir):
    from tracebi import pipeline_registry as _pipe_reg
    _disc_pipes = _pipe_reg.auto_discover(_pipelines_dir)
    for _pname in _disc_pipes:
        try:
            _pr = _pipe_reg.get_runner(_pname)
            from web.api.registry import registry as _registry_ref
            if _pname not in _registry_ref.list_pipeline_names():
                _registry_ref.add_pipeline(_pname, _pr)
        except Exception as _exc:
            import warnings
            warnings.warn(f"[tracebi] pipeline '{_pname}' failed to load: {_exc}")
    if _disc_pipes:
        print(f"[tracebi] auto-discovered {len(_disc_pipes)} pipeline(s) from {_pipelines_dir}")


# ── Mount registered Dash dashboards ──────────────────────────────────────────

from web.api.registry import registry as _registry  # noqa: E402

_embed_dashboards = os.environ.get("TRACEBI_EMBED_DASHBOARDS", "1") != "0"
if _embed_dashboards:
    for _dash_name, _dash_entry in _registry.dashboards().items():
        _prefix = f"/dashboards/{_dash_name}/"
        try:
            _dash_app = _dash_entry["server"].get_app(requests_pathname_prefix=_prefix)
            app.mount(_prefix, WSGIMiddleware(_dash_app.server))
        except ImportError:
            pass  # dash not installed — skip silently
else:
    if _registry.dashboards():
        print(
            f"[tracebi] TRACEBI_EMBED_DASHBOARDS=0 — {len(_registry.dashboards())} "
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
