import io
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from web.api.errors import error_detail
from web.api.lineage_graph import lineage_to_graph
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


class QueryRequest(BaseModel):
    fact: str
    measures: dict[str, str]                  # {column: agg} e.g. {"revenue": "sum"}
    dimensions: Optional[list[str]] = None    # ["dim_customer.region", ...]
    filters: Optional[dict[str, Any]] = None  # equality filters on the fact table
    aggregate: bool = True


@router.post("/{name}/query")
def run_query(name: str, body: QueryRequest):
    """
    Run a star-schema query against a model's facts/dimensions and return
    the result rows plus the full lineage of the query that was executed.
    """
    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")

    started = time.perf_counter()
    try:
        ds = model.query(
            fact=body.fact,
            measures=body.measures,
            dimensions=body.dimensions,
            filters=body.filters,
            aggregate=body.aggregate,
        )
    except ValueError as exc:
        # Unknown fact/dimension/agg or malformed reference — caller error.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=error_detail("Query failed", exc))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    df = ds.to_pandas()
    lineage = ds.lineage_to_dict()
    engine = next(
        (n["metadata"].get("engine") for n in reversed(lineage)
         if n.get("metadata", {}).get("engine")),
        None,
    )
    return {
        "model": name,
        "fact": body.fact,
        "rows": len(df),
        "columns": list(df.columns),
        "data": df.to_dict(orient="records"),
        "engine": engine,
        "elapsed_ms": elapsed_ms,
        "lineage": lineage,
        "lineage_graph": lineage_to_graph(lineage),
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
