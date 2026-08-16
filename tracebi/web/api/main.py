"""
TraceBi Web API — FastAPI application.

Startup loads the app module, if one is named, which populates the
registry with connectors, models, reports, and pipeline runners. Set the
TRACEBI_APP environment variable to point at a different module.

    TRACEBI_APP=myproject.tracebi_config uvicorn tracebi.web.api.main:app --reload

Project-root directories are also auto-discovered at startup so you can define
artifacts outside of the app module package:

    models/       DataModel definitions (each file exposes a ``model`` variable)
    pipelines/    PipelineRunner definitions (each file exposes a ``runner`` variable)
    reports/      Named report factories (use @register.report() decorator)
    requests/     Ad-hoc report scripts with request_params() and run()
    scheduled/    Scheduled report scripts

Environment switches:
    TRACEBI_APP                 — app module to import (default: none; set
                                  tracebi.web.demo_app for the bundled demo)
    TRACEBI_MODELS_DIR          — model definitions folder (default: models)
    TRACEBI_PIPELINES_DIR       — pipeline definitions folder (default: pipelines)
    TRACEBI_REPORTS_DIR         — reports folder: specs, packages, factories (default: reports)
    TRACEBI_REQUESTS_DIR        — request scripts folder (default: requests)
    TRACEBI_SCHEDULED_DIR       — scheduled scripts folder (default: scheduled)
    TRACEBI_DEV_MODE=1          — mount /_dev/reload
    TRACEBI_AUTH_USER / _PASS   — enable HTTP Basic auth
    TRACEBI_AUTH_PROXY_HEADER   — enable proxy header-trust auth
"""

import importlib
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tracebi.web.api.errors import error_detail

from tracebi.web.api.routers import connectors, models, reports, pipelines, requests, docs
from tracebi.web.api.auth import install_if_configured as _install_auth

from tracebi._version import get_version as _tracebi_version

