"""Step 1 — PULL: land raw AltsVault exports as CSV, untouched.

Nothing is cleaned or reshaped here; whatever the API says is what hits the
disk, so the transform can be re-run without spending another API call.

Two facts about the API shape this:

* **CSV, not JSON.** Some exports fail in the API's JSON serializer; CSV works
  for all of them, so it is the only mode used.
* **No server-side filtering.** Only ``limit`` (max 5000), ``offset`` and
  ``format``. Every pull is a full-table download, paged until a short page.

The public demo has no login, so anyone can press Run. A pull younger than
``MIN_INTERVAL`` is reused instead of hitting the API again.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from tracebi.web.demo_app.altsvault import RAW_DIR

BASE = "https://alts-vault.com/api/v1"
PAGE = 5000                      # the API's maximum
MIN_INTERVAL = timedelta(hours=1)
UA = "tracebi-demo-altsvault/0.1"
MANIFEST = "_pull_manifest.json"

#: Only what the credit-marks transform reads.
EXPORTS = [
    "position_marks",
    "fund_marks",
    "quality_fund_completeness",
    "fund_crowding",
    "issuer_fund_exposure",
]


def _key() -> str:
    key = os.environ.get("ALTSVAULT_API_KEY")
    if not key:
        raise RuntimeError(
            "ALTSVAULT_API_KEY is not set on this server, so the AltsVault "
            "exports can't be pulled.")
    return key


def _get(url: str, key: str, attempts: int = 4) -> str:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}", "User-Agent": UA})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):   # retrying an auth failure is noise
                raise RuntimeError(
                    f"AltsVault refused the API key ({exc.code}).") from None
            if attempt == attempts:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == attempts:
                raise
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def _fetch(export: str, key: str) -> tuple[str, int]:
    """Page one export to exhaustion → (csv_text, data_rows). Each page
    repeats the header; only the first is kept."""
    header, body, offset = None, [], 0
    while True:
        text = _get(f"{BASE}/datasets/{export}?limit={PAGE}&offset={offset}&format=csv", key)
        rows = list(io.StringIO(text))
        if not rows:
            break
        if header is None:
            header = rows[0]
        elif rows[0] != header:
            raise RuntimeError(f"{export}: header changed mid-pull at offset {offset}")
        body.extend(rows[1:])
        if len(rows) - 1 < PAGE:
            break
        offset += PAGE
    if header is None:
        return "", 0
    if body and not body[-1].endswith("\n"):
        body[-1] += "\n"
    return header + "".join(body), len(body)


def read_manifest() -> dict:
    try:
        with open(os.path.join(RAW_DIR, MANIFEST), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def pull(force: bool = False) -> dict:
    """Pull every export in EXPORTS; returns the pull manifest.

    Reuses the last pull when it is younger than MIN_INTERVAL and complete,
    unless *force*. The manifest records rows, bytes and a sha256 per export.
    """
    last = read_manifest()
    if not force and last.get("pulled_at") and set(EXPORTS) <= set(last.get("exports", {})):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last["pulled_at"])
        if age < MIN_INTERVAL:
            return {**last, "reused": True}

    key = _key()
    os.makedirs(RAW_DIR, exist_ok=True)
    pulled_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {"source": BASE, "pulled_at": pulled_at, "exports": {}}
    for export in EXPORTS:
        csv_text, rows = _fetch(export, key)
        tmp = os.path.join(RAW_DIR, f".{export}.csv.tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            fh.write(csv_text)
        os.replace(tmp, os.path.join(RAW_DIR, f"{export}.csv"))
        manifest["exports"][export] = {
            "rows": rows,
            "bytes": len(csv_text.encode()),
            "sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        }
    with open(os.path.join(RAW_DIR, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return {**manifest, "reused": False}
