"""Browser smoke of the served app.

Skipped unless ``TRACEBI_E2E=1``. A normal ``pytest tests/`` does not need
Chromium or the ``e2e`` extra. The CI job ``ui-smoke`` sets the variable.
"""

from __future__ import annotations

import os
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
_REPORT = "portfolio_showcase"
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
    from playwright.sync_api import sync_playwright

    project = tmp_path / "portfolio_project"
    shutil.copytree(
        _PROJECT,
        project,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
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
                assert not errors, "\n".join(errors)

            page.goto(base + "/")
            page.get_by_role("heading", name="Desk").wait_for()
            fail_on_browser_errors()

            page.goto(base + "/reports")
            fail_on_browser_errors()
            page.get_by_text(_REPORT, exact=True).click()
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

            page.get_by_role("button", name="Source").click()
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
