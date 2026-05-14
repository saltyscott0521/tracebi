from fastapi import APIRouter, HTTPException
from web.api.registry import registry

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
def list_models():
    """List all registered data models."""
    return registry.list_models()


@router.get("/{name}")
def get_model(name: str):
    """Get full detail for a data model (tables, relationships)."""
    detail = registry.describe_model(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    return detail


@router.get("/{name}/tables/{table_name}/preview")
def preview_table(name: str, table_name: str, rows: int = 50):
    """Load a table from a model and return the first N rows."""
    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    try:
        ds = model.load(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    df = ds.to_pandas().head(rows)
    return {
        "model": name,
        "table": table_name,
        "rows": len(df),
        "columns": list(df.columns),
        "data": df.to_dict(orient="records"),
        "lineage": ds.lineage_to_dict(),
    }
