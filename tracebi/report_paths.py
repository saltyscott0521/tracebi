"""Report names are paths below ``reports/``.

A report at the top of the reports folder is named ``weekly_summary``; one in a
folder is named by its path, ``finance/weekly_summary``, so two folders can
each hold a report of the same name. Every surface that turns a name into a
file (the CLI, the web API, the agent gateway, schedules) goes through here, so
a name can never climb out of ``reports/`` or ``output/``.
"""

from __future__ import annotations

import os
from typing import Optional


def report_name_error(name: str) -> Optional[str]:
    """``None`` if *name* is a safe report name, else a message saying why not.

    Allowed: ``weekly`` and ``finance/month_end/weekly``. Refused: an empty
    name or segment, an absolute path, ``..``, backslashes, and segments that
    start with ``.`` or ``_`` (discovery skips those, so no report has one).
    """
    if not isinstance(name, str) or not name:
        return "a report name is required"
    if "\\" in name or name.startswith("/") or os.path.isabs(name):
        return (f"invalid report name {name!r}: use the report's name, or its "
                f"path below reports/ with forward slashes (finance/weekly)")
    for part in name.split("/"):
        if not part or part in (".", "..") or part.startswith((".", "_")):
            return (f"invalid report name {name!r}: each part of a report path "
                    f"must be a folder or report name, not {part!r}")
    return None


def output_html(output_dir: str, name: str) -> str:
    """``<output_dir>/<name>.html``, keeping the report's folders.

    ``finance/weekly`` builds to ``output/finance/weekly.html``, so two
    same-named reports in different folders never overwrite each other.
    """
    err = report_name_error(name)
    if err:
        raise ValueError(err)
    *folders, leaf = name.split("/")
    return os.path.join(output_dir, *folders, f"{leaf}.html")


def report_name_for_dir(directory: str, project_root: Optional[str] = None) -> str:
    """The report name of a package directory: its path below ``reports/``.

    ``reports/finance/weekly`` is ``finance/weekly``. A package outside the
    reports folder (a test fixture, an explicit path) is named by its own
    directory, as before folders existed.
    """
    root = project_root or os.getcwd()
    reports = os.path.realpath(
        os.path.join(root, os.environ.get("TRACEBI_REPORTS_DIR", "reports")))
    full = os.path.realpath(directory)
    if full.startswith(reports + os.sep):
        return os.path.relpath(full, reports).replace(os.sep, "/")
    return os.path.basename(os.path.normpath(directory))
