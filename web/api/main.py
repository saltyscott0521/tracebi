"""
TraceBi Web API — FastAPI application.

Startup loads the app module (default: web.demo_app) which populates the
registry with connectors, models, reports, and pipeline runners. Set the
TRACEBI_APP environment variable to point at a different module.

    TRACEBI_APP=myproject.tracebi_config uvicorn web.api.main:app --reload
"""

import importlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.wsgi import WSGIMiddleware

from web.api.routers import connectors, models, reports, pipelines, dashboards

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

app.include_router(connectors.router, prefix="/api")
app.include_router(models.router,     prefix="/api")
app.include_router(reports.router,    prefix="/api")
app.include_router(pipelines.router,  prefix="/api")
app.include_router(dashboards.router, prefix="/api")


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


# ── Mount registered Dash dashboards ──────────────────────────────────────────

from web.api.registry import registry as _registry  # noqa: E402

for _dash_name, _dash_entry in _registry._dashboards.items():
    _prefix = f"/dashboards/{_dash_name}/"
    try:
        _dash_app = _dash_entry["server"].get_app(requests_pathname_prefix=_prefix)
        app.mount(_prefix, WSGIMiddleware(_dash_app.server))
    except ImportError:
        pass  # dash not installed — skip silently


# ── Serve built React UI (production) ──────────────────────────────────────

_ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")

if os.path.isdir(_ui_dist):
    app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")
