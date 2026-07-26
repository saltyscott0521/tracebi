"""
``tracebi.web`` — auto-discovery helpers and the registration facade.

Kept for backward compatibility: ``register`` now lives in the library
proper and is better imported as ``from tracebi import register``, since
the registry is no longer part of the web layer. This spelling still
works and appears throughout the scaffolds and docs.

Notebook usage::

    from tracebi import register          # preferred
    from tracebi.web import register      # equivalent, original spelling

    register.connector(my_connector)
    register.model(my_model, default=True)

    @register.report("weekly_sales", description="…")
    def weekly_sales():
        return Report(...)

    @register.scheduled("daily_kpis", cron="0 7 * * *")
    def daily_kpis():
        return Report(...)

    register.auto_discover("requests/")

These calls populate the process-global singleton in
:mod:`tracebi.registry`. No web install is required — the same code works
in a bare notebook and under the running server, and lookups fall back to
the project-root ``models/`` and ``pipelines/`` directories.
"""

from __future__ import annotations

from tracebi.web.discovery import auto_discover, reload_modules
from tracebi.web.register import register

__all__ = ["register", "auto_discover", "reload_modules"]
