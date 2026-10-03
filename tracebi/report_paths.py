"""Report names are paths below ``reports/``.

A report at the top of the reports folder is named ``weekly_summary``; one in a
folder is named by its path, ``finance/weekly_summary``, so two folders can
each hold a report of the same name. Every surface that turns a name into a
file (the CLI, the web API, the agent gateway, schedules) goes through here, so
a name can never climb out of ``reports/`` or ``output/``.

:func:`open_report` is the one read of a named report. The permission check
will go there.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


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


@dataclass(frozen=True)
class OpenedReport:
    """Where a named report lives, for one read.

    ``path`` and ``spec_path`` are the package directory and the
    ``<name>.json`` spec under the reports folder. They are set only when
    *name* passes :func:`report_name_error` — an unsafe name is refused
    before any filesystem access. ``package_dir`` is ``path`` when that
    directory holds ``report.json``; ``has_template`` / ``has_spec`` say the
    other two files are present.

    The registry fields are filled only when the caller passes a registry
    (the web app). A spec's compiled package directory lives on the factory,
    not at ``path``, so ``registry_package_dir`` is that directory.
    """

    name: str
    purpose: str
    reports_dir: Path
    name_error: Optional[str]
    path: Optional[Path]
    spec_path: Optional[Path]
    package_dir: Optional[Path]
    has_template: bool
    has_spec: bool
    registered: Optional[bool]
    registry_package_dir: Optional[str]
    source: Optional[dict]


def open_report(
    name: str,
    *,
    purpose: str,
    reports_dir: Optional[Union[str, os.PathLike]] = None,
    registry: Optional[object] = None,
) -> OpenedReport:
    """Resolve *name* for one read. Every open, download, Source view, MCP
    tool and schedule calls this.

    Validates *name* with :func:`report_name_error` and, when it is safe,
    locates the package directory and spec file under the reports folder.
    When *registry* is given, also locates the registered factory. An unsafe
    name sets ``name_error`` and does not touch the filesystem. A missing
    report is not an error here: the location fields stay empty so each
    caller raises the not-found error it already raises (HTTP 404, the
    gateway's error dict, the CLI's ``FileNotFoundError``).

    This is where the permission check will go. *purpose* names the read —
    ``view``, ``build``, ``source``, ``schedule``, ``manage`` — so that check
    can map it to View, Build, Publish or Manage without each call site
    changing again. The check raises before the report is handed back.
    """
    if reports_dir is None:
        reports_dir = os.environ.get("TRACEBI_REPORTS_DIR", "reports")
    reports_dir = Path(reports_dir)
    name_error = report_name_error(name)
    path = spec_path = package_dir = None
    has_template = has_spec = False
    if name_error is None:
        path = reports_dir / name
        spec_path = reports_dir / f"{name}.json"
        if (path / "report.json").is_file():
            package_dir = path
            has_template = (path / "template.html").is_file()
        has_spec = spec_path.is_file()

    registered = registry_package_dir = source = None
    if registry is not None:
        registered = name in {r["name"] for r in registry.list_reports()}
        if registered:
            registry_package_dir = registry.report_package_dir(name)
            source = registry.report_source(name)

    return OpenedReport(
        name=name if isinstance(name, str) else "",
        purpose=purpose,
        reports_dir=reports_dir,
        name_error=name_error,
        path=path,
        spec_path=spec_path,
        package_dir=package_dir,
        has_template=has_template,
        has_spec=has_spec,
        registered=registered,
        registry_package_dir=registry_package_dir,
        source=source,
    )
