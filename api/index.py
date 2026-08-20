"""TEMPORARY DIAGNOSTIC — heavy deps, no tracebi code.

Isolates whether the runtime crash is the heavy dependency imports (cold-start
weight / native libs on the Lambda) vs. tracebi's own startup code. Each import
is guarded so /api/health can report exactly which one, if any, fails.
Reverted immediately.
"""

import importlib

from fastapi import FastAPI

app = FastAPI()

_results = {}
for _name in ("pandas", "numpy", "duckdb", "sqlalchemy", "psycopg", "openpyxl", "jinja2"):
    try:
        _mod = importlib.import_module(_name)
        _results[_name] = getattr(_mod, "__version__", "ok")
    except BaseException as _exc:  # noqa: BLE001
        _results[_name] = f"FAILED: {type(_exc).__name__}: {_exc}"


@app.get("/api/health")
@app.get("/api/{path:path}")
def health(path: str = ""):  # noqa: ARG001
    return {"diagnostic": "heavy-deps, no tracebi", "imports": _results}
