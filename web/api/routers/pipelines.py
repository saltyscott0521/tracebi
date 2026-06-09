from fastapi import APIRouter, HTTPException
import pandas as pd

from web.api.registry import registry

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("")
def list_pipelines():
    """List all registered pipeline runners and their layer status."""
    result = []
    for pipeline_name in registry.list_pipeline_names():
        runner = registry.get_pipeline(pipeline_name)
        layers = []
        for layer_name, reg in runner._layers.items():
            try:
                df = pd.read_sql(
                    "SELECT status, completed_at, rows_out FROM tracebi_runs "
                    f"WHERE layer_name = '{layer_name}' "
                    "ORDER BY id DESC LIMIT 1",
                    con=runner._engine_(),
                )
                if df.empty:
                    last_status, last_run, last_rows_out = None, None, None
                else:
                    row = df.iloc[0]
                    last_status = row["status"]
                    last_run = str(row["completed_at"] or "")
                    last_rows_out = int(row["rows_out"]) if row["rows_out"] is not None else None
            except Exception as exc:
                last_status, last_run, last_rows_out = f"error: {exc}", None, None

            layers.append({
                "name": layer_name,
                "type": reg.layer_type,
                "schedule": reg.schedule,
                "depends_on": reg.depends_on,
                "last_status": last_status,
                "last_run": last_run,
                "last_rows_out": last_rows_out,
            })
        result.append({"pipeline": pipeline_name, "layers": layers})
    return result


@router.post("/{pipeline_name}/run")
def run_pipeline(pipeline_name: str, refresh: bool = True):
    """
    Run every layer in a pipeline.

    With ``refresh=true`` (default), each leaf is run with its full
    upstream chain, so dependencies fire in the right order with no
    duplicates. Set ``refresh=false`` to fire every registered layer
    independently regardless of dependencies.
    """
    runner = registry.get_pipeline(pipeline_name)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")

    layer_names = list(runner._layers.keys())
    if not layer_names:
        return {"pipeline": pipeline_name, "status": "empty", "ran": []}

    ran: list[str] = []
    try:
        if refresh:
            # Leaves = layers nothing else depends on. Running each leaf
            # with refresh=True walks the full chain via PipelineRunner.
            depends = {reg.depends_on for reg in runner._layers.values() if reg.depends_on}
            leaves = [n for n in layer_names if n not in depends] or layer_names
            seen: set[str] = set()
            for leaf in leaves:
                for name in runner._resolve_chain(leaf):
                    if name in seen:
                        continue
                    seen.add(name)
                    runner._execute(name)
                    ran.append(name)
        else:
            for name in layer_names:
                runner._execute(name)
                ran.append(name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"pipeline": pipeline_name, "status": "ok", "ran": ran}


@router.post("/{pipeline_name}/layers/{layer_name}/run")
def run_layer(pipeline_name: str, layer_name: str, refresh: bool = False):
    """
    Trigger a pipeline layer on demand.

    Set refresh=true to walk the full depends_on chain upstream first.
    """
    runner = registry.get_pipeline(pipeline_name)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")
    if layer_name not in runner._layers:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer_name}' not found in pipeline '{pipeline_name}'",
        )
    try:
        runner.run(layer_name, refresh=refresh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"pipeline": pipeline_name, "layer": layer_name, "status": "triggered"}


@router.get("/{pipeline_name}/layers/{layer_name}/history")
def layer_history(pipeline_name: str, layer_name: str, limit: int = 20):
    """Return the run history for a specific layer."""
    runner = registry.get_pipeline(pipeline_name)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_name}' not found")
    if layer_name not in runner._layers:
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer_name}' not found in pipeline '{pipeline_name}'",
        )
    try:
        df = pd.read_sql(
            "SELECT * FROM tracebi_runs "
            f"WHERE layer_name = '{layer_name}' "
            f"ORDER BY id DESC LIMIT {limit}",
            con=runner._engine_(),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "pipeline": pipeline_name,
        "layer": layer_name,
        "runs": df.to_dict(orient="records"),
    }
