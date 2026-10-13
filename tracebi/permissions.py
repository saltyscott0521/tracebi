"""Who may do what to a report: the one check.

A folder in the library is a directory that is not itself a report package.
It may hold a small ``_folder.yaml`` that grants four ordered permissions to
sign-in groups or names::

    view:    [finance, ceo@example.com]   # see the folder; open reports and builds
    build:   [finance-analysts]           # + create and edit drafts in it
    publish: [finance-leads]              # + approve a draft into it; its schedule
    manage:  [bi-admins]                  # + change the folder's permissions

Each level includes the ones above it in the list. The web app, the agent
gateway, the scheduler and the CLI all ask :func:`granted_level` (through
``report_paths.open_report``, the one read of a named report) and never decide
for themselves.

Rules this module keeps:

* **No ``_folder.yaml`` anywhere means no folder restriction.** The roles
  (viewer / analyst / admin) decide, as before; nobody is locked out.
* **The nearest file wins.** Starting at the report's folder and walking up to
  the library root, the first ``_folder.yaml`` found is the whole rule for
  everything below it: it replaces its ancestors' rules, it does not add to
  them. It is read at request time (cached by file time), so an edit applies
  to the next request.
* **A folder narrows what a role may do; it never widens it.** A person's
  level is capped by their role (viewer: View; analyst: up to Publish; admin:
  Manage), because the routes still check roles. A ``manage`` grant does not
  make a viewer a publisher.
* **Admins always keep Manage**, and so does anyone with no sign-in role at all
  (the CLI, the scheduler, a notebook, the unauthenticated app): a typo in a
  ``_folder.yaml`` must not lock the people who can fix it out of it.
* **A malformed file fails closed** for everyone but those: nobody else is
  granted anything under it, a warning is logged, and nothing raises.
* Group names and person names are matched ignoring case; ``*`` grants a level
  to every named person.

A ``_folder.yaml`` may also say what the folder **accepts** (not a permission,
so it does not change who holds what)::

    accepts: labelled     # default: anything honestly labelled
    accepts: checkable    # only reports whose every number a query can re-run

:func:`folder_accepts` reads it with the same nearest-file rule; the draft
publish and request paths enforce it (``tracebi/drafts.py``). An unknown value
makes the file malformed, and a malformed file is read as ``checkable`` (the
strict answer) for this purpose.

**My published.** Each signed-in person has a folder of their own,
``my-published/<their sign-in name>/`` (:func:`personal_folder`), where they hold
Publish: reports there are shareable and schedulable without the shared
folders. Nobody else sees it unless a ``_folder.yaml`` inside it grants them
View (the library's own file never reaches in). Admins and the no-identity
actors keep Manage as everywhere. A person with no sign-in name and role (the
shared gateway token, the CLI, an app with no sign-in) has no personal folder.

Purposes (``open_report(..., purpose=)``) map to levels: ``view`` and
``source`` are View, ``build`` is Build, ``schedule`` and ``manage`` (changing
what is published) are Publish. Manage itself is for changing permissions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from tracebi.audit import get_actor, get_groups

log = logging.getLogger("tracebi.permissions")

FOLDER_FILE = "_folder.yaml"
LEVELS = ("view", "build", "publish", "manage")
NONE, VIEW, BUILD, PUBLISH, MANAGE = -1, 0, 1, 2, 3
_PURPOSE_LEVEL = {"view": VIEW, "source": VIEW, "build": BUILD,
                  "schedule": PUBLISH, "manage": PUBLISH}
_ROLE_CEILING = {"viewer": VIEW, "analyst": PUBLISH}
ACCEPTS = ("labelled", "checkable")
#: The library folder that holds each signed-in person's own published folder.
PERSONAL_ROOT = "my-published"


class NotPermitted(PermissionError):
    """The person can see the report but may not do this to it."""

    def __init__(self, name: str, needed: int) -> None:
        self.name, self.needed = name, needed
        self.level = LEVELS[needed]
        super().__init__(
            f"{self.level} permission is needed on the folder of {name}; "
            f"ask a folder manager (its _folder.yaml) for it.")


@dataclass(frozen=True)
class Principal:
    """Who is asking: a sign-in name, its role, and its sign-in groups."""

    name: Optional[str] = None
    role: Optional[str] = None
    groups: tuple = ()


def current_principal() -> Principal:
    """The actor of this request, tool call or command (``tracebi.audit``)."""
    name, role = get_actor()
    return Principal(name, role, get_groups())


def level_for_purpose(purpose: str) -> int:
    return _PURPOSE_LEVEL.get(purpose, VIEW)


# ── _folder.yaml ───────────────────────────────────────────────────────────

class _Rule:
    """One parsed ``_folder.yaml``: who holds which level."""

    def __init__(self, grants: Optional[dict], path: Path,
                 accepts: str = ACCEPTS[0]) -> None:
        self.path = path
        #: ``None`` for a malformed file, which grants nothing.
        self.grants = grants
        #: What the folder takes in (``ACCEPTS``); a malformed file is strict.
        self.accepts = accepts

    def level_of(self, principal: Principal) -> int:
        if self.grants is None or principal.name is None:
            return NONE
        held = {principal.name.casefold(), *(g.casefold() for g in principal.groups)}
        best = NONE
        for level, who in self.grants.items():
            if "*" in who or held & who:
                best = max(best, LEVELS.index(level))
        return best


_cache: dict = {}


def _parse(path: Path) -> _Rule:
    import yaml

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return _malformed(path, f"cannot be read: {exc}")
    if doc is None:
        return _Rule({}, path)
    if not isinstance(doc, dict):
        return _malformed(path, "must be a mapping of permission to names")
    grants: dict = {}
    accepts = ACCEPTS[0]
    for key, value in doc.items():
        if key == "accepts":
            if value not in ACCEPTS:
                return _malformed(path, f"accepts must be one of {', '.join(ACCEPTS)}, not {value!r}")
            accepts = value
            continue
        if key not in LEVELS:
            return _malformed(
                path, f"unknown permission {key!r} (use {', '.join(LEVELS)}, or accepts)")
        names = [value] if isinstance(value, str) else value
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            return _malformed(path, f"{key} must be a name or a list of names")
        grants[key] = {n.strip().casefold() for n in names}
    return _Rule(grants, path, accepts)


def _malformed(path: Path, why: str) -> _Rule:
    log.warning("%s %s; nobody but admins is granted anything under it", path, why)
    return _Rule(None, path, ACCEPTS[1])


def _rule_in(directory: Path) -> Optional[_Rule]:
    path = directory / FOLDER_FILE
    try:
        stat = path.stat()
    except OSError:
        _cache.pop(path, None)
        return None
    if not path.is_file():
        return None
    signature = (stat.st_mtime_ns, stat.st_size)
    hit = _cache.get(path)
    if hit is None or hit[0] != signature:
        hit = _cache[path] = (signature, _parse(path))
    return hit[1]


def _nearest_rule(root: Path, relative: str) -> Optional[_Rule]:
    """The first ``_folder.yaml`` from *relative*'s folder up to *root*."""
    # The name was validated: no '..', no empty or hidden segment.
    parts = relative.split("/")[:-1]
    for depth in range(len(parts), -1, -1):
        rule = _rule_in(root.joinpath(*parts[:depth]))
        if rule is not None:
            return rule
    return None


