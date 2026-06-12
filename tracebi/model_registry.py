"""
Standalone model registry — works without the web layer.

Define a model once in ``models/<name>.py`` and import it from any notebook
or script::

    from tracebi.model_registry import get_model, list_models

    model = get_model("sales")        # lazy-loads models/sales.py on first call
    print(list_models())              # ["banking", "sales"]

Each model file must expose a module-level ``model`` variable (a DataModel).
The registry auto-discovers ``models/`` in the current working directory on
first access, or you can point it at a specific path with ``auto_discover()``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Any, Optional


class ModelRegistry:
    """
    Lazy-loading registry for DataModel instances.

    Use the module-level helpers (``get_model``, ``list_models``, etc.) rather
    than this class directly — they target the process-global registry and
    handle auto-discovery from ``models/`` automatically.
    """

    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._paths: dict[str, str] = {}      # stem -> absolute file path
        self._default: Optional[str] = None

    # ── Registration ───────────────────────────────────────────────────────

    def register(self, model: Any, default: bool = False) -> None:
        """Explicitly register a DataModel instance."""
        self._models[model.name] = model
        if default or self._default is None:
            self._default = model.name

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
        """
        Return a model by name, loading its file on first access.

        *name* matches either the file stem (e.g. ``"sales"`` for
        ``models/sales.py``) or the DataModel's ``.name`` attribute.
        """
        if name not in self._models:
            if name in self._paths:
                self._load(name, self._paths[name])
            else:
                available = sorted(set(self._models) | set(self._paths))
                raise KeyError(
                    f"Model '{name}' not found. Available: {available}"
                )
        return self._models[name]

    def get_default(self) -> Any:
        if self._default is None:
            raise KeyError("No default model registered or discovered.")
        return self.get(self._default)

    def list_models(self) -> list[str]:
        """Names of all known models (registered + on-disk but not yet loaded)."""
        return sorted(set(self._models) | set(self._paths))

    # ── Private ────────────────────────────────────────────────────────────

    def _load(self, stem: str, path: str) -> None:
        mod_name = f"tracebi_model_{stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load model file: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if not hasattr(module, "model"):
            raise AttributeError(
                f"Model file '{path}' must define a module-level 'model' variable "
                "(a DataModel instance)."
            )
        loaded = module.model
        self._models[stem] = loaded
        if loaded.name != stem:
            # Also index by the DataModel's own .name so both work
            self._models[loaded.name] = loaded
        if self._default is None:
            self._default = stem


# ── Process-global registry ────────────────────────────────────────────────

_registry = ModelRegistry()
_auto_discovered = False


def _ensure_discovered() -> None:
    global _auto_discovered
    if _auto_discovered:
        return
    _auto_discovered = True
    d = os.path.join(os.getcwd(), "models")
    if os.path.isdir(d):
        _registry.auto_discover(d)


# ── Public API ─────────────────────────────────────────────────────────────

def get_model(name: str) -> Any:
    """Return a model by name, auto-discovering ``models/`` in cwd if needed."""
    _ensure_discovered()
    return _registry.get(name)


def get_default_model() -> Any:
    """Return the default model (first discovered, or explicitly set via ``set_default``)."""
    _ensure_discovered()
    return _registry.get_default()


def list_models() -> list[str]:
    """List all known model names (discovered + explicitly registered)."""
    _ensure_discovered()
    return _registry.list_models()


def register(model: Any, default: bool = False) -> None:
    """Explicitly register a DataModel instance with the global registry."""
    _registry.register(model, default=default)


def set_default(name: str) -> None:
    """Set the default model by name."""
    _registry.set_default(name)


def auto_discover(path: str) -> list[str]:
    """Scan *path* for model files and record them for lazy loading."""
    return _registry.auto_discover(path)
