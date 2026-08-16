"""
The init scaffold is the product's first run — it must walk the three-phase
workflow end to end and finish with `tracebi verify` reading REPRODUCES.

These tests run the scaffolded project through subprocesses (the exact
commands the scaffolded README gives a new user), so they are hermetic: no
shared registry state with the rest of the suite.
"""

import compileall
import subprocess
import sys
from pathlib import Path

import pytest

from tracebi import cli

pytest.importorskip("duckdb")


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "tracebi.cli", *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


class TestInitScaffold:
    def test_init_creates_the_three_phase_layout(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        for d in ("inputs", "transforms", "models", "reports", "requests",
                  "pipelines", "scheduled", "data", "output"):
            assert (proj / d).is_dir(), f"missing {d}/"
        assert (proj / "inputs" / "orders.csv").is_file()
        assert (proj / "transforms" / "sample_transform.py").is_file()
        assert (proj / "models" / "sample_model.py").is_file()
        assert (proj / "reports" / "sample_dashboard.json").is_file()

    def test_init_scaffolds_an_agent_guide(self, tmp_path):
        """A fresh agent landing in the project must find orientation there —
        the project onboards its own agent."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        guide = proj / "AGENTS.md"
        assert guide.is_file(), "init must scaffold AGENTS.md"
        text = guide.read_text()
        # It must teach the load-bearing concepts, not just exist.
        for concept in ("tracebi context", "tracebi verify", "transforms/",
                        "models/", "reports/", "receipt"):
            assert concept in text, f"AGENTS.md should mention {concept}"

    def test_init_loop_ends_in_reproduces(self, tmp_path):
        """The README's four commands, verbatim: transform → validate →
        build → verify. The first thing a new user runs ends green."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0

        # ① transform — clean the sample input, sink the warehouse
        out = subprocess.run(
            [sys.executable, "transforms/sample_transform.py"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        assert (proj / "data" / "warehouse.duckdb").exists()

        # the scaffolded spec validates against the scaffolded model
        out = _run(["spec", "validate", "reports/sample_dashboard.json"], proj)
        assert out.returncode == 0, out.stdout + out.stderr

        # ③ render + receipt
        out = _run(["report", "build", "sample_dashboard"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        manifest = proj / "data" / "sample_dashboard.html.manifest.json"
        assert manifest.is_file()

        # the loop closes: every checked section reproduces
        out = _run(["verify", "data/sample_dashboard.html.manifest.json"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "REPRODUCES" in out.stdout
        assert "reproduces" in out.stdout.lower()

    def test_scaffolded_python_compiles(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        for f in ("transforms/sample_transform.py", "models/sample_model.py",
                  "requests/sample_report.py"):
            assert compileall.compile_file(
                str(proj / f), quiet=2
            ), f"{f} does not compile"

    def test_scaffolded_model_is_lazy(self, tmp_path):
        """Importing the scaffolded model must not touch the warehouse —
        it has to load before phase ① has ever run."""
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        # No warehouse exists yet; a connect-at-import would fail here.
        out = subprocess.run(
            [sys.executable, "-c",
             "from tracebi.model_registry import get_model; "
             "m = get_model('sample_model'); print('lazy-ok', m.name)"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        assert "lazy-ok" in out.stdout


class TestNewTransform:
    def test_scaffold_compiles(self, tmp_path):
        out = _run(["new-transform", "Orders Clean",
                    "--transforms-dir", str(tmp_path / "transforms")], tmp_path)
        assert out.returncode == 0, out.stderr
        f = tmp_path / "transforms" / "orders_clean.py"
        assert f.is_file()
        assert compileall.compile_file(str(f), quiet=2)
        text = f.read_text()
        assert "DuckDBConnector" in text
        assert "def run()" in text


class TestNewModelScaffold:
    def test_no_connect_at_import(self, tmp_path):
        """The new-model template must construct lazily — discovery imports
        every model file, and a connect at import opens a connection (or
        fails outright) on every scan."""
        out = _run(["--models-dir", str(tmp_path / "models"),
                    "new-model", "My Model"], tmp_path)
        assert out.returncode == 0, out.stderr
        text = (tmp_path / "models" / "my_model.py").read_text()
        assert "\nmodel.connect()" not in text
