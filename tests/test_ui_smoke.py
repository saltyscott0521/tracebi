"""Browser smoke of the served app.

Skipped unless ``TRACEBI_E2E=1``. A normal ``pytest tests/`` does not need
Chromium or the ``e2e`` extra. The CI job ``ui-smoke`` sets the variable.
"""

from __future__ import annotations

import json
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

            # / is the library: every report by folder, under the report's own
            # name, with its verdict and schedule. Five places in the sidebar,
            # Docs last; its foot keeps no Help link.
            page.goto(base + "/")
            page.get_by_role("heading", name="Reports", exact=True).wait_for()
            assert page.url.rstrip("/") == base, page.url
            sidebar = page.get_by_role("navigation", name="Main")
            for place in ("Reports", "Ask", "Data", "Review", "Docs"):
                sidebar.get_by_role("link", name=place, exact=True).wait_for()
            expect(sidebar.get_by_role("link", name="Help")).to_have_count(0)
            expect(sidebar.get_by_role("link", name="Reports", exact=True)).to_have_attribute("aria-current", "page")
            lib_row = page.locator(f'[data-report="{_REPORT}"]')
            expect(lib_row).to_contain_text(_TITLE)
            expect(lib_row).to_contain_text("Never built")
            expect(lib_row).to_contain_text("Mondays 07:00")   # its schedule, in words
            # A model is a filter chip on the list, not the frame of the app.
            page.get_by_role("group", name="Model").get_by_role("button", name=re.compile(r"^Direct Lending Portfolio")).click()
            page.wait_for_url("**/?model=portfolio_model")
            expect(page.locator('[data-report="housing_model/affordability"]')).to_have_count(0)
            expect(lib_row).to_be_visible()
            fail_on_browser_errors()

            # Data is the chain, as four tabs with addresses of their own. Models
            # lists each model as a chain row whose segments link where they say.
            sidebar.get_by_role("link", name="Data", exact=True).click()
            page.wait_for_url("**/data")
            data_tabs = page.get_by_role("navigation", name="Data: what to show")
            data_tabs.get_by_role("link", name="Models").wait_for()
            assert data_tabs.get_by_role("link").all_inner_texts() == ["Models", "Sources", "Warehouse", "Map"]
            expect(data_tabs.get_by_role("link", name="Models")).to_have_attribute("aria-current", "page")
            chain = page.get_by_role("list", name="How Direct Lending Portfolio is made")
            for text, href in [("sources", "/data/sources?model=portfolio_model"),
                               ("holdings_transform", "/data/portfolio_model/transform"),
                               ("tables", "/data/warehouse?model=portfolio_model"),
                               ("measures", "/data/portfolio_model"),
                               ("reports", "/?model=portfolio_model")]:
                expect(chain.get_by_role("link", name=re.compile(text))).to_have_attribute("href", href)
            # Sources: the crm connection is not reachable here, says so quietly,
            # and names the transform that reads it.
            data_tabs.get_by_role("link", name="Sources").click()
            page.wait_for_url("**/data/sources")
            page.locator('[data-source="crm"]').click()
            page.wait_for_url("**/data/sources?source=crm")
            expect(page.get_by_text("Not connected here · set TRACEBI_CRM_URL")).to_be_visible()
            expect(page.locator(".src-readby")).to_contain_text("holdings_transform (issuer_ratings)")
            # Warehouse: who wrote each table, and what fed it.
            data_tabs.get_by_role("link", name="Warehouse").click()
            page.wait_for_url("**/data/warehouse")
            rating = page.locator('#wh-warehouse [data-table="dim_rating"]')
            expect(rating).to_contain_text("Written by holdings_transform")
            expect(rating).to_contain_text("Fed from crm.issuer_ratings · snapshot inputs/issuer_ratings.csv")
            fail_on_browser_errors()

            # Picking a model opens its page: the line as its header, stations
            # that are links, and tabs with addresses of their own. Model is the
            # one open to start with.
            data_tabs.get_by_role("link", name="Models").click()
            page.wait_for_url("**/data")
            page.get_by_role("link", name=re.compile(r"^Direct Lending Portfolio")).click()
            page.wait_for_url("**/data/portfolio_model")
            line = page.get_by_role("navigation", name="How portfolio_model is made")

            def station(name: str):
                return line.get_by_role("link", name=re.compile(rf"^{name}\b"))

            expect(station("Model")).to_have_attribute("aria-current", "page")
            # Its facts are read from what exists: the sources the transform
            # names, the transform the pipeline runs, the warehouse file it
            # writes, the model's tables and joins.
            expect(station("Sources")).to_contain_text("crm")
            expect(station("Sources")).to_have_attribute("href", "/data/sources?model=portfolio_model")
            expect(station("Transform")).to_contain_text("holdings_transform")
            expect(line).to_contain_text("warehouse.duckdb")
            expect(station("Model")).to_contain_text(re.compile(r"\d+ tables · \d+ joins"))
            station("Transform").click()
            page.wait_for_url("**/data/portfolio_model/transform")
            expect(station("Transform")).to_have_attribute("aria-current", "page")
            station("Model").click()
            page.wait_for_url("**/data/portfolio_model")
            page.go_back()
            page.wait_for_url("**/data/portfolio_model/transform")
            expect(sidebar.get_by_role("link", name="Data", exact=True)).to_have_attribute("aria-current", "page")
            # The Reports station is the library, narrowed to the model.
            station("Reports").click()
            page.wait_for_url("**/?model=portfolio_model")
            page.go_back()
            fail_on_browser_errors()

            # Ask keeps its own model pick.
            sidebar.get_by_role("link", name="Ask", exact=True).click()
            page.wait_for_url("**/ask")
            page.get_by_role("link", name=re.compile(r"^Direct Lending Portfolio")).click()
            page.wait_for_url("**/ask?model=portfolio_model")
            page.get_by_role("heading", name="Ask", exact=True).wait_for()
            assert page.get_by_label("Model").input_value() == "portfolio_model"
            fail_on_browser_errors()

            # The Map is Data's models as one picture: opening one zooms in, and
            # picking a measure says in words which reports ask for it. Models and
            # reports go by their labels.
            page.goto(base + "/data")
            page.get_by_role("navigation", name="Data: what to show").get_by_role("link", name="Map").click()
            page.wait_for_url("**/data/map")
            page.get_by_role("button", name="Open Direct Lending Portfolio").click()
            page.wait_for_url("**/data/map?model=portfolio_model")
            page.get_by_role("button", name=re.compile(r"^measure: fv_share")).click()
            expect(page.get_by_label("Selection")).to_contain_text("Portfolio Concentration")
            fail_on_browser_errors()

            # Old addresses land on the page that replaced them, query and all.
            for old, new in [
                ("/models/portfolio_model?tab=refresh", "/data/portfolio_model/transform"),
                ("/m/portfolio_model/refresh", "/data/portfolio_model/transform"),
                ("/m/portfolio_model/sources", "/data/portfolio_model/sources"),
                ("/m/portfolio_model", "/data/portfolio_model"),
                ("/m/portfolio_model/model", "/data/portfolio_model/model"),
                ("/m/portfolio_model/transform", "/data/portfolio_model/transform"),
                ("/m/portfolio_model/reports", "/?model=portfolio_model"),
                ("/m/portfolio_model/reports?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/m/portfolio_model?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/m/portfolio_model/explore", "/ask?model=portfolio_model"),
                ("/m/portfolio_model/runs", "/runs?model=portfolio_model"),
                ("/models/portfolio_model", "/data/portfolio_model"),
                ("/models/portfolio_model?tab=explore", "/ask?model=portfolio_model"),
                ("/models/portfolio_model?tab=reports", "/?model=portfolio_model"),
                ("/explore", "/ask"),
                ("/models", "/data"),
                ("/map", "/data/map"),
                ("/data?view=map", "/data/map"),
                ("/data?view=map&model=portfolio_model", "/data/map?model=portfolio_model"),
                ("/data/portfolio_model/reports", "/?model=portfolio_model"),
                ("/data/portfolio_model/reports?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/sources", "/data/sources"),
                ("/connectors", "/data/sources"),
                ("/refresh", "/data"),
                ("/pipelines?model=portfolio_model", "/data/portfolio_model/transform"),
                ("/reports", "/"),
                ("/reports?r=portfolio_model/portfolio_book", "/reports/portfolio_model/portfolio_book"),
                ("/?r=portfolio_model/portfolio_book", "/reports/portfolio_model/portfolio_book"),
                ("/workflow", "/docs/get-started#phases"),
                ("/getting-started", "/docs/get-started"),
                ("/getting-started#phases", "/docs/get-started#phases"),
                ("/handbook", "/docs"),
                ("/handbook/concepts/trace", "/docs/concepts/trace"),
                ("/docs/concepts/receipts", "/docs/concepts/trace"),
            ]:
                page.goto(base + old)
                page.wait_for_url(base + new)
            fail_on_browser_errors()

            # A model's reports are the library, narrowed to it (the Data page's
            # Reports station goes there). A fresh checkout has built nothing, and
            # opening a report does not build it: it says so, marked, and offers
            # to build it.
            page.goto(base + "/?model=portfolio_model")
            # The redirects above each asked the server to re-check every build;
            # give the desk time to answer this page too.
            expect(lib_row).to_contain_text("Never built", timeout=60_000)
            expect(lib_row).to_contain_text("Mondays 07:00")   # its schedule, in words
            lib_row.click()
            page.wait_for_url(f"**/reports/{_REPORT}")
            page.get_by_text("There is no page to show yet").wait_for()
            assert page.locator("iframe").count() == 0
            # The way to a draft is in the command bar.
            page.get_by_role("button", name="Edit as a draft").wait_for()
            page.get_by_role("button", name="Build it now").click()
            try:
                page.locator("iframe.rp__frame").wait_for()
            except Exception as exc:
                fail_on_browser_errors()
                raise AssertionError(page.inner_text("body")[:4000]) from exc
            fail_on_browser_errors()

            # The report has the whole page, at an address of its own.
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
            # The report frame has no network and needs none: the page carries
            # its slice and recomputes the cut itself, so it never asks the app.
            asked = []
            page.on("request", lambda r: asked.append(r.url) if r.url.endswith("/selection") else None)
            report.locator("select[data-tb-column='dim_issuer.sector']").select_option("Software")
            report.locator("#fig-treemap g.sector").first.wait_for()
            expect(report.locator("#fig-treemap g.cell")).to_have_count(2)
            assert asked == []
            fail_on_browser_errors()

            # An open report is a page of its own: the nav stays as a rail, the list
            # does not, and the breadcrumb's Reports link goes back to the library.
            rail = page.get_by_role("navigation", name="Main")
            expect(rail.get_by_role("link", name="Reports")).to_have_attribute("aria-current", "page")
            assert not page.get_by_placeholder("Search reports…").is_visible()
            crumb = page.get_by_role("navigation", name="Where this report is")
            back = crumb.get_by_role("link", name="Reports", exact=True)
            back.wait_for()
            crumb.get_by_role("link", name="Direct Lending Portfolio").wait_for()

            # Export is one menu of the three files, and says which carries the trace.
            page.get_by_role("button", name="Export").click()
            menu = page.get_by_role("menu")
            links = menu.get_by_role("menuitem").all()
            assert [link.inner_text().split("\n")[0] for link in links] == ["PDF", "Excel", "HTML"]
            assert [link.get_attribute("href").rsplit("=", 1)[1] for link in links] == ["pdf", "xlsx", "html"]
            assert "the file with its trace" in menu.inner_text()
            assert "receipt" not in menu.inner_text().lower()
            page.keyboard.press("Escape")
            assert menu.count() == 0

            # The receipt, the lineage, the builds and the files are one panel
            # beside the report, "About this build". Its Trace is the build's
            # own certificate, in the honesty language, sink contracts and all.
            page.get_by_role("button", name="About this build").click()
            page.get_by_role("tab", name="Trace").click()
            page.get_by_role("button", name="Check again").wait_for()
            receipt = page.frame_locator("iframe.rpanel__receipt")
            receipt.get_by_text("How each number was made").wait_for()
            receipt.get_by_text("This page does not claim the numbers are right", exact=False).wait_for()
            receipt.locator("summary", has_text="About this build").click()
            receipt.get_by_text("fact_holdings: the sink satisfied its contract").wait_for()
            page.get_by_role("tab", name="Lineage").click()
            page.get_by_text("Where the numbers on this page came from").wait_for()
            page.get_by_text("fact_holdings").first.wait_for()
            page.get_by_role("tab", name="Files").click()
            page.get_by_role("button", name="report.json").wait_for()
            page.get_by_role("button", name="Close the panel").click()
            assert page.get_by_role("tab", name="Files").count() == 0

            downloaded = page.evaluate(
                """async (url) => {
                    const response = await fetch(url);
                    return {status: response.status, body: await response.text()};
                }""",
                f"/api/reports/{_REPORT}/download?format=html",
            )
            assert downloaded["status"] == 200, _tail(log_path)
            assert _TITLE in downloaded["body"]

            # Rebuild makes more build rows, and the library re-checks the new one:
            # the strip counts it as reproducing, and its row says when it was built.
            page.get_by_role("button", name="Rebuild").click()
            page.get_by_text("Report ran successfully").wait_for()
            # The report's own chip says what the app's check found: the file
            # alone says "Not checked", framed here it is told the verdict. The
            # app's header shows it, so the masthead keeps only its Trace link;
            # the frame's trace says the same as the header.
            frame = page.frame_locator("iframe.rp__frame")
            expect(page.locator(".rp__titlerow")).to_contain_text("Reproduces", timeout=60_000)
            expect(frame.locator(".tb-receipt-drawer .tb-verdict").first).to_have_text(
                "Reproduces", timeout=60_000)
            expect(frame.locator(".tb-masthead .tb-verdict").first).to_be_hidden()
            expect(frame.locator(".tb-masthead .tb-receipt-link").first).to_have_text("Trace")
            # The footer is one line: its link opens the drawer, which holds
            # what the build's disclosure says, so the disclosure stands down.
            expect(frame.locator(".tb-footer-line .tb-receipt-link").first).to_have_text(
                "How these numbers were made")
            expect(frame.locator(".tb-footer-line + .tb-footer-details").first).to_be_hidden()
            back.click()
            page.wait_for_url(base + "/")
            glance = page.get_by_role("group", name="At a glance")
            expect(glance).to_contain_text("1 reproduces")
            expect(lib_row).to_contain_text("Reproduces")
            expect(lib_row).to_contain_text("Built ")

            # A build whose source changed since never reads as fine: the library's
            # row and strip, the model's line, the chip and the bar of
            # its page all say Needs a look, and nothing there claims it reproduces.
            def source_changed(route):
                desk = route.fetch().json()
                for built in desk["builds"]:
                    built["verdict"] = "source_drift"
                route.fulfill(json=desk)

            page.route("**/api/desk", source_changed)
            page.reload()
            # The desk re-runs every recorded query before it answers.
            expect(lib_row).to_contain_text("Needs a look", timeout=60_000)
            expect(lib_row).not_to_contain_text("Reproduces")
            expect(glance).to_contain_text("1 needs a look")
            expect(glance).to_contain_text("0 reproduce")
            # The model's line counts it the same way, in the chip's words.
            page.goto(f"{base}/data/portfolio_model")
            line = page.get_by_role("navigation", name="How portfolio_model is made")
            expect(line.get_by_role("link", name=re.compile(r"^Reports\b"))).to_contain_text("1 needs a look")
            expect(line).not_to_contain_text("reproduce")
            page.goto(f"{base}/reports/{_REPORT}")
            page.get_by_role("button", name="Needs a look", exact=True).wait_for()
            why = page.get_by_role("status").filter(has_text="The data changed since it was built")
            expect(why).to_be_visible()
            assert "Reproduces" not in why.inner_text()
            expect(frame.locator(".tb-receipt-drawer .tb-verdict").first).to_have_text("Needs a look")
            page.unroute("**/api/desk")

            # A library row opens the same page, titled with the report's own name.
            page.goto(base + "/")
            fail_on_browser_errors()
            lib_row.click()
            page.wait_for_url(f"**/reports/{_REPORT}")
            page.locator("iframe").wait_for()
            assert page.get_by_role("heading", name=_TITLE, exact=True).is_visible()

            # A build is not a check: History shows the list's verdict on the newest
            # build of the report, and a plain "Not checked" (never green) on
            # every older one. By default a report is one row, its older builds
            # folded under it.
            page.goto(base + "/runs")
            page.get_by_role("heading", name="History", exact=True).wait_for()
            # A row reads the report's name; its identifier is the row's data-target.
            rows = page.locator(f'tr[data-target="{_REPORT}"]')
            rows.first.wait_for()
            assert _TITLE in rows.first.inner_text()
            page.get_by_text("Checking…").wait_for(state="detached")
            expect(rows).to_have_count(1)
            rows.first.get_by_role("button", name=re.compile(r"^\d+ older runs?")).click()
            verdicts = [r.locator(".runs__verdict").inner_text() for r in rows.all()]
            assert len(verdicts) >= 2, verdicts
            assert verdicts[0] == "Reproduces", verdicts
            assert set(verdicts[1:]) == {"Not checked"}, verdicts
            # Every run lists them flat, and stays in the address.
            page.get_by_role("button", name="Every run", exact=True).click()
            page.wait_for_url("**/runs?all=1")
            expect(rows).to_have_count(len(verdicts))
            fail_on_browser_errors()

            # Given room, a report's three KPI cards sit on one row. (The old
            # ?r= address still opens it.)
            page.goto(f"{base}/reports?r=portfolio_model/portfolio_overview")
            page.wait_for_url(f"{base}/reports/portfolio_model/portfolio_overview")
            page.get_by_role("button", name="Build it now").click()
            cards = page.frame_locator("iframe").locator(".tb-kpi")
            cards.nth(2).wait_for()
            tops = {round(card.bounding_box()["y"]) for card in cards.all()}
            assert cards.count() == 3 and len(tops) == 1, tops

            # Each tab can show the code behind what it shows.
            page.goto(base + "/data/portfolio_model/model")
            page.get_by_role("button", name="Code", exact=True).click()
            page.get_by_text("models/portfolio_model.yaml").first.wait_for()
            page.goto(base + "/data/portfolio_model/transform")
            page.get_by_role("button", name="Code", exact=True).click()
            page.get_by_role("button", name="transform", exact=True).click()
            page.get_by_text("transforms/holdings_transform.sql").first.wait_for()
            # The Transform tab says what the warehouse holds, and that its checks
            # passed when it was last written, before any report is opened.
            table = page.locator("details", has_text="fact_holdings")
            table.wait_for()
            assert re.search(r"[\d,]+ rows", table.locator("summary").inner_text())
            assert table.locator("summary").get_by_text("Checks passed", exact=True).count() == 1
            table.locator("summary").click()
            table.get_by_text("The sink satisfied its contract").wait_for()
            fail_on_browser_errors()
            # Ask: a sentence of the model's tokens. A measure and a dimension
            # picked from their slots; the answer is the query's own rows: the
            # sentence, a chart whose first value is the API's display text for
            # that row, and Not checked (an ad hoc query has no receipt).
            page.goto(base + "/ask?model=portfolio_model")
            sentence = page.locator(".ask-sentence")
            sentence.get_by_role("button", name="a measure").click()
            page.get_by_role("option", name=re.compile(r"^Measure\s*Fair value")).click()
            sentence.get_by_role("button", name="a dimension").click()
            page.get_by_role("option", name=re.compile(r"Sector")).click()
            sentence.get_by_role("button", name="in any order").click()
            page.get_by_role("option", name=re.compile(r"Largest first")).click()
            page.get_by_role("button", name="Ask", exact=True).click()
            expect(page.locator(".ask-answer__sentence")).to_have_text(
                "Fair value by sector, largest first — 6 rows")
            api = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"{base}/api/models/portfolio_model/query", method="POST",
                headers={"Content-Type": "application/json"},
                data=json.dumps({"fact": "fact_holdings", "measures": ["fair_value"],
                                 "dimensions": ["dim_issuer.sector"],
                                 "order_by": [{"column": "fair_value", "desc": True}]}).encode(),
            )).read())
            first = api["display"][0]["fair_value"]
            expect(page.locator(".ask-bars .recharts-label").first).to_have_text(first)
            answer = page.get_by_role("region", name="The answer")
            expect(answer.locator(".verdict")).to_have_text("Not checked")
            assert "&q=" in page.url        # the link reproduces the question
            fail_on_browser_errors()

            # Advanced is the query builder on the same question: the measure
            # picked above is ticked there. It leads with the model's own
            # measures (each with what it means), sends their names, and the
            # results are in their declared formats.
            page.get_by_text("Advanced: the query builder").click()
            builder = page.locator(".explore-grid")
            expect(builder.get_by_role("checkbox").first).to_be_checked()
            builder.get_by_text("Total fair value").wait_for()
            # However long the builder is, Run stays in view.
            builder.scroll_into_view_if_needed()
            expect(page.get_by_text("▶ Run query")).to_be_in_viewport(ratio=1)
            builder.get_by_text("positions", exact=True).first.click()
            page.get_by_text("▶ Run query").click()
            expect(page.locator(".ask-answer__sentence")).to_contain_text("Fair value and positions by sector")
            page.get_by_text("The query as code").click()
            page.locator(".codeview__tabs").get_by_role("button", name="Python").click()
            assert 'measures=["fair_value", "positions"]' in page.locator(".codeview__code").inner_text()
            assert re.search(r"\$[\d,]+", answer.locator("table tbody tr").first.inner_text())
            fail_on_browser_errors()

            # Group by offers only what the picked fact joins.
            page.goto(base + "/ask?model=housing_model")
            page.get_by_text("Advanced: the query builder").click()
            builder = page.locator(".explore-grid")
            expect(builder).to_contain_text("dim_year")
            expect(builder).not_to_contain_text("dim_held")
            page.get_by_role("button", name="fact_cohort_path").click()
            expect(builder).to_contain_text("dim_held")
            page.get_by_role("button", name="fact_ten_year").click()
            expect(builder).not_to_contain_text("dim_held")
            expect(builder).to_contain_text("dim_cohort")
            fail_on_browser_errors()

            # Transform: Refresh data, its one primary action, opens the Runs
            # tab, which follows the run to its end…
            page.goto(base + "/data/portfolio_model/transform")
            # The page reads the warehouse as it opens; a transform that starts
            # writing it meanwhile fails, so let those reads finish first.
            page.wait_for_load_state("networkidle")
            assert page.get_by_role("button", name="Refresh data").count() == 1
            page.get_by_role("button", name="Refresh data").click()
            output = page.get_by_role("log", name="Run output")
            output.get_by_text("Run succeeded").wait_for()
            text = output.inner_text()
            assert "[transform] ✓" in text and "[build] ✓" in text, text
            assert page.get_by_role("list", name="Runs").get_by_role("button").count() == 1
            # …the Transform tab now says when it was refreshed…
            page.get_by_text("Last refreshed").wait_for()
            # …and the run links the reports it rebuilt, each to its page in the app.
            page.get_by_role("link", name="portfolio_book", exact=True).click()
            page.wait_for_url("**/reports/portfolio_model/portfolio_book")
            fail_on_browser_errors()

            # That refresh is a run of its model: its Runs tab lists it, and opens
            # in History, where All models names the model beside it.
            page.goto(base + "/data/portfolio_model/transform")
            page.get_by_role("link", name="Runs", exact=True).click()
            page.wait_for_url("**/data/portfolio_model/runs")
            page.locator("tr", has_text="Pipeline run").first.wait_for()
            page.get_by_role("link", name="Open in History").click()
            page.wait_for_url("**/runs?model=portfolio_model")
            page.get_by_role("heading", name="History", exact=True).wait_for()
            page.locator("tr", has_text="Pipeline run").first.wait_for()
            page.goto(base + "/runs")
            pipeline_row = page.locator("tr", has_text="Pipeline run").first
            pipeline_row.wait_for()
            expect(pipeline_row).to_contain_text("Direct Lending Portfolio")   # the model, by its label
            expect(sidebar.get_by_role("link", name="Review", exact=True)).to_have_attribute("aria-current", "page")
            fail_on_browser_errors()

            # Drafts: a report draft on disk is listed on Review's Drafts tab
            # (the old /drafts lands there), rendered live, follows edits to
            # its file without a reload, and publishes with a toast.
            draft = project / "drafts" / "anonymous" / "reports" / "portfolio_model" / "draft_demo"
            shutil.copytree(project / "reports" / "portfolio_model" / "portfolio_overview", draft)
            template = draft / "app.jsx"
            template.write_text(
                template.read_text(encoding="utf-8").replace("The funds' Schedule", "Draft Marker One"),
                encoding="utf-8")
            page.goto(base + "/drafts")
            page.wait_for_url("**/review/drafts")
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
            page.get_by_role("button", name="app.jsx").wait_for()
            page.get_by_role("button", name="Publish", exact=True).click()
            # The destination picker names every place it can go and whether
            # that publishes directly or asks (this app has no sign-in: Manage).
            picker = page.get_by_label("Publish to", exact=True)
            picker.wait_for()
            assert "Its own place" in picker.locator("option:checked").inner_text()
            page.get_by_text("Publishes directly: you hold Publish permission there.").wait_for()
            page.get_by_role("button", name="Publish for everyone").click()
            page.get_by_text("Published report portfolio_model/draft_demo").wait_for()
            page.get_by_role("link", name="Open the published report").wait_for()
            assert (project / "reports" / "portfolio_model" / "draft_demo" / "report.json").is_file()
            fail_on_browser_errors()

            # The library is the folder tree, each folder under its model's name.
            # Where no folder file applies and the person's level is the same
            # everywhere, a folder says nothing about permissions.
            page.goto(base + "/")
            page.get_by_role("region", name="Direct Lending Portfolio").get_by_role(
                "button", name=re.compile(r"Direct Lending Portfolio\s*\d+$")).wait_for()
            expect(page.get_by_role("button", name="Permissions")).to_have_count(0)
            fail_on_browser_errors()

            # A signed-in person also has My published (always listed, even
            # empty), and a folder's permissions are read-only in the app. The
            # sign-in is faked at the API: the real one is the e2e journey.
            def fake_folders(route):
                route.fulfill(json={
                    "personal": "my-published/ada@example.com",
                    "folders": [{
                        "path": "my-published/ada@example.com", "name": "My published",
                        "personal": True, "mine": True, "level": "publish", "mode": "publish",
                        "accepts": "labelled", "reports": 0,
                        "permissions": {"file": None, "grants": {}, "accepts": "labelled",
                                        "malformed": False, "editable": False},
                    }, {
                        "path": "portfolio_model", "name": "portfolio_model", "personal": False,
                        "mine": False, "level": "manage", "mode": "publish",
                        "accepts": "labelled", "reports": 9,
                        "permissions": {"file": "portfolio_model/_folder.yaml",
                                        "grants": {"publish": ["leads"]}, "accepts": "labelled",
                                        "malformed": False, "editable": False},
                    }]})
            page.route("**/api/folders", fake_folders)
            page.goto(base + "/")
            page.get_by_role("button", name=re.compile(r"My published\s*\d*$")).wait_for()
            page.get_by_text("Nothing here yet.").wait_for()
            # A personal folder and one with a _folder.yaml say who may do what,
            # behind a Permissions disclosure at the folder's header.
            perms = page.get_by_role("button", name="Permissions")
            expect(perms).to_have_count(2)
            perms.first.click()
            page.get_by_text("Only you see this folder unless you share it by file.").wait_for()
            perms.nth(1).click()
            page.get_by_text("From portfolio_model/_folder.yaml.").wait_for()
            page.get_by_text("Editing them here is not available yet.").first.wait_for()
            fail_on_browser_errors()
            page.unroute("**/api/folders")

            # A model draft that moves published figures lists them and makes
            # Publish wait for the person to accept the impact.
            model_text = (project / "models" / "portfolio_model.yaml").read_text(encoding="utf-8")
            moved = model_text.replace("name: fair_value\n    column: fair_value\n    agg: sum",
                                       "name: fair_value\n    column: fair_value\n    agg: avg", 1)
            assert moved != model_text
            model_draft = project / "drafts" / "anonymous" / "models" / "portfolio_model.yaml"
            model_draft.parent.mkdir(parents=True, exist_ok=True)
            model_draft.write_text(moved, encoding="utf-8")
            page.goto(base + "/drafts/anonymous/models/portfolio_model")
            page.get_by_role("heading", name="Impact on published reports").wait_for()
            impact = page.get_by_role("list", name="Reports this model draft touches")
            impact.get_by_text("Numbers move").first.wait_for()
            page.get_by_role("button", name="Publish", exact=True).click()
            go = page.get_by_role("button", name="Publish for everyone")
            expect(go).to_be_disabled()
            page.get_by_role("checkbox").check()
            expect(go).to_be_enabled()
            go.click()
            page.get_by_text("Published model portfolio_model").wait_for()
            assert (project / "models" / "portfolio_model.yaml").read_text(encoding="utf-8") == moved
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


