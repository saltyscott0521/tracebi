"""
Demo app registry — the single wiring file for the demo app instance.

Everything registered here is visible to the web UI. The demo app is fully
self-contained: its DataModels live in this package's models/ subdirectory
(sales_model.py, wealth_model.py — both MemoryConnector-backed), its reports
in reports/, and its pipeline below. It runs identically from any working
directory, which is also what makes it a faithful miniature of a real
project: models/ + reports/ + a pipeline, wired through the one registry.

To add a new report: create reports/<name>.py with a
@register.report(...) decorated factory function. It will be picked up
automatically on the next server start (or dev-mode reload).
"""

import os

from tracebi.web.api.registry import registry
from tracebi import model_registry
from tracebi.model_registry import get_model
from tracebi.web.demo_app.pipeline import runner, pipeline_model
from tracebi.web.discovery import auto_discover

# ── Models (this package's models/, discovered by the package __init__) ───────
# The __init__ registers models/ with the shared model registry under their
# file stems, so get_model("sales_model") resolves regardless of cwd.

sales_model = get_model("sales_model")
wealth_model = get_model("wealth_model")

registry.add_model(sales_model, default=True)
registry.add_model(wealth_model)

# The pipeline's serving model (reads the silver tables) is defined in
# pipeline.py, not models/, so register it by name here — the medallion_revenue
# spec resolves it as "SalesPipelineModel" at render time.
model_registry.register(pipeline_model)
registry.add_model(pipeline_model)

# Surface each model's connectors on the Connectors page.
for _conn in (*sales_model.connectors(), *wealth_model.connectors()):
    registry.add_connector(_conn)

# ── Pipeline ──────────────────────────────────────────────────────────────────

registry.add_pipeline("sales", runner)

# AltsVault: a live, real-data pipeline (pull → transform → build) whose model
# reads the warehouse it sinks. See altsvault/__init__.py.
from tracebi.web.demo_app.altsvault import WAREHOUSE as _AV_WAREHOUSE  # noqa: E402
from tracebi.web.demo_app.altsvault.model import model as altsvault_model  # noqa: E402
from tracebi.web.demo_app.altsvault.pipeline import runner as altsvault_runner  # noqa: E402

model_registry.register(altsvault_model)
registry.add_model(altsvault_model)
registry.add_pipeline("altsvault", altsvault_runner)


def _bootstrap_altsvault() -> None:
    """First start with an API key and no warehouse yet: run the pipeline once,
    in the background, so the report exists before anyone presses Run."""
    try:
        altsvault_runner.run("build", refresh=True)
    except Exception as exc:  # noqa: BLE001 — the Refresh page shows the failed run
        print(f"[tracebi] altsvault bootstrap did not finish: {exc}")


if os.environ.get("ALTSVAULT_API_KEY") and not os.path.exists(_AV_WAREHOUSE):
    import threading

    threading.Thread(target=_bootstrap_altsvault, name="altsvault-bootstrap",
                     daemon=True).start()

# ── Reports (auto-discovered) ─────────────────────────────────────────────────
# Each .py file in reports/ that is not prefixed with _ is imported.
# The @register.report(...) decorator in each file fires on import,
# registering the factory with the registry above.

_reports_dir = os.path.join(os.path.dirname(__file__), "reports")
auto_discover(_reports_dir)
