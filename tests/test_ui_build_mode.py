"""Browser tests of Build mode: point at a figure, pin a note, watch the agent work.

Skipped unless ``TRACEBI_E2E=1`` (needs Chromium; see test_ui_smoke.py).
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

from tests.test_ui_smoke import _PROJECT, _free_port, _tail, _wait_health

pytestmark = pytest.mark.skipif(
    os.environ.get("TRACEBI_E2E") != "1",
    reason="set TRACEBI_E2E=1 to run the browser tests (needs the e2e extra)",
)


def _serve(project: Path, log_path: Path, dev_mode: bool):
    env = {k: v for k, v in os.environ.items() if not k.startswith("TRACEBI_")}
    env["TRACEBI_APP"] = ""
    if dev_mode:
        env["TRACEBI_DEV_MODE"] = "1"
    port = _free_port()
    log = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "tracebi.web.run", "--port", str(port), "--no-reload"],
        cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    _wait_health(f"{base}/api/health", server, log_path)
    return base, server, log


def test_pointing_at_a_figure_reaches_the_agent(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(_PROJECT, project, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".DS_Store", "data", "output", ".tracebi"))
    done = subprocess.run([sys.executable, "run_workflow.py"], cwd=project,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr or done.stdout

    base, server, log = _serve(project, tmp_path / "server.log", dev_mode=True)
    report = "saas_model/mrr_dashboard"
    api = f"{base}/api/reports/{report}/workbench/pointing"

    def pointing():
        with urllib.request.urlopen(api, timeout=10) as r:
            return json.loads(r.read())["pointing"]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(60_000)
            page.goto(f"{base}/m/saas_model/reports?r={report}")
            page.locator("iframe").wait_for()
            frame = page.frame_locator("iframe")
            frame.locator("#kpi-mrr").wait_for()

            page.get_by_role("button", name="◎ Build").click()
            assert pointing() is None
            frame.locator("#kpi-mrr").click()

            note = page.locator(".point-note")
            note.get_by_text("Pointing at").wait_for()
            assert "kpis → ending_mrr" in note.inner_text()
            got = pointing()
            assert (got["kind"], got["id"], got["binding"], got["cell"]) == (
                "figure", "kpi-mrr", "kpis", "ending_mrr"), got

            # Not a figure: a heading is described by where it is, not by a query.
            frame.locator("h1").click()
            page.wait_for_function(
                "() => /h1/.test(document.querySelector('.point-note')?.innerText || '')")
            got = pointing()
            assert got["kind"] == "element" and got["tag"] == "h1", got

            # A note on what you point at is a pin the agent can read; when the agent
            # resolves it (here, through the files the MCP server shares) the pane
            # shows the answer without a reload.
            frame.locator("#kpi-mrr").click()
            page.get_by_label("Note for the agent").fill("make this a line chart")
            page.get_by_role("button", name="Pin for the agent").click()
            page.locator(".wb-item", has_text="make this a line chart").wait_for()
            from tracebi.workbench import read_pins, resolve_pin
            wb = project / ".tracebi" / "workbench" / "saas_model" / "mrr_dashboard"
            assert [p["note"] for p in read_pins(str(wb))] == ["make this a line chart"]
            assert read_pins(str(wb))[0]["target"]["binding"] == "kpis"
            resolve_pin(str(wb), "kpi-mrr", note="made it a line", by="agent")
            page.get_by_text("Agent: made it a line").wait_for(state="attached")

            # The preview is live: the agent edits the package and the report in the
            # pane changes on its own.
            template = project / "reports" / "saas_model" / "mrr_dashboard" / "template.html"
            template.write_text(template.read_text().replace(
                "Scale leads ending MRR", "Edited while you watch"))
            frame.get_by_role("heading", name="Edited while you watch").wait_for(timeout=15_000)

            # Escape stops pointing; so does leaving Build mode.
            frame.locator("#kpi-mrr").click()
            page.keyboard.press("Escape")
            page.wait_for_function(
                "() => /Click a figure/.test(document.querySelector('.point-note')?.innerText || '')")
            frame.locator("#kpi-mrr").click()
            page.get_by_role("button", name="◎ Build").click()
            page.wait_for_function("() => !document.querySelector('.point-note')")
            deadline = 50
            while pointing() is not None and deadline:
                page.wait_for_timeout(100)
                deadline -= 1
            assert pointing() is None, "leaving Point mode must stop pointing"
            browser.close()
    finally:
        log.close()
        server.terminate()
        server.wait(timeout=10)
    assert "Traceback" not in _tail(tmp_path / "server.log"), _tail(tmp_path / "server.log")


def test_build_mode_is_absent_unless_the_server_is_in_dev_mode(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(_PROJECT, project, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".DS_Store", "data", "output", ".tracebi"))
    done = subprocess.run([sys.executable, "run_workflow.py"], cwd=project,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr or done.stdout

    base, server, log = _serve(project, tmp_path / "server.log", dev_mode=False)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(60_000)
            page.goto(f"{base}/m/saas_model/reports?r=saas_model/mrr_dashboard")
            page.locator("iframe").wait_for()
            assert page.get_by_role("button", name="◎ Build").count() == 0
            browser.close()
        request = urllib.request.Request(
            f"{base}/api/reports/saas_model/mrr_dashboard/workbench/pointing",
            data=b'{"kind": "figure"}', method="POST",
            headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request, timeout=10)
        assert refused.value.code == 403
    finally:
        log.close()
        server.terminate()
        server.wait(timeout=10)
