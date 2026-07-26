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
    TRACEBI_DEV_MODE=1          — mount /_dev/reload
    TRACEBI_AUTH_USER / _PASS   — enable HTTP Basic auth
    TRACEBI_AUTH_PROXY_HEADER   — enable proxy header-trust auth
"""

import importlib
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.api.errors import error_detail

from web.api.routers import connectors, models, reports, pipelines, requests, docs
from web.api.auth import install_if_configured as _install_auth

from tracebi._version import get_version as _tracebi_version

app = FastAPI(
    title="TraceBi API",
    description="Code-first, traceable BI — REST interface to your TraceBi data layer.",
    version=_tracebi_version(),
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
app.include_router(docs.router,       prefix="/api")

# Dev-mode reload endpoint — opt-in via TRACEBI_DEV_MODE=1.
if os.environ.get("TRACEBI_DEV_MODE") == "1":
    from web.api.routers import dev
    app.include_router(dev.router, prefix="/api")
    print("[tracebi] dev mode: /api/_dev/reload mounted")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/discovery")
def discovery():
    """
    What happened to every file auto-discovery looked at: registered,
    skipped (and why), or failed (with the error).

    Discovery is convention-based and quiet — a file in the wrong place or
    one that raises on import simply never appears. This answers "why isn't
    my report showing up?" without reading the server's stderr.
    """
    from tracebi.web.discovery import discovery_report

    entries = discovery_report()
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"summary": counts, "entries": entries}


@app.get("/api/spec/schema")
def spec_schema():
    """JSON Schema for a report spec, generated from the section dataclasses."""
    from tracebi.spec import json_schema
    return json_schema()


@app.post("/api/spec/validate")
def spec_validate(body: dict):
    """
    Check a report spec without executing it.

    Validates section types, field names, enum values, and — against the
    registered models — that each referenced model, fact, measure and
    dimension exists. Returns field-scoped errors like
    ``sections[2].data.query.fact``, so an author can fix the spec before
    anything runs.
    """
    from tracebi.spec import ReportSpec

    try:
        spec = ReportSpec.from_dict(body)
    except Exception as exc:  # noqa: BLE001 — a malformed spec is a 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = spec.validate(_registered_models())
    result["data_coverage"] = spec.data_coverage()
    return result


@app.post("/api/spec/render")
def spec_render(body: dict):
    """Build a report spec against the registered models and render it to HTML."""
    from tracebi.reports.html_renderer import HTMLRenderer
    from tracebi.spec import ReportSpec

    try:
        spec = ReportSpec.from_dict(body)
        report = spec.build(_registered_models())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=error_detail("Spec render failed", exc)
        ) from exc

    manifest = report.build_manifest(format="html", output_path="(in-memory)")
    return {"html": HTMLRenderer().to_html(report), "manifest": manifest.to_dict()}


def _registered_models() -> dict:
    """Registered models keyed by name, for spec validation and building."""
    from web.api.registry import registry as _reg
    return {m["name"]: _reg.get_model(m["name"]) for m in _reg.list_models()}


@app.get("/api/schema")
def schema():
    """
    The framework's vocabulary as data: every report section with its
    fields, types, defaults and allowed values, the DataSet
    verbs, measure kinds, filter operators, and the discovery conventions.

    Generated from the code rather than hand-maintained, so it stays
    correct. Intended for tools — an agent authoring a project, an editor
    completing a constructor, or a UI building a form.
    """
    from tracebi.capabilities import describe
    return describe()


# ── Load app module ────────────────────────────────────────────────────────

# An app module wires up connectors, which cannot be
# expressed as a file convention. Set TRACEBI_APP="" to skip it entirely —
# a project that only uses the models/ pipelines/ reports/ requests/
# directories needs no app module, and loading the bundled demo into
# someone else's project would fail on data they do not have.
_app_module = os.environ.get("TRACEBI_APP", "web.demo_app").strip()

if _app_module:
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
