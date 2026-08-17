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
        # M5 flip ledger: init no longer scaffolds requests/ — the
        # deprecated lane is not handed to new projects.
        for d in ("inputs", "transforms", "models", "reports",
                  "pipelines", "scheduled", "data", "output"):
            assert (proj / d).is_dir(), f"missing {d}/"
        assert not (proj / "requests").exists(), \
            "init must not scaffold the deprecated requests/ lane"
        assert (proj / "inputs" / "orders.csv").is_file()
        assert (proj / "transforms" / "sample_transform.py").is_file()
        assert (proj / "models" / "sample_model.py").is_file()
        # Round-2 flip: the sample report is an ARTIFACT PACKAGE — the one
        # report lane — not a legacy JSON spec.
        assert (proj / "reports" / "sample_dashboard" / "report.json").is_file()
        assert (proj / "reports" / "sample_dashboard" / "template.html").is_file()
        import json as _json
        pkg = _json.loads((proj / "reports" / "sample_dashboard" /
                           "report.json").read_text())
        assert pkg.get("libs") == ["echarts"], \
            "the sample chart must opt into the vendored ECharts or it is blank"
        assert not (proj / "reports" / "sample_dashboard.json").exists(), \
            "the scaffold must not teach the legacy spec lane"

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

        # ③ render + receipt — the sample is an artifact package, so the
        # first page a project renders demonstrates the real lane: figure
        # claims, the presentation stack, provenance badges, and a manifest
        # that joins the sink contract (round-2 finding: the scaffold must
        # not teach the form `migrate` exists to convert away from).
        out = _run(["report", "build", "sample_dashboard"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        # M1 flip ledger: report build renders to output/ (finding #14).
        manifest = proj / "output" / "sample_dashboard.html.manifest.json"
        assert manifest.is_file()

        html = (proj / "output" / "sample_dashboard.html").read_text(
            encoding="utf-8")
        assert "tb-kpi" in html, "the sample page must use the shipped stack"
        # The scaffold's exploration block ("Working notes") must be DELETED
        # by the build — the inlined stylesheet still names the attribute in
        # its selectors, so assert on the content, not the string.
        assert "Working notes" not in html, \
            "exploration blocks must be deleted at the final build"
        import json as _json
        m = _json.loads(manifest.read_text(encoding="utf-8"))
        assert m["schema_version"] == 2 and m.get("figures"), \
            "the sample must produce the figure claims layer"
        contracts = m.get("transform_contracts", {})
        assert contracts and all(
            r.get("status") == "satisfied" for r in contracts.values()
        ), "the sample receipt must join the scaffolded sink contract green"

        # the loop closes under --strict: every figure in the scaffold is
        # bound, so the CI-gate bar itself reads green on first contact.
        out = _run(["verify", "output/sample_dashboard.html.manifest.json",
                    "--strict", "--contracts"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "REPRODUCES" in out.stdout
        assert "satisfied" in out.stdout

    def test_scaffolded_python_compiles(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        for f in ("transforms/sample_transform.py", "models/sample_model.py"):
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
        # Notebook-shaped: percent cells, top-level execution — every
        # notebook editor opens it as a notebook; python runs it as a script.
        assert "# %%" in text and "# %% [markdown]" in text


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


class TestNotebookShapedTransforms:
    """Transforms are notebook-shaped .py (percent cells) — every notebook
    editor opens them as notebooks while the file stays reviewable Python —
    and literal .ipynb runs top-to-bottom fresh via run-transform."""

    def test_scaffolds_are_percent_format(self, tmp_path):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        sample = (proj / "transforms" / "sample_transform.py").read_text()
        assert "# %% [markdown]" in sample and "# %%" in sample
        from tracebi.cli import _transform_template_text
        assert "# %% [markdown]" in _transform_template_text("X")

    def test_run_transform_executes_py_and_ipynb(self, tmp_path, monkeypatch):
        import json as _json
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        monkeypatch.chdir(proj)
        # the scaffolded notebook-shaped .py runs top-to-bottom
        assert cli.main(["run-transform", "sample_transform"]) == 0
        assert (proj / "data" / "warehouse.duckdb").exists()
        # a literal .ipynb transform runs fresh, cells concatenated in order
        nb = {"cells": [
            {"cell_type": "markdown", "source": ["# methodology\n"]},
            {"cell_type": "code", "source": ["x = 2\n"]},
            {"cell_type": "code",
             "source": ["open('nb_ran.txt', 'w').write(str(x * 21))\n"]},
        ], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
        (proj / "transforms" / "probe.ipynb").write_text(_json.dumps(nb))
        assert cli.main(["run-transform", "probe"]) == 0
        assert (proj / "nb_ran.txt").read_text() == "42"

    def test_run_transform_missing_is_a_clean_error(self, tmp_path, monkeypatch):
        proj = tmp_path / "proj"
        assert cli.main(["init", str(proj)]) == 0
        monkeypatch.chdir(proj)
        assert cli.main(["run-transform", "nope"]) == 1
