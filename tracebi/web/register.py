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

    def model(self, model) -> "_Register":
        _registry().add_model(model)
        return self

    def pipeline(self, name: str, runner) -> "_Register":
        _registry().add_pipeline(name, runner)
        return self

    def dashboard(self, name: str, server, description: str = "") -> "_Register":
        _registry().add_dashboard(name, server, description=description)
        return self

    def report(self, name: str, description: str = "") -> Callable:
        """Decorator: register a zero-arg report factory."""
        return _registry().report(name, description=description)

    def add_report(
        self,
        name: str,
        factory: Callable,
        description: str = "",
    ) -> "_Register":
        _registry().add_report(name, factory, description=description)
        return self

    def auto_discover(self, path: str, package: Optional[str] = None) -> list[str]:
        """Discover and import request modules in *path*. See :func:`auto_discover`."""
        from tracebi.web.discovery import auto_discover
        return auto_discover(path, package=package)


register = _Register()
