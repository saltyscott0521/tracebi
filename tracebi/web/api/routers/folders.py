"""The library's folders, as the signed-in person sees them (read-only)."""

from fastapi import APIRouter

from tracebi import folders
from tracebi.web.api.registry import registry

router = APIRouter(prefix="/folders", tags=["folders"])


@router.get("")
def list_folders():
    """Folders the caller may see, with their level in each and whether a
    publish there is direct or a request. Their own ``My published`` comes
    first (``personal``); a folder's permissions are shown to those with
    Manage, and to its owner, read-only: they are edited in ``_folder.yaml``."""
    return folders.list_folders(r["name"] for r in registry.list_reports())
