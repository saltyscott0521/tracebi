"""Keep web report builds out of the repo's output/ during tests.

The reports router writes ``output/<name>.html`` beside the working
directory. Tests that drive that router stay in the repo root (they
resolve models and packages from there), so a build would leave a
receipt in the checkout. Tests that ``chdir`` have already chosen a
directory; those still write beside that directory.
"""

import os
from pathlib import Path

import pytest

# No test reaches GitHub for a release check (tracebi/_updates.py). Set at
# import so subprocesses inherit it; tests/test_updates.py turns it back on
# against a fake release feed.
os.environ["TRACEBI_UPDATE_CHECK"] = "0"
# No build takes a cover (tracebi/reports/cover.py): each is a Chromium
# launch, and the suite builds hundreds of reports. The reference journey
# turns it back on where covers are what it checks.
os.environ["TRACEBI_COVERS"] = "0"
# Every subprocess a test starts (the UI smoke server, CLI runs, a
# project's run_workflow.py) imports the tree these tests live in, not
# whatever checkout the editable install points at: from a git worktree
# that is another branch's code (design/pitfalls.md).
_TREE = str(Path(__file__).resolve().parents[1])
os.environ["PYTHONPATH"] = os.pathsep.join(
    [_TREE] + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep)
               if p and p != _TREE])


@pytest.fixture(autouse=True)
def _report_builds_leave_the_repo(monkeypatch, tmp_path):
    import tracebi.web.api.routers.reports as reports

    repo = Path.cwd().resolve()
    scratch = tmp_path / "output"

    def _output_dir() -> str:
        if Path.cwd().resolve() == repo:
            return str(scratch)
        return os.path.join(os.getcwd(), "output")

    monkeypatch.setattr(reports, "_output_dir", _output_dir)
    # The shared run store defaults to data/tracebi.db beside cwd. Point it
    # at this test's temp dir so a schedule or build never writes the repo.
    monkeypatch.setenv(
        "TRACEBI_STATE_URL", f"sqlite:///{tmp_path / 'state.db'}")
