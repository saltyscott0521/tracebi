"""
Live-preview server for ``tracebi dev <request>``.

Watches a request file, re-runs it on every save, and serves the rendered
HTML report on a local port. The served page polls ``/__status`` and reloads
itself when the file changes, so an analyst can keep the browser next to
their editor and see the report update on save. Script errors render as a
styled traceback page that also auto-reloads once the script is fixed.
"""

from __future__ import annotations

import http.server
import json
import os
import threading
import traceback
import webbrowser
from pathlib import Path

_REFRESH_SNIPPET = """
<script>
(function () {
  var current = __VERSION__;
  setInterval(function () {
    fetch("/__status")
      .then(function (r) { return r.json(); })
      .then(function (s) { if (s.version !== current) location.reload(); })
      .catch(function () {});
  }, 1000);
})();
</script>
"""

_ERROR_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>tracebi dev — error</title>
<style>
body {{ font-family: 'Segoe UI', Calibri, Arial, sans-serif; background: #f5f7fa;
       padding: 40px; color: #1a1a2e; }}
.box {{ max-width: 900px; margin: 0 auto; background: #fff; border-radius: 6px;
        box-shadow: 0 2px 16px rgba(0,0,0,0.08); overflow: hidden; }}
.head {{ background: #C62828; color: #fff; padding: 18px 24px; }}
.head h1 {{ font-size: 16px; margin: 0; }}
.head p {{ font-size: 12px; margin: 6px 0 0 0; opacity: 0.9; }}
pre {{ margin: 0; padding: 20px 24px; font-size: 12px; line-height: 1.5;
      overflow-x: auto; white-space: pre-wrap; }}
</style></head>
<body><div class="box">
<div class="head"><h1>{title}</h1>
<p>{file} — fix the script and save; this page reloads automatically.</p></div>
<pre>{trace}</pre>
</div></body></html>"""


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def render_request(path: Path) -> str:
    """Run the request and return report HTML, or a styled error page."""
    try:
        from tracebi._request_runner import execute_request
        from tracebi.reports.html_renderer import HTMLRenderer
        report = execute_request(path)
        return HTMLRenderer().to_html(report)
    except (Exception, SystemExit):
        return _ERROR_PAGE.format(
            title="Request script failed",
            file=_esc(path.name),
            trace=_esc(traceback.format_exc()),
        )


def _inject_refresh(html: str, version: int) -> str:
    snippet = _REFRESH_SNIPPET.replace("__VERSION__", str(version))
    if "</body>" in html:
        return html.replace("</body>", snippet + "</body>", 1)
    return html + snippet


def serve_dev(
    path: Path,
    port: int = 8001,
    open_browser: bool = True,
    poll_interval: float = 0.5,
) -> int:
    """Serve *path* with live reload until Ctrl+C. Returns an exit code."""
    path = Path(path)
    state = {"html": render_request(path), "version": 0}
    lock = threading.Lock()

    def watch():
        last_mtime = os.path.getmtime(path)
        stop = threading.Event()
        while not stop.wait(poll_interval):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue   # file briefly missing during atomic save
            if mtime != last_mtime:
                last_mtime = mtime
                html = render_request(path)
                with lock:
                    state["html"] = html
                    state["version"] += 1
                print(f"  Reloaded {path.name} (v{state['version']})")

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/__status":
                with lock:
                    body = json.dumps({"version": state["version"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            with lock:
                body = _inject_refresh(state["html"], state["version"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # silence request logs
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    url = f"http://127.0.0.1:{port}"
    print(f"\n  TraceBi dev — watching {path}")
    print(f"  Preview at {url} (reloads on save)")
    print("  Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dev server stopped.")
    finally:
        server.server_close()
    return 0
