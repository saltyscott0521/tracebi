"""A report's script cannot reach the app that shows it.

Skipped unless ``TRACEBI_E2E=1`` (needs Chromium; see test_ui_smoke.py).

A report can carry its author's ``script.js``. The app shows it in a frame, and
a frame with the app's own origin would let that script reach ``window.parent``
and call the app's API as the signed-in viewer (the report's own
``connect-src 'none'`` does not stop a call made through the parent). So every
frame is sandboxed to an opaque origin, and the pages the server hands out to
open on their own carry the same sandbox as a header.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from tests.test_ui_build_mode import _serve
from tests.test_ui_smoke import _PROJECT, _tail

pytestmark = pytest.mark.skipif(
    os.environ.get("TRACEBI_E2E") != "1",
    reason="set TRACEBI_E2E=1 to run the browser tests (needs the e2e extra)",
)

# What a hostile script tries, recorded on <html data-probe> for the test to read.
_PROBE = """
(function () {
  var out = {};
  var root = document.documentElement;
  function put(k, v) { out[k] = v; root.setAttribute("data-probe", JSON.stringify(out)); }
  put("origin", window.origin);
  try { put("parent_document", "READ:" + window.parent.document.title.length); }
  catch (e) { put("parent_document", "blocked:" + e.name); }
  try { put("storage", "READ:" + window.localStorage.length); }
  catch (e) { put("storage", "blocked:" + e.name); }
  try {
    window.parent.fetch("/api/models").then(
      function (r) { put("parent_fetch", "CALLED:" + r.status); },
      function () { put("parent_fetch", "failed"); });
  } catch (e) { put("parent_fetch", "blocked:" + e.name); }
})();
"""


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "portfolio_project"
    shutil.copytree(_PROJECT, project, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".DS_Store", "data", "output", ".tracebi"))
    done = subprocess.run([sys.executable, "run_workflow.py"], cwd=project,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr or done.stdout
    # The workflow built it before the probe below existed: the page builds it again.
    (project / "output" / "saas_model" / "cohort_brief.html").unlink()
    package = project / "reports" / "saas_model" / "cohort_brief"
    (package / "script.js").write_text(_PROBE, encoding="utf-8")
    template = package / "template.html"
    template.write_text(template.read_text(encoding="utf-8").replace(
        "</article>", '<button data-tb-download data-tb-binding="kpis" id="csv">CSV</button></article>', 1),
        encoding="utf-8")
    return project


def _probe(locator) -> dict:
    locator.wait_for(state="attached")
    # The parent_fetch answer arrives last.
    for _ in range(100):
        got = json.loads(locator.get_attribute("data-probe") or "{}")
        if "parent_fetch" in got:
            return got
        locator.page.wait_for_timeout(100)
    raise AssertionError(f"the probe never finished: {got}")


def test_a_report_script_cannot_reach_the_app_it_is_shown_in(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    project = _project(tmp_path)
    base, server, log = _serve(project, tmp_path / "server.log", dev_mode=False)
    report = "saas_model/cohort_brief"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(60_000)
            page.goto(f"{base}/reports/{report}")
            page.get_by_role("button", name="Build it now").click()
            page.locator("iframe").wait_for()

            # In the app: the frame has an opaque origin and no way through the parent.
            got = _probe(page.frame_locator("iframe").locator("html"))
            assert got["origin"] == "null", got
            assert got["parent_document"].startswith("blocked"), got
            assert got["parent_fetch"].startswith("blocked"), got
            assert got["storage"].startswith("blocked"), got

            # What the sandbox still allows: saving a figure's data as CSV.
            with page.expect_download() as saved:
                page.frame_locator("iframe").locator("#csv").click()
            assert saved.value.suggested_filename == "kpis.csv"

            # Opened on its own, by the share link: the same, because the server says so.
            page.goto(f"{base}/r/{report}")
            got = _probe(page.locator("html"))
            assert got["origin"] == "null", got
            assert got["storage"].startswith("blocked"), got
            browser.close()
        with urllib.request.urlopen(f"{base}/r/{report}", timeout=30) as response:
            policy = response.headers["Content-Security-Policy"]
        assert policy.split()[0] == "sandbox" and "allow-same-origin" not in policy, policy
    finally:
        log.close()
        server.terminate()
        server.wait(timeout=10)
    assert "Traceback" not in _tail(tmp_path / "server.log"), _tail(tmp_path / "server.log")
