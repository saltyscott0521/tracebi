from fastapi import APIRouter, HTTPException
from web.api.registry import registry

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("")
def list_connectors():
    """List all registered connectors."""
    return registry.list_connectors()


@router.get("/{name}")
def get_connector(name: str):
    """Get detail for a single connector."""
    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    entry = {"name": c.name, "type": type(c).__name__}
    if hasattr(c, "_tables"):
        entry["tables"] = list(c._tables.keys())
    elif hasattr(c, "_directory"):
        entry["directory"] = c._directory
    elif hasattr(c, "_url"):
        entry["url"] = c._url
    return entry
