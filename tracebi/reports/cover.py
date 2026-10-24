"""A cover for a built report: a picture of its first screen.

The library shows each report by its cover. It is taken at build, beside the
HTML (``output/<name>.cover.png``), through the same headless Chromium that
prints a PDF (``tracebi/reports/pdf.py``), local files only.

A cover is a picture of query results, never one: it is not part of the
trace, is never fingerprinted, and ``verify`` never reads it. It is also not
something a build needs, so a missing Playwright or Chromium writes no cover
and says why (the ``pdf`` extra brings both); the build is as it was and the
app draws a generated cover instead.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from tracebi.reports.pdf import _DRAWN, _launch_args, _local_only

#: The size of a cover: the first screen of a wide window.
WIDTH, HEIGHT = 1200, 750

# Once Chromium has failed to start in this process, every later build would
# fail the same way, one slow launch each: say it once and stop trying.
_unavailable: Optional[str] = None


def cover_path(html_path: str) -> str:
    """Where the cover of the build at *html_path* lives: beside it."""
    return os.path.splitext(html_path)[0] + ".cover.png"


def capture_cover(html_path: str) -> tuple[Optional[str], Optional[str]]:
    """Capture the built page at *html_path*: ``(cover path, None)``, or
    ``(None, why it was skipped)``. Never raises.

    The first screen at 1200×750, light, reduced motion (so a chart is drawn
    where it ends, not mid-animation), once hydration has drawn every chart.
    An older cover beside the page is removed first, so a build that cannot
    take one never leaves the last build's picture standing in for it.
    """
    global _unavailable
    dest = cover_path(html_path)
    _remove(dest)
    if os.environ.get("TRACEBI_COVERS") == "0":
        return None, "covers are off (TRACEBI_COVERS=0)"
    if _unavailable:
        return None, _unavailable
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _unavailable = "Playwright is not installed (pip install 'tracebi[pdf]')"
        return None, _unavailable
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=True, args=_launch_args())
            except Exception:  # noqa: BLE001 — the reason is the install line
                _unavailable = ("Chromium is not installed "
                                "(python -m playwright install chromium)")
                return None, _unavailable
            try:
                page = browser.new_page(
                    viewport={"width": WIDTH, "height": HEIGHT},
                    color_scheme="light", reduced_motion="reduce")
                page.route("**/*", _local_only)
                page.goto(Path(html_path).resolve().as_uri(), wait_until="load")
                page.wait_for_function(_DRAWN, timeout=30_000)
                page.screenshot(path=dest)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 — a cover is never worth a failed build
        _remove(dest)
        return None, f"the page could not be captured ({type(exc).__name__})"
    return dest, None


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
