"""The reference project, end to end: both transforms sink, then EVERY report
in it — packages, folders, the JSON spec, the scenario —
builds and holds to the receipt bar. The showcase and the housing report are
the maintained demos; a feature that breaks either breaks this test, so the
demos can never quietly stop demoing.

Built once per module (the transforms take seconds); each test reads the
built project.
"""

import json
import os
import shutil

import pytest

from tests.e2e.conftest import REFERENCE_PROJECT, run_cli

REPORTS = {
    "portfolio_model/portfolio_dashboard": "portfolio_model/portfolio_dashboard",
    "portfolio_model/portfolio_book": "portfolio_model/portfolio_book",
    "portfolio_model/portfolio_overview": "portfolio_model/portfolio_overview",
    "portfolio_model/portfolio_concentration": "portfolio_model/portfolio_concentration",
    "portfolio_model/portfolio_showcase": "portfolio_model/portfolio_showcase",
    "housing_model/affordability": "housing_model/affordability",
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from tracebi import model_registry, pipeline_registry

    proj = tmp_path_factory.mktemp("ref") / "portfolio_project"
    shutil.copytree(REFERENCE_PROJECT, proj, ignore=shutil.ignore_patterns(
        "data", "output", ".tracebi", "explorations", "__pycache__", "*.duckdb"))
    saved = (os.getcwd(), model_registry._registry, model_registry._auto_discovered,
             pipeline_registry._registry, pipeline_registry._auto_discovered)
    model_registry._registry = model_registry.ModelRegistry()
    model_registry._auto_discovered = False
    pipeline_registry._registry = pipeline_registry.PipelineRegistry()
    pipeline_registry._auto_discovered = False
    os.chdir(proj)
    try:
        for transform in ("holdings_transform", "affordability_transform"):
            code, out = run_cli("run-transform", transform)
            assert code == 0, out
        for name in REPORTS:
            code, out = run_cli("report", "build", name)
            assert code == 0, f"{name}: {out}"
        yield proj
    finally:
        os.chdir(saved[0])
        (model_registry._registry, model_registry._auto_discovered,
         pipeline_registry._registry, pipeline_registry._auto_discovered) = saved[1:]


def _manifest(proj, name):
    return proj / "output" / f"{name}.html.manifest.json"


@pytest.mark.parametrize("name", sorted(REPORTS))
def test_every_report_reproduces_and_its_file_is_intact(built, name):
    manifest = _manifest(built, name)
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 0, out
    assert "REPRODUCES" in out
    code, out = run_cli("verify", "--file", str(built / "output" / f"{name}.html"))
    assert code == 0, out
    assert "FILE INTACT" in out


def test_every_model_keeps_its_reports_in_its_own_folder_and_has_a_pipeline(built):
    """The convention: reports/<model>/ holds a model's reports, and
    pipelines/<model>.py rebuilds its data and then those reports."""
    from tracebi.pipeline import model_pipeline
    from tracebi.pipeline.model_pipeline import reports_of

    models = sorted(p.stem for p in (built / "models").glob("*.py") if not p.stem.startswith("_"))
    assert models == ["housing_model", "portfolio_model"]
    for model in models:
        names = reports_of(model)
        assert names, f"reports/{model}/ has no reports"
        assert (built / "pipelines" / f"{model}.py").is_file(), f"{model} has no pipeline"
        # ...and every report in the reference project sits under a model's folder
    everything = {name for names in map(reports_of, models) for name in names}
    assert everything == set(REPORTS), "a report sits outside its model's folder"
    assert model_pipeline  # exported at the top level for project pipelines


@pytest.mark.parametrize("model", ["portfolio_model", "housing_model"])
def test_a_models_pipeline_rebuilds_its_data_then_its_reports(built, model):
    from tracebi.pipeline.model_pipeline import reports_of

    code, out = run_cli("run-pipeline", model)
    assert code == 0, out
    assert "transform" in out and "build" in out
    for name in reports_of(model):
        code, out = run_cli("verify", str(_manifest(built, name)), "--contracts")
        assert code == 0 and "REPRODUCES" in out, f"{name}: {out}"


def test_the_showcase_carries_every_affordance(built):
    html = (built / "output" / "portfolio_model" / "portfolio_showcase.html").read_text()
    from tests.test_presentation_js import assert_built_receipt_rows
    assert_built_receipt_rows(html)
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

    manifest = json.loads(_manifest(built, "portfolio_model/portfolio_showcase").read_text())
    assert manifest["schema_version"] == 2
    assert len(manifest["figures"]) >= 10
    assert manifest["transform_contracts"] and all(
        r.get("status") == "satisfied" for r in manifest["transform_contracts"].values())
    assert manifest["semantic_contract"]["portfolio_model"]["sha256"]
    assert manifest["methodology"]["transform_notes"]


def test_a_showcase_control_recomputes_on_the_model(built):
    """Picking a sector re-runs the stamped queries on the model and the cut
    total matches a direct query — interactivity subsets, never computes."""
    from tracebi.model_registry import ModelRegistry
    from tracebi.reports.selection import evaluate_selection
    from tracebi.reports.template_package import TemplatePackage

    previous = os.getcwd()
    os.chdir(built)
    try:
        registry = ModelRegistry()
        registry.auto_discover(str(built / "models"))
        models = {"portfolio_model": registry.get("portfolio_model")}
        package = TemplatePackage(str(built / "reports" / "portfolio_model" / "portfolio_showcase"))
        base = evaluate_selection(package, models, {})
        control = next(c for c in base["controls"] if c["column"] == "dim_issuer.sector")
        assert len(control["included"]) > 1
        sector = control["included"][0]
        cut = evaluate_selection(package, models, {"dim_issuer.sector": sector})
        model = models["portfolio_model"]
        expected = model.query("fact_holdings", ["fair_value", "positions", "mark"],
                               filters={"dim_issuer.sector": sector})
    finally:
        os.chdir(previous)

    def cell(result, figure_id):
        return next(f for f in result["figures"] if f["id"] == figure_id)

    fair, detail = cell(cut, "kpi-fv"), cell(cut, "tbl-detail")
    assert fair["value"] != cell(base, "kpi-fv")["value"]
    assert 0 < len(detail["rows"]) < len(cell(base, "tbl-detail")["rows"])
    assert all(row["dim_issuer.sector"] == sector for row in detail["rows"])
    # The cut is the model's own answer to that query, byte for byte.
    assert fair["fingerprint"] == expected.fingerprint()
    assert cell(cut, "kpi-mark")["fingerprint"] == expected.fingerprint()


def test_the_housing_scenario_is_recorded_never_receipted(built):
    manifest = json.loads(_manifest(built, "housing_model/affordability").read_text())
    assert [s["name"] for s in manifest["scenarios"]] == ["today"]
    assert all(s["verifiable"] is False for s in manifest["scenarios"])
    ids = {f["id"] for f in manifest["figures"]}
    assert {"chart-ten-year", "ten-worst", "ten-best", "ten-today", "chart-paths",
            "chart-rate", "chart-pti", "chart-share"} <= ids
    assert not any(i.startswith("calc-") for i in ids), \
        "a scenario output must never be recorded as a figure"
