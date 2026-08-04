"""
The agent gateway: TraceBi's kernel exposed over the Model Context Protocol.

An agent connected here never touches the warehouse. It sees the semantic
contract (``describe()`` plus each model's tables, dimensions and named
measures), asks star-schema questions in that vocabulary, and gets back
**stamped** results: the rows, plus the resolved query, the full lineage
chain, and a fingerprint of the complete result. The stamp is the point —
any number an agent puts in front of a person is traceable back to exactly
which query produced it, whether or not the agent used TraceBi to render
the page it appears on.

Deliberately read-and-compute only. Queries, validation and spec rendering
compute but persist nothing beyond an output file; pipeline execution
writes to the warehouse and stays off this surface until per-agent scopes
exist to gate it.

Two layers, on purpose:

* module-level ``gateway_*`` functions — plain Python, fully testable with
  no MCP dependency installed
* :func:`build_server` — a thin registration of those functions as MCP
  tools, the only place the optional ``mcp`` package is imported

Run it with ``tracebi mcp`` (stdio, for a local agent) or
``tracebi mcp --transport http --port 8765`` (for a remote one).
"""

from __future__ import annotations

import hmac
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from tracebi.audit import actor

#: Rows returned in a query response. The fingerprint always covers the
#: full result; the cap only limits transport. An agent that needs more
#: than _ROW_HARD_CAP rows is building a table, and should do that through
#: a report spec rather than paging raw rows through a chat context.
_ROW_DEFAULT = 50
_ROW_HARD_CAP = 500


class GatewayAuthError(RuntimeError):
    """Refusal to serve the HTTP transport without an auth decision."""


#: The refusal an operator sees when starting the HTTP transport with no
#: auth decision made. It must say exactly what to do — a gateway that
#: fails closed but cryptically just teaches people to reach for --insecure.
_HTTP_AUTH_REFUSAL = (
    "Refusing to serve the MCP gateway over HTTP without authentication.\n"
    "Either set TRACEBI_MCP_TOKEN to a secret value — every client must "
    "then send 'Authorization: Bearer <token>' — or pass --insecure to "
    "serve unauthenticated on purpose."
)


class StaticTokenVerifier:
    """
    Verify the single static token from ``TRACEBI_MCP_TOKEN``.

    Deliberately the minimal slice of gateway auth: one shared secret,
    compared in constant time. Per-agent credentials and scopes are a
    later, separate design; until then work done with the token is still
    attributed as ``mcp:<TRACEBI_MCP_ACTOR>``.
    """

    def __init__(self, token: str) -> None:
        self._token = token.encode("utf-8")

    async def verify_token(self, token: str):
        # Imported here, not at module top: the gateway_* functions must
        # stay importable without the optional ``mcp`` package, and this
        # method only ever runs inside a server build_server() created.
        from mcp.server.auth.provider import AccessToken

        if not hmac.compare_digest(token.encode("utf-8"), self._token):
            return None
        return AccessToken(token=token, client_id=_mcp_actor(), scopes=[])


def _mcp_actor() -> str:
    """The identity recorded against this gateway's work."""
    return f"mcp:{os.environ.get('TRACEBI_MCP_ACTOR', 'agent')}"


def _models_dir() -> Path:
    return Path(os.environ.get("TRACEBI_MODELS_DIR", "models"))


def _load_models() -> dict:
    """Every project model, keyed both by ``model.name`` and file stem."""
    from tracebi import model_registry

    models: dict = {}
    d = _models_dir()
    if d.is_dir():
        for stem in model_registry.auto_discover(str(d)):
            try:
                m = model_registry.get_model(stem)
            except Exception:  # noqa: BLE001 — a broken file shouldn't hide the others
                continue
            models[m.name] = m
            models.setdefault(stem, m)
    # Explicitly registered models (tests, notebooks) participate too.
    for name in model_registry.list_models():
        if name not in models:
            try:
                models[name] = model_registry.get_model(name)
            except Exception:  # noqa: BLE001
                continue
    return models


def _get_model(name: str):
    models = _load_models()
    if name not in models:
        raise KeyError(
            f"Model '{name}' not found. Available: {sorted(set(models))}"
        )
    return models[name]


def _json_rows(df, limit: int) -> list[dict]:
    """First *limit* rows as JSON-safe dicts (numpy scalars and dates included)."""
    return json.loads(df.head(limit).to_json(orient="records", date_format="iso"))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "report"


