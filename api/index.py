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
# framework, not a project) — but only serve it when its warehouse actually
# exists in the deployment: portfolio_model reads data/warehouse.duckdb, which
# the serverless bundle does not carry (data/ is gitignored and the function
# filesystem is read-only), and serving models whose every query 500s is worse
# than serving none. A deployment of your own project keeps its models/ and
# reports/ at the repo root, so the fallback is _ROOT — that flow is
# unaffected. The public tracebi.com demo opts into the self-contained
# in-memory demo app via TRACEBI_APP instead.
_project = _ROOT / "examples" / "portfolio_project"
_warehouse = _project / "data" / "warehouse.duckdb"
os.chdir(_project if _warehouse.is_file() else _ROOT)

# Heal a legacy TRACEBI_APP. A Vercel env var set before the web app moved
# INTO the tracebi package still reads e.g. "web.demo_app"; main.py refuses that
# old spelling by design (a migration guard) and the whole API function then
# crashes at import (FUNCTION_INVOCATION_FAILED). Rewrite the old namespace to
# the current one here so the deploy self-heals without a dashboard edit.
_app = os.environ.get("TRACEBI_APP", "").strip()
if _app == "web" or _app.startswith("web."):
    os.environ["TRACEBI_APP"] = "tracebi." + _app

# Otherwise default to no app module: a real project deploying this gets its own
# models/ and reports/ (discovered without an app module) rather than someone
# else's demo data.
os.environ.setdefault("TRACEBI_APP", "")

from tracebi.web.api.main import app  # noqa: E402  (after sys.path/env setup)

__all__ = ["app"]
