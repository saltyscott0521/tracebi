"""TEMPORARY DIAGNOSTIC — a trivial function with no tracebi import.

Purpose: isolate whether the Vercel Python function *mechanism* works at all.
If /api/health returns 200 here, the serverless plumbing is fine and the real
500 lives in importing/running the tracebi app. If this ALSO 500s, the function
setup itself (build/config/runtime) is broken, independent of the app.

Reverted immediately once the answer is in.
"""

import sys

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "diagnostic": "trivial function — no tracebi import",
        "python": sys.version,
    }


@app.get("/api/{path:path}")
def catchall(path: str):
    return {"status": "ok", "path": path, "diagnostic": "trivial function"}
