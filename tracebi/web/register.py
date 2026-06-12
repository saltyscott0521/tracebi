"""
``tracebi.web.register`` — thin facade over the running web registry.

All functions resolve the registry lazily so importing this module never
forces the web stack to load. Errors point users at the right extras key
when the web layer is missing.
"""

from __future__ import annotations

from typing import Callable, Optional


def _registry():
    try:
        from web.api.registry import registry as _r
    except ImportError as exc:
        raise ImportError(
            "tracebi.web helpers require the web layer. "
            "Install with: pip install 'tracebi[web]', and make sure your "
            "Python process can import the 'web' package."
        ) from exc
    return _r


class _Register:
    """
    Callable namespace exposed as ``tracebi.web.register``.

    Methods mirror the registry singleton so notebook authors can register
    resources without learning the FastAPI layout.
    """

    def connector(self, connector) -> "_Register":
        _registry().add_connector(connector)
        return self

    def model(self, model, default: bool = False) -> "_Register":
        _registry().add_model(model, default=default)
        return self

    def set_default_model(self, name: str) -> "_Register":
        _registry().set_default_model(name)
        return self

    def get_default_model(self):
        """Return the default DataModel — web registry first, then models/ on disk."""
        try:
            return _registry().get_default_model()
        except ImportError:
            from tracebi.model_registry import get_default_model as _get
            return _get()

    def get_model(self, name: str):
        """Return a model by name — web registry first, then models/ on disk."""
        try:
            return _registry().get_model(name)
        except ImportError:
            from tracebi.model_registry import get_model as _get
            return _get(name)

    def pipeline(self, name: str, runner) -> "_Register":
        _registry().add_pipeline(name, runner)
        return self

    def get_runner(self, name: str):
        """Return a runner by name — web registry first, then pipelines/ on disk."""
        try:
            result = _registry().get_pipeline(name)
            if result is not None:
                return result
            raise KeyError(name)
        except ImportError:
            pass
        from tracebi.pipeline_registry import get_runner as _get
        return _get(name)

    def dashboard(self, name: str, server, description: str = "") -> "_Register":
        _registry().add_dashboard(name, server, description=description)
        return self

    def report(self, name: str, description: str = "") -> Callable:
        """Decorator: register a zero-arg report factory."""
        return _registry().report(name, description=description)

    def scheduled(
        self,
        name: str,
        cron: str,
        description: str = "",
    ) -> Callable:
        """Decorator: register a report factory tagged with a cron schedule."""
        return _registry().scheduled(name, cron=cron, description=description)

    def add_report(
        self,
        name: str,
        factory: Callable,
        description: str = "",
    ) -> "_Register":
        _registry().add_report(name, factory, description=description)
        return self

    def auto_discover(self, path: str, package: Optional[str] = None) -> list[str]:
        """Discover and import request modules in *path*."""
        from tracebi.web.discovery import auto_discover
        return auto_discover(path, package=package)


register = _Register()
