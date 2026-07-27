"""
Vercel Python serverless entry point.

Vercel's Python runtime looks for a module-level ASGI/WSGI ``app``, so this
file's job is to expose the FastAPI application with settings appropriate to
an *ephemeral* process. Everything under ``/api`` is rewritten here by
``vercel.json``.

What works well on serverless
-----------------------------
The read-and-compute surface, which is most of the product: models, Explore
queries, the capability schema, spec validate/render, synchronous report
runs, docs. TraceBi recomputes from source on every call by design — it never
caches a query result — so there is no warm state to lose.

What does not, and why
----------------------
* **Scheduling.** APScheduler needs a process that outlives a request. Use
  Supabase ``pg_cron`` or Vercel Cron to hit an endpoint instead.
* **Background report runs.** ``POST /api/reports/{name}/runs`` hands work to
  an in-process thread pool and returns a ``run_id``; the next poll lands in
  a different, fresh process that has never heard of it. Use the synchronous
  ``POST /api/reports/{name}/run``.
* **Local SQLite.** The filesystem is read-only outside ``/tmp``, and ``/tmp``
  is not shared between invocations. Point connectors and
  ``PipelineRunner(db_url=...)`` at Supabase Postgres — which is exactly why
  that pairing works.

Cold starts pay roughly a second importing pandas. Expected, not a bug.
"""

import os
import sys
from pathlib import Path

# The repo root must be importable so `web.api.main`, `models/`, and
# `pipelines/` resolve the same way they do locally. Vercel runs functions
# from the project root, but be explicit rather than relying on it.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Artifact discovery is relative to the working directory.
os.chdir(_ROOT)

# Don't load the bundled demo app: it builds demo data and runs a six-layer
# SQLite pipeline at import time, which would fail on a read-only filesystem
# and add seconds to every cold start. A project's own models/ and reports/
# directories are discovered without it.
os.environ.setdefault("TRACEBI_APP", "")

from web.api.main import app  # noqa: E402  (after sys.path/env setup)

__all__ = ["app"]
