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
from starlette.responses import JSONResponse, Response


_PROTECTED_PREFIXES = ("/api/", "/dashboards/")
_EXEMPT_PATHS = ("/api/health",)


# ── Authorization ───────────────────────────────────────────────────────────
#
# Authentication answers "who is this"; until now nothing asked "may they".
# Both middlewares set request.state.user and no code read it, so any
# authenticated principal could run every report, execute every request
# script, and trigger every pipeline layer.
#
# Three roles, ordered. The split is by *side effect*, which is what a
# security review asks about and what a reader can predict without a table:
#
#   viewer   reads. Browsing models, reports, lineage, and running Explore
#            queries — analytical reads that write nothing.
#   analyst  viewer, plus executing report and request code.
#   admin    analyst, plus running pipeline layers, which write to the
#            warehouse, and dev-mode reload.

ROLES = ("viewer", "analyst", "admin")
_ROLE_RANK = {role: i for i, role in enumerate(ROLES)}

#: Role assumed for an authenticated principal with no role of their own,
#: once any role configuration exists. Overridable per deployment.
_DEFAULT_ROLE = "viewer"


def _required_role(method: str, path: str) -> str:
    """
    Minimum role for *method* *path*.

    Unlisted writes require `analyst`, so a route added later is guarded by
    default rather than open by default.
    """
    if method in ("GET", "HEAD", "OPTIONS"):
        return "viewer"
    if path.startswith("/api/pipelines/") or path.startswith("/api/_dev/"):
        return "admin"
    # Explore and spec validation compute but persist nothing, so they sit
    # with the reads rather than behind an execute permission.
    if path.startswith("/api/models/") and path.endswith("/query"):
        return "viewer"
    if path.startswith("/api/spec/validate"):
        return "viewer"
    return "analyst"


def _rank(role: Optional[str]) -> int:
    return _ROLE_RANK.get(role or "", -1)


def _highest_role(values) -> Optional[str]:
    """Best known role among *values*; unknown names are ignored, not fatal."""
    known = [v for v in values if v in _ROLE_RANK]
    return max(known, key=_rank) if known else None


class _Authorizer:
    """
    Resolves a principal's role and decides whether a request is permitted.

    Role comes from a header claim forwarded by the SSO proxy (the usual
    enterprise shape — the org's IdP already knows the groups) or from an
    explicit user→role map for the Basic-auth case.

    **Enforcement is opt-in, deliberately.** With neither source configured
    every principal is treated as `admin`, so adding this cannot silently
    lock existing deployments out of their own pipelines. Configure either
    source and enforcement switches on for everyone, with unmatched
    principals falling back to TRACEBI_AUTH_DEFAULT_ROLE (`viewer`).
    """

    def __init__(self) -> None:
        self.role_header = os.environ.get("TRACEBI_AUTH_ROLE_HEADER", "").strip()
        self.role_map = self._parse_map(os.environ.get("TRACEBI_AUTH_ROLE_MAP", ""))
        self.default_role = (
            os.environ.get("TRACEBI_AUTH_DEFAULT_ROLE", "").strip() or _DEFAULT_ROLE
        )
        if self.default_role not in _ROLE_RANK:
            raise ValueError(
                f"TRACEBI_AUTH_DEFAULT_ROLE must be one of {ROLES}, "
                f"got {self.default_role!r}"
            )

    @property
    def enabled(self) -> bool:
        return bool(self.role_header or self.role_map)

    @staticmethod
    def _parse_map(raw: str) -> dict:
        """Parse ``alice:admin,bob:analyst`` into a dict, ignoring blanks."""
        out = {}
        for pair in raw.split(","):
            if ":" not in pair:
                continue
            user, _, role = pair.partition(":")
            user, role = user.strip(), role.strip()
            if user and role in _ROLE_RANK:
                out[user] = role
        return out

    def role_for(self, request: Request, user: Optional[str]) -> str:
        if not self.enabled:
            # No authorization configured: preserve pre-existing behaviour
            # rather than breaking a running deployment.
            return "admin"
        if self.role_header:
            raw = request.headers.get(self.role_header, "")
            # Group claims are conventionally comma- or space-separated.
            claimed = _highest_role(raw.replace(" ", ",").split(","))
            if claimed:
                return claimed
        if user and user in self.role_map:
            return self.role_map[user]
        return self.default_role

    def check(self, request: Request, user: Optional[str]) -> Optional[Response]:
        """None when permitted, otherwise the 403 to return."""
        role = self.role_for(request, user)
        request.state.role = role
        needed = _required_role(request.method, request.url.path)
        if _rank(role) >= _rank(needed):
            return None
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "message": (
                        f"Role '{role}' may not {request.method} {request.url.path}. "
                        f"Requires '{needed}' or higher."
                    ),
                    "role": role,
                    "required_role": needed,
                }
            },
        )


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Single-credential HTTP Basic auth guarding the API and dashboards."""

    def __init__(self, app, username: str, password: str, realm: str = "TraceBi") -> None:
        super().__init__(app)
        self._username = username
        self._password = password
        self._realm = realm
        self._authz = _Authorizer()

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
        denied = self._authz.check(request, self._username)
        if denied is not None:
            return denied
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
        self._authz = _Authorizer()

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
        denied = self._authz.check(request, user)
        if denied is not None:
            return denied
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
        trusted_list = [ip for ip in trusted.split(",") if ip.strip()]
        if not trusted_list:
            import warnings
            warnings.warn(
                "TRACEBI_AUTH_PROXY_HEADER is set without "
                "TRACEBI_AUTH_PROXY_TRUSTED_IPS. Any client that can reach "
                f"this server directly can authenticate by sending the "
                f"'{proxy_header}' header itself. Set "
                "TRACEBI_AUTH_PROXY_TRUSTED_IPS to your proxy's address(es) "
                "unless the server is only reachable through the proxy.",
                stacklevel=2,
            )
        app.add_middleware(
            ProxyHeaderAuthMiddleware,
            header=proxy_header,
            trusted_ips=trusted_list,
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
