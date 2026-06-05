"""
Optional auth for the TraceBi web layer.

Two modes, mutually exclusive:

* **Basic auth** — enabled when ``TRACEBI_AUTH_USER`` and ``TRACEBI_AUTH_PASS``
  are both set. Single shared user/password, suitable for small-team deployments.

* **Proxy header trust** — enabled when ``TRACEBI_AUTH_PROXY_HEADER`` is set.
  Designed for sitting behind Authelia / oauth2-proxy / Cloudflare Access,
  which authenticate the user upstream and forward the identity in a header
  (default ``X-Forwarded-User``). The header value is exposed at
  ``request.state.user`` for downstream handlers. Optionally set
  ``TRACEBI_AUTH_PROXY_TRUSTED_IPS`` (comma-separated) to require the
  request to originate from a known proxy address.

Both modes exempt ``/api/health`` so liveness probes work without credentials.
For multi-user identity, use the proxy mode.
"""

from __future__ import annotations

import base64
import ipaddress
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
        if not path.startswith(_PROTECTED_PREFIXES):
            return await call_next(request)
        if path in _EXEMPT_PATHS:
            return await call_next(request)
        if not self._check(request.headers.get("authorization")):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Basic realm="{self._realm}"'},
            )
        request.state.user = self._username
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


class ProxyHeaderAuthMiddleware(BaseHTTPMiddleware):
    """
    Trust an upstream proxy's identity header.

    The auth header value is exposed at ``request.state.user`` and the raw
    name at ``request.state.user_header``. When ``trusted_ips`` is set,
    requests from any other address are rejected with 401.
    """

    def __init__(
        self,
        app,
        header: str = "X-Forwarded-User",
        trusted_ips: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        self._header = header
        self._trusted_networks = [
            ipaddress.ip_network(ip.strip(), strict=False)
            for ip in (trusted_ips or [])
            if ip.strip()
        ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith(_PROTECTED_PREFIXES):
            return await call_next(request)
        if path in _EXEMPT_PATHS:
            return await call_next(request)

        if self._trusted_networks and not self._is_trusted_client(request):
            return Response(status_code=401, content="proxy not in trusted_ips")

        user = request.headers.get(self._header)
        if not user:
            return Response(
                status_code=401,
                content=f"missing identity header {self._header}",
            )
        request.state.user = user
        request.state.user_header = self._header
        return await call_next(request)

    def _is_trusted_client(self, request: Request) -> bool:
        host = request.client.host if request.client else None
        if not host:
            return False
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(addr in net for net in self._trusted_networks)


def install_if_configured(app) -> Optional[str]:
    """
    Install the appropriate auth middleware on *app* based on env vars.

    Returns the mode that was installed (``"basic"`` / ``"proxy"``) or
    ``None`` when no auth is configured.
    """
    user = os.environ.get("TRACEBI_AUTH_USER")
    pw = os.environ.get("TRACEBI_AUTH_PASS")
    proxy_header = os.environ.get("TRACEBI_AUTH_PROXY_HEADER")

    if proxy_header:
        trusted = os.environ.get("TRACEBI_AUTH_PROXY_TRUSTED_IPS", "")
        app.add_middleware(
            ProxyHeaderAuthMiddleware,
            header=proxy_header,
            trusted_ips=[ip for ip in trusted.split(",") if ip.strip()],
        )
        return "proxy"

    if user and pw:
        app.add_middleware(
            BasicAuthMiddleware,
            username=user,
            password=pw,
            realm=os.environ.get("TRACEBI_AUTH_REALM", "TraceBi"),
        )
        return "basic"

    return None
