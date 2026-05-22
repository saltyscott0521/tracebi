from fastapi import APIRouter
from web.api.registry import registry

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("")
def list_dashboards():
    """List all registered dashboards."""
    return registry.list_dashboards()
