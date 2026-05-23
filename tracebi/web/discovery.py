"""
Folder-based auto-discovery for request and scheduled scripts.

Two entry points:

* :func:`auto_discover` — import every ``*.py`` file in a directory
  (non-recursive, skips ``_*``).  Decorators inside (``@registry.report``,
  ``@registry.scheduled``) fire as a side effect of import.

* :func:`reload_modules` — re-import the modules previously discovered
  via :func:`auto_discover`. Used by the optional dev-mode reload endpoint
  to pick up edits without restarting the server.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from typing import Optional


# Track everything we've imported so we can reload it later.
_discovered: dict[str, str] = {}  # module_name -> file path


def auto_discover(path: str, package: Optional[str] = None) -> list[str]:
    """
    Import every ``*.py`` file in *path* (non-recursive, skips ``_*``).

    Args:
        path:    Directory to scan. Relative paths are resolved against the
                 current working directory.
        package: Optional package name to register the modules under. When
                 omitted, modules are imported under synthetic names
                 ``tracebi_request_<filename>`` so they do not collide with
                 anything on ``sys.path``.

    Returns:
        List of imported module names. Useful for logging on startup.
    """
    if not os.path.isdir(path):
        return []

    discovered: list[str] = []
    for entry in sorted(os.listdir(path)):
        if not entry.endswith(".py") or entry.startswith("_"):
            continue
        full = os.path.join(path, entry)
        stem = entry[:-3]
        mod_name = f"{package}.{stem}" if package else f"tracebi_request_{stem}"
        spec = importlib.util.spec_from_file_location(mod_name, full)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        discovered.append(mod_name)
        _discovered[mod_name] = full
    return discovered


def reload_modules() -> list[str]:
    """
    Re-import every module previously imported through :func:`auto_discover`.

    Useful for dev-mode: edit a request script, hit the reload endpoint,
    re-evaluate registrations without bouncing the server.
    """
    import time

    importlib.invalidate_caches()
    reloaded: list[str] = []
    for mod_name, path in list(_discovered.items()):
        if not os.path.isfile(path):
            continue
        # Bump mtime forward so Python's pyc cache (1s-resolution) cannot
        # shadow rapid back-to-back edits.
        future = time.time() + 2
        os.utime(path, (future, future))
        # Drop any stale .pyc that might already point at the old content.
        cache = importlib.util.cache_from_source(path)
        if cache and os.path.isfile(cache):
            try:
                os.remove(cache)
            except OSError:
                pass

        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        reloaded.append(mod_name)
    return reloaded


def discovered_modules() -> dict[str, str]:
    """Read-only view of currently-discovered modules → file path."""
    return dict(_discovered)