# ── Gateway operations ─────────────────────────────────────────────────────


def gateway_context(model: Optional[str] = None) -> dict:
    """
    The semantic contract: TraceBi's full vocabulary, optionally plus one
    model's schema. This is the first call an agent should make — every
    fact, dimension, measure and section it may reference is in here, and
    nothing outside it will validate.
    """
    from tracebi.capabilities import describe

    payload = describe()
    if model:
        payload["model"] = _get_model(model).info()
    return payload


def gateway_models() -> dict:
    """
    Models this project exposes, with table/fact/dimension counts.

    The registry indexes each model under both its file stem and its
    ``.name``; listing both as separate models made an agent's world look
    twice its size, so aliases are collapsed to one entry with every name
    that resolves to it.
    """
    by_id: dict[int, tuple[Any, list[str]]] = {}
    for name, m in _load_models().items():
        by_id.setdefault(id(m), (m, []))[1].append(name)

    out = {}
    for m, names in by_id.values():
        primary = getattr(m, "name", None) or names[0]
        try:
            info = m.info()
        except Exception as exc:  # noqa: BLE001
            out[primary] = {"error": str(exc)}
            continue
        out[primary] = {
            "aliases": sorted(n for n in names if n != primary),
            "tables": sorted(info.get("tables", {}))
            if isinstance(info.get("tables"), dict)
            else info.get("tables"),
            "facts": info.get("facts"),
            "dimensions": info.get("dimensions"),
            "measures": [
                mm.get("name") if isinstance(mm, dict) else mm
                for mm in (info.get("measures") or [])
            ],
        }
    return {"models": out}


def gateway_model_info(model: str) -> dict:
    """One model's full schema — tables, relationships, facts, dimensions, measures."""
    return _get_model(model).info()


def gateway_query(
    model: str,
    fact: str,
    measures: Any,
    dimensions: Optional[list[str]] = None,
    filters: Optional[dict] = None,
    aggregate: bool = True,
    allow_fanout: bool = False,
    limit: int = _ROW_DEFAULT,
) -> dict:
    """
    Run a star-schema query and return a **stamped** result.

    The stamp — resolved query, lineage chain, fingerprint — describes the
    *full* result; ``rows`` is a transport-capped preview of it. So a
    number quoted from this response is verifiable even when the row that
    carried it was beyond the cap: re-run the recorded query and compare
    fingerprints.
    """
    limit = max(1, min(int(limit), _ROW_HARD_CAP))
    m = _get_model(model)
    with actor(_mcp_actor()):
        ds = m.query(
            fact=fact,
            measures=measures,
            dimensions=list(dimensions or []),
            filters=filters or None,
            aggregate=aggregate,
            allow_fanout=allow_fanout,
        )
    df = ds.to_pandas()
    return {
        "model": model,
        "query": {
            "fact": fact,
            "measures": measures,
            "dimensions": list(dimensions or []),
            "filters": filters or {},
            "aggregate": aggregate,
            "allow_fanout": allow_fanout,
        },
        "columns": list(df.columns),
        "row_count": len(df),
        "rows": _json_rows(df, limit),
        "rows_returned": min(limit, len(df)),
        "truncated": len(df) > limit,
        "fingerprint": ds.fingerprint(),
        "lineage": ds.lineage_to_dict(),
        "actor": _mcp_actor(),
    }


def gateway_validate_spec(spec: Any) -> dict:
    """
    Check a report spec against the project's models without loading a row.

    Errors carry a path (``sections[0].data.query.fact``) so an agent can
    repair its own spec and retry.
    """
    from tracebi.spec import ReportSpec

    try:
        rs = (
            ReportSpec.from_json(spec)
            if isinstance(spec, str)
            else ReportSpec.from_dict(spec)
        )
    except Exception as exc:  # noqa: BLE001 — a malformed spec is data, not a crash
        return {"ok": False, "errors": [f"spec could not be parsed: {exc}"],
                "warnings": []}
    return rs.validate(_load_models())


