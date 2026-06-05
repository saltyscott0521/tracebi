"""
Demo app registry — the single wiring file for the demo app instance.

Everything registered here is visible to the web UI. Reports live in
reports/ and are auto-discovered; all other resources (connector, model,
dashboard, pipeline) are registered explicitly below.

To add a new report: create reports/<name>.py with a
@register.report(...) decorated factory function. It will be picked up
automatically on the next server start (or dev-mode reload).
"""

import os

from web.api.registry import registry
from web.demo_app.model import connector, model
from web.demo_app.pipeline import runner
from web.demo_app.dashboard import dashboard_server
from tracebi.web.discovery import auto_discover

# ── Connector + Model ─────────────────────────────────────────────────────────

registry.add_connector(connector)
registry.add_model(model, default=True)

# ── Dashboard ─────────────────────────────────────────────────────────────────

registry.add_dashboard(
    "sales",
    dashboard_server,
    description="Live sales overview with associative region and product filters.",
)

# ── Pipeline ──────────────────────────────────────────────────────────────────

registry.add_pipeline("sales", runner)

# ── Reports (auto-discovered) ─────────────────────────────────────────────────
# Each .py file in reports/ that is not prefixed with _ is imported.
# The @register.report(...) decorator in each file fires on import,
# registering the factory with the registry above.

_reports_dir = os.path.join(os.path.dirname(__file__), "reports")
auto_discover(_reports_dir)