# ── The check ──────────────────────────────────────────────────────────────

def granted_level(name: str, principal: Optional[Principal] = None, *,
                  reports_dir: Optional[Union[str, os.PathLike]] = None) -> int:
    """The highest level *principal* (default: the current actor) holds on
    report *name*: ``NONE`` (-1) for nothing, else VIEW < BUILD < PUBLISH < MANAGE.

    A name that is not a safe library path holds nothing for anyone.
    """
    from tracebi.report_paths import locate, report_name_error

    if report_name_error(name):
        return NONE
    who = principal or current_principal()
    ceiling = _ROLE_CEILING.get(who.role, MANAGE)
    if ceiling == MANAGE:
        return MANAGE
    root, relative = locate(name, reports_dir)
    if name.startswith(PERSONAL_ROOT + "/"):
        return min(ceiling, _personal_level(root, name, who))
    rule = _nearest_rule(root, relative) if relative is not None else None
    if rule is None:
        return ceiling
    return min(ceiling, rule.level_of(who))


def _personal_level(root: Path, name: str, who: Principal) -> int:
    """The level on a report under ``my-published/<person>/``: its owner holds
    Publish; anyone else holds only what a ``_folder.yaml`` inside that
    personal folder grants. A rule above it (the library's own) never reaches
    in, so a public folder's ``view: ['*']`` does not expose it."""
    parts = name.split("/")[:-1]               # my-published, <person>, ...
    mine = len(parts) > 1 and parts[1] == personal_slug(who)
    best = PUBLISH if mine else NONE
    for depth in range(len(parts), 1, -1):
        rule = _rule_in(root.joinpath(*parts[:depth]))
        if rule is not None:
            return max(best, rule.level_of(who))
    return best


