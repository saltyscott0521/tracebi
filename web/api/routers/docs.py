"""
Read-only access to the markdown guides in docs/.

Serves the files as raw markdown; the React UI renders them on the
Getting Started page. Only files that exist in the docs directory are
addressable — names are matched against a directory listing, so path
traversal is structurally impossible.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/docs", tags=["docs"])


def _docs_dir() -> Path:
    """
    Locate the markdown guides.

    Resolved at call time rather than import time, and checked in order:
    an explicit override, the working directory (an installed project may
    ship its own docs/), then the repo checkout. The repo-relative path
    alone silently produced an empty Getting Started page whenever the
    server ran from anywhere but a source tree.
    """
    override = os.environ.get("TRACEBI_DOCS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    cwd_docs = Path.cwd() / "docs"
    if cwd_docs.is_dir():
        return cwd_docs
    return Path(__file__).resolve().parents[3] / "docs"


def _title(path: Path) -> str:
    """First markdown H1 in the file, or the filename as a fallback."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem.replace("-", " ").title()


def _guides() -> dict[str, Path]:
    docs_dir = _docs_dir()
    if not docs_dir.is_dir():
        return {}
    return {p.stem: p for p in sorted(docs_dir.glob("*.md"))}


@router.get("")
def list_guides():
    """List available guides: name (slug), title, and size."""
    return [
        {"name": name, "title": _title(path), "bytes": path.stat().st_size}
        for name, path in _guides().items()
    ]


@router.get("/{name}")
def get_guide(name: str):
    """Return one guide's markdown content."""
    path = _guides().get(name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Guide '{name}' not found")
    return {"name": name, "title": _title(path), "content": path.read_text(encoding="utf-8")}
