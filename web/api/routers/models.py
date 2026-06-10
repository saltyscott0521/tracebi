import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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


def _safe_filename(name: str) -> str:
    """Keep header-safe characters only (Content-Disposition filename)."""
    return "".join(c for c in name if c.isalnum() or c in "._- ") or "export"


def _load_table(name: str, table_name: str):
    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    try:
        return model.load(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{name}/tables/{table_name}/preview")
def preview_table(name: str, table_name: str, rows: int = 50):
    """Load a table from a model and return the first N rows."""
    ds = _load_table(name, table_name)
    full_df = ds.to_pandas()
    df = full_df.head(rows)
    return {
        "model": name,
        "table": table_name,
        "rows": len(df),
        "total_rows": len(full_df),
        "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in full_df.dtypes.items()},
        "data": df.to_dict(orient="records"),
        "lineage": ds.lineage_to_dict(),
    }


@router.get("/{name}/tables/{table_name}/export.csv")
def export_table_csv(name: str, table_name: str):
    """Download the full table as CSV."""
    ds = _load_table(name, table_name)
    buf = io.StringIO()
    ds.to_pandas().to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={
            "Content-Disposition":
                f'attachment; filename="{_safe_filename(table_name)}.csv"',
        },
    )
