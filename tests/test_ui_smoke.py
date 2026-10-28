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
# The library's h1 is its name; how fresh it is is the lede's, in plain words.
_LIBRARY_H1 = re.compile(r"^Reports$")


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
    workflow = subprocess.run(
        [sys.executable, "run_workflow.py"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    assert workflow.returncode == 0, workflow.stderr or workflow.stdout
    # The workflow builds every report, so the library opens built. This
    # journey starts from none built, so opening a report builds it (and
    # records the run the Runs step reads).
    for built in (project / "output").rglob("*.html"):
        built.unlink()

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
            # What the report frame tells the app, kept for a failure's report.
            page.add_init_script("""
                window.__tbMsgs = [];
                window.addEventListener('message', e => {
                  const m = e.data;
                  if (!m || m.tracebiFrame !== 1) return;
                  window.__tbMsgs.push([Math.round(performance.now()), m.type,
                    m.type === 'tracebi-selection' && m.payload
                      ? JSON.stringify(m.payload.selection) + ' authored=' + m.payload.authored : '']);
                }, true);
            """)
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
            # name, with its verdict and schedule. The sidebar is its folder
            # tree (All reports, then a row per folder), then Data, Review and
            # Docs; Ask is not a place of its own, and the foot keeps no Help link.
            page.goto(base + "/")
            page.get_by_role("heading", level=1, name=_LIBRARY_H1).wait_for()
            expect(page).to_have_title("Reports · TraceBi")
            assert page.url.rstrip("/") == base, page.url
            sidebar = page.get_by_role("navigation", name="Main")
            all_reports = sidebar.get_by_role("link", name=re.compile(r"^All reports \d+$"))
            all_reports.wait_for()
            for place in ("Data", "Review", "Docs"):
                sidebar.get_by_role("link", name=place, exact=True).wait_for()
            expect(sidebar.get_by_role("link", name="Ask", exact=True)).to_have_count(0)
            expect(sidebar.get_by_role("link", name="Help")).to_have_count(0)
            expect(all_reports).to_have_attribute("aria-current", "page")
            folder_row = sidebar.get_by_role("link", name=re.compile(r"^Direct Lending Portfolio \d+$"))
            expect(folder_row).to_have_attribute("href", "/?folder=portfolio_model")
            # The first visit shows one quiet row under the folder tiles: Get
            # started, the showcase. Dismissed, it is gone, and stays gone.
            welcome = page.get_by_role("region", name="Welcome to TraceBi")
            expect(welcome).to_be_visible()
            expect(welcome.get_by_role("link", name="Get started")).to_have_attribute("href", "/docs/get-started")
            expect(welcome.get_by_role("link", name=re.compile(r"^Open .*Showcase"))).to_have_attribute(
                "href", "/reports/portfolio_model/portfolio_showcase")
            welcome.get_by_role("button", name="Dismiss the welcome").click()
            expect(welcome).to_have_count(0)
            page.reload()
            page.get_by_role("heading", level=1, name=_LIBRARY_H1).wait_for()
            expect(page.get_by_role("region", name="Welcome to TraceBi")).to_have_count(0)
            # An empty list says what it is and offers the one thing that
            # fills it, and that action lands where it says.
            page.goto(base + "/review/drafts")
            page.get_by_text("No drafts", exact=True).wait_for()
            page.get_by_role("link", name="Open the reports").click()
            page.wait_for_url(base + "/")
            page.get_by_role("heading", level=1, name=_LIBRARY_H1).wait_for()
            # The folder's own row of covers holds the report (the row of the
            # newest builds may hold it too).
            lib_row = page.locator(f'[data-row="folder"] [data-report="{_REPORT}"]')
            expect(lib_row).to_contain_text(_TITLE)
            # The verdict waits on the desk re-checking every receipt the
            # workflow left.
            expect(lib_row).to_contain_text("Never built", timeout=60_000)
            expect(lib_row).to_contain_text("Mondays 07:00")   # its schedule, in words
            # A project is a filter chip on the list, not the frame of the app;
            # the chips say projects, as the tiles above them do.
            chips = page.get_by_role("group", name="Project")
            expect(chips.get_by_role("button", name=re.compile(r"^All projects"))).to_be_visible()
            chips.get_by_role("button", name=re.compile(r"^Direct Lending Portfolio")).click()
            page.wait_for_url("**/?model=portfolio_model")
            expect(page.locator('[data-report="housing_model/affordability"]')).to_have_count(0)
            expect(lib_row).to_be_visible()
            fail_on_browser_errors()

            # Grid is the library as a directory: a tile per folder, then a
            # row of covers per folder, each report in its folder's row once,
            # each cover one link, the showcase first in its row. With no
            # covers taken here, every tile draws its own. List is one toggle
            # away, and stays picked after a reload.
            page.goto(base + "/")
            reports = json.loads(urllib.request.urlopen(f"{base}/api/reports").read())
            listed = len(reports)
            folders = {r["name"].rsplit("/", 1)[0] for r in reports}
            expect(page.locator(".ftiles a.ftile[data-folder]")).to_have_count(len(folders))
            tiles = page.locator('[data-row="folder"] a.ctile[data-report]')
            expect(tiles).to_have_count(listed)
            assert sorted(tiles.evaluate_all("els => els.map(e => e.dataset.report)")) == sorted(
                r["name"] for r in reports)
            expect(page.locator('[data-row="folder"] a.ctile .gcover')).to_have_count(listed)
            row = page.get_by_role("region", name="Direct Lending Portfolio")
            assert row.locator("a.ctile").first.get_attribute("data-report") == _REPORT
            expect(row.get_by_role("link", name=re.compile("^Open project"))).to_have_attribute(
                "href", "/?folder=portfolio_model")
            # The library names its top-level folders as projects: the tiles
            # are the Projects, the SaaS project's tile says so over its name,
            # and the old ?project= address opens the same page as ?folder=.
            projects = page.get_by_role("list", name="Projects")
            saas = projects.locator('a.ftile[data-folder="saas_model"]')
            expect(saas.locator(".ftile__kind")).to_have_text("Project")
            expect(saas.locator(".ftile__name")).to_have_text("SaaS Subscriptions")
            expect(page.locator(".dir-head__lede")).to_contain_text(f"{len(folders)} projects")
            view = page.get_by_role("group", name="View")
            view.get_by_role("button", name="List").click()
            expect(page.locator(".lfolder__rows a.lrow[data-report]")).to_have_count(listed)
            expect(tiles).to_have_count(0)
            page.reload()
            expect(page.locator(".lfolder__rows a.lrow[data-report]")).to_have_count(listed)
            view = page.get_by_role("group", name="View")
            view.get_by_role("button", name="Grid").click()
            expect(tiles).to_have_count(listed)
            # The whole tile is the link; a later step follows it.
            expect(row.locator("a.ctile").first).to_have_attribute("href", f"/reports/{_REPORT}")
            # A search narrows every row and drops the empty ones.
            page.get_by_label("Search reports").fill("Cohort")
            expect(tiles).to_have_count(1)
            expect(page.get_by_role("region", name="Direct Lending Portfolio")).to_have_count(0)
            page.get_by_label("Search reports").fill("")
            fail_on_browser_errors()

            # A folder has a page of its own: its hero (the label as the h1, what
            # it holds, Ask this model), then its reports by kind, and the
            # sidebar's row for it is the current entry, with its kinds under it.
            sidebar.get_by_role("link", name=re.compile(r"^Direct Lending Portfolio \d+$")).click()
            page.wait_for_url("**/?folder=portfolio_model")
            page.get_by_role("heading", level=1, name="Direct Lending Portfolio").wait_for()
            # A top-level folder's page is a project's: its title and its
            # eyebrow say Project.
            expect(page).to_have_title("Direct Lending Portfolio · Project · Reports · TraceBi")
            expect(page.locator(".fhero__eyebrow")).to_contain_text(re.compile(r"^Project"))
            crumbs = page.get_by_role("navigation", name="Breadcrumb")
            expect(crumbs.get_by_role("link", name="Library")).to_have_attribute("href", "/")
            expect(folder_row).to_have_attribute("aria-current", "page")
            expect(all_reports).not_to_have_attribute("aria-current", "page")
            sidebar.get_by_role("link", name=re.compile(r"^Dashboards · \d+$")).wait_for()
            ours = [r for r in reports if r["name"].startswith("portfolio_model/")]
            dashboards = page.get_by_role("region", name="Dashboards")
            pages = page.get_by_role("region", name="Pages")
            expect(dashboards.locator("a.ctile[data-report]")).to_have_count(
                sum(r["made_from"] == "app.jsx" for r in ours))
            expect(pages.locator("a.ctile[data-report]")).to_have_count(
                sum(r["made_from"] == "template.html" for r in ours))
            expect(page.get_by_role("link", name="Ask this model")).to_have_attribute(
                "href", "/ask?model=portfolio_model")
            # ?project= is the same page, at the address that stays ?folder=.
            page.goto(base + "/?project=saas_model")
            page.wait_for_url("**/?folder=saas_model")
            page.get_by_role("heading", level=1, name="SaaS Subscriptions").wait_for()
            # A folder that does not exist (or is hidden) is a page that does not.
            page.goto(base + "/?folder=no_such_folder")
            page.get_by_role("heading", name="Page not found").wait_for()
            fail_on_browser_errors()

            # Data opens on its home, a status board: a card per folder with one
            # health pill, and Needs attention naming the gaps and the CRM that
            # is not reachable here. Its four lists are nested under it in the
            # sidebar, each a plain link to its list.
            sidebar.get_by_role("link", name="Data", exact=True).click()
            page.wait_for_url("**/data")
            page.get_by_role("heading", level=1, name="Data").wait_for()
            data_tabs = sidebar.get_by_role("list", name="Data")
            assert data_tabs.get_by_role("link").all_inner_texts() == [
                "Sources", "Transforms", "Warehouse", "Models"]
            expect(sidebar.get_by_role("link", name="Data", exact=True)).to_have_attribute("aria-current", "page")
            cards = page.locator(".rcard")
            expect(cards).to_have_count(5)
            assert cards.locator(".rcard__k").all_inner_texts() == [
                "Sources", "Transforms", "Warehouse", "Models", "Reports"]
            expect(page.locator('[data-card="Sources"]')).to_contain_text("1 unreachable")
            attention = {
                "source:crm": "Not connected here · set TRACEBI_CRM_URL",
                "transform:holdings_transform_pandas": "No pipeline runs it",
                "table:warehouse.fact_holdings_by_sector": "No model reads it",
                "files:unread": "nar_existing_median_1968_2012.csv",
            }
            for node, why in attention.items():
                expect(page.locator(f'[data-attention="{node}"]')).to_contain_text(why)
            # Setup on the unreachable source opens its sheet where you are.
            page.locator('[data-attention="source:crm"]').get_by_role("button", name="Setup").click()
            setup = page.get_by_role("dialog", name="Setup · CRM (Postgres)")
            expect(setup.get_by_text("Not connected here · set TRACEBI_CRM_URL")).to_be_visible()
            expect(setup.get_by_text("Set by TRACEBI_CRM_URL")).to_be_visible()
            setup.get_by_role("button", name="Close").click()
            fail_on_browser_errors()

            # The map is Lineage, one click away: five lanes in the order the
            # data moves, read through Coverage, with the gaps drawn.
            page.get_by_role("link", name="View lineage").click()
            page.wait_for_url("**/data/lineage")
            page.get_by_role("heading", level=1, name="Lineage").wait_for()
            board = page.locator(".map-board")
            board.locator('[data-node="model:portfolio_model"]').wait_for()
            assert board.locator(".map-lane__stage").all_inner_texts() == [
                "⓪ Sources", "① Transforms", "Warehouse", "② Models", "③ Reports"]
            lenses = page.get_by_role("group", name="Lens")
            expect(lenses.get_by_role("button", name="Coverage")).to_have_attribute("aria-pressed", "true")
            # The warehouse lane holds one group per transform that wrote it.
            assert sorted(board.locator('[data-lane="warehouse"] .mcard[data-node]').evaluate_all(
                "els => els.map(e => e.dataset.node)")) == [
                "group:affordability_transform", "group:holdings_transform", "group:saas_transform",
                "group:wealth_transform"]
            gap = board.locator('[data-node="transform:holdings_transform_pandas"]')
            expect(gap).to_have_class(re.compile(r"\bmcard--gap\b"))
            expect(gap).to_contain_text("no pipeline runs it")
            unread = board.locator('[data-node="files:unread"]')
            expect(unread).to_contain_text("no transform reads it")
            # Hovering a model lights its path: its reports, not another model.
            board.locator('[data-node="model:saas_model"]').hover()
            lit = re.compile(r"\bis-lit\b")
            expect(board.locator('[data-node="report:saas_model/mrr_dashboard"]')).to_have_class(lit)
            expect(board.locator('[data-node="report:portfolio_model/portfolio_book"]')).to_have_class(
                re.compile(r"\bis-dim\b"))
            # What agents see: no CRM table is on the allowlist, so the CRM goes dark.
            lenses.get_by_role("button", name="What agents see").click()
            page.wait_for_url("**/data/lineage?lens=access")
            expect(board.locator('[data-node="source:crm"]')).to_have_class(re.compile(r"\bis-dark\b"))
            # A group's passport: the same rows as every piece, and Zoom to
            # schema lands on the warehouse's schema with that group selected.
            board.locator('[data-node="group:holdings_transform"] .mcard__main').click()
            page.wait_for_url(re.compile(r"node=group%3Aholdings_transform"))
            passport = page.get_by_role("complementary", name="Passport")
            expect(passport.get_by_role("heading", level=2)).to_have_text("written by holdings_transform")
            assert passport.locator("dt").all_inner_texts() == [
                "From", "Written by", "Last moved", "Trust", "Agents"]
            passport.get_by_role("link", name="Zoom to schema").click()
            page.wait_for_url(re.compile(r"/data/warehouse\?view=schema&group="))
            expect(page.get_by_role("complementary", name="Inspector").locator(
                '[data-writer="holdings_transform"]')).to_be_visible()
            fail_on_browser_errors()

            # Sources: connections and input files in one list, the console's:
            # sorted by a header, filtered by a chip, both in the address.
            data_tabs.get_by_role("link", name="Sources").click()
            page.wait_for_url("**/data/sources")
            expect(data_tabs.get_by_role("link", name="Sources")).to_have_attribute("aria-current", "page")
            sources = page.get_by_role("table", name="Sources")
            sources.locator('[data-source="inputs/holdings.csv"]').wait_for()
            # The warehouse is not a source; nor is a file a connection stands for.
            assert sorted(sources.locator("tr[data-source]").evaluate_all(
                "els => els.map(e => e.dataset.source)")) == [
                "bank", "billing", "crm", "inputs/holdings.csv", "inputs/housing_history.csv",
                "inputs/issuer_ratings.csv", "inputs/nar_existing_median_1968_2012.csv",
                "inputs/subscriptions.csv"]
            crm = sources.locator('[data-source="crm"]')
            expect(crm).to_contain_text("CRM (Postgres)")
            expect(crm).to_contain_text("Unreachable")
            expect(crm).to_contain_text("holdings_transform")
            sources.get_by_role("button", name="Status").click()
            page.wait_for_url("**/data/sources?sort=status")
            expect(sources.get_by_role("columnheader", name=re.compile(r"^Status"))).to_have_attribute(
                "aria-sort", "ascending")
            statuses = sources.locator("tbody tr td:nth-child(3)").all_inner_texts()
            assert statuses == sorted(statuses), statuses
            page.get_by_role("group", name="Show").get_by_role("button", name="Unreachable").click()
            page.wait_for_url(re.compile(r"/data/sources\?.*filter=unreachable"))
            expect(sources.locator("tbody tr")).to_have_count(1)
            expect(sources.locator("tbody tr")).to_have_attribute("data-source", "crm")
            # A source's page opens on Overview: the passport's rows among its
            # facts; Tables lists what it holds with a tick for agents; Settings
            # is how it is reached.
            crm.get_by_role("link", name="CRM (Postgres)").click()
            page.wait_for_url("**/data/sources/crm")
            page.goto(base + "/data/sources/bank")
            page.get_by_role("heading", level=1, name="Core banking (SQLite file)").wait_for()
            tabs = page.get_by_role("tablist", name="What to show")
            expect(tabs.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
            details = page.locator(".rdetails")
            for row in ("From", "Read by", "Last moved", "Trust", "Agents"):
                expect(details.locator(f'[data-row="{row}"]')).to_have_count(1)
            expect(details.locator('[data-row="From"]')).to_contain_text("inputs/bank.sqlite")
            tabs.get_by_role("tab", name=re.compile(r"^Tables")).click()
            page.wait_for_url("**/data/sources/bank?tab=tables")
            expect(page.get_by_role("link", name="accounts", exact=True)).to_have_attribute(
                "href", "/data/sources/bank/accounts")
            expect(page.get_by_role("checkbox", name="Agents may read accounts")).to_be_visible()
            expect(page.locator('tr[data-table="accounts"]')).to_contain_text("wealth_dim_account")
            tabs.get_by_role("tab", name="Settings").click()
            page.wait_for_url("**/data/sources/bank?tab=settings")
            expect(page.get_by_role("tabpanel")).to_contain_text("TRACEBI_BANK_URL")
            expect(page.get_by_role("tabpanel")).to_contain_text("connections/bank.yaml")
            # inputs/: a data file opens its table page; scripts are folded.
            page.goto(base + "/data/sources/inputs?tab=tables")
            expect(page.get_by_role("link", name="issuer_ratings.csv")).to_have_attribute(
                "href", "/data/sources/inputs/issuer_ratings.csv")
            expect(page.get_by_text(re.compile(r"^\d+ other files$"))).to_be_visible()
            fail_on_browser_errors()

            # Transforms: every file in transforms/, each with its form and its
            # status; its name opens its own page.
            data_tabs.get_by_role("link", name="Transforms").click()
            page.wait_for_url("**/data/transforms")
            for name, form in [("holdings_transform", "SQL"), ("saas_transform", "SQL"),
                               ("wealth_transform", "SQL"), ("affordability_transform", "Python")]:
                row = page.locator(f'[data-transform="{name}"]')
                expect(row).to_contain_text(form)
                expect(row).to_contain_text("Checks passed")
                expect(row.get_by_role("link", name=name, exact=True)).to_have_attribute(
                    "href", f"/data/transforms/{name}")
            expect(page.locator('[data-transform="holdings_transform_pandas"]')).to_contain_text("No pipeline runs it")
            # Models: one row each; its row menu holds Ask.
            data_tabs.get_by_role("link", name="Models").click()
            page.wait_for_url("**/data/models")
            model_row = page.locator('tr[data-model="portfolio_model"]')
            expect(model_row).to_contain_text("Checks passed")
            model_row.get_by_role("button", name="Actions for Direct Lending Portfolio").click()
            expect(page.get_by_role("menuitem", name="Ask this model")).to_have_attribute(
                "href", "/ask?model=portfolio_model")
            page.keyboard.press("Escape")
            expect(page.get_by_role("menu")).to_have_count(0)

            # Warehouse: every table as a list by default, the data browser one
            # switch away, its tree grouped by the transform that wrote each
            # table; what a run read is said once, on its group.
            data_tabs.get_by_role("link", name="Warehouse").click()
            page.wait_for_url("**/data/warehouse")
            # The browser tab names the page, so tabs and bookmarks differ.
            expect(page).to_have_title("Warehouse · Data · TraceBi")
            with urllib.request.urlopen(base + "/api/warehouse") as resp:
                listing = json.load(resp)["warehouses"][0]
            wh = page.get_by_role("table", name="Warehouse tables")
            expect(wh.locator("tbody tr")).to_have_count(len(listing["tables"]))
            view_row = wh.locator('[data-table="fact_holdings_by_sector"]')
            expect(view_row).to_contain_text("view")
            expect(view_row).to_contain_text("Nobody reads it")
            page.get_by_role("group", name="Show the warehouse as").get_by_role("button", name="Schema").click()
            page.wait_for_url("**/data/warehouse?view=schema")
            tree = page.get_by_role("tree", name="Tables")
            writers = [wr["transform"] for wr in listing["writers"]]
            tree.locator("[data-writer]").first.wait_for()
            assert sorted(tree.locator("[data-writer]").evaluate_all(
                "els => els.map(e => e.dataset.writer)")) == sorted(writers)
            tree.locator('[data-writer="holdings_transform"]').click()
            page.wait_for_url(re.compile(r"group="))
            inspector = page.get_by_role("complementary", name="Inspector")
            group = inspector.locator('[data-writer="holdings_transform"]')
            expect(group).to_contain_text(
                "holdings_transform · wrote 7 tables and 1 view · read crm.issuer_ratings (snapshot inputs/issuer_ratings.csv) on that run")
            expect(page.get_by_text("read crm.issuer_ratings", exact=False)).to_have_count(1)
            # A sink view has its own glyph and says what defines it.
            tree.locator('[data-table="fact_holdings_by_sector"]').click()
            page.wait_for_url(re.compile(r"table=fact_holdings_by_sector"))
            expect(inspector.locator('.dbx-insp__title [aria-label="View"]')).to_be_visible()
            expect(inspector).to_contain_text("defined by holdings_transform over dim_issuer, fact_holdings")
            tree.locator('[data-table="dim_rating"]').click()
            page.wait_for_url(re.compile(r"table=dim_rating"))
            expect(inspector.get_by_role("link", name="Open table")).to_have_attribute(
                "href", "/data/warehouse/dim_rating")
            expect(inspector.get_by_role("link", name="holdings_transform", exact=True)).to_have_attribute(
                "href", "/data/transforms/holdings_transform")
            # A table's page: its Columns tab says each column's profile, the
            # distinct counts the profile route's.
            tree.locator('[data-table="dim_cohort"]').click()
            page.wait_for_url(re.compile(r"table=dim_cohort"))
            inspector.get_by_role("link", name="Open table").click()
            page.wait_for_url("**/data/warehouse/dim_cohort")
            expect(page.get_by_role("navigation", name="Breadcrumb")).to_have_text(re.compile(r"Data\s*›\s*Warehouse\s*›\s*dim_cohort"))
            expect(data_tabs.get_by_role("link", name="Warehouse")).to_have_attribute("aria-current", "page")
            page.get_by_role("tab", name=re.compile(r"^Columns")).click()
            with urllib.request.urlopen(base + "/api/tables/warehouse/dim_cohort/profile") as resp:
                profile = json.load(resp)["columns"]
            for col, p in profile.items():
                expect(page.locator("table.tpage__profile tr").filter(
                    has=page.get_by_text(col, exact=True))).to_contain_text(f"{p['distinct']:,}")
            fail_on_browser_errors()

            # One table's page: the grid sorts and searches in the engine, so
            # what it shows is what the table API answers; the cut is in the
            # address, so Back steps back through it; ⌘K finds the table by name.
            def api(path: str):
                with urllib.request.urlopen(base + "/api" + path) as resp:
                    return json.load(resp)

            page.goto(base + "/data/warehouse/fact_holdings?tab=data")
            grid = page.get_by_role("grid", name="Rows of fact_holdings")
            grid.wait_for()
            expect(page.get_by_role("heading", level=1)).to_have_text("fact_holdings")
            names = [c["name"] for c in api("/tables/warehouse/fact_holdings")["columns"]]
            fair = grid.get_by_role("columnheader", name=re.compile(r"^fair_value"))
            fair.get_by_role("button", name="fair_value DOUBLE").click()
            expect(fair).to_have_attribute("aria-sort", "ascending")
            fair.get_by_role("button", name="fair_value DOUBLE").click()
            expect(fair).to_have_attribute("aria-sort", "descending")
            largest = api("/tables/warehouse/fact_holdings/rows?sort=fair_value&desc=1&limit=1")["rows"][0]
            first_cell = grid.locator("tbody tr").first.locator("td").nth(names.index("fair_value"))
            # The cell's title is the raw value, as JavaScript writes the number.
            expect(first_cell).to_have_attribute("title", repr(largest[names.index("fair_value")]).removesuffix(".0"))
            page.get_by_role("searchbox", name="Search fact_holdings").fill("Revolving")
            page.wait_for_url("**q=Revolving**")
            matched = api("/tables/warehouse/fact_holdings/rows?q=Revolving&limit=1")["total"]
            expect(page.locator(".grid__count")).to_contain_text(f"of {matched} row")
            page.go_back()
            page.wait_for_url(lambda url: "q=" not in url)
            expect(fair).to_have_attribute("aria-sort", "descending")
            page.go_back()
            expect(fair).to_have_attribute("aria-sort", "ascending")
            # Its Columns tab says where a SQL transform's column came from, and
            # View lineage opens the map with the table selected.
            page.goto(base + "/data/warehouse/fact_holdings?tab=columns")
            expect(page.locator("table.tpage__profile tr").filter(
                has=page.get_by_text("par", exact=True))).to_contain_text("inputs/holdings.csv.par")
            page.get_by_role("link", name="View lineage").click()
            page.wait_for_url("**/data/lineage?node=table%3Awarehouse.fact_holdings")
            expect(page.get_by_role("complementary", name="Passport").get_by_role("heading", level=2)).to_have_text(
                "fact_holdings")
            # A connection that is not reachable here says which variable, and
            # links to its page on Sources; the rows its last run read from the
            # committed snapshot stand in on Data, said so.
            page.goto(base + "/data/sources/crm/issuer_ratings")
            expect(page.get_by_text("Not connected here · set TRACEBI_CRM_URL")).to_be_visible()
            expect(page.get_by_role("link", name="Open its connection")).to_have_attribute(
                "href", "/data/sources/crm")
            expect(page.locator('.rdetails [data-row="Read by"]')).to_contain_text(
                "holdings_transform as crm.issuer_ratings")
            page.get_by_role("tab", name="Data").click()
            expect(page.get_by_text("Read from snapshot · inputs/issuer_ratings.csv")).to_be_visible()
            snap = page.get_by_role("grid", name="Rows of issuer_ratings.csv")
            expect(snap.locator("tbody tr")).to_have_count(
                api("/tables/inputs/issuer_ratings.csv")["rows"])
            # (Sources: the board lists warehouse tables by name, the palette's too.)
            page.goto(base + "/data/sources")
            # The shortcut is heard once the app has mounted: wait for the page
            # before pressing it, or on a slow runner the palette never opens.
            page.get_by_role("heading", name="Sources", exact=True).wait_for()
            page.keyboard.press("Control+k")
            # Type into the palette's box once it exists: keystrokes sent before
            # it mounts are lost on a slow runner, and then nothing matches.
            box = page.get_by_placeholder("Jump to a page, model, report, pipeline…")
            box.wait_for()
            box.fill("fact_hold")
            # The warehouse's tables are read once the palette opens.
            page.get_by_text("fact_holdings", exact=True).wait_for()
            page.keyboard.press("Enter")
            page.wait_for_url("**/data/warehouse/fact_holdings")
            # It finds a connection and a transform too, each on its own page.
            page.keyboard.press("Control+k")
            box.wait_for()
            box.fill("holdings_trans")
            page.get_by_role("group", name="Transforms").get_by_text("holdings_transform", exact=True).wait_for()
            # A project is found under Projects.
            box.fill("SaaS Sub")
            page.get_by_role("group", name="Projects").get_by_text("SaaS Subscriptions", exact=True).wait_for()
            page.keyboard.press("Escape")
            fail_on_browser_errors()

            # A model's page: a breadcrumb, its name, its actions top right
            # (one Ask this model), then its tabs; Schema holds the canvas.
            page.goto(base + "/data/models")
            page.locator('tr[data-model="portfolio_model"]').get_by_role(
                "link", name=re.compile(r"^Direct Lending Portfolio")).click()
            page.wait_for_url("**/data/models/portfolio_model")
            expect(page.get_by_role("navigation", name="Breadcrumb")).to_have_text(
                re.compile(r"Data\s*›\s*Models\s*›\s*Direct Lending Portfolio"))
            expect(data_tabs.get_by_role("link", name="Models")).to_have_attribute("aria-current", "page")
            expect(sidebar.get_by_role("link", name="Data", exact=True)).not_to_have_attribute("aria-current", "page")
            expect(page.get_by_role("link", name="Ask this model")).to_have_count(1)
            tabs = page.get_by_role("tablist", name="What to show")
            assert [t.split()[0] for t in tabs.get_by_role("tab").all_inner_texts()][:4] == [
                "Overview", "Schema", "Measures", "Lineage"]
            expect(page.locator('.rdetails [data-row="Defined in"]')).to_contain_text("models/portfolio_model.yaml")
            tabs.get_by_role("tab", name="Schema").click()
            page.wait_for_url("**/data/models/portfolio_model?tab=schema")
            page.get_by_role("tree", name="Tables").wait_for()
            expect(page.locator(".react-flow")).to_be_visible()
            fail_on_browser_errors()

            # Ask is asked from a model: its Data page has the action, and so
            # does its folder's page. Ask keeps its own model pick.
            expect(page.get_by_role("link", name="Ask this model")).to_have_attribute(
                "href", "/ask?model=portfolio_model")
            page.goto(base + "/?folder=portfolio_model")
            page.get_by_role("link", name="Ask this model").click()
            page.wait_for_url("**/ask?model=portfolio_model")
            page.get_by_role("heading", name="Ask", exact=True).wait_for()
            # Asking a model, its folder is where you are.
            expect(folder_row).to_have_attribute("aria-current", "page")
            page.goto(base + "/ask")
            page.get_by_role("heading", name="Ask", exact=True).wait_for()
            # Ask's own pick of the model: the page before may still hold its
            # "Read by" links with the same text for a moment.
            page.locator('a[href="/ask?model=portfolio_model"]', has_text="Direct Lending Portfolio").first.click()
            page.wait_for_url("**/ask?model=portfolio_model")
            assert page.get_by_label("Model").input_value() == "portfolio_model"
            fail_on_browser_errors()

            # Old addresses land on the page that replaced them, query and all.
            for old, new in [
                ("/models/portfolio_model?tab=refresh", "/data/transforms/holdings_transform"),
                ("/m/portfolio_model/refresh", "/data/transforms/holdings_transform"),
                ("/m/portfolio_model/sources", "/data/sources"),
                ("/m/portfolio_model", "/data/models/portfolio_model"),
                ("/m/portfolio_model/model", "/data/models/portfolio_model"),
                ("/m/portfolio_model/transform", "/data/transforms/holdings_transform"),
                ("/m/portfolio_model/reports", "/?model=portfolio_model"),
                ("/m/portfolio_model/reports?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/m/portfolio_model?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/m/portfolio_model/explore", "/ask?model=portfolio_model"),
                ("/m/portfolio_model/runs", "/runs?model=portfolio_model"),
                ("/models/portfolio_model", "/data/models/portfolio_model"),
                ("/models/portfolio_model?tab=explore", "/ask?model=portfolio_model"),
                ("/models/portfolio_model?tab=reports", "/?model=portfolio_model"),
                ("/explore", "/ask"),
                ("/models", "/data/models"),
                ("/models?m=portfolio_model", "/data/models/portfolio_model"),
                ("/map", "/data/lineage"),
                ("/data/map", "/data/lineage"),
                ("/data?view=map", "/data/lineage"),
                # The map was Data's home: its lens, selection and lane are Lineage's.
                ("/data?lens=trust", "/data/lineage?lens=trust"),
                ("/data?node=model%3Asaas_model&lane=models", "/data/lineage?node=model%3Asaas_model&lane=models"),
                ("/data?model=portfolio_model", "/data/lineage?lens=flow&node=model%3Aportfolio_model"),
                ("/data?view=map&model=portfolio_model", "/data/models/portfolio_model"),
                ("/data/map?model=portfolio_model", "/data/models/portfolio_model"),
                # Data's own older addresses: a model and its tabs, a table,
                # a source opened by its query, a folder narrowed to a model.
                ("/data/portfolio_model", "/data/models/portfolio_model"),
                ("/data/portfolio_model/model?table=fact_holdings", "/data/models/portfolio_model?table=fact_holdings"),
                ("/data/portfolio_model/transform", "/data/transforms/holdings_transform"),
                ("/data/portfolio_model/sources", "/data/sources"),
                ("/data/portfolio_model/runs", "/runs?model=portfolio_model"),
                ("/data/tables/warehouse/fact_holdings", "/data/warehouse/fact_holdings"),
                ("/data/tables/crm/issuer_ratings", "/data/sources/crm/issuer_ratings"),
                ("/data/tables/inputs/issuer_ratings.csv", "/data/sources/inputs/issuer_ratings.csv"),
                ("/data/sources?source=crm", "/data/sources/crm"),
                ("/data/sources?model=portfolio_model", "/data/sources"),
                ("/data/warehouse?model=portfolio_model", "/data/warehouse"),
                ("/data/transforms?file=holdings_transform", "/data/transforms/holdings_transform"),
                ("/data/portfolio_model/reports", "/?model=portfolio_model"),
                ("/data/portfolio_model/reports?r=portfolio_model/portfolio_book",
                 "/reports/portfolio_model/portfolio_book"),
                ("/sources", "/data/sources"),
                ("/connectors", "/data/sources"),
                ("/refresh", "/data"),
                ("/pipelines?model=portfolio_model", "/data/transforms/holdings_transform"),
                ("/reports", "/"),
                ("/reports?r=portfolio_model/portfolio_book", "/reports/portfolio_model/portfolio_book"),
                ("/?r=portfolio_model/portfolio_book", "/reports/portfolio_model/portfolio_book"),
                ("/workflow", "/docs/concepts/the-three-phase-workflow"),
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
            # does not, and the breadcrumb's Library link goes back to the library;
            # its folder link opens the folder's page.
            rail = page.get_by_role("navigation", name="Main")
            expect(rail.get_by_role("link", name="Reports")).to_have_attribute("aria-current", "page")
            assert not page.get_by_placeholder("Search reports…").is_visible()
            crumb = page.get_by_role("navigation", name="Where this report is")
            back = crumb.get_by_role("link", name="Library", exact=True)
            back.wait_for()
            expect(crumb.get_by_role("link", name="Direct Lending Portfolio")).to_have_attribute(
                "href", "/?folder=portfolio_model")

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
            # The page says it is rebuilding until the run settles; the first
            # build's toast may still be up, so the note is what is waited on.
            rebuilding = page.get_by_text("Rebuilding: re-running every query")
            rebuilding.wait_for()
            expect(rebuilding).to_be_hidden(timeout=60_000)
            page.get_by_text("Report ran successfully").first.wait_for()
            # The report's own chip says what the app's check found: the file
            # alone says "Not checked", framed here it is told the verdict. The
            # app's header shows it, so the masthead keeps only its Trace link;
            # the frame's trace says the same as the header.
            frame = page.frame_locator("iframe.rp__frame")
            try:
                expect(page.locator(".rp__titlerow")).to_contain_text("Reproduces", timeout=60_000)
            except AssertionError as exc:
                runs = page.evaluate(
                    "async (u) => { const r = await fetch(u); return await r.text() }",
                    f"/api/reports/{_REPORT}/runs",
                )
                msgs = page.evaluate("window.__tbMsgs.slice(-40)")
                frames = [
                    (f.name, f.evaluate(
                        "() => [location.href, location.hash, document.title,"
                        " (document.querySelector(\"select[data-tb-column='dim_issuer.sector']\") || {}).value,"
                        " (document.querySelector('#tracebi-receipt-data, #tracebi-slice-fact_holdings') || {}).id]"))
                    for f in page.frames if f != page.main_frame
                ]
                raise AssertionError(
                    f"{exc}\n--- frames ---\n{frames}\n--- messages ---\n{msgs}"
                    f"\n--- runs ---\n{runs[:1500]}\n--- server log ---\n{_tail(log_path, 40)}"
                ) from exc
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
            # The Data home's Reports card counts it the same way, in the chip's words.
            page.goto(f"{base}/data")
            reports_card = page.locator('[data-card="Reports"]')
            expect(reports_card).to_contain_text("1 needs a look", timeout=60_000)   # the desk re-checks again
            expect(reports_card).not_to_contain_text("reproduce")
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
            expect(page).to_have_title(f"{_TITLE} · TraceBi")

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
            # The workflow built every report, so every row waits on the desk.
            expect(page.get_by_text("Checking…")).to_have_count(0, timeout=60_000)
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
            # One Kind filter, in the words a reader sees: no two kinds a reader
            # cannot tell apart ("Pipeline" and "Pipeline run" were two).
            kinds = page.get_by_label("Kind").locator("option").all_inner_texts()
            assert kinds == ["All kinds", "Report builds", "Data refreshes", "Schedules", "Publishes",
                             "Credential changes"], kinds
            page.get_by_label("Kind").select_option(label="Report builds")
            try:
                expect(page).to_have_url(re.compile(r"/runs\?all=1&kind=build$"), timeout=30_000)
            except AssertionError as exc:
                raise AssertionError(
                    f"{exc}\n--- url --- {page.url}\n--- kind value --- "
                    f"{page.get_by_label('Kind').input_value()}\n--- errors ---\n"
                    + "\n".join(errors) + "\n--- main ---\n" + page.inner_text("main")[:1500]
                ) from exc
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

            # A model's Measures tab, which ?view=measures (an older address)
            # still opens: every measure says what it is in words (rank and
            # running total too), with its description and synonyms, and a
            # reload stays on it.
            page.goto(base + "/data/models/portfolio_model?view=measures")
            measure_rows = page.locator("tr[data-measure]")
            measure_rows.first.wait_for()
            expect(page.get_by_role("tab", name=re.compile(r"^Measures"))).to_have_attribute("aria-selected", "true")
            defs = page.locator("tr[data-measure] td.mlist__def").all_inner_texts()
            assert len(defs) == measure_rows.count() and all(d.strip() for d in defs), defs
            expect(page.locator('tr[data-measure="fv_rank"] td.mlist__def')).to_have_text("rank by fair value, largest first")
            fv_row = page.locator('tr[data-measure="fair_value"]')
            expect(fv_row).to_contain_text("Total fair value")
            expect(fv_row).to_contain_text("market value")
            expect(fv_row).to_contain_text("Which sectors hold the most fair value?")
            page.reload()
            measure_rows.first.wait_for()
            # A measure picked there opens Schema with the fact it runs on selected.
            fv_row.get_by_role("button", name="Total fair value").click()
            page.wait_for_url(re.compile(r"/data/models/portfolio_model\?.*table=fact_holdings"))
            expect(page.get_by_role("complementary", name="Inspector").locator(
                '[data-measure="fair_value"]')).to_have_class(re.compile(r"\bis-on\b"))
            # Tables: ?table= (with the old ?view=tables) selects that table:
            # its shape is read through the table API, its page one link away.
            with urllib.request.urlopen(base + "/api/tables/warehouse/fact_holdings") as resp:
                holdings = json.load(resp)
            page.goto(base + "/data/models/portfolio_model?view=tables&table=fact_holdings")
            inspector = page.get_by_role("complementary", name="Inspector")
            expect(inspector).to_contain_text(f"{holdings['rows']} rows × {len(holdings['columns'])} columns")
            expect(inspector.get_by_role("link", name="Open table")).to_have_attribute(
                "href", "/data/warehouse/fact_holdings")
            tree = page.get_by_role("tree", name="Tables")
            tree.locator('[data-table="dim_fund"]').click()
            page.wait_for_url("**/data/models/portfolio_model?view=tables&table=dim_fund")
            expect(inspector.locator('[data-inspecting="dim_fund"]')).to_be_visible()
            page.go_back()
            page.wait_for_url("**/data/models/portfolio_model?view=tables&table=fact_holdings")
            fail_on_browser_errors()
            # Selecting a table in the tree: the inspector is a short card, its
            # joins as sentences (no columns, no sample: those are on its
            # page); the address keeps it.
            page.goto(base + "/data/models/portfolio_model?tab=schema")
            tree.locator('[data-table="fact_holdings"]').click()
            page.wait_for_url("**/data/models/portfolio_model?tab=schema&table=fact_holdings")
            inspector = page.get_by_role("complementary", name="Inspector")
            expect(inspector.locator('[data-section="columns"]')).to_have_count(0)
            expect(inspector.get_by_role("grid")).to_have_count(0)
            join = inspector.get_by_role("button", name="fact_holdings.fund_id → dim_fund.fund_id · many to one")
            expect(join).to_be_visible()
            # A measure is reachable from its fact.
            expect(inspector.locator('[data-measure="fair_value"]')).to_be_visible()
            join.click()
            page.wait_for_url("**/data/models/portfolio_model?tab=schema&table=dim_fund")
            fail_on_browser_errors()

            # What an agent sees is the model the context route returns: the
            # model page's Agents tab.
            page.goto(base + "/data/models/portfolio_model?tab=agents")
            expect(page.locator("pre.sem-agent")).to_contain_text('"questions"')
            # Each page can show the code behind what it shows: a model's in its
            # Settings tab, a transform's in its Code tab (View code, top right).
            page.goto(base + "/data/models/portfolio_model?tab=settings")
            page.get_by_text("models/portfolio_model.yaml").first.wait_for()
            page.goto(base + "/data/transforms/holdings_transform")
            page.get_by_role("button", name="View code", exact=True).click()
            page.wait_for_url("**/data/transforms/holdings_transform?tab=code")
            page.get_by_text("transforms/holdings_transform.sql").first.wait_for()
            page.goto(base + "/data/transforms/holdings_transform")
            # The transform's page says what it wrote, and that its checks
            # passed when it was last written, before any report is opened.
            table = page.locator('[data-writer="holdings_transform"] [data-table="fact_holdings"]')
            table.wait_for()
            assert re.search(r"\b25\b", table.inner_text())
            assert table.get_by_text("Checks passed", exact=True).count() == 1
            page.locator('[data-writer="holdings_transform"]').get_by_text("The sink satisfied its contract").wait_for()
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
            expect(page.locator(".ask-bars .answer-chart__value").first).to_have_text(first)
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

            # Transform: Refresh data, its one primary action (top right), unfolds
            # the run's output on its Steps tab and follows it to its end…
            # A read of the warehouse does not hold Refresh data back (a write
            # waits for a read to let go): with the page's read still pending,
            # the button is enabled.
            held, released = [], []

            def hold(route):
                if released:
                    route.continue_()
                else:
                    held.append(route)

            page.route("**/api/connectors/warehouse/warehouse", hold)
            page.goto(base + "/data/transforms/holdings_transform?tab=steps")
            for _ in range(100):
                if held:
                    break
                page.wait_for_timeout(100)
            assert held, "the transform's page never read the warehouse"
            expect(page.get_by_role("button", name="Refresh data")).to_be_enabled()
            released.append(True)
            for route in held:
                route.continue_()
            page.unroute("**/api/connectors/warehouse/warehouse")
            page.wait_for_load_state("networkidle")
            assert page.get_by_role("button", name="Refresh data").count() == 1
            page.get_by_role("button", name="Refresh data").click()
            output = page.get_by_role("log", name="Run output")
            output.get_by_text("Run succeeded").wait_for()
            text = output.inner_text()
            assert "[transform] ✓" in text and "[build] ✓" in text, text
            assert len(page.request.get(base + "/api/pipelines/portfolio_model/runs").json()) == 1
            # …its page now says when it was refreshed…
            page.get_by_text(re.compile(r"^Refreshed ")).first.wait_for()
            # …and the run links the reports it rebuilt, each to its page in the app.
            page.get_by_role("link", name="portfolio_book", exact=True).click()
            page.wait_for_url("**/reports/portfolio_model/portfolio_book")
            fail_on_browser_errors()

            # Depends on this (read-only): a warehouse table selected on the
            # map lists the figures downstream of it by report, each with the
            # number its built page prints, the one /api/desk reads off it.
            page.goto(base + "/data/lineage?node=table:warehouse.fact_holdings")
            deps = page.get_by_role("complementary", name="Passport").locator(".deps")
            expect(deps.locator(".deps__sum")).to_have_text(re.compile(r"^\d+ figures in \d+ reports$"))
            dash = deps.locator('[data-report="portfolio_model/portfolio_dashboard"]')
            dash.locator("summary").click()
            values = [v for b in page.request.get(base + "/api/desk").json()["builds"]
                      if b["report"] == "portfolio_model/portfolio_dashboard"
                      for v in b["values"]]
            shown = [v for v in values if dash.locator(f'[data-figure="{v["id"]}"]').count()]
            assert shown, values
            for v in shown:
                expect(dash.locator(f'[data-figure="{v["id"]}"]')).to_contain_text(f'{v["label"]} · {v["text"]} · ')
            fail_on_browser_errors()

            # A refresh moves on the map, observed only: started from the
            # transform's Overview (the button is top right on every tab; the
            # run unfolds on Steps), its Lineage tab shows the run on the
            # transform node, and once the run ends nothing moves.
            page.goto(base + "/data/transforms/holdings_transform")
            page.wait_for_load_state("networkidle")
            page.get_by_role("button", name="Refresh data").click()
            page.get_by_role("tab", name="Lineage").click()
            page.locator('[data-node="transform:holdings_transform"][data-run]').wait_for()
            page.wait_for_function("() => !document.querySelector('[data-run]')")
            fail_on_browser_errors()

            # That refresh is a run of its model: the model page's old Runs
            # tab is History narrowed to it, where All models names the model
            # beside it.
            page.goto(base + "/data/portfolio_model/runs")
            page.wait_for_url("**/runs?model=portfolio_model")
            page.get_by_role("heading", name="History", exact=True).wait_for()
            page.locator("tr", has_text="Data refresh").first.wait_for()
            page.goto(base + "/runs")
            pipeline_row = page.locator("tr", has_text="Data refresh").first
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
            # everywhere, a folder says nothing about permissions in the list;
            # its own page says what the person may do there.
            page.goto(base + "/")
            page.get_by_role("group", name="View").get_by_role("button", name="List").click()
            page.get_by_role("region", name="Direct Lending Portfolio").get_by_role(
                "button", name=re.compile(r"Direct Lending Portfolio\s*\d+$")).wait_for()
            expect(page.get_by_role("button", name="Permissions")).to_have_count(0)
            page.goto(base + "/?folder=portfolio_model")
            page.get_by_role("region", name="Permissions").get_by_text(
                "No folder file applies, so roles decide.").wait_for()
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
            # In the directory My published is a row that says how it fills,
            # the sidebar's last folder, and a page of its own with the same note.
            page.get_by_role("group", name="View").get_by_role("button", name="Grid").click()
            page.get_by_role("region", name="My published").get_by_text("Nothing here yet.").wait_for()
            mine = page.get_by_role("navigation", name="Main").locator("a.tree__folder")
            expect(mine.last).to_contain_text("My published")
            mine.last.click()
            page.get_by_role("heading", level=1, name="My published").wait_for()
            page.get_by_text("Only you see this folder unless you share it by file.").wait_for()
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

            # An agent proposes a change to a SQL transform (the person let
            # agents read the billing database): each proposal was dry-run
            # against a throwaway copy, and Review shows the diff with the
            # dry run, its tables as grids. One whose checks fail leads with
            # the failure and cannot be approved.
            billing = project / "connections" / "billing.yaml"
            billing.write_text(billing.read_text(encoding="utf-8") + 'agents:\n  tables: "*"\n',
                               encoding="utf-8")
            proposed = subprocess.run([sys.executable, "-c", (
                "import json\n"
                "from tracebi import mcp_server as gw\n"
                "t = gw.gateway_read_transform('saas_transform')\n"
                "sql = t['text'].replace('AS plan_id, plan\\n', "
                "'AS plan_id, plan, upper(plan) AS plan_code\\n')\n"
                "good = gw.gateway_propose_transform('saas_transform', sql, t['contract_yaml'], "
                "'Each plan carries its code', change=True)\n"
                "bad = gw.gateway_propose_transform('saas_transform', sql, t['contract_yaml'] + "
                "'  - rows: fact_account_month\\n    exactly: 1\\n', 'Plan codes, one row', change=True)\n"
                "print(json.dumps([good['dry_run']['ok'], bad['dry_run']['ok']]))\n")],
                cwd=project, env=env, capture_output=True, text=True, check=False)
            assert proposed.returncode == 0, proposed.stderr
            assert json.loads(proposed.stdout.strip().splitlines()[-1]) == [True, False]
            page.set_viewport_size({"width": 1440, "height": 1000})
            page.goto(base + "/review")
            attention = page.get_by_role("list", name="Needs attention")
            good = attention.locator("li", has_text="Each plan carries its code")
            good.get_by_role("button", name="Review").click()
            dry = good.get_by_role("region", name="Dry run")
            expect(dry.get_by_text("Dry run: 4 tables, checks", exact=False)).to_be_visible()
            expect(dry.locator("th", has_text="plan_code")).to_be_visible()
            expect(good.get_by_text("+SELECT row_number() OVER (ORDER BY plan) - 1 AS plan_id, plan, upper(plan) AS plan_code")).to_be_visible()
            expect(good.get_by_role("button", name="Approve and run")).to_be_enabled()
            good.screenshot(path=str(tmp_path / "review-dry-run-passed.png"))
            good.get_by_role("button", name="Close").click()
            bad = attention.locator("li", has_text="Plan codes, one row")
            bad.get_by_role("button", name="Review").click()
            failed = bad.get_by_role("region", name="Dry run")
            expect(failed.get_by_text("Dry run failed", exact=True).first).to_be_visible()
            expect(failed.locator("li.is-failed", has_text="fact_account_month")).to_be_visible()
            expect(bad.get_by_role("button", name="Approve and run")).to_be_disabled()
            bad.screenshot(path=str(tmp_path / "review-dry-run-failed.png"))
            bad.get_by_role("button", name="Close").click()
            page.set_viewport_size({"width": 1280, "height": 720})
            fail_on_browser_errors()

            # Review lists the reports nobody has built yet as one item, and
            # Build all builds them: the item goes once every build has landed.
            page.goto(base + "/review")
            unbuilt = page.get_by_role("list", name="Needs attention").locator("li", has_text="never been built")
            unbuilt.get_by_role("button", name="Build all").click()
            expect(unbuilt).to_have_count(0, timeout=180_000)
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
    """Behind a proxy that names roles, a viewer's sidebar is Reports, Ask and
    Docs, an analyst's adds Review (its tabs Attention, Drafts, History,
    Verify) and Data, read-only (no Refresh data, which an admin has), and an
    address above the role is a plain page saying who it is for and what this
    person can do. A viewer meets nothing they cannot act on: no My published,
    and a report nobody has built says who builds it, with no Share. The API
    enforces the roles; this is what the app shows."""
    from playwright.sync_api import expect, sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(
        _PROJECT,
        project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "data", ".tracebi"),
    )
    for built in (project / "output").rglob("*.html"):   # nothing built here yet
        built.unlink()
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
            viewer.get_by_role("heading", name="This part of the app is for analysts.").wait_for()
            viewer.get_by_text("You can read reports, ask a model questions and read the docs.").wait_for()
            expect(viewer.get_by_role("link", name="Go to the reports")).to_have_attribute("href", "/")
            sidebar = viewer.get_by_role("navigation", name="Main")
            sidebar.get_by_role("link", name=re.compile(r"^All reports \d+$")).wait_for()
            expect(sidebar.get_by_role("link", name="Ask", exact=True)).to_have_count(0)
            for place in ("Data", "Review"):
                expect(sidebar.get_by_role("link", name=place, exact=True)).to_have_count(0)
            # Docs is for everyone: the handbook, Get started in its first section.
            sidebar.get_by_role("link", name="Docs", exact=True).click()
            viewer.wait_for_url("**/docs")
            viewer.get_by_role("heading", name="Docs", exact=True).wait_for()
            # The sidebar's link: the home page links it too, in its Start here list.
            viewer.get_by_role("navigation", name="Docs pages").get_by_role(
                "link", name="Get started", exact=True).click()
            viewer.wait_for_url("**/docs/get-started")
            viewer.get_by_role("heading", name="Get started", exact=True).wait_for()
            # A Docs page's one h1 is its own title; "Docs" is the crumb.
            expect(viewer.locator("h1")).to_have_count(1)
            expect(viewer.locator("h1")).to_have_text("Get started")
            for tab in ("/data/sources", "/data/transforms", "/data/warehouse", "/data/models"):
                viewer.goto(base + tab)
                viewer.get_by_role("heading", name="This part of the app is for analysts.").wait_for()
            # ⌘K lists the same places: nothing inside Review or Data.
            viewer.keyboard.press("Control+k")
            viewer.get_by_placeholder("Jump to a page, model, report, pipeline…").fill("History")
            viewer.get_by_text("No matches for").wait_for()
            # Nor the design notes (design/, outside the handbook).
            viewer.get_by_placeholder("Jump to a page, model, report, pipeline…").fill("Navigation v3")
            viewer.get_by_text("No matches for").wait_for()
            viewer.keyboard.press("Escape")
            viewer.goto(base + "/review")
            viewer.get_by_role("heading", name="This part of the app is for analysts.").wait_for()
            # An open report keeps the same places in its rail. Nobody has
            # built it: the viewer is told who builds it, and offered no Share
            # (a link to nothing) and no About this build (a panel of dashes).
            viewer.goto(f"{base}/reports/{_REPORT}")
            rail = viewer.get_by_role("navigation", name="Main")
            expect(rail.get_by_role("link", name="Reports")).to_have_attribute("aria-current", "page")
            expect(rail.get_by_role("link", name="Ask")).to_have_count(0)
            expect(rail.get_by_role("link", name="Review")).to_have_count(0)
            viewer.get_by_text("Not built yet. An analyst or admin builds it.").wait_for()
            for command in ("Share", "About this build", "Build it now"):
                expect(viewer.get_by_role("button", name=command)).to_have_count(0)
            # The library has no My published for a role that cannot publish
            # into it; an analyst's has one.
            viewer.goto(base + "/")
            viewer.locator(f'[data-report="{_REPORT}"]').wait_for()
            expect(viewer.get_by_role("region", name="My published")).to_have_count(0)

            analyst = as_role("analyst")
            analyst.goto(base + "/runs")
            sidebar = analyst.get_by_role("navigation", name="Main")
            expect(sidebar.get_by_role("link", name="Review", exact=True)).to_have_attribute("aria-current", "page")
            tabs = analyst.get_by_role("navigation", name="Review: what to show")
            assert tabs.get_by_role("link").all_inner_texts() == ["Attention", "Drafts", "History", "Verify"]
            expect(tabs.get_by_role("link", name="History")).to_have_attribute("aria-current", "page")
            analyst.goto(base + "/")
            analyst.get_by_role("region", name="My published").wait_for()
            # Data is the analyst's to read: a transform's page, with no
            # Refresh data (it writes the warehouse); the admin's has one.
            expect(sidebar.get_by_role("link", name="Data", exact=True)).to_have_count(1)
            analyst.goto(base + "/data/transforms/holdings_transform?tab=steps")
            analyst.get_by_role("group", name="What to show of the pipeline").wait_for()
            expect(analyst.get_by_role("button", name="Refresh data")).to_have_count(0)
            admin = as_role("admin")
            admin.goto(base + "/data/transforms/holdings_transform")
            admin.get_by_role("button", name="Refresh data").wait_for()
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