def test_the_sidebar_shows_what_the_role_uses(tmp_path: Path) -> None:
    """Behind a proxy that names roles, a viewer's sidebar is Reports and Ask,
    an analyst's adds Review (its tabs Attention, Drafts, History, Verify), and
    an address above the role is a plain page saying who it is for. The API
    enforces the roles; this is what the app shows."""
    from playwright.sync_api import expect, sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(
        _PROJECT,
        project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "data", ".tracebi"),
    )
    port = _free_port()
    env = os.environ.copy()
    env["TRACEBI_APP"] = ""
    for key in ("TRACEBI_REPORTS_DIR", "TRACEBI_MODELS_DIR", "TRACEBI_PIPELINES_DIR",
                "TRACEBI_DEV_MODE", "TRACEBI_OUTPUT_ROOT"):
        env.pop(key, None)
    env.update({
        "TRACEBI_AUTH_PROXY_HEADER": "X-Forwarded-User",
        "TRACEBI_AUTH_PROXY_TRUSTED_IPS": "127.0.0.1",
        "TRACEBI_AUTH_ROLE_HEADER": "X-Forwarded-Role",
    })
    log_path = tmp_path / "server.log"
    log_file = log_path.open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "-m", "tracebi.web.run", "--port", str(port), "--no-reload"],
        cwd=project, env=env, stdout=log_file, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_health(f"{base}/api/health", server, log_path)
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)

            def as_role(role: str):
                page = browser.new_context(extra_http_headers={
                    "X-Forwarded-User": f"{role}@example.com", "X-Forwarded-Role": role,
                }).new_page()
                page.set_default_timeout(60_000)
                page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
                return page

            # An address above the role: a plain page, in the app's frame (drawn
            # once the role is known, so the sidebar below is the viewer's).
            viewer = as_role("viewer")
            viewer.goto(base + "/data")
            viewer.get_by_role("heading", name="This part of the app is for admins.").wait_for()
            expect(viewer.get_by_role("link", name="Go to the reports")).to_have_attribute("href", "/")
            sidebar = viewer.get_by_role("navigation", name="Main")
            sidebar.get_by_role("link", name="Ask", exact=True).wait_for()
            for place in ("Data", "Review"):
                expect(sidebar.get_by_role("link", name=place, exact=True)).to_have_count(0)
            # Docs is for everyone: the handbook, Get started first.
            sidebar.get_by_role("link", name="Docs", exact=True).click()
            viewer.wait_for_url("**/docs")
            viewer.get_by_role("heading", name="Docs", exact=True).wait_for()
            viewer.get_by_role("link", name="Get started", exact=True).click()
            viewer.wait_for_url("**/docs/get-started")
            viewer.get_by_role("heading", name="Get started", exact=True).wait_for()
            for tab in ("/data/sources", "/data/warehouse", "/data/map"):
                viewer.goto(base + tab)
                viewer.get_by_role("heading", name="This part of the app is for admins.").wait_for()
            # ⌘K lists the same places: nothing inside Review or Data.
            viewer.keyboard.press("Control+k")
            viewer.get_by_placeholder("Jump to a page, model, report, pipeline…").fill("History")
            viewer.get_by_text("No matches for").wait_for()
            viewer.keyboard.press("Escape")
            viewer.goto(base + "/review")
            viewer.get_by_role("heading", name="This part of the app is for analysts.").wait_for()
            # An open report keeps the same places in its rail.
            viewer.goto(f"{base}/reports/{_REPORT}")
            rail = viewer.get_by_role("navigation", name="Main")
            expect(rail.get_by_role("link", name="Reports")).to_have_attribute("aria-current", "page")
            expect(rail.get_by_role("link", name="Ask")).to_have_count(1)
            expect(rail.get_by_role("link", name="Review")).to_have_count(0)

            analyst = as_role("analyst")
            analyst.goto(base + "/runs")
            sidebar = analyst.get_by_role("navigation", name="Main")
            expect(sidebar.get_by_role("link", name="Review", exact=True)).to_have_attribute("aria-current", "page")
            expect(sidebar.get_by_role("link", name="Data", exact=True)).to_have_count(0)
            tabs = analyst.get_by_role("navigation", name="Review: what to show")
            assert tabs.get_by_role("link").all_inner_texts() == ["Attention", "Drafts", "History", "Verify"]
            expect(tabs.get_by_role("link", name="History")).to_have_attribute("aria-current", "page")
            analyst.goto(base + "/data/portfolio_model")
            analyst.get_by_role("heading", name="This part of the app is for admins.").wait_for()
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
