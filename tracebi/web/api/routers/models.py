import io
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tracebi.sources import is_framework_table
from tracebi.web.api.errors import error_detail
from tracebi.web.api.lineage_graph import lineage_to_graph
from tracebi.web.api.registry import registry
from tracebi.web.api.source_view import source_payload

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
    detail = dict(detail)
    from tracebi.model_registry import model_path

    # A model that names one of TraceBi's own tables (as its name or its
    # source) does not list it, and its routes refuse it: see _load_table.
    tables = detail.get("tables") or []
    detail["tables"] = [t for t in tables if not _is_framework(t)]
    detail["hidden_framework_tables"] = len(tables) - len(detail["tables"])
    path = model_path(name) or model_path(detail.get("name") or name)
    if path:
        try:
            detail["source_file"] = os.path.relpath(path, os.getcwd())
        except ValueError:
            detail["source_file"] = path
    return detail


@router.get("/{name}/source")
def model_source(name: str):
    """The model's file, read-only: the contract a model's Data page describes."""
    detail = registry.describe_model(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    from tracebi.model_registry import model_path

    path = model_path(name) or model_path(detail.get("name") or name)
    return source_payload(
        [("model", path)],
        missing_hint="This model is registered in Python code (an app module), not from a models/ file.",
        hint="The model: its tables, joins, facts, dimensions and measures.",
    )


@router.get("/{name}/context")
def model_context(name: str, brief: bool = False):
    """What an agent receives for this model: the ``model`` of
    ``tracebi context --model <name>`` and of the gateway's ``get_context``,
    from the one function behind all three, so the page that curates the
    words shows the exact text."""
    from tracebi.capabilities import describe_model

    model = registry.get_model(name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    return describe_model(model, brief=brief)


def _safe_filename(name: str) -> str:
    """Keep header-safe characters only (Content-Disposition filename)."""
    return "".join(c for c in name if c.isalnum() or c in "._- ") or "export"


def _is_framework(table: dict) -> bool:
    """A model table that is one of TraceBi's own, by its name or its source."""
    return is_framework_table(table.get("name", "")) or is_framework_table(table.get("source") or "")


def _load_table(name: str, table_name: str):
    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    # A framework table answers as a missing one does: the state store's
    # sessions and tokens are never rows a page can read.
    declared = next((t for t in model.info().get("tables", []) if t.get("name") == table_name), None)
    if is_framework_table(table_name) or (declared and _is_framework(declared)):
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found in model '{name}'")
    try:
        return model.load(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _records(df) -> list[dict]:
    """Rows for a JSON response. JSON has no NaN or infinity, and data can hold
    one (an empty cell, an empty total, a division by zero): those go out as
    null rather than failing the whole response."""
    df = df.replace([float("inf"), float("-inf")], float("nan"))
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def _open_model_table(name: str, table_name: str):
    """The model table's ``(connector, source table)`` opened through the one
    table API (:mod:`tracebi.web.api.routers.tables`), or None when that
    source is not one it reads (a ``SELECT`` source, a CSV folder, a cloud
    warehouse), which keeps the connector's own load."""
    from tracebi.web.api.routers import tables

    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    entry = next((t for t in model.info().get("tables", []) if t["name"] == table_name), None)
    if entry is None:
        return None             # _load_table answers the 404, naming the tables
    connector = next(c for c in model.connectors() if c.name == entry["connector"])
    return lambda: tables.open_table(connector, entry["source"])


def _read_model_table(name: str, table_name: str, read):
    """*read* on the opened model table; None when it is not read that way."""
    from tracebi.model.engine import QueryTimeout
    from tracebi.web.api.routers import tables

    opener = _open_model_table(name, table_name)
    if opener is None:
        return None
    try:
        with opener() as reader:
            return read(reader)
    except (tables.Unsupported, tables.NotInCatalog):
        return None
    except tables.NotConnected as exc:
        raise HTTPException(status_code=404, detail=exc.answer["reason"])
    except QueryTimeout as exc:
        raise HTTPException(status_code=504, detail=error_detail("Read stopped", exc))


@router.get("/{name}/tables/{table_name}/preview")
def preview_table(name: str, table_name: str, rows: int = 50):
    """The first N rows of a model's table (at most 500), read in the engine
    where its source is, never by loading the whole table."""
    from tracebi.web.api.routers.tables import MAX_LIMIT, read_rows

    rows = max(1, min(rows, MAX_LIMIT))
    page = _read_model_table(name, table_name, lambda r: read_rows(r, limit=rows))
    if page is not None:
        names = [c["name"] for c in page["columns"]]
        return {
            "model": name,
            "table": table_name,
            "rows": len(page["rows"]),
            "total_rows": page["total"],
            "columns": names,
            "dtypes": {c["name"]: c["type"] for c in page["columns"]},
            "data": [dict(zip(names, row)) for row in page["rows"]],
        }
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
        "data": _records(df),
    }


@router.get("/{name}/dimensions/{ref}/values")
def dimension_values(name: str, ref: str, limit: int = 200):
    """The distinct values of one dimension attribute (``dim_issuer.sector``),
    sorted, at most *limit*: what Ask offers to filter on. Read from the
    dimension's own table, so it lists every member, not only those a fact
    row uses."""
    detail = registry.describe_model(name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
    dim_name, _, attribute = ref.partition(".")
    dim = next((d for d in detail.get("dimensions") or [] if d["name"] == dim_name), None)
    if dim is None or attribute not in (dim.get("attributes") or []):
        raise HTTPException(status_code=404, detail=(
            f"'{ref}' is not a dimension attribute of '{name}' (dimension.attribute)"))
    df = _load_table(name, dim["table"]).to_pandas()
    if attribute not in df.columns:      # a derived attribute (a time grain, a bin)
        raise HTTPException(status_code=422, detail=(
            f"'{ref}' is derived when a query runs, so it has no stored values to list"))
    values = sorted(df[attribute].dropna().drop_duplicates().astype(object).tolist(),
                    key=lambda v: (type(v).__name__, v))
    limit = max(1, min(limit, 1000))
    return {
        "model": name,
        "dimension": ref,
        "values": [v if isinstance(v, (str, int, float, bool)) else str(v)
                   for v in values[:limit]],
        "total": len(values),
        "truncated": len(values) > limit,
    }


class QueryRequest(BaseModel):
    # One grammar on every surface (architecture v2 §2.2): the body is the
    # same QuerySpec dict Python, report specs, and the MCP gateway speak —
    # validated by QuerySpec.from_dict, not by a parallel pydantic shape.
    # measures accepts BOTH forms: {column: agg} ad-hoc aggregations AND a
    # list of declared measure names (ratio measures included) — the
    # semantic layer's vocabulary is reachable over HTTP.
    fact: str
    measures: Any                             # {column: agg} or [measure names]
    dimensions: Optional[list[str]] = None    # ["dim_customer.region", ...]
    filters: Optional[dict[str, Any]] = None  # WHERE — before aggregation
    having: Optional[dict[str, Any]] = None   # HAVING — on aggregated measures
    aggregate: bool = True
    allow_fanout: bool = False
    order_by: Optional[list] = None           # [{"column":..,"desc":..}] or "-col"
    limit: Optional[int] = None               # requires order_by


@router.post("/{name}/query")
def run_query(name: str, body: QueryRequest):
    """
    Run a star-schema query against a model's facts/dimensions and return
    the result rows plus the full lineage of the query that was executed.
    """
    from tracebi.model.data_model import QuerySpec
    from tracebi.model.engine import QueryTimeout, statement_timeout

    model = registry.get_model(name)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{name}' not found")

    started = time.perf_counter()
    try:
        spec = QuerySpec.from_dict({
            k: v for k, v in {
                "fact": body.fact,
                "measures": body.measures,
                "dimensions": body.dimensions,
                "filters": body.filters,
                "having": body.having,
                "aggregate": body.aggregate,
                "allow_fanout": body.allow_fanout,
                "order_by": body.order_by,
                "limit": body.limit,
            }.items() if v is not None
        })
        # A reader's query stops at the project's statement timeout
        # (tracebi.yaml engine.query_timeout_s) instead of holding a worker.
        with statement_timeout():
            ds = model.execute(spec)
    except QueryTimeout as exc:
        raise HTTPException(status_code=504, detail=error_detail("Query stopped", exc))
    except ValueError as exc:
        # Unknown fact/dimension/agg or malformed reference — caller error.
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=error_detail("Query failed", exc))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

    # JSON has no NaN or infinity, and a result can hold one (an empty total, a
    # division by zero): they go out as missing, null in data and blank in
    # display, rather than failing the whole response.
    df = ds.to_pandas().replace([float("inf"), float("-inf")], float("nan"))
    lineage = ds.lineage_to_dict()
    engine = next(
        (n["metadata"].get("engine") for n in reversed(lineage)
         if n.get("metadata", {}).get("engine")),
        None,
    )
    # The cells as a built report's table writes them (the model's declared
    # formats), beside the raw values: "data" is what a download uses.
    from tracebi.reports.template_package import declared_column_formats, display_rows

    return {
        "model": name,
        "fact": body.fact,
        "rows": len(df),
        "columns": list(df.columns),
        "data": _records(df),
        "display": display_rows(df, declared_column_formats(model, df.columns)),
        "engine": engine,
        "elapsed_ms": elapsed_ms,
        "lineage": lineage,
        "lineage_graph": lineage_to_graph(lineage),
    }


@router.get("/{name}/tables/{table_name}/export.csv")
def export_table_csv(name: str, table_name: str):
    """Download the full table as CSV, streamed from the engine where its
    source is read by the table API."""
    from tracebi.web.api.routers.tables import stream_csv

    opener = _open_model_table(name, table_name)
    if opener is not None and _read_model_table(name, table_name, lambda r: True):
        return stream_csv(opener, table_name)
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
