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

from web.api.routers import connectors, models, reports, pipelines, ui

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
app.include_router(ui.router)


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


# ── Serve built React UI (production) ──────────────────────────────────────

_ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")

if os.path.isdir(_ui_dist):
    app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")
