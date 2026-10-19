"""
Run the three-phase workflow end to end, up to the point the web server takes
over.

    python run_workflow.py

    ⓪  INPUT        inputs/holdings.csv                (a raw pull; API export / CSV / SQL)
    ①  TRANSFORM    transforms/holdings_transform.sql  → data/warehouse.duckdb
                    transforms/saas_transform.py       → data/warehouse.duckdb
                    transforms/affordability_transform.py → data/housing.duckdb
    ②  MODEL        models/portfolio_model.yaml          (a star schema over the sink)
    ③  REPORT       reports/portfolio_model/portfolio_dashboard/        → data/portfolio_dashboard.html

This script does phase ① (build the warehouse) and renders phase ③ once, offline,
so you can open the HTML directly. To serve the dashboard on the front end:

    python -m tracebi.web.run          # then open http://127.0.0.1:8000 → Reports

The server auto-discovers models/ and reports/; it reads the same warehouse.
"""

from __future__ import annotations

import importlib.util
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load(path: str):
    """Import a module from a file path without needing it on sys.path."""
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    raw = os.path.join(ROOT, "inputs", "holdings.csv")

    # Phase ① — ensure a raw input exists, then transform → sink.
    if not os.path.exists(raw):
        print("· generating a messy source file into inputs/")
        _load(os.path.join(ROOT, "inputs", "generate_raw.py"))

    # The SQL form: statements run top to bottom in one fresh connection, then
    # the sink contract beside it (holdings_transform.contract.yaml).
    # transforms/holdings_transform_pandas.py sinks the same tables in pandas.
    print("① transform → sink")
    from tracebi.transforms import run_transform
    form = run_transform(os.path.join(ROOT, "transforms", "holdings_transform.sql"), root=ROOT)
    print(f"    form: {form}")

    # The SaaS metrics sample (reports/saas_model) sinks its own tables into the
    # same warehouse: a billing export cleaned to one row per account per month.
    # The transform is a plain script; loading it runs it top to bottom.
    print("① saas transform → sink")
    _load(os.path.join(ROOT, "transforms", "saas_transform.py"))

    # The housing sample (reports/housing_model/affordability) has its own input
    # and warehouse: public annual series, sunk to data/housing.duckdb.
    print("① housing transform → sink")
    housing = _load(os.path.join(ROOT, "transforms", "affordability_transform.py"))
    print(f"    {housing.run()}")

    # Phase ② + ③ — build the model, render the dashboard offline.
    os.environ.setdefault("TRACEBI_MODELS_DIR", os.path.join(ROOT, "models"))
    from tracebi.model_registry import get_model, list_models
    from tracebi.reports.template_package import TemplatePackage

    print("② model")
    models = {name: get_model(name) for name in list_models()}
    print(f"    loaded {sorted(models)}")

    print("③ dashboard → html")
    package = os.path.join(ROOT, "reports", "portfolio_model", "portfolio_dashboard")
    out = os.path.join(ROOT, "data", "portfolio_dashboard.html")
    TemplatePackage(package).render(models, out)
    print(f"    wrote {out}")

    print("\nServe it on the front end:")
    print("    python -m tracebi.web.run   →   http://127.0.0.1:8000  (Reports)")


if __name__ == "__main__":
    main()
