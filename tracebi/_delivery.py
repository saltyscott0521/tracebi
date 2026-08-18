"""
Scheduled delivery — distribution with the receipt attached (roadmap #11, v1).

A report that leaves the project must carry its receipt: :func:`send_report`
emails the built ``.html`` **and** its ``.manifest.json`` side by side, with
a plain-text body stating what was rendered, when, from which code, and —
when a verify result is supplied — the receipt-level verdict. The CLI's
``tracebi report send`` refuses to call this at all while the receipt does
not verify (``--force`` overrides, pasting the failing verdict prominently
into the body): distribution never outruns verification, and a red flag
travels WITH the report, never silently.

Stdlib only — ``smtplib``/``email`` for mail, ``urllib`` for the Slack
webhook. Configuration is explicit environment variables (the framework
never reads connector URLs implicitly; a delivery endpoint is the same kind
of secret):

    TRACEBI_SMTP_URL       smtp://user:pass@host:port (STARTTLS when the
                           server offers it) or smtps://… (implicit TLS)
    TRACEBI_SMTP_FROM      the From: address
    TRACEBI_SLACK_WEBHOOK  optional — the CLI pings it after a send
"""

from __future__ import annotations

import json
import os
import smtplib
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Sequence, Union
from urllib.parse import unquote, urlsplit


def _contracts_line(contracts: Optional[dict]) -> str:
    """The transform-contracts one-liner for the body — the phase-① join as
    recorded at build, never a claim this module checked anything."""
    if not contracts:
        return "Sink contracts: none recorded"
    counts: dict[str, int] = {}
    for rec in contracts.values():
        status = rec.get("status", "?") if isinstance(rec, dict) else "?"
        counts[status] = counts.get(status, 0) + 1
    joined = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    return f"Sink contracts: {joined}"


def _body(name: str, manifest: dict, verify_result: Optional[dict],
          manifest_name: str) -> str:
    lines: list[str] = []
    if verify_result is not None and verify_result.get("exit_code", 0) != 0:
        # The red flag travels with the report — first thing the reader sees.
        lines += [
            "*** RED FLAG: THIS RECEIPT DID NOT VERIFY ***",
            verify_result.get("verdict_detail", ""),
            "",
        ]
    lines += [
        f"Report: {name}",
        f"Rendered at: {manifest.get('rendered_at', 'unknown')}",
        f"Code (git SHA): {manifest.get('git_sha', 'unknown')}",
    ]
    if verify_result is not None:
        lines.append(f"Verify: {verify_result.get('verdict_detail', '')}")
    lines.append(_contracts_line(manifest.get("transform_contracts")))
    lines += [
        "",
        "The attached HTML is self-contained; its .manifest.json receipt is "
        "attached beside it.",
        f"Re-check it any time with: tracebi verify {manifest_name}",
    ]
    return "\n".join(lines) + "\n"


def send_report(html_path: Union[str, Path], manifest_path: Union[str, Path],
                to: Union[str, Sequence[str]], subject: Optional[str] = None,
                verify_result: Optional[dict] = None) -> list[str]:
    """
    Email the built report ``.html`` with its manifest receipt attached.

    *to* is a list of addresses or one comma-separated string. The body is
    plain text: report name, ``rendered_at``, ``git_sha``, the verify
    verdict line when *verify_result* (a :func:`tracebi.verify.verify_manifest`
    result dict) is passed, and the sink-contracts one-liner. When the
    passed result did not verify, its verdict is pasted prominently at the
    top — the caller decided the red flag travels with the report.

    Reads ``TRACEBI_SMTP_URL`` and ``TRACEBI_SMTP_FROM``; raises a
    ``RuntimeError`` naming exactly the missing variables when unset
    (invariant 4: fail loudly, name the fix). Returns the recipient list.
    """
    html_path = Path(html_path)
    manifest_path = Path(manifest_path)
    if isinstance(to, str):
        to = [a.strip() for a in to.split(",") if a.strip()]
    to = list(to)
    if not to:
        raise ValueError("send_report: no recipients given")

    url = os.environ.get("TRACEBI_SMTP_URL")
    sender = os.environ.get("TRACEBI_SMTP_FROM")
    missing = [name for name, value in
               (("TRACEBI_SMTP_URL", url), ("TRACEBI_SMTP_FROM", sender))
               if not value]
    if missing:
        raise RuntimeError(
            "report delivery is not configured: set " + " and ".join(missing)
            + ". TRACEBI_SMTP_URL is smtp://user:pass@host:port (or "
              "smtps:// for implicit TLS); TRACEBI_SMTP_FROM is the "
              "From: address."
        )

    parsed = urlsplit(url)
    if parsed.scheme not in ("smtp", "smtps"):
        raise RuntimeError(
            f"TRACEBI_SMTP_URL must start with smtp:// or smtps://, "
            f"got {parsed.scheme or url!r}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            manifest = {}
    except (OSError, json.JSONDecodeError):
        manifest = {}
    name = manifest.get("report_name") or html_path.stem

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject or f"[tracebi] {name}"
    msg.set_content(_body(name, manifest, verify_result, manifest_path.name))
    # BOTH artifacts, side by side: the page and the receipt that stands
    # behind it. The manifest bytes go verbatim — it is the receipt.
    msg.add_attachment(html_path.read_bytes(), maintype="text",
                       subtype="html", filename=html_path.name)
    msg.add_attachment(manifest_path.read_bytes(), maintype="application",
                       subtype="json", filename=manifest_path.name)

    host = parsed.hostname or "localhost"
    port = parsed.port or (465 if parsed.scheme == "smtps" else 25)
    cls = smtplib.SMTP_SSL if parsed.scheme == "smtps" else smtplib.SMTP
    server = cls(host, port, timeout=30)
    try:
        if parsed.scheme == "smtp":
            try:
                server.starttls()
            except smtplib.SMTPNotSupportedError:
                pass  # a plain local relay; credentials below are its call
        if parsed.username:
            server.login(unquote(parsed.username),
                         unquote(parsed.password or ""))
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 — the send already happened or raised
            pass
    return to


def slack_notify(webhook_url: str, text: str) -> int:
    """POST *text* as JSON to a Slack incoming webhook; returns the HTTP
    status. Network errors propagate — the caller decides whether a failed
    ping matters (the CLI reports it but keeps the send's exit code)."""
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — operator-set URL
        return resp.status