app = FastAPI(
    title="TraceBi API",
    description=("The trust layer for AI-generated analytics: a code-first BI "
                 "framework where every number has a receipt."),
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
    from tracebi.web.api.routers import dev
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
    return {"html": HTMLRenderer.for_project().to_html(report), "manifest": manifest.to_dict()}


def _registered_models() -> dict:
    """Registered models keyed by name, for spec validation and building."""
    from tracebi.web.api.registry import registry as _reg
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
# expressed as a file convention. The default is no app module: a project
# that only uses the models/ pipelines/ reports/ requests/ directories needs
# none, and a serve should show *your* project, not the bundled demo. Opt
# into the demo explicitly with TRACEBI_APP=tracebi.web.demo_app (it is
# self-contained and runs from any working directory).
_app_module = os.environ.get("TRACEBI_APP", "").strip()

if _app_module:
    # Checked *before* importing, not in the handler below, because the legacy
    # spelling may still import and do nothing: `git pull` leaves the old
    # web/api and web/demo_app directories behind whenever an untracked file
    # (a stale __pycache__) is in them, and a directory with no modules is a
    # perfectly importable namespace package. That registers nothing, raises
    # nothing, and boots a server that passes every healthcheck with an empty
    # registry — so refuse the spelling itself rather than waiting to fail.
    if _app_module == "web" or _app_module.startswith("web."):
        raise ImportError(
            f"TRACEBI_APP={_app_module!r} predates the namespace move: the web "
            f"app now ships inside the tracebi package. Use "
            f"'tracebi.{_app_module}' (e.g. TRACEBI_APP=tracebi.web.demo_app). "
            f"If you upgraded in place, delete any leftover top-level "
            f"web/api and web/demo_app directories too."
        )
    try:
        importlib.import_module(_app_module)
    except Exception as exc:
        # Deliberately broad: an app module can fail with anything (a KeyError
        # from a missing model, say), and a broken app module must start the
        # server empty with a warning rather than crash it.
        import warnings
        warnings.warn(
            f"TRACEBI_APP module '{_app_module}' could not be imported: {exc}. "
            "The API will start with an empty registry.",
            stacklevel=1,
        )

# Folder-based auto-discovery — decorator-based artifacts fire registry side
# effects on import (reports use @register.report, requests expose run()).
for _env, _default in (
    ("TRACEBI_REQUESTS_DIR",   "requests"),
    ("TRACEBI_SCHEDULED_DIR",  "scheduled"),
    ("TRACEBI_REPORTS_DIR",    "reports"),
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
            from tracebi.web.api.registry import registry as _registry_ref
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
            from tracebi.web.api.registry import registry as _registry_ref
            if _pname not in _registry_ref.list_pipeline_names():
                _registry_ref.add_pipeline(_pname, _pr)
        except Exception as _exc:
            import warnings
            warnings.warn(f"[tracebi] pipeline '{_pname}' failed to load: {_exc}")
    if _disc_pipes:
        print(f"[tracebi] auto-discovered {len(_disc_pipes)} pipeline(s) from {_pipelines_dir}")


# ── Serve built React UI (production) ──────────────────────────────────────

# tracebi/web/ui/dist — inside the installed package, which is why the wheel
# can carry the bundle at all. The Node workspace stays at the repo root
# (web/ui/) and vite's build.outDir writes here.
_ui_dist = os.path.join(os.path.dirname(__file__), "..", "ui", "dist")

# The bundle is index.html, not the directory: `npm run build` empties dist
# before it writes (vite's emptyOutDir), so a build that fails leaves the
# directory there and nothing in it. Mounting that serves the bare 404 this
# branch exists to prevent.
if os.path.isfile(os.path.join(_ui_dist, "index.html")):
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
else:
    # tracebi/web/ui/dist is gitignored, so a fresh clone has no bundle. Without this
    # branch "/" is a bare 404 and nothing says why — say why instead.
    from fastapi import Request as _Request
    from fastapi.responses import HTMLResponse as _HTMLResponse, JSONResponse as _JSONResponse

    # The remedy depends on which tree we are running from. A checkout can
    # build the bundle; an installed package cannot — telling someone to run
    # npm inside site-packages is not an instruction they can follow.
    # tracebi/web/api/ → three levels up is the repo root (or site-packages,
    # which has no pyproject.toml and so takes the installed-package branch).
    _repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    if os.path.isfile(os.path.join(_repo_root, "pyproject.toml")):
        _UI_REMEDY = (
            f"cd {os.path.join(_repo_root, 'web', 'ui')} && npm ci && npm run build"
        )
    else:
        _UI_REMEDY = (
            "This installed package carries no UI bundle. Install a wheel built "
            "with one (see .github/workflows/release.yml), or run the server from "
            "a clone of https://github.com/saltyscott0521/tracebi"
        )
    _UI_MISSING_MSG = (
        "The TraceBi web UI has not been built, so there is no page to serve here. "
        f"The API is running normally — try /api/health. {_UI_REMEDY}"
    )

    print(f"[tracebi] WARNING: no built UI at {_ui_dist} — the API works but / "
          f"has no page. {_UI_REMEDY}", file=sys.stderr)

    def _accepts_html(request: _Request) -> bool:
        """True when the client listed text/html as acceptable.

        A substring test on the raw header reads ``text/html;q=0`` (an
        explicit refusal) as a request for HTML and ``TEXT/HTML`` as a
        refusal, so parse the list instead. Multiple Accept headers count.
        """
        for entry in ",".join(request.headers.getlist("accept")).split(","):
            media, _, params = entry.partition(";")
            if media.strip().lower() != "text/html":
                continue
            for param in params.split(";"):
                key, _, value = param.partition("=")
                if key.strip().lower() == "q":
                    try:
                        return float(value) > 0
                    except ValueError:
                        return False
            return True
        return False

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def ui_not_built(request: _Request):
        if not _accepts_html(request):
            return _JSONResponse({"detail": _UI_MISSING_MSG, "remedy": _UI_REMEDY})
        return _HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<title>TraceBi — UI not built</title>"
            "<h1>TraceBi API is running</h1>"
            "<p>The web UI has not been built, so there is no page to serve here.</p>"
            f"<pre>{_UI_REMEDY}</pre>"
            "<p>Restart the server once that is in place. The API is unaffected — "
            "see <a href='/api/health'>/api/health</a> and "
            "<a href='/docs'>/docs</a>.</p>"
        )
