"""Browser smoke of the served app.

Skipped unless ``TRACEBI_E2E=1``. A normal ``pytest tests/`` does not need
Chromium or the ``e2e`` extra. The CI job ``ui-smoke`` sets the variable.
"""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("TRACEBI_E2E") != "1",
    reason="set TRACEBI_E2E=1 to run the browser smoke (needs the e2e extra)",
)

_REPO = Path(__file__).resolve().parents[1]
_PROJECT = _REPO / "examples" / "portfolio_project"
_REPORT = "portfolio_model/portfolio_showcase"   # its path: it lives in a folder
_LABEL = "portfolio_showcase"            # what the list shows under the folder
_TITLE = "Portfolio Showcase"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_health(url: str, proc: subprocess.Popen, log_path: Path, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(
                f"server exited {proc.returncode}\n{_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = str(exc)
        time.sleep(0.25)
    raise AssertionError(f"health never came up ({last})\n{_tail(log_path)}")


def _tail(path: Path, n: int = 40) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def test_real_app_smoke(tmp_path: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(
        _PROJECT,
        project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "data", ".tracebi"),
    )
    # What a fresh checkout has: no pages built on this machine earlier, so
    # opening a report builds it (and records the run the Runs step reads).
    for built in (project / "output").rglob("*.html"):
        built.unlink()
    workflow = subprocess.run(
        [sys.executable, "run_workflow.py"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert workflow.returncode == 0, workflow.stderr or workflow.stdout

    port = _free_port()
    env = os.environ.copy()
    env["TRACEBI_APP"] = ""
    for key in (
        "TRACEBI_REPORTS_DIR",
        "TRACEBI_MODELS_DIR",
        "TRACEBI_PIPELINES_DIR",
        "TRACEBI_DEV_MODE",
        "TRACEBI_OUTPUT_ROOT",
    ):
        env.pop(key, None)
    log_path = tmp_path / "server.log"
    log_file = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "tracebi.web.run", "--port", str(port), "--no-reload"],
        cwd=project,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(f"{base}/api/health", server, log_path)
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(180_000)
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            page.on(
                "console",
                lambda msg: errors.append(f"console {msg.type}: {msg.text}")
                if msg.type == "error"
                else None,
            )

            def fail_on_browser_errors() -> None:
                # pageerror is delivered just after goto returns.
                page.wait_for_timeout(200)
                assert not errors, "\n".join(errors)

            # Two models and no remembered pick: / opens every model's reports.
            page.goto(base + "/")
            page.get_by_role("heading", name="Reports", exact=True).wait_for()
            assert page.url.rstrip("/").endswith("/reports"), page.url
            fail_on_browser_errors()

            # Picking one scopes every page beneath the switcher to it.
            page.goto(base + "/models")
            page.get_by_role("heading", name="Data model", exact=True).wait_for()
            page.get_by_role("link", name="portfolio_model").first.click()
            page.wait_for_url("**/m/portfolio_model")
            page.get_by_role("link", name="Explore", exact=True).click()
            page.wait_for_url("**/m/portfolio_model/explore")
            page.get_by_role("heading", name="Explore", exact=True).wait_for()
            assert page.get_by_label("Model").input_value() == "portfolio_model"
            fail_on_browser_errors()

            # The pick is remembered: / now opens that model's reports.
            page.goto(base + "/")
            page.wait_for_url("**/m/portfolio_model/reports")

            # Old addresses land on the page that replaced them.
            page.goto(base + "/models/portfolio_model?tab=refresh")
            page.wait_for_url("**/m/portfolio_model/refresh")

            page.goto(base + "/reports")
            fail_on_browser_errors()
            page.get_by_text(_LABEL, exact=True).click()
            try:
                page.locator("iframe").wait_for()
            except Exception as exc:
                fail_on_browser_errors()
                raise AssertionError(page.inner_text("body")[:4000]) from exc
            page.wait_for_function(
                """(title) => {
                    const frame = document.querySelector('iframe');
                    if (!frame) return false;
                    return (frame.srcdoc || '').includes(title);
                }""",
                arg=_TITLE,
            )

            # The d3 figure (tracebi.draw) follows the page: drawn in the
            # theme's accent, and redrawn from the server's selection when the
            # sector filter changes, as the declared figures are.
            report = page.frame_locator("iframe")
            report.get_by_role("button", name="Detail", exact=True).click()
            cells = report.locator("#fig-treemap g.cell rect")
            cells.first.wait_for()
            assert cells.count() == 13
            accent = report.locator("html").evaluate(
                "el => getComputedStyle(el).getPropertyValue('--tb-accent').trim()")
            assert cells.first.get_attribute("fill") == accent
            report.locator("select[data-tb-column='dim_issuer.sector']").select_option("Software")
            report.locator("#fig-treemap g.sector").first.wait_for()
            page.wait_for_function(
                """() => document.querySelector('iframe').contentDocument
                    .querySelectorAll('#fig-treemap g.cell').length === 2""")
            fail_on_browser_errors()

            # An open report has the whole page: the list steps aside, and
            # "← All reports" brings it back.
            assert not page.get_by_placeholder("Search reports…").is_visible()
            page.get_by_role("button", name="← All reports").wait_for()

            # One Download menu holds the three files, each with its caveat.
            page.get_by_role("button", name="↓ Download").click()
            menu = page.locator(".dl-menu")
            links = menu.get_by_role("link").all()
            assert [link.inner_text().split("\n")[0] for link in links] == ["HTML", "Excel", "PDF"]
            assert [link.get_attribute("href").rsplit("=", 1)[1] for link in links] == ["html", "xlsx", "pdf"]
            assert "carries no receipt" in menu.inner_text()
            page.keyboard.press("Escape")
            assert menu.count() == 0

            # Lineage is a tab like the others: no button to reveal it first.
            assert page.get_by_role("button", name="View Lineage").count() == 0
            page.get_by_role("button", name="Lineage", exact=True).click()
            page.get_by_text("Where each number on the page came from").wait_for()

            page.get_by_role("button", name="Code", exact=True).click()
            page.get_by_role("button", name="report.json").wait_for()

            downloaded = page.evaluate(
                """async (url) => {
                    const response = await fetch(url);
                    return {status: response.status, body: await response.text()};
                }""",
                f"/api/reports/{_REPORT}/download?format=html",
            )
            assert downloaded["status"] == 200, _tail(log_path)
            assert _TITLE in downloaded["body"]

            # Rebuild makes more build rows, and the list re-checks the new one.
            page.get_by_role("button", name="↺ Rebuild").click()
            page.get_by_text("Report ran successfully").wait_for()
            page.get_by_role("button", name="← All reports").click()
            page.locator(".list-item", has_text=_LABEL).get_by_text("Reproduces", exact=True).wait_for()

            # A build is not a check: Runs shows the list's verdict on the newest
            # build of the report, and a plain "Not checked" (never green) on
            # every older one.
            page.goto(base + "/runs")
            page.get_by_role("heading", name="Runs", exact=True).wait_for()
            rows = page.locator("tr", has_text=_REPORT)
            rows.first.wait_for()
            page.get_by_text("Checking…").wait_for(state="detached")
            verdicts = [r.locator("td").last.inner_text() for r in rows.all()]
            assert len(verdicts) >= 2, verdicts
            assert verdicts[0] == "Reproduces", verdicts
            assert set(verdicts[1:]) == {"Not checked"}, verdicts
            fail_on_browser_errors()

            # Given room, a report's three KPI cards sit on one row.
            page.goto(f"{base}/reports?r=portfolio_model/portfolio_overview")
            cards = page.frame_locator("iframe").locator(".tb-kpi")
            cards.nth(2).wait_for()
            tops = {round(card.bounding_box()["y"]) for card in cards.all()}
            assert cards.count() == 3 and len(tops) == 1, tops

            # Each page can show the code behind what it shows.
            page.goto(base + "/m/portfolio_model")
            page.get_by_role("button", name="Code", exact=True).click()
            page.get_by_text("models/portfolio_model.yaml").first.wait_for()
            page.goto(base + "/m/portfolio_model/refresh")
            page.get_by_role("button", name="Code", exact=True).click()
            page.get_by_role("button", name="transform", exact=True).click()
            page.get_by_text("transforms/holdings_transform.py").first.wait_for()
            # Sources → Warehouse says what the warehouse holds and that the sink
            # satisfied its contract, before any report is opened.
            page.goto(base + "/m/portfolio_model/sources")
            page.get_by_role("button", name="Warehouse", exact=True).click()
            table = page.locator("details", has_text="fact_holdings")
            table.wait_for()
            assert re.search(r"[\d,]+ rows", table.locator("summary").inner_text())
            assert table.locator("summary").get_by_text("satisfied", exact=True).count() == 1
            fail_on_browser_errors()
            # Explore leads with the model's own measures (each with what it means),
            # sends their names, and writes the results in their declared formats.
            page.goto(base + "/m/portfolio_model/explore")
            page.get_by_text("Total fair value").wait_for()
            # However long the builder is, Run stays in view.
            expect(page.get_by_text("▶ Run query")).to_be_in_viewport(ratio=1)
            page.get_by_text("fair_value", exact=True).first.click()
            page.get_by_text("positions", exact=True).first.click()
            page.get_by_text("sector", exact=True).first.click()
            page.get_by_text("▶ Run query").click()
            page.get_by_text("The query as code").wait_for()
            assert 'measures=["fair_value", "positions"]' in page.locator(".codeview__code").inner_text()
            assert re.search(r"\$[\d,]+", page.locator("table tbody tr").first.inner_text())
            fail_on_browser_errors()

            # Group by offers only what the picked fact joins.
            page.goto(base + "/m/housing_model/explore")
            builder = page.locator(".explore-grid")
            expect(builder).to_contain_text("dim_year")
            page.get_by_role("button", name="fact_ten_year").click()
            expect(builder).not_to_contain_text("dim_year")
            expect(builder).to_contain_text("dim_cohort")
            fail_on_browser_errors()

            # Refresh: Run all opens the Runs tab, which follows the run to its end…
            page.goto(base + "/m/portfolio_model/refresh")
            page.get_by_role("button", name="Run all").click()
            output = page.get_by_role("log", name="Run output")
            output.get_by_text("Run succeeded").wait_for()
            text = output.inner_text()
            assert "[transform] ✓" in text and "[build] ✓" in text, text
            assert page.get_by_role("list", name="Runs").get_by_role("button").count() == 1
            # …then links the reports it rebuilt, each to its page in the app.
            page.get_by_role("link", name="portfolio_book", exact=True).click()
            page.wait_for_url("**/m/portfolio_model/reports?r=portfolio_model%2Fportfolio_book")
            fail_on_browser_errors()

            # That refresh is a run of its model: the model's Runs lists it, and
            # All models names the model beside it.
            page.goto(base + "/m/portfolio_model/runs")
            page.locator("tr", has_text="Pipeline run").first.wait_for()
            page.goto(base + "/runs")
            pipeline_row = page.locator("tr", has_text="Pipeline run").first
            pipeline_row.wait_for()
            assert "portfolio_model" in pipeline_row.inner_text()
            fail_on_browser_errors()

            # Drafts: a report draft on disk is listed, rendered live, follows
            # edits to its file without a reload, and publishes with a toast.
            draft = project / "drafts" / "anonymous" / "reports" / "portfolio_model" / "draft_demo"
            shutil.copytree(project / "reports" / "portfolio_model" / "portfolio_overview", draft)
            template = draft / "template.html"
            template.write_text(
                template.read_text(encoding="utf-8").replace("Portfolio Overview", "Draft Marker One"),
                encoding="utf-8")
            page.goto(base + "/drafts")
            page.get_by_role("heading", name="Drafts", exact=True).wait_for()
            row = page.get_by_role("list", name="Drafts").get_by_role("link")
            assert "portfolio_model/draft_demo" in row.inner_text()
            assert "changed" in row.inner_text().lower()
            row.click()
            page.wait_for_url("**/drafts/anonymous/reports/portfolio_model/draft_demo")
            page.get_by_role("heading", name="portfolio_model/draft_demo", exact=True).wait_for()
            page.wait_for_function(
                "(t) => (document.querySelector('iframe')?.srcdoc || '').includes(t)",
                arg="Draft Marker One")
            template.write_text(
                template.read_text(encoding="utf-8").replace("Draft Marker One", "Draft Marker Two"),
                encoding="utf-8")
            page.wait_for_function(
                "(t) => (document.querySelector('iframe')?.srcdoc || '').includes(t)",
                arg="Draft Marker Two")
            page.get_by_role("button", name="Files", exact=True).click()
            page.get_by_role("button", name="template.html").wait_for()
            page.get_by_role("button", name="Publish", exact=True).click()
            page.get_by_role("button", name="Publish for everyone").click()
            page.get_by_text("Published report portfolio_model/draft_demo").wait_for()
            page.get_by_role("link", name="Open the published report").wait_for()
            assert (project / "reports" / "portfolio_model" / "draft_demo" / "report.json").is_file()
            fail_on_browser_errors()
            browser.close()
        assert not errors, "\n".join(errors)
    finally:
        log_file.close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
