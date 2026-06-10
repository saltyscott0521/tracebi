from fastapi import APIRouter, HTTPException

from web.api.registry import registry

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("")
def list_pipelines():
    """List all registered pipeline runners and their layer status."""
    result = []
    for pipeline_name in registry.list_pipeline_names():
        runner = registry.get_pipeline(pipeline_name)
        layers = []
        for layer in runner.layers():
            try:
                last = runner.last_run(layer["name"])
            except Exception as exc:
                last = None
                layer["last_status"] = f"error: {exc}"
            if last is not None:
                layer["last_status"] = last["status"]
                layer["last_run"] = str(last["completed_at"] or "")
                layer["last_rows_out"] = (
                    int(last["rows_out"]) if last["rows_out"] is not None else None
                )
            else:
                layer.setdefault("last_status", None)
                layer["last_run"] = None
                layer["last_rows_out"] = None
            layers.append(layer)
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

    layers = runner.layers()
    if not layers:
        return {"pipeline": pipeline_name, "status": "empty", "ran": []}
    layer_names = [layer["name"] for layer in layers]

    ran: list[str] = []
    try:
        if refresh:
            # Leaves = layers nothing else depends on. Running each leaf's
            # full chain covers every layer in dependency order.
            depends = {layer["depends_on"] for layer in layers if layer["depends_on"]}
            leaves = [n for n in layer_names if n not in depends] or layer_names
            seen: set[str] = set()
            for leaf in leaves:
                for name in runner.execution_order(leaf):
                    if name in seen:
                        continue
                    seen.add(name)
                    runner.execute_layer(name)
                    ran.append(name)
        else:
            for name in layer_names:
                runner.execute_layer(name)
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
    if not runner.has_layer(layer_name):
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
    if not runner.has_layer(layer_name):
        raise HTTPException(
            status_code=404,
            detail=f"Layer '{layer_name}' not found in pipeline '{pipeline_name}'",
        )
    try:
        runs = runner.run_history(layer_name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "pipeline": pipeline_name,
        "layer": layer_name,
        "runs": runs,
    }
