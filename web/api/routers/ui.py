import os
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from web.api.registry import registry

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "templates",
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
router = APIRouter(tags=["ui"])


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "connector_count": len(registry.list_connectors()),
        "model_count": len(registry.list_models()),
        "report_count": len(registry.list_reports()),
        "pipeline_count": len(registry.list_pipeline_names()),
    })


@router.get("/connectors")
def connectors(request: Request):
    return templates.TemplateResponse("connectors.html", {
        "request": request,
        "connectors": registry.list_connectors(),
    })


@router.get("/models")
def models(request: Request):
    return templates.TemplateResponse("models.html", {
        "request": request,
        "models": registry.list_models(),
    })


@router.get("/reports")
def reports(request: Request):
    return templates.TemplateResponse("reports.html", {
        "request": request,
        "reports": registry.list_reports(),
    })


@router.get("/pipelines")
def pipelines(request: Request):
    return templates.TemplateResponse("pipelines.html", {
        "request": request,
        "pipeline_names": registry.list_pipeline_names(),
    })
