"""The housing sample in the reference project builds, reproduces, and
records its scenarios as unverifiable."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent / "examples" / "portfolio_project"


def test_housing_report_builds_and_verifies(tmp_path):
    project = tmp_path / "portfolio_project"
    shutil.copytree(_PROJECT, project,
                    ignore=shutil.ignore_patterns("data", "output", ".tracebi",
                                                  "__pycache__"))
    subprocess.run([sys.executable, "transforms/affordability_transform.py"],
                   cwd=project, check=True, capture_output=True)
    built = subprocess.run(
        [sys.executable, "-m", "tracebi.cli", "report", "build",
         "housing/affordability"],
        cwd=project, capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr

    manifest_path = next((project / "output").rglob("*.manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert [s["name"] for s in manifest["scenarios"]] == ["then", "now"]
    assert all(s["verifiable"] is False for s in manifest["scenarios"])
    ids = {f["id"] for f in manifest["figures"]}
    assert {"chart-two-tests", "chart-paths", "chart-rate", "chart-price-income",
            "vs-entry-then", "vs-entry-now", "vs-pay-then", "vs-pay-now",
            "vs-later-then", "vs-later-now", "pk-pay-then", "pk-later",
            "tbl-compare"} <= ids
    assert not any(i.startswith("calc-") for i in ids), \
        "a scenario output must never be recorded as a figure"

    verified = subprocess.run(
        [sys.executable, "-m", "tracebi.cli", "verify", str(manifest_path),
         "--strict", "--contracts"],
        cwd=project, capture_output=True, text=True, env=dict(os.environ))
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "REPRODUCES" in verified.stdout
