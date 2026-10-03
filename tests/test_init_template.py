"""
``tracebi init --template saas-metrics`` scaffolds a project that verifies.

Default ``tracebi init`` (no flag) stays the sample orders dashboard.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tracebi import cli
from tracebi.capabilities import describe

pytest.importorskip("duckdb")

_REPO = Path(__file__).parent.parent


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "tracebi.cli", *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


class TestTemplateFlag:
    def test_unknown_template_refuses_with_the_known_list(self, tmp_path, capsys):
        proj = tmp_path / "nope"
        assert cli.main(["init", str(proj), "--template", "sales-pipeline"]) == 1
        err = capsys.readouterr().err
        assert "unknown template" in err
        assert "saas-metrics" in err
        assert not proj.exists()

    def test_default_init_is_unchanged(self, tmp_path):
        proj = tmp_path / "plain"
        assert cli.main(["init", str(proj)]) == 0
        assert (proj / "models" / "sample_model.py").is_file()
        assert (proj / "reports" / "sample_dashboard" / "template.html").is_file()
        assert (proj / "inputs" / "orders.csv").is_file()
        assert not (proj / "models" / "saas_model.py").exists()
        assert not (proj / "reports" / "saas_model").exists()
        readme = (proj / "README.md").read_text(encoding="utf-8")
        assert "sample_dashboard" in readme
        assert "saas-metrics" not in readme

    def test_alias_and_force(self, tmp_path, capsys):
        proj = tmp_path / "saas"
        assert cli.main(
            ["init", str(proj), "--template", "saas_metrics"]) == 0
        assert (proj / "models" / "saas_model.py").is_file()
        assert (proj / "transforms" / "saas_transform.py").is_file()
        assert (proj / "reports" / "saas_model" / "mrr_dashboard"
                / "template.html").is_file()
        assert (proj / "reports" / "saas_model" / "cohort_brief"
                / "report.json").is_file()
        readme = (proj / "README.md").read_text(encoding="utf-8")
        assert "saas-metrics" in readme
        assert "tracebi connect" in readme
        model = proj / "models" / "saas_model.py"
        model.write_text("# edited\n", encoding="utf-8")
        assert cli.main(["init", str(proj), "--template", "saas-metrics"]) == 1
        assert model.read_text(encoding="utf-8") == "# edited\n"
        assert cli.main(
            ["init", str(proj), "--template", "saas-metrics", "--force"]) == 0
        assert "DataModel" in model.read_text(encoding="utf-8")
        # capsys drains the init prints so they don't leak into later asserts
        capsys.readouterr()

    def test_context_and_both_guides_name_the_template(self):
        payload = describe(brief=True)["templates"]
        assert payload["names"] == ["saas-metrics"]
        known = payload["known"]
        assert known[0]["name"] == "saas-metrics"
        assert "saas_metrics" in known[0]["aliases"]
        assert "saas_model/mrr_dashboard" in known[0]["reports"]
        assert "saas_model/cohort_brief" in known[0]["reports"]
        guides = {
            "repo AGENTS.md": (_REPO / "AGENTS.md").read_text(encoding="utf-8"),
            "scaffolded AGENTS.md": (
                _REPO / "tracebi" / "_scaffold" / "init_agents.md"
            ).read_text(encoding="utf-8"),
        }
        for name, text in guides.items():
            assert "saas-metrics" in text, name
            assert "saas_metrics" in text, name
            assert "tracebi connect" in text, name


class TestSaasTemplateVerifies:
    def test_transform_build_and_verify(self, tmp_path):
        proj = tmp_path / "saas"
        assert cli.main(
            ["init", str(proj), "--template", "saas-metrics"]) == 0
        sample = (proj / "inputs" / "subscriptions.csv").read_text(
            encoding="utf-8").splitlines()
        assert 1 < len(sample) <= 301  # header + a few hundred rows at most

        # The model must load before phase ① has run.
        lazy = subprocess.run(
            [sys.executable, "-c",
             "from tracebi.model_registry import get_model; "
             "m = get_model('saas_model'); print('lazy-ok', m.name)"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert lazy.returncode == 0, lazy.stderr
        assert "lazy-ok saas_model" in lazy.stdout

        for _ in range(2):  # idempotent: a second sink replaces the tables
            sunk = subprocess.run(
                [sys.executable, "transforms/saas_transform.py"],
                capture_output=True, text=True, cwd=str(proj),
            )
            assert sunk.returncode == 0, sunk.stderr
            assert "account-months:" in sunk.stdout

        reports = (
            "saas_model/mrr_dashboard",
            "saas_model/cohort_brief",
        )
        for name in reports:
            built = _run(["report", "build", name], proj)
            assert built.returncode == 0, built.stderr
            manifest = proj / "output" / f"{name}.html.manifest.json"
            assert manifest.is_file()
            verified = _run(
                ["verify", str(manifest), "--strict", "--contracts"], proj)
            assert verified.returncode == 0, verified.stdout + verified.stderr
            assert "REPRODUCES" in verified.stdout
