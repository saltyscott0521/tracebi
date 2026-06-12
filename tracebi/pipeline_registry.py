"""
Standalone pipeline registry — works without the web layer.

Define a PipelineRunner once in ``pipelines/<name>.py`` and reference it from
any script or notebook::

    from tracebi.pipeline_registry import get_runner, list_pipelines

    runner = get_runner("sales")      # lazy-loads pipelines/sales.py on first call
    runner.run("orders_silver")
    print(list_pipelines())           # ["sales"]

Each pipeline file must expose a module-level ``runner`` variable (a PipelineRunner).
The registry auto-discovers ``pipelines/`` in the current working directory on
first access, or you can point it at a specific path with ``auto_discover()``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Optional


class PipelineRegistry:
    """
    Lazy-loading registry for PipelineRunner instances.

    Use the module-level helpers (``get_runner``, ``list_pipelines``, etc.)
    rather than this class directly — they target the process-global registry
    and handle auto-discovery from ``pipelines/`` automatically.
    """

    def __init__(self) -> None:
        self._runners: dict[str, Any] = {}
        self._paths: dict[str, str] = {}      # stem -> absolute file path
        self._default: Optional[str] = None

    # ── Registration ───────────────────────────────────────────────────────

    def register(self, name: str, runner: Any, default: bool = False) -> None:
        """Explicitly register a PipelineRunner under *name*."""
        self._runners[name] = runner
        if default or self._default is None:
            self._default = name

    def set_default(self, name: str) -> None:
        self._default = name

    # ── Discovery ──────────────────────────────────────────────────────────

    def auto_discover(self, path: str) -> list[str]:
        """
        Record all ``*.py`` files in *path* for lazy loading.

        Non-recursive; skips files whose names begin with ``_``. Files are
        not imported until ``get()`` is called for that name.

        Returns the list of discovered stems (file names without ``.py``).
        """
        if not os.path.isdir(path):
            return []
        found: list[str] = []
        for entry in sorted(os.listdir(path)):
            if entry.startswith("_") or not entry.endswith(".py"):
                continue
            stem = entry[:-3]
            self._paths[stem] = os.path.join(path, entry)
            if self._default is None:
                self._default = stem
            found.append(stem)
        return found

    # ── Lookup ─────────────────────────────────────────────────────────────

    def get(self, name: str) -> Any:
        """Return a runner by name, loading its file on first access."""
        if name not in self._runners:
            if name in self._paths:
                self._load(name, self._paths[name])
            else:
                available = sorted(set(self._runners) | set(self._paths))
                raise KeyError(
                    f"Pipeline '{name}' not found. Available: {available}"
                )
        return self._runners[name]

    def get_default(self) -> Any:
        if self._default is None:
            raise KeyError("No default pipeline registered or discovered.")
        return self.get(self._default)

    def list_pipelines(self) -> list[str]:
        """Names of all known pipelines (registered + on-disk but not yet loaded)."""
        return sorted(set(self._runners) | set(self._paths))

    # ── Private ────────────────────────────────────────────────────────────

    def _load(self, stem: str, path: str) -> None:
        mod_name = f"tracebi_pipeline_{stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load pipeline file: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if not hasattr(module, "runner"):
            raise AttributeError(
                f"Pipeline file '{path}' must define a module-level 'runner' variable "
                "(a PipelineRunner instance)."
            )
        self._runners[stem] = module.runner


# ── Process-global registry ────────────────────────────────────────────────

_registry = PipelineRegistry()
_auto_discovered = False


def _ensure_discovered() -> None:
    global _auto_discovered
    if _auto_discovered:
        return
    _auto_discovered = True
    d = os.path.join(os.getcwd(), "pipelines")
    if os.path.isdir(d):
        _registry.auto_discover(d)


# ── Public API ─────────────────────────────────────────────────────────────

def get_runner(name: str) -> Any:
    """Return a runner by name, auto-discovering ``pipelines/`` in cwd if needed."""
    _ensure_discovered()
    return _registry.get(name)


def get_default_runner() -> Any:
    """Return the default runner (first discovered, or explicitly set via ``set_default``)."""
    _ensure_discovered()
    return _registry.get_default()


def list_pipelines() -> list[str]:
    """List all known pipeline names (discovered + explicitly registered)."""
    _ensure_discovered()
    return _registry.list_pipelines()


def register(name: str, runner: Any, default: bool = False) -> None:
    """Explicitly register a PipelineRunner with the global registry."""
    _registry.register(name, runner, default=default)


def set_default(name: str) -> None:
    """Set the default pipeline by name."""
    _registry.set_default(name)


def auto_discover(path: str) -> list[str]:
    """Scan *path* for pipeline files and record them for lazy loading."""
    return _registry.auto_discover(path)
