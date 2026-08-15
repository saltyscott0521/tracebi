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

# The repo root must be importable so `tracebi.web.api.main`, `models/`, and
# `pipelines/` resolve the same way they do locally. Vercel runs functions
# from the project root, but be explicit rather than relying on it.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Artifact discovery is relative to the working directory. In this repo the
# working project lives at examples/portfolio_project (the repo root is the
# framework, not a project); a real deployment of your own project keeps its
# models/ and reports/ at ITS root, so the fallback is _ROOT.
_project = _ROOT / "examples" / "portfolio_project"
os.chdir(_project if _project.is_dir() else _ROOT)

# Default to no app module, because a real project deploying this should get
# its own models/ and reports/ (both discovered without an app module) rather
# than someone else's demo data.
#
# This is now a default rather than a hard rule. It used to be the latter: the
# bundled demo app wrote its pipeline SQLite into the checkout, which raises on
# a read-only serverless filesystem and took the demo's reports and connectors
# down with it. tracebi/web/demo_app/pipeline.py now falls back to a writable location,
# so setting TRACEBI_APP=tracebi.web.demo_app here is a supported way to deploy the
# demo — that is exactly what tracebi.com does. Import cost is ~1.4s including
# the six-layer pipeline run, most of which is importing pandas either way.
os.environ.setdefault("TRACEBI_APP", "")

from tracebi.web.api.main import app  # noqa: E402  (after sys.path/env setup)

__all__ = ["app"]
