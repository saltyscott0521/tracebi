"""``POST /api/library/sync``: a git webhook that pulls the library.

A library folder (or the whole project) can be a git checkout of a repository
where changes arrive by pull request: the git lane of remote authoring, where
review happens in the pull request. On a push to the branch, the repository's
webhook calls this endpoint; it fast-forwards each checkout and live discovery
picks up what changed.

It is outside the app's sign-in (a webhook has none) and guarded by its own
secret, ``TRACEBI_LIBRARY_SYNC_SECRET``: a GitHub-style
``X-Hub-Signature-256`` HMAC of the body, or the secret itself in
``X-TraceBi-Sync-Token``. With no secret set the endpoint does not exist.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/library", tags=["library"])


def _secret() -> str:
    return os.environ.get("TRACEBI_LIBRARY_SYNC_SECRET", "")


def _signed(secret: str, body: bytes, request: Request) -> bool:
    token = request.headers.get("x-tracebi-sync-token")
    if token is not None:
        return hmac.compare_digest(token.encode(), secret.encode())
    sig = request.headers.get("x-hub-signature-256") or ""
    want = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig.encode(), want.encode())


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                         timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip() or f"git {args[0]} failed")
    return out.stdout.strip()


def _checkouts() -> list:
    """The git checkouts holding the project and its library roots, once each."""
    from tracebi.report_paths import library_roots

    tops: list = []
    for root in [Path.cwd()] + [r for _, r in library_roots()]:
        try:
            top = Path(_git(root, "rev-parse", "--show-toplevel"))
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            continue
        if top not in tops:
            tops.append(top)
    return tops


def _reload_pipelines(changed: list) -> list:
    """Pipelines whose file a pull changed are loaded again, so the next run
    uses the new file (new ones are found by live discovery)."""
    from tracebi import pipeline_registry
    from tracebi.web.api.registry import registry

    pdir = Path(os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines")).resolve()
    names = sorted({p.stem for p in changed
                    if p.parent == pdir and p.suffix in (".py", ".yaml", ".yml")
                    and p.is_file() and p.stem in registry.list_pipeline_names()})
    for name in names:
        registry.add_pipeline(name, pipeline_registry.reload(name, str(pdir)))
    return names


@router.post("/sync")
async def sync_library(request: Request):
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=404, detail="Not Found")
    if not _signed(secret, await request.body(), request):
        raise HTTPException(status_code=401, detail="bad or missing signature")
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_sync)       # git and discovery block


def _sync() -> dict:
    from tracebi.connections import connections_dir
    from tracebi.web.discovery import rescan_library

    synced, changed = [], []
    for top in _checkouts():
        try:
            before = _git(top, "rev-parse", "HEAD")
            _git(top, "pull", "--ff-only")
            after = _git(top, "rev-parse", "HEAD")
            if before != after:
                changed += [(top / f).resolve() for f in
                            _git(top, "diff", "--name-only", before, after).splitlines()]
            synced.append({"checkout": str(top), "from": before, "to": after})
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            synced.append({"checkout": str(top), "error": str(exc)})
    if not synced:
        raise HTTPException(status_code=422, detail="no library folder is a git checkout")
    found = rescan_library(os.environ.get("TRACEBI_MODELS_DIR", "models"),
                           os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"),
                           str(connections_dir()))
    return {"synced": synced, "discovered": found,
            "pipelines_reloaded": _reload_pipelines(changed)}
