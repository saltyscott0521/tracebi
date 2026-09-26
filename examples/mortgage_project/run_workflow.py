"""
Run the mortgage sample end to end.

    python run_workflow.py

    ⓪  INPUT        inputs/housing_history.csv          (refresh: python inputs/fetch_data.py)
    ①  TRANSFORM    transforms/affordability_transform.py → data/warehouse.duckdb
    ②  MODEL        models/housing_model.py              (one row per year)
    ③  REPORT       reports/affordability/               → output/affordability.html

Then open output/affordability.html, or serve the project:

    tracebi serve        # Reports → Then vs Now
"""

from __future__ import annotations

import importlib.util
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    print("① transform → sink")
    summary = _load(os.path.join(ROOT, "transforms", "affordability_transform.py")).run()
    print(f"    {summary}")

    os.environ.setdefault("TRACEBI_MODELS_DIR", os.path.join(ROOT, "models"))
    from tracebi.model_registry import get_model, list_models
    from tracebi.reports.template_package import TemplatePackage

    print("② model")
    models = {name: get_model(name) for name in list_models()}
    print(f"    loaded {sorted(models)}")

    print("③ report → html")
    out = os.path.join(ROOT, "output", "affordability.html")
    TemplatePackage(os.path.join(ROOT, "reports", "affordability")).render(models, out)
    print(f"    wrote {out}")


if __name__ == "__main__":
    main()
