"""
Optional HTTP Basic auth middleware for the TraceBi web layer.

Enabled when the ``TRACEBI_AUTH_USER`` and ``TRACEBI_AUTH_PASS`` environment
variables are both set. Off by default — the API stays open so local
development and the demo deployment work without any configuration.

This is intentionally minimal: a single shared user/password, suitable for
small-team deployments behind a reverse proxy or VPN. For multi-user
identity, sit the app behind Authelia / Cloudflare Access / oauth2-proxy.

Routes prefixed with ``/api/health`` and the static UI assets are exempt
so health checks and the login prompt work cleanly.
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_PROTECTED_PREFIXES = ("/api/", "/dashboards/")
_EXEMPT_PATHS = ("/api/health",)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Single-credential HTTP Basic auth guarding the API and dashboards."""

    def __init__(self, app, username: str, password: str, realm: str = "TraceBi") -> None:
        super().__init__(app)
        self._username = username
        self._password = password
        self._realm = realm

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Static UI assets are public; the SPA prompts in-page if API calls fail.
        if not path.startswith(_PROTECTED_PREFIXES):
            return await call_next(request)
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        if not self._check(request.headers.get("authorization")):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{self._realm}"'},
            )
        return await call_next(request)

    def _check(self, header: Optional[str]) -> bool:
        if not header or not header.lower().startswith("basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        except Exception:
            return False
        user, _, password = decoded.partition(":")
        return (
            secrets.compare_digest(user, self._username)
            and secrets.compare_digest(password, self._password)
        )


def install_if_configured(app) -> bool:
    """Install BasicAuthMiddleware on *app* when credentials are configured."""
    user = os.environ.get("TRACEBI_AUTH_USER")
    pw = os.environ.get("TRACEBI_AUTH_PASS")
    if user and pw:
        app.add_middleware(
            BasicAuthMiddleware,
            username=user,
            password=pw,
            realm=os.environ.get("TRACEBI_AUTH_REALM", "TraceBi"),
        )
        return True
    return False
