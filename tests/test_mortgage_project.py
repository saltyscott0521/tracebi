"""The mortgage sample project builds, reproduces, and records its scenarios."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent / "examples" / "mortgage_project"


def test_mortgage_project_builds_and_verifies(tmp_path):
    project = tmp_path / "mortgage_project"
    shutil.copytree(_PROJECT, project,
                    ignore=shutil.ignore_patterns("data", "output", ".tracebi",
                                                  "__pycache__"))
    subprocess.run([sys.executable, "run_workflow.py"], cwd=project, check=True,
                   capture_output=True)
    manifest_path = project / "output" / "affordability.html.manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert [s["name"] for s in manifest["scenarios"]] == ["then", "now"]
    assert all(s["verifiable"] is False for s in manifest["scenarios"])
    ids = {f["id"] for f in manifest["figures"]}
    assert {"chart-rate", "chart-price-income", "chart-payment",
            "chart-share", "kpi-then-share", "kpi-now-share"} <= ids
    assert not any(i.startswith("calc-") for i in ids), \
        "a scenario output must never be recorded as a figure"

    verified = subprocess.run(
        [sys.executable, "-m", "tracebi.cli", "verify", str(manifest_path),
         "--strict", "--contracts"],
        cwd=project, capture_output=True, text=True,
        env={**__import__("os").environ, "TRACEBI_MODELS_DIR": "models"})
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "REPRODUCES" in verified.stdout

    page = (project / "output" / "affordability.html").read_text()
    assert 'data-tb-scenario="then"' in page
    assert "hydrateScenarios" in page
