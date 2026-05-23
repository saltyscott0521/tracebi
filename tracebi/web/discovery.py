"""
Folder-based auto-discovery for request scripts.

Scans a directory for ``*.py`` files (skipping anything starting with
``_``) and imports each. Any ``@registry.report(...)`` decorator inside
the file triggers registration as a side effect of import.

Usage::

    from tracebi.web import auto_discover
    auto_discover("requests/")
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Optional


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
    return discovered
