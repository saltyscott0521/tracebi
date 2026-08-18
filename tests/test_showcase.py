"""
The showcase must never rot.

``examples/portfolio_project/reports/portfolio_showcase`` is the maintained
kitchen-sink demo — every figure kind, control, layout, and trust
affordance on the reference data. This test rebuilds it hermetically (a
tmp copy of the reference project, transform run fresh) and holds it to
the full bar: build green, controls and receipt affordances present,
verify + contracts green, offline file check green. A feature that breaks
the demo breaks this test — the demo can never quietly stop demoing.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

_REFERENCE = Path(__file__).parent.parent / "examples" / "portfolio_project"


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "tracebi.cli", *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


@pytest.fixture()
def showcase_project(tmp_path):
    proj = tmp_path / "proj"
    shutil.copytree(
        _REFERENCE, proj,
        ignore=shutil.ignore_patterns("data", "output", ".tracebi",
                                      "explorations", "__pycache__"),
    )
    out = subprocess.run(
        [sys.executable, "transforms/holdings_transform.py"],
        capture_output=True, text=True, cwd=str(proj),
    )
    assert out.returncode == 0, out.stderr
    return proj


class TestShowcase:
    def test_builds_verifies_and_carries_every_affordance(
            self, showcase_project):
        proj = showcase_project
        out = _run(["report", "build", "portfolio_showcase"], proj)
        assert out.returncode == 0, out.stdout + out.stderr

        html = (proj / "output" / "portfolio_showcase.html").read_text(
            encoding="utf-8")
        # Controls, layout, and trust affordances all present on the page.
        for marker in ("data-tb-filter", "data-tb-search", "data-tb-download",
                       "tb-tabs", "tb-cols-2", 'id="tracebi-receipt"',
                       "tb-methodology", "data-tb-unverified",
                       "tb-semantic-contract-portfolio_model"):
            assert marker in html, f"showcase lost its {marker} affordance"
        assert "Working notes" not in html, "exploration must die at build"

        manifest = json.loads(
            (proj / "output" / "portfolio_showcase.html.manifest.json")
            .read_text(encoding="utf-8"))
        # The full trust surface rides the receipt.
        assert manifest["schema_version"] == 2
        assert len(manifest["figures"]) >= 10
        assert manifest["transform_contracts"] and all(
            r.get("status") == "satisfied"
            for r in manifest["transform_contracts"].values())
        assert manifest["semantic_contract"]["portfolio_model"]["sha256"]
        assert manifest["methodology"]["transform_notes"]

        # verify green (NOT --strict: the showcase deliberately carries an
        # honest unverified figure and a python-derived one — the demo
        # demos honesty, not just green).
        out = _run(["verify",
                    "output/portfolio_showcase.html.manifest.json",
                    "--contracts"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "REPRODUCES" in out.stdout

        # and the offline file check.
        out = _run(["verify", "--file", "output/portfolio_showcase.html"],
                   proj)
        assert out.returncode == 0, out.stdout + out.stderr
