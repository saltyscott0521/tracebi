"""
Folder-based auto-discovery for request and scheduled scripts.

Two entry points:

* :func:`auto_discover` — import every ``*.py`` and ``*.ipynb`` file in a
  directory (non-recursive, skips ``_*``).  Decorators inside
  (``@registry.report``, ``@registry.scheduled``) fire as a side effect of
  import. Notebook code cells are concatenated into a script first; line
  magics and shell escapes are silently dropped.

* :func:`reload_modules` — re-import the modules previously discovered
  via :func:`auto_discover`. Used by the optional dev-mode reload endpoint
  to pick up edits without restarting the server.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from typing import Optional


# Track everything we've imported so we can reload it later.
_discovered: dict[str, str] = {}  # module_name -> file path


# Per-file outcome of every discovery attempt, in order. Discovery is
# convention-based and quiet by nature: a file in the wrong place, or one
# that raises on import, simply never appears. Recording what happened is
# the difference between "why isn't my report showing up?" and an answer.
_outcomes: list[dict] = []


def discovery_report() -> list[dict]:
    """
    What happened to every file discovery looked at.

    Each entry is ``{directory, file, module, status, reason}`` where status
    is ``registered``, ``skipped``, or ``failed``. Consumed by
    ``tracebi validate``, ``GET /api/discovery``, and agent tooling.
    """
    return [dict(o) for o in _outcomes]


def clear_discovery_report() -> None:
    """Forget recorded outcomes (used between test runs and dev reloads)."""
    _outcomes.clear()


def _register_spec_file(full_path: str, stem: str) -> dict:
    """
    Register a ``reports/<name>.json`` report spec.

    The factory resolves models and builds the report at *call* time, not at
    discovery time. Two reasons. Discovery runs at server startup, where doing
    real query work would be the same mistake the demo pipeline made — and a
    model the spec names may be registered after this file is scanned, so
    binding eagerly would make discovery order significant.

    Validation is deliberately structural only: the schema, the section types,
    the shape of each data reference. Checking a spec *against* its models
    needs the models, so that is left to ``tracebi spec validate`` and to the
    first run, which reports a real error rather than a startup failure.
    """
    from tracebi.registry import registry
    from tracebi.spec import ReportSpec

    try:
        spec = ReportSpec.from_json(open(full_path, encoding="utf-8").read())
    except Exception as exc:  # noqa: BLE001 — one bad file must not stop startup
        return {"status": "failed", "module": stem,
                "reason": f"{type(exc).__name__}: {exc}"}

    problems = [p for p in spec.validate().get("errors", [])]
    if problems:
        return {"status": "failed", "module": stem,
                "reason": "; ".join(str(p) for p in problems[:3])}

    def factory(_spec=spec):
        from tracebi.model_registry import get_model, list_models
        models = {}
        for name in list_models():
            try:
                m = get_model(name)
            except Exception:  # noqa: BLE001 — a broken model is that model's problem
                continue
            # A DataRef may name either the file stem (sales_model) or the
            # model's own name (SalesModel); accept both so an author is not
            # made to care which one they saw.
            models[name] = m
            models[getattr(m, "name", name)] = m
        return _spec.build(models=models)

    registry.add_report(stem, factory, spec.description or "")
    return {"status": "registered", "module": stem}


def _register_template_package(dir_path: str, stem: str) -> dict:
    """
    Register a freeform report package — ``reports/<name>/`` holding
    ``report.json`` + ``template.html`` (architecture §7, lane B).

    The same contract as :func:`_register_spec_file`: a zero-arg factory that
    resolves models at *call* time, not at discovery time, and flows through
    ``registry.add_report`` unchanged. A package is *a name and a zero-arg
    callable*, exactly like every other report — so it lists on the Reports
    page and in ``registry.list_reports`` beside specs and code factories.

    Loading validates only the *structure* of the package and its data
    bindings (``TemplatePackage.__init__`` reuses ``DataRef`` parsing and
    touches no model). Resolving a binding against its model — and the freeform
    render of ``template.html`` — happens in ``tracebi report build`` and at
    factory-call time, so a model registered after this scan still resolves.
    The factory returns the package's carrier :class:`Report` (the synthetic
    sections whose fingerprints back the receipt); the self-contained freeform
    ``.html`` is produced by the build step, not the web report-run path.
    """
    from tracebi.registry import registry
    from tracebi.reports.template_package import TemplatePackage

    try:
        pkg = TemplatePackage(dir_path)
    except Exception as exc:  # noqa: BLE001 — one bad package must not stop startup
        return {"status": "failed", "module": stem,
                "reason": f"{type(exc).__name__}: {exc}"}

    def factory(_pkg=pkg):
        from tracebi.model_registry import get_model, list_models
        models = {}
        for name in list_models():
            try:
                m = get_model(name)
            except Exception:  # noqa: BLE001 — a broken model is that model's problem
                continue
            # Accept either the file stem or the model's own name, as the spec
            # factory does — an author should not have to care which they saw.
            models[name] = m
            models[getattr(m, "name", name)] = m
        report, _ = _pkg.build(models)
        return report

    # Tag the factory with its package directory so the web layer can detect
    # an artifact-backed report (via registry.report_factory) and serve the
    # REAL artifact render — embedded data, figure claims, schema-2 manifest
    # — instead of the carrier (architecture v2 §2.3, web parity). The
    # factory contract itself is unchanged: a name and a zero-arg callable.
    factory._tracebi_package_dir = dir_path

    registry.add_report(stem, factory, pkg.description or "")
    return {"status": "registered", "module": stem}


def auto_discover(
    path: str,
    package: Optional[str] = None,
    strict: bool = False,
) -> list[str]:
    """
    Import every ``*.py`` / ``*.ipynb`` file in *path* (non-recursive,
    skips ``_*``).

    Args:
        path:    Directory to scan. Relative paths are resolved against the
                 current working directory.
        package: Optional package name to register the modules under. When
                 omitted, modules are imported under synthetic names
                 ``tracebi_request_<filename>`` so they do not collide with
                 anything on ``sys.path``.
        strict:  Re-raise the first import error instead of recording it.
                 Off by default so one broken file cannot stop a server
                 from starting — the failure is recorded in
                 :func:`discovery_report` and surfaced by
                 ``tracebi validate``.

    Returns:
        List of successfully imported module names.
    """
    if not os.path.isdir(path):
        _outcomes.append({
            "directory": path, "file": None, "module": None,
            "status": "skipped", "reason": "directory does not exist",
        })
        return []


    discovered: list[str] = []
    for entry in sorted(os.listdir(path)):
        full = os.path.join(path, entry)
        record = {"directory": path, "file": entry, "module": None}

        if entry.startswith("_"):
            _outcomes.append({**record, "status": "skipped",
                              "reason": "name starts with '_'"})
            continue
        is_py = entry.endswith(".py")
        is_nb = entry.endswith(".ipynb")
        is_spec = entry.endswith(".json")

        if is_spec:
            # A report as data rather than as code. Registered without
            # importing anything, which is the point: a spec is a bounded
            # document that can be checked before it runs, where a .py file
            # is arbitrary code that has already run by the time you see it.
            outcome = _register_spec_file(full, stem=entry[: -len(".json")])
            _outcomes.append({**record, **outcome})
            if outcome["status"] == "registered":
                discovered.append(outcome["module"])
            continue

        if not (is_py or is_nb):
            if not os.path.isdir(full):
                _outcomes.append({**record, "status": "skipped",
                                  "reason": "not a .py, .ipynb or .json file"})
            elif (os.path.isfile(os.path.join(full, "report.json"))
                  and os.path.isfile(os.path.join(full, "template.html"))):
                # A freeform report package: report.json + template.html in a
                # subdirectory. Registered like a spec file; other
                # subdirectories are still skipped below.
                outcome = _register_template_package(full, stem=entry)
                _outcomes.append({**record, **outcome})
                if outcome["status"] == "registered":
                    discovered.append(outcome["module"])
            else:
                _outcomes.append({**record, "status": "skipped",
                                  "reason": "subdirectories are not scanned"})
            continue

        stem = entry[: -len(".ipynb") if is_nb else -3]
        mod_name = f"{package}.{stem}" if package else f"tracebi_request_{stem}"
        record["module"] = mod_name

        try:
            if is_nb:
                from tracebi._notebook import notebook_to_source
                source = notebook_to_source(full)
                code = compile(source, full, "exec")
                module = type(sys)("tracebi_request_nb_" + stem)
                module.__file__ = full
                sys.modules[mod_name] = module
                exec(code, module.__dict__)  # noqa: S102
            else:
                spec = importlib.util.spec_from_file_location(mod_name, full)
                if spec is None or spec.loader is None:
                    _outcomes.append({**record, "status": "failed",
                                      "reason": "could not build an import spec"})
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = module
                spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — recorded, and re-raised if strict
            sys.modules.pop(mod_name, None)
            _outcomes.append({
                **record, "status": "failed",
                "reason": f"{type(exc).__name__}: {exc}",
            })
            if strict:
                raise
            continue

        discovered.append(mod_name)
        _discovered[mod_name] = full
        _outcomes.append({**record, "status": "registered", "reason": None})
    return discovered


def reload_modules() -> list[str]:
    """
    Re-import every module previously imported through :func:`auto_discover`.

    Useful for dev-mode: edit a request script, hit the reload endpoint,
    re-evaluate registrations without bouncing the server.
    """
    import time

    importlib.invalidate_caches()
    reloaded: list[str] = []
    for mod_name, path in list(_discovered.items()):
        if not os.path.isfile(path):
            continue
        # Bump mtime forward so Python's pyc cache (1s-resolution) cannot
        # shadow rapid back-to-back edits.
        future = time.time() + 2
        os.utime(path, (future, future))
        # Drop any stale .pyc that might already point at the old content.
        cache = importlib.util.cache_from_source(path)
        if cache and os.path.isfile(cache):
            try:
                os.remove(cache)
            except OSError:
                pass

        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        reloaded.append(mod_name)
    return reloaded


def discovered_modules() -> dict[str, str]:
    """Read-only view of currently-discovered modules → file path."""
    return dict(_discovered)