def gateway_render_spec(spec: Any, output_dir: str = "output") -> dict:
    """
    Validate, build and render a spec to a self-contained HTML artifact,
    writing the lineage manifest beside it.

    Refuses to render an invalid spec — an artifact from a spec that failed
    validation would be exactly the ungoverned output this surface exists
    to prevent.
    """
    from tracebi.reports.html_renderer import HTMLRenderer
    from tracebi.spec import ReportSpec

    try:
        rs = (
            ReportSpec.from_json(spec)
            if isinstance(spec, str)
            else ReportSpec.from_dict(spec)
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"spec could not be parsed: {exc}"],
                "warnings": []}

    models = _load_models()
    result = rs.validate(models)
    if not result["ok"]:
        return {"ok": False, "errors": result["errors"],
                "warnings": result["warnings"]}

    # Every failure comes back on the one documented channel —
    # {ok: false, errors: [...]} with the exception type, never a raw
    # traceback. Build and render run real queries, so they can fail in
    # ways validation cannot see (a column only the table knows, a
    # non-unique dimension key, a connector error).
    try:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{_slug(rs.name)}.html"
        manifest_path = out_dir / f"{_slug(rs.name)}.manifest.json"

        with actor(_mcp_actor()):
            report = rs.build(models)
            HTMLRenderer().render(report, str(html_path))
            manifest = report.build_manifest("html", str(html_path)).to_dict()

        manifest_path.write_text(
            json.dumps(manifest, indent=2, default=str), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — reported on the error channel
        return {"ok": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "warnings": result["warnings"]}
    fingerprints = [
        s["dataset_fingerprint"]
        for s in manifest.get("sections", [])
        if s.get("dataset_fingerprint")
    ]
    return {
        "ok": True,
        "html_path": str(html_path),
        "manifest_path": str(manifest_path),
        "report_name": rs.name,
        "sections": len(manifest.get("sections", [])),
        "dataset_fingerprints": fingerprints,
        "warnings": result["warnings"],
    }


def gateway_reports() -> dict:
    """Reports the project exposes, from the discovery report."""
    from tracebi.web.discovery import discovery_report

    return {"reports": discovery_report()}


def gateway_verify_manifest(manifest: Any) -> dict:
    """
    Close the loop: re-run every recorded query in a rendered manifest and
    classify each section — ``reproduces`` (fingerprint matches),
    ``source_drift`` (result differs and an input fingerprint moved),
    ``unexplained`` (result differs but the inputs did not — the alarming
    case), or ``unverifiable`` (no recorded query to re-run).

    *manifest* is the manifest as a dict, or a path to the
    ``*.manifest.json`` file ``render_report_spec`` wrote. On success the
    result carries per-section classifications plus a summary; ``ok`` is
    True only when every section reproduces or is unverifiable — a drifted
    or unexplained receipt is not an ok one.
    """
    from tracebi.verify import load_models, verify_manifest

    if isinstance(manifest, str):
        p = Path(manifest)
        if not p.is_file():
            return {"ok": False, "errors": [f"manifest file not found: {manifest}"]}
        try:
            manifest = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {"ok": False, "errors": [f"manifest is not valid JSON: {exc}"]}
    if not isinstance(manifest, dict):
        return {"ok": False, "errors": [
            f"manifest must be a dict or a file path, got {type(manifest).__name__}"
        ]}

    try:
        with actor(_mcp_actor()):
            return verify_manifest(manifest, load_models())
    except Exception as exc:  # noqa: BLE001 — corrupt receipts are data, not crashes
        return {"ok": False, "errors": [
            f"manifest could not be verified: {type(exc).__name__}: {exc}"
        ]}


# ── MCP registration ───────────────────────────────────────────────────────


def build_server(token: Optional[str] = None):
    """
    Register the gateway operations as MCP tools.

    With *token*, the streamable-http transport requires
    ``Authorization: Bearer <token>`` on every request (401 otherwise),
    via the SDK's own ``token_verifier`` hook; stdio ignores it.

    The only place the optional ``mcp`` package is imported, per the
    fail-loudly rule for optional dependencies.
    """
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover — exercised by hand
        raise ImportError(
            "The MCP gateway needs the 'mcp' package. "
            "Install it with: pip install 'tracebi[mcp]'"
        ) from exc

    auth_kwargs: dict[str, Any] = {}
    if token is not None:
        from mcp.server.auth.settings import AuthSettings

        auth_kwargs = {
            "token_verifier": StaticTokenVerifier(token),
            # AuthSettings models an OAuth resource server, so it demands
            # an issuer_url — but a static shared token has no issuer. The
            # placeholder is never served: without an auth_server_provider
            # no OAuth routes exist, and with resource_server_url=None no
            # metadata routes exist. Only the bearer check remains.
            "auth": AuthSettings(
                issuer_url="http://127.0.0.1",
                resource_server_url=None,
            ),
        }

    server = MCPServer(
        name="tracebi",
        **auth_kwargs,
        instructions=(
            "TraceBi semantic gateway. Call get_context first — it returns "
            "the full vocabulary (models, facts, dimensions, measures, "
            "report sections) and nothing outside it will validate. Query "
            "with query_model; every response is stamped with the resolved "
            "query, lineage and a fingerprint of the full result — cite the "
            "fingerprint when you quote a number. Author reports as specs: "
            "validate_report_spec to check without executing, "
            "render_report_spec to produce the governed HTML artifact and "
            "its manifest. The loop is closed: verify_manifest re-runs a "
            "manifest's recorded queries and classifies every section as "
            "reproduces, source drift, or unexplained — a receipt you "
            "rendered is a receipt you (or anyone later) can check."
        ),
    )

    server.tool(
        name="get_context",
        description=(
            "TraceBi's semantic contract: every model, section type, chart "
            "type, DataSet verb, measure kind and filter operator. Pass "
            "model=<name> to include that model's tables, dimensions and "
            "named measures. Call this first."
        ),
    )(gateway_context)
    server.tool(
        name="list_models",
        description="Models this project exposes, with facts, dimensions and measures.",
    )(gateway_models)
    server.tool(
        name="describe_model",
        description="One model's full schema: tables, relationships, facts, dimensions, named measures.",
    )(gateway_model_info)
    server.tool(
        name="query_model",
        description=(
            "Run a star-schema query. measures is {column: agg} (sum, count, "
            "mean, min, max, nunique); dimensions are 'dim_name.attribute' "
            "references; filters accept equality, lists (IN) and operator "
            "dicts (gte, between, contains, ...). Returns rows plus a stamp: "
            "the resolved query, lineage chain, and a fingerprint of the "
            "full result. Quote the fingerprint with any number you cite."
        ),
    )(gateway_query)
    server.tool(
        name="validate_report_spec",
        description=(
            "Check a report spec (JSON) against the project's models without "
            "loading any data. Errors carry a path like "
            "sections[0].data.query.fact — fix and retry."
        ),
    )(gateway_validate_spec)
    server.tool(
        name="render_report_spec",
        description=(
            "Validate, build and render a report spec to a self-contained "
            "HTML artifact plus a lineage manifest written beside it. "
            "Refuses invalid specs."
        ),
    )(gateway_render_spec)
    server.tool(
        name="list_reports",
        description="Reports the project exposes, with registration status per file.",
    )(gateway_reports)
    server.tool(
        name="verify_manifest",
        description=(
            "Re-run every recorded query in a rendered manifest (a dict, or "
            "a path to the *.manifest.json render_report_spec wrote) and "
            "classify each section: reproduces, source_drift (an input "
            "fingerprint moved), unexplained (result differs but inputs "
            "match), or unverifiable (no recorded query). Closes the loop "
            "on your own receipts."
        ),
    )(gateway_verify_manifest)

    return server


def serve(transport: str = "stdio", port: int = 8765,
          insecure: bool = False) -> None:
    """
    Build the server and run it until interrupted.

    The HTTP transport refuses to start until the operator makes an auth
    decision: set ``TRACEBI_MCP_TOKEN`` (bearer auth on every request) or
    pass ``insecure=True`` explicitly. stdio has no network surface and is
    unchanged.
    """
    if transport == "http":
        # .strip(): a whitespace-only value is an unset token that *looks*
        # set — the worst kind for an auth gate.
        token = os.environ.get("TRACEBI_MCP_TOKEN", "").strip()
        if not token and not insecure:
            raise GatewayAuthError(_HTTP_AUTH_REFUSAL)
        auth_mode = (
            "bearer (TRACEBI_MCP_TOKEN)" if token else "none (--insecure)"
        )
        server = build_server(token=token or None)
        # After build_server: a posture line printed before a failed build
        # would announce an auth mode that never came up.
        # stderr: on stdio the protocol owns stdout, so operator-facing
        # posture lines go to stderr on every transport for consistency.
        print(
            f"[tracebi] mcp gateway: transport=http auth={auth_mode} "
            f"actor={_mcp_actor()}",
            file=sys.stderr,
        )
        server.run(transport="streamable-http", port=port)
    else:
        server = build_server()
        server.run(transport="stdio")
