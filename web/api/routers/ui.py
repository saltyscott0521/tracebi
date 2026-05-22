import os
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from web.api.registry import registry

_OVERVIEW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "..", "docs", "overview.html",
)

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
router = APIRouter(tags=["ui"])


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {
        "connector_count": len(registry.list_connectors()),
        "model_count": len(registry.list_models()),
        "report_count": len(registry.list_reports()),
        "pipeline_count": len(registry.list_pipeline_names()),
    })


@router.get("/connectors")
def connectors(request: Request):
    return templates.TemplateResponse(request, "connectors.html", {
        "connectors": registry.list_connectors(),
    })


@router.get("/models")
def models(request: Request):
    return templates.TemplateResponse(request, "models.html", {
        "models": registry.list_models(),
    })


@router.get("/reports")
def reports(request: Request):
    return templates.TemplateResponse(request, "reports.html", {
        "reports": registry.list_reports(),
    })


@router.get("/pipelines")
def pipelines(request: Request):
    return templates.TemplateResponse(request, "pipelines.html", {
        "pipeline_names": registry.list_pipeline_names(),
    })


@router.get("/dashboards")
def dashboards(request: Request):
    return templates.TemplateResponse(request, "dashboards.html", {
        "dashboards": registry.list_dashboards(),
    })


@router.get("/overview")
def overview():
    return FileResponse(_OVERVIEW_PATH, media_type="text/html")
