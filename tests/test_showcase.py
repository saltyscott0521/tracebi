"""
The showcase must never rot.

``examples/portfolio_project/reports/showcase/portfolio_showcase`` is the maintained
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
        out = _run(["report", "build", "showcase/portfolio_showcase"], proj)
        assert out.returncode == 0, out.stdout + out.stderr

        html = (proj / "output" / "showcase" / "portfolio_showcase.html").read_text(
            encoding="utf-8")
        from tests.test_presentation_js import assert_built_receipt_rows
        assert_built_receipt_rows(html)
        # Controls, layout, and trust affordances all present on the page.
        for marker in ("data-tb-filter", "data-tb-search", "data-tb-download",
                       "tb-tabs", "tb-cols-2", 'id="tracebi-receipt"',
                       "tb-methodology", "data-tb-unverified",
                       "tb-semantic-contract-portfolio_model",
                       'id="tracebi-selection"', 'id="tracebi-grain"',
                       "connect-src 'self'", 'class="tb-total"',
                       "data-tb-sort", "data-tb-bars", "data-tb-direction",
                       "tb-table--freeze"):
            assert marker in html, f"showcase lost its {marker} affordance"
        assert "Working notes" not in html, "exploration must die at build"

        manifest = json.loads(
            (proj / "output" / "showcase" / "portfolio_showcase.html.manifest.json")
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
                    "output/showcase/portfolio_showcase.html.manifest.json",
                    "--contracts"], proj)
        assert out.returncode == 0, out.stdout + out.stderr
        assert "REPRODUCES" in out.stdout

        # and the offline file check.
        out = _run(["verify", "--file", "output/showcase/portfolio_showcase.html"],
                   proj)
        assert out.returncode == 0, out.stdout + out.stderr

        # A sector cut moves fair value, the ratio, and the holdings table
        # together. The fingerprint is the model's, not a browser sum.
        self._sector_recomputes_on_the_model(proj)

    def _sector_recomputes_on_the_model(self, proj):
        import os

        from tracebi.model_registry import ModelRegistry
        from tracebi.reports.selection import evaluate_selection
        from tracebi.reports.template_package import TemplatePackage

        previous = os.getcwd()
        os.chdir(proj)
        try:
            registry = ModelRegistry()
            registry.auto_discover(str(proj / "models"))
            model = registry.get("portfolio_model")
            package = TemplatePackage(
                str(proj / "reports" / "showcase" / "portfolio_showcase"))
            models = {"portfolio_model": model}
            base = evaluate_selection(package, models, {})
            control = next(
                c for c in base["controls"]
                if c["column"] == "dim_issuer.sector")
            assert len(control["included"]) > 1
            sector = control["included"][0]
            cut = evaluate_selection(
                package, models, {"dim_issuer.sector": sector})
        finally:
            os.chdir(previous)

        def cell(result, figure_id):
            return next(f for f in result["figures"] if f["id"] == figure_id)

        fair = cell(cut, "kpi-fv")
        mark = cell(cut, "kpi-mark")
        detail = cell(cut, "tbl-detail")
        assert fair["value"] != cell(base, "kpi-fv")["value"]
        assert mark["value"] != cell(base, "kpi-mark")["value"]
        assert len(detail["rows"]) < len(cell(base, "tbl-detail")["rows"])
        assert detail["rows"]
        assert all(row["dim_issuer.sector"] == sector for row in detail["rows"])
        expected = model.query(
            "fact_holdings", ["fair_value", "positions", "mark"],
            filters={"dim_issuer.sector": sector},
        )
        assert fair["fingerprint"] == expected.fingerprint()
        assert mark["fingerprint"] == expected.fingerprint()
