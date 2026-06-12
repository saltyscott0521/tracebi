"""
Demo app registry — the single wiring file for the demo app instance.

Everything registered here is visible to the web UI. The DataModels
themselves live at the project root in models/ (sales_model.py,
wealth_model.py) and are pulled in via the shared model registry — the web
layer runs on top of those base files. Reports live in reports/ and are
auto-discovered; the dashboard and pipeline are registered explicitly below.

To add a new report: create reports/<name>.py with a
@register.report(...) decorated factory function. It will be picked up
automatically on the next server start (or dev-mode reload).
"""

import os

from web.api.registry import registry
from tracebi.model_registry import get_model
from web.demo_app.pipeline import runner
from web.demo_app.dashboard import dashboard_server
from tracebi.web.discovery import auto_discover

# ── Models (defined in models/, shared with notebooks and scripts) ────────────

sales_model = get_model("sales_model")
wealth_model = get_model("wealth_model")

registry.add_model(sales_model, default=True)
registry.add_model(wealth_model)

# Surface each model's connectors on the Connectors page.
for _conn in (*sales_model.connectors(), *wealth_model.connectors()):
    registry.add_connector(_conn)

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
