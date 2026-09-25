"""The ``altsvault`` pipeline on the Refresh page: pull → transform → build.

Each step is registered with ``PipelineRunner`` like any layer. The runner
only needs ``execute()`` to return something with a length (rows out) and a
lineage whose metadata may carry ``rows_ingested`` (rows in), so a step can be
arbitrary work: an API pull, a pandas transform, a report build.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

from tracebi import PipelineRunner
from tracebi.web.demo_app.altsvault import DATA_DIR
from tracebi.web.demo_app.altsvault.model import connector, model

REPORT = "altsvault/credit_marks"
PACKAGE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "reports", "altsvault", "credit_marks")


class _Ran:
    """What a step hands the runner: rows out (len) and rows in (lineage)."""

    def __init__(self, rows_in: int, rows_out: int) -> None:
        self._rows_out = rows_out
        self.lineage = [SimpleNamespace(metadata={"rows_ingested": rows_in})]

    def __len__(self) -> int:
        return self._rows_out


class _Step:
    def __init__(self, label: str, fn) -> None:
        self.layer_label = label
        self._fn = fn

    def execute(self) -> _Ran:
        return self._fn()


def _pull() -> _Ran:
    from tracebi.web.demo_app.altsvault.pull import pull

    manifest = pull()
    rows = sum(e["rows"] for e in manifest["exports"].values())
    return _Ran(rows, rows)


def _transform() -> _Ran:
    from tracebi.web.demo_app.altsvault.transform import run

    # The model's connector holds a read-only handle on the warehouse; DuckDB
    # won't open the same file read-write in this process until it's released.
    connector.disconnect()
    rows_in, rows_out = run()
    return _Ran(rows_in, rows_out)


def _build() -> _Ran:
    from tracebi.report_paths import output_html
    from tracebi.reports.template_package import TemplatePackage

    connector.disconnect()               # re-open read-only on the fresh tables
    out = output_html(os.path.join(os.getcwd(), "output"), REPORT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    manifest = TemplatePackage(PACKAGE).render({model.name: model}, out)
    figures = len(manifest.to_dict().get("figures") or [])
    return _Ran(figures, figures)


os.makedirs(DATA_DIR, exist_ok=True)
runner = PipelineRunner(db_url=f"sqlite:///{os.path.join(DATA_DIR, 'runs.db')}")
runner.register(_Step("pull", _pull), name="pull")
runner.register(_Step("transform", _transform), name="transform", depends_on="pull")
runner.register(_Step("build", _build), name="build", depends_on="transform")
