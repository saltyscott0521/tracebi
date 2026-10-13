"""The library's folders as the signed-in person sees them.

Nothing here decides access: every level comes from :mod:`tracebi.permissions`
(the one check). This module lists the folders the person may at least see,
what they may do in each (publish directly, or ask), and the destinations a
draft may be published to.
"""

from __future__ import annotations

from typing import Iterable, Optional

from tracebi import permissions
from tracebi.report_paths import library_roots

_MODE = {permissions.PUBLISH: "publish", permissions.MANAGE: "publish",
         permissions.BUILD: "request"}


def mode_of(level: int) -> Optional[str]:
    """What publishing into a place at *level* does: ``publish`` (directly),
    ``request`` (Build only: someone with Publish approves), or ``None``."""
    return _MODE.get(level)


def _walk(root, prefix: str):
    """Every folder below *root* that is not a report package (a directory
    holding ``report.json``) or inside one, hidden, or underscore-led."""
    for child in sorted(root.iterdir()):
        if (not child.is_dir() or child.name.startswith((".", "_"))
                or (child / "report.json").is_file()):
            continue
        path = f"{prefix}{child.name}"
        yield path
        yield from _walk(child, f"{path}/")


def _library_folders() -> list:
    found = []
    for label, root in library_roots():
        if root.is_dir():
            found.extend(_walk(root, f"{label}/" if label else ""))
    return found


def _entry(path: str, reports: Iterable[str], mine: bool) -> dict:
    level = permissions.folder_level(path)
    personal = path.startswith(permissions.PERSONAL_ROOT + "/")
    slug = path.split("/")[1] if personal else None
    entry = {
        "path": path,
        "name": ("My published" if mine else f"{slug}'s published") if personal
        else path.rsplit("/", 1)[-1],
        "personal": personal, "mine": mine,
        "level": permissions.LEVELS[level], "mode": mode_of(level),
        "accepts": permissions.folder_accepts(f"{path}/x"),
        "reports": sum(1 for n in reports if n.startswith(f"{path}/")),
    }
    if level >= permissions.MANAGE or mine:
        entry["permissions"] = permissions.describe_folder(path)
        entry["permissions"]["editable"] = False        # file-only for now
    return entry


def list_folders(report_names: Iterable[str]) -> dict:
    """``{"personal": <path or None>, "folders": [...]}``: the folders the
    person may see (View or more), their own ``My published`` first, even
    before it exists. ``personal`` is ``None`` when they have none (no
    sign-in identity, or the library is mounted), with ``personal_note``
    saying why."""
    names = list(report_names)
    mine = permissions.personal_folder()
    paths = [p for p in _library_folders()
             if p != permissions.PERSONAL_ROOT and p != mine]
    shown = [_entry(p, names, False) for p in paths if permissions.folder_level(p) >= permissions.VIEW]
    if mine:
        shown.insert(0, _entry(mine, names, True))
    # Others' personal folders sort after the shared ones.
    shown.sort(key=lambda e: (not e["mine"], e["personal"], e["path"]))
    out = {"personal": mine, "folders": shown}
    if not mine:
        out["personal_note"] = (
            "My published needs a signed-in person; this session has no sign-in "
            "identity (the shared token, the command line, or an app without "
            "sign-in), so publish into a shared folder instead.")
    return out


def destinations(path: str, report_names: Iterable[str]) -> list:
    """Where the report draft *path* may be published, for the person asking:
    its own place first (what a publish with no folder does), then every
    folder they hold Build or more in. Each says whether it publishes
    directly or sends a request, and what the folder accepts."""
    own = permissions.granted_level(path)
    own_folder = path.rsplit("/", 1)[0] if "/" in path else ""
    options = [{
        "folder": None, "destination": path, "personal": False,
        "label": f"Its own place ({own_folder}/)" if own_folder else "The top of the library",
        "mode": mode_of(own), "accepts": permissions.folder_accepts(path),
    }]
    leaf = path.rsplit("/", 1)[-1]
    for entry in list_folders(report_names)["folders"]:
        if entry["mode"] is None:
            continue
        options.append({
            "folder": entry["path"], "destination": f"{entry['path']}/{leaf}",
            "personal": entry["personal"], "label": entry["name"],
            "mode": entry["mode"], "accepts": entry["accepts"],
        })
    return options
