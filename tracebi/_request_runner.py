"""
Execute a request script (.py or .ipynb) and extract its Report object.

Used by ``tracebi dev`` and the web API's /api/requests endpoints to render
a request's report in memory, without relying on the script writing output
files. The script runs with ``__name__`` set to ``"tracebi_request"`` so its
``if __name__ == "__main__":`` block (typically file rendering) does not fire.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union


def execute_request(path: Union[str, Path]):
    """
    Run a request file and return the Report it defines.

    Prefers a module-level variable named ``report``; otherwise returns the
    first Report instance found in the script's namespace.

    Raises:
        LookupError: The script ran but defined no Report object.
        Exception:   Whatever the script itself raised.
    """
    from tracebi.reports.report import Report

    path = Path(path)
    if path.suffix == ".ipynb":
        from tracebi._notebook import notebook_to_source
        source = notebook_to_source(path)
    else:
        source = path.read_text(encoding="utf-8")

    ns: dict = {"__name__": "tracebi_request", "__file__": str(path)}
    exec(compile(source, str(path), "exec"), ns)  # noqa: S102

    report = ns.get("report")
    if isinstance(report, Report):
        return report
    for value in ns.values():
        if isinstance(value, Report):
            return value
    raise LookupError(
        f"No Report object found in {path.name}. Assign your report to a "
        "module-level variable, e.g. `report = Report(...)`."
    )
