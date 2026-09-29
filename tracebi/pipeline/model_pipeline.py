"""The pipeline every model gets: rebuild its data, then rebuild its reports.

    from tracebi import model_pipeline
    runner = model_pipeline("portfolio_model", transform="holdings_transform")

Reports are organised by model — ``reports/<model>/`` — so a model, the
transform that fills its warehouse, and the reports that read it belong
together, and one pipeline runs the whole chain:

* **transform**: ``tracebi run-transform <transform>``, the phase ① script that
  sinks the model's tables (and checks their sink contract).
* **build**: ``tracebi report build`` for every report in ``reports/<model>/``,
  each with its receipt.

Both are ordinary pipeline steps (see ``PipelineRunner.register_step``), so they
appear on the Pipelines page and in ``tracebi run-pipeline`` with run history.
Run from the project root, like every other ``tracebi`` command.
"""

from __future__ import annotations

import contextlib
import io
import os
from typing import Optional

from tracebi.pipeline.runner import PipelineRunner


def reports_of(model: str, reports_dir: str = "reports") -> list[str]:
    """The names of the reports in ``reports/<model>/``: each package (a folder
    with a ``report.json``) and each ``*.json`` spec, as ``<model>/<name>``."""
    folder = os.path.join(reports_dir, model)
    if not os.path.isdir(folder):
        return []
    names = []
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "report.json")):
            names.append(f"{model}/{entry}")
        elif entry.endswith(".json") and os.path.isfile(path):
            names.append(f"{model}/{entry[:-5]}")
    return names


def _cli(*args: str) -> str:
    """Run ``tracebi <args>`` in-process; return its output, or raise with it."""
    from tracebi import cli

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = cli.main(list(args))
        except SystemExit as exc:      # a script that ends with sys.exit(): a
            code = exc.code if isinstance(exc.code, int) else int(bool(exc.code))  # failed step, not a dead runner
    if code:
        raise RuntimeError(f"tracebi {' '.join(args)} failed:\n{out.getvalue().strip()}")
    return out.getvalue()


def model_pipeline(
    model: str,
    transform: str,
    *,
    db_url: Optional[str] = None,
    reports_dir: str = "reports",
) -> PipelineRunner:
    """A runner with ``transform`` → ``build`` steps for *model*.

    Args:
        model:       The model's name (its file in ``models/`` and its folder in
                     ``reports/``).
        transform:   The phase ① transform to run, as ``tracebi run-transform`` names it.
        db_url:      Where run history is kept (default ``data/<model>_runs.db``).
        reports_dir: The project's reports folder.
    """
    from tracebi.model_registry import get_model

    if db_url is None:
        os.makedirs("data", exist_ok=True)
        db_url = f"sqlite:///{os.path.abspath(os.path.join('data', model + '_runs.db'))}"

    def release() -> None:
        # The model holds its warehouse open read-only; the transform needs it
        # read-write, and DuckDB allows one or the other in a process.
        get_model(model).disconnect()

    def run_transform():
        release()
        _cli("run-transform", transform)
        release()
        return len(get_model(model).info()["tables"])          # tables now in place

    def build_reports():
        # `run-pipeline` keeps going after a failure so it can report them all;
        # a report rebuilt on a warehouse the transform just failed to refresh
        # would look current and not be.
        last = runner.run_history("transform", limit=1)
        if last and last[0]["status"] != "success":
            raise RuntimeError("the last transform did not succeed; not rebuilding "
                               "reports from a warehouse it failed to refresh")
        names = reports_of(model, reports_dir)
        if not names:
            raise RuntimeError(f"no reports in {os.path.join(reports_dir, model)}/")
        for name in names:
            _cli("report", "build", name)
        return len(names)                                       # reports rebuilt

    runner = PipelineRunner(db_url=db_url)
    runner.register_step("transform", run_transform)
    runner.register_step("build", build_reports, depends_on="transform")
    return runner
