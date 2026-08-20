"""TEMPORARY DIAGNOSTIC — walk the tracebi import chain to find the crash.

The heavy deps import fine on the Lambda; the crash is somewhere in importing
tracebi's own code. Import the chain module-by-module, guarded, and report the
first failure and its traceback. A plain module-level FastAPI `app` (no
conditional definition) so the build stays happy. Reverted immediately.
"""

import importlib
import os
import sys
import traceback

from fastapi import FastAPI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TRACEBI_APP", "")

app = FastAPI()

_walk = {}
for _mod in (
    "tracebi",
    "tracebi.registry",
    "tracebi.model.data_model",
    "tracebi.connectors.duckdb_connector",
    "tracebi.connectors.sql_connector",
    "tracebi.reports.template_package",
    "tracebi.verify",
    "tracebi.web.api.routers.reports",
    "tracebi.web.api.routers.verify",
    "tracebi.web.api.main",
):
    try:
        importlib.import_module(_mod)
        _walk[_mod] = "ok"
    except BaseException as _exc:  # noqa: BLE001
        _walk[_mod] = f"FAILED: {type(_exc).__name__}: {_exc}"
        _walk["_traceback"] = traceback.format_exc().splitlines()[-20:]
        break


@app.get("/api/health")
@app.get("/api/{path:path}")
def health(path: str = ""):  # noqa: ARG001
    return {"diagnostic": "tracebi import walk", "walk": _walk}
