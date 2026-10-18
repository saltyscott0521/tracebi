"""Live discovery: a running server picks up report packages, specs and
model files added (or removed) without a restart.

These drive :func:`rescan` and the watcher thread directly on the library
registry. They never import ``tracebi.web.api.main`` (see CLAUDE.md,
invariant 3).
"""

import json
import os
import time

import pytest

from tracebi.registry import registry
from tracebi.web import discovery


# Structure only: discovery never resolves a binding against its model.
_DATA = {"k": {"model": "any_model", "query": {"fact": "f", "measures": ["m"]}}}


def _package(root, name, title="Live"):
    pkg = root / name
    pkg.mkdir(parents=True)
    (pkg / "report.json").write_text(json.dumps({"name": title, "data": _DATA}))
    (pkg / "template.html").write_text("<main><h1>{{ title }}</h1></main>")
    return pkg


def _names():
    return {r["name"] for r in registry.list_reports()}


@pytest.fixture()
def reports(tmp_path):
    root = tmp_path / "reports"
    root.mkdir()
    yield root
    for name in [n for n, src in discovery._live_reports.items()
                 if src.startswith(str(tmp_path))]:
        registry.remove_report(name)
        discovery._live_reports.pop(name, None)
    for name in [n for n, (src, _t) in discovery._failed_sources.items()
                 if src.startswith(str(tmp_path))]:
        discovery._failed_sources.pop(name, None)


def test_a_deleted_package_is_forgotten(reports):
    pkg = _package(reports, "goes_away")
    discovery.rescan(str(reports))
    assert "goes_away" in _names()

    for f in pkg.iterdir():
        f.unlink()
    pkg.rmdir()
    changes = discovery.rescan(str(reports))
    assert changes["removed"] == ["goes_away"]
    assert "goes_away" not in _names()


def test_a_broken_package_is_retried_only_when_it_changes(reports, monkeypatch):
    pkg = _package(reports, "broken_live")
    (pkg / "report.json").write_text("{ not json")
    calls = []
    real = discovery._register_template_package

    def counting(path, stem):
        calls.append(stem)
        return real(path, stem)

    monkeypatch.setattr(discovery, "_register_template_package", counting)
    assert discovery.rescan(str(reports))["failed"] == ["broken_live"]
    assert discovery.rescan(str(reports))["failed"] == []
    assert calls == ["broken_live"], "an unchanged broken package is not re-parsed"
    outcome = [o for o in discovery.discovery_report() if o.get("module") == "broken_live"]
    assert len(outcome) == 1 and outcome[0]["status"] == "failed"

    (pkg / "report.json").write_text(json.dumps({"name": "Fixed", "data": _DATA}))
    later = time.time() + 5
    os.utime(pkg / "report.json", (later, later))
    assert discovery.rescan(str(reports))["added"] == ["broken_live"]
    assert "broken_live" in _names()
