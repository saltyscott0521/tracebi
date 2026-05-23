"""
``tracebi.web`` — helpers for the TraceBi web layer.

This module gives library users and notebook authors a clean entry point
to the running web server's resource registry without importing the web
application package directly.

Notebook usage::

    from tracebi.web import register

    register.connector(my_connector)
    register.model(my_model)

    @register.report("weekly_sales", description="…")
    def weekly_sales():
        return Report(...)

    register.auto_discover("requests/")

These calls populate the singleton in ``web.api.registry`` if the web
package is importable (i.e. you installed ``tracebi[web]``). When the
web package is not available, an informative ``ImportError`` is raised.
"""

from __future__ import annotations

from tracebi.web.discovery import auto_discover
from tracebi.web.register import register

__all__ = ["register", "auto_discover"]