def personal_slug(principal: Optional[Principal] = None) -> Optional[str]:
    """The folder name of the person's own published folder, or ``None``.

    Only a signed-in person has one: the name and a sign-in role are both
    needed. The shared gateway token, the CLI, the scheduler and an app with
    no sign-in act as no one in particular (and hold Manage everywhere), so
    there is no "mine" to point at. Under ``TRACEBI_LIBRARY_MOUNTS`` the
    library is several labelled roots with no place for it, so there is none.
    """
    from tracebi.drafts import slug_owner
    from tracebi.report_paths import parse_library_mounts

    who = principal or current_principal()
    if not who.name or not who.role or parse_library_mounts() is not None:
        return None
    return slug_owner(who.name.removeprefix("mcp:"))


def personal_folder(principal: Optional[Principal] = None) -> Optional[str]:
    """``my-published/<person>``: the person's own published folder, or ``None``
    when they have none (:func:`personal_slug`)."""
    slug = personal_slug(principal)
    return f"{PERSONAL_ROOT}/{slug}" if slug else None


def folder_accepts(name: str, *,
                   reports_dir: Optional[Union[str, os.PathLike]] = None) -> str:
    """What the folder of report *name* accepts: ``labelled`` (the default, and
    the answer where no ``_folder.yaml`` applies) or ``checkable``. The same
    nearest-file rule as the permissions; it binds everyone, admins included,
    because it is about what the folder holds, not who may act."""
    from tracebi.report_paths import locate, report_name_error

    if report_name_error(name):
        return ACCEPTS[1]
    root, relative = locate(name, reports_dir)
    rule = _nearest_rule(root, relative) if relative is not None else None
    return rule.accepts if rule is not None else ACCEPTS[0]


def folder_level(folder: str, principal: Optional[Principal] = None) -> int:
    """The level *principal* holds on library *folder* (a path, which need not
    exist yet): what they would hold on a report put straight inside it."""
    return granted_level(f"{folder}/x", principal)


def describe_folder(folder: str, *,
                    reports_dir: Optional[Union[str, os.PathLike]] = None) -> dict:
    """What the rule over *folder* says, for showing it (never for deciding):
    the ``_folder.yaml`` that applies (``file``, a path below its library root,
    or ``None`` when none does), the names granted each level, what the
    folder accepts, and whether the file is malformed (then it grants nothing)."""
    from tracebi.report_paths import locate

    root, relative = locate(f"{folder}/x", reports_dir)
    if relative is None:
        rule = None
    elif folder.startswith(PERSONAL_ROOT + "/"):
        parts = relative.split("/")[:-1]
        rule = next((r for d in range(len(parts), 1, -1)
                     if (r := _rule_in(root.joinpath(*parts[:d])))), None)
    else:
        rule = _nearest_rule(root, relative)
    if rule is None:
        return {"file": None, "grants": {}, "accepts": ACCEPTS[0], "malformed": False}
    return {"file": rule.path.relative_to(root).as_posix(),
            "grants": {k: sorted(v) for k, v in (rule.grants or {}).items()},
            "accepts": rule.accepts, "malformed": rule.grants is None}


def can(action: str, name: str, principal: Optional[Principal] = None, *,
        reports_dir: Optional[Union[str, os.PathLike]] = None) -> bool:
    """May *principal* do *action* (a level or a purpose) to report *name*?"""
    needed = LEVELS.index(action) if action in LEVELS else level_for_purpose(action)
    return granted_level(name, principal, reports_dir=reports_dir) >= needed


def require(action: str, name: str, principal: Optional[Principal] = None, *,
            reports_dir: Optional[Union[str, os.PathLike]] = None) -> None:
    """Raise :class:`NotPermitted` unless :func:`can`. For writes to a path
    that may not exist yet (a new report in a folder)."""
    if not can(action, name, principal, reports_dir=reports_dir):
        needed = LEVELS.index(action) if action in LEVELS else level_for_purpose(action)
        raise NotPermitted(name, needed)
