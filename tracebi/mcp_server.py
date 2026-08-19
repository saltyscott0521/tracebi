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

import hmac
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional, TypedDict

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


def _report_name_error(report: str) -> Optional[str]:
    """``None`` if ``report`` is a safe package name, else an error message.

    The name indexes ``reports/<name>/`` and must never be a path: reject path
    separators, an absolute path, and a leading dot so ``reports_dir / report``
    can never escape the reports directory (``/etc/x`` resolves to an absolute
    path; ``../../etc`` traverses out). Applied by every tool that turns a
    caller-supplied name into a filesystem path.
    """
    if os.sep in report or "/" in report or report.startswith("."):
        return f"invalid report name {report!r}: pass the package name, not a path"
    return None


def _confined_output_dir(output_dir: str) -> "tuple[Optional[Path], Optional[str]]":
    """Resolve ``output_dir`` for an artifact write, refusing dangerous targets.

    An MCP-driving agent chooses ``output_dir``, so two protections apply.
    ALWAYS: the artifact may never be written inside the installed ``tracebi``
    package — an agent must not clobber shipped assets like
    ``web/ui/dist/index.html``, which a running server would then serve.
    OPT-IN: if ``$TRACEBI_OUTPUT_ROOT`` is set, the resolved directory must stay
    within it — strict confinement for a hardened deployment, mirroring the
    opt-in auth model (secure when configured, no default-deny that would break
    an existing workflow that writes elsewhere). Returns ``(dir, None)`` when
    allowed, ``(None, error)`` otherwise.
    """
    try:
        resolved = (Path.cwd() / output_dir).resolve()
    except (OSError, ValueError) as exc:
        return None, f"invalid output_dir {output_dir!r}: {exc}"

    import tracebi
    pkg = Path(tracebi.__file__).resolve().parent
    if resolved == pkg or pkg in resolved.parents:
        return None, (
            f"output_dir {output_dir!r} resolves inside the installed tracebi "
            f"package; refusing to overwrite shipped files"
        )

    root_env = os.environ.get("TRACEBI_OUTPUT_ROOT")
    if root_env:
        root = Path(root_env).resolve()
        if resolved != root and root not in resolved.parents:
            return None, (
                f"output_dir {output_dir!r} escapes TRACEBI_OUTPUT_ROOT "
                f"({root}); artifacts must be written under it"
            )
    return resolved, None


#: Cap on a single fetched artifact. Large enough for the artifact envelope the
#: scale docs describe (a few MB), small enough that an accidental huge file
#: does not blow the MCP response — over it, the agent reads the path directly.
_FETCH_MAX_BYTES = 16 * 1024 * 1024


def _confined_read_path(path: str) -> "tuple[Optional[Path], Optional[str]]":
    """Resolve *path* for a READ, refusing anything outside the artifact area.

    The fetch tool hands back bytes the render/build tools wrote, so it reads
    only where those tools live: under the working directory (or
    ``$TRACEBI_OUTPUT_ROOT`` when set), never inside the installed ``tracebi``
    package, and never a traversal to an arbitrary server file. Returns
    ``(path, None)`` when allowed, ``(None, error)`` otherwise.
    """
    try:
        resolved = (Path.cwd() / path).resolve()
    except (OSError, ValueError) as exc:
        return None, f"invalid path {path!r}: {exc}"

    import tracebi
    pkg = Path(tracebi.__file__).resolve().parent
    if resolved == pkg or pkg in resolved.parents:
        return None, (
            f"path {path!r} resolves inside the installed tracebi package"
        )

    root = Path(os.environ.get("TRACEBI_OUTPUT_ROOT") or Path.cwd()).resolve()
    if resolved != root and root not in resolved.parents:
        return None, (
            f"path {path!r} escapes the artifact root ({root}); fetch reads "
            f"only files the render/build tools wrote under it"
        )
    if not resolved.is_file():
        return None, f"no file at {path!r}"
    return resolved, None


#: The authoring SOP, served as the ``tracebi://guide`` resource. An agent
#: reaching TraceBi only over MCP never sees AGENTS.md or the repo docs, so the
#: essential rules have to live on the surface itself.
_AUTHORING_GUIDE = """\
# Working with the TraceBi gateway

TraceBi is a trust layer for AI-generated analytics: every number you put in
front of a person should carry a receipt. This gateway is how you produce one.

## The loop
1. **get_context** — first call. Returns the whole vocabulary: models, facts,
   dimensions, named measures, the `presentation` block (the `data-tb-*`
   figure grammar, tokens, formats) and `transform_contracts`. Nothing
   outside it validates.
2. **query_model** — ask star-schema questions. Every result is *stamped*: the
   resolved query, the lineage chain, and a SHA-256 fingerprint of the full
   result. Cite the fingerprint with any number you quote. "Top N" is
   `order_by` + `limit` in the query — declarative, in the receipt.
3. **author the report** — the report form is an ARTIFACT PACKAGE
   (`reports/<name>/`): `report.json` names query bindings; `template.html`
   is your page, where every figure claims a binding via
   `data-tb-figure` + `data-tb-binding` (or is honestly
   `data-tb-unverified` — no third state). Any element works, including a
   `<span>` inside a sentence: bind prose numbers instead of typing them.
   Blocks marked `data-tb-stage="exploration"` die at build. Interactive
   objects are declarative too: `data-tb-filter` / `data-tb-search` subset
   which stamped rows display (never compute — value figures are exempt),
   tables scroll past `data-tb-rows`, `data-tb-download` exports the
   stamped CSV verbatim, tabs via `data-tb-tab`, layouts via
   `.tb-cols-2/3`; every built page carries the receipt drawer. Details
   in get_context's `presentation` block.
   (A JSON ReportSpec is the same thing as a serialization — read
   `tracebi://spec-schema`, then **validate_report_spec** →
   **render_report_spec**, which refuses invalid specs. Heed validate's
   warnings, not just its errors: a filter/column it cannot pre-verify fails
   at render if it is wrong — render returns a clean `{ok:false}` to act on.)
4. **workbench_state** — while iterating under `tracebi dev`, read this
   before every editing pass: the human steers by PINNING figures in the
   portal with notes, and pins come first.
5. **build_report** — the publish step: builds the package to a
   self-contained HTML + manifest, validating every figure claim. Writes
   only its own artifact and receipt.
6. **fetch_artifact** — build/render return a server-side PATH, not bytes.
   Pass the returned `html_path` (to deliver the report) or `manifest_path`
   (to hand to verify) here to read the actual content back.
7. **verify_manifest** — re-runs the recorded queries and classifies each
   section. Only `reproduces` means a number was re-run and matched; a
   manifest with nothing to check is not a pass.

## The two planes
- **Definition plane (git):** transforms, models, report specs are authored
  and code-reviewed in the repo. A REUSABLE measure belongs here — a reviewed
  edit to the model file, not a workaround in the report layer. But a one-off
  derived number never dead-ends the loop: `query_model` measures accept
  `{expr, agg}` and `{ratio: [num, den]}` alongside declared names, so you can
  compute it in the query itself (and promote it to a declared measure later).
- **Contract plane (this gateway):** you *use* the semantic contract; you do
  not change it here. The gateway is read-and-compute only — it never writes
  the warehouse. The two render tools (`render_report_spec`, `build_report`)
  write only their own artifact and receipt; the read tools are annotated
  read-only so a client can see it.

## The rules
- Never quote a number without its fingerprint.
- Never hard-code a figure a query could produce.
- If something can't be verified, say so — an honest "unverifiable" beats a
  green badge on unchecked work.
- The trust machinery covers the model boundary onward (the query and the
  report), not the phase-① pandas that built the warehouse. A transform may
  declare a *sink contract* (checks on the tables it lands, recorded beside
  the warehouse); a report manifest's `transform_contracts` block then says
  whether each loaded table's sink satisfied its contract — `satisfied`,
  `stale` (re-sunk since checked; never green), or `no_contract`. That claim
  certifies the sink, never the pandas, and never colors a figure status.
"""


# ── Structured output schemas ───────────────────────────────────────────────
# Typed returns so the gateway can advertise an MCP outputSchema and hand the
# agent structured content, not JSON inside a text blob — the stamp and the
# verdict become machine-typed. Plain ``typing`` only: the gateway_* layer must
# stay importable with no ``mcp`` package installed. All ``total=False`` because
# several tools share one dict between a success shape and an
# ``{ok, errors}`` envelope, and the MCP SDK drops any returned key the schema
# does not name — so every key a function can return is listed here.


class ContextResult(TypedDict, total=False):
    tracebi_version: str
    semantic_model: Any
    report_sections: Any
    dataset_verbs: Any
    number_formats: Any
    conventions: Any
    cheat_sheets: Any
    model: Any  # present only when a model= argument was passed


class ModelsResult(TypedDict, total=False):
    models: dict[str, Any]


class ModelInfoResult(TypedDict, total=False):
    name: str
    tables: Any
    relationships: Any
    facts: Any
    dimensions: Any
    measures: Any
    connectors: Any
    filter_operators: Any


class QueryResult(TypedDict, total=False):
    ok: bool
    errors: list[str]
    model: str
    query: dict[str, Any]
    columns: list[str]
    row_count: int
    rows: list[dict[str, Any]]
    rows_returned: int
    truncated: bool
    fingerprint: str
    lineage: Any
    actor: str


class ValidateResult(TypedDict, total=False):
    ok: bool
    errors: list[str]
    warnings: list[str]


class RenderResult(TypedDict, total=False):
    ok: bool
    html_path: str
    manifest_path: str
    report_name: str
    sections: int
    dataset_fingerprints: list[str]
    warnings: list[str]
    errors: list[str]


class FetchArtifactResult(TypedDict, total=False):
    ok: bool
    errors: list[str]
    path: str
    content_type: str
    bytes: int
    content: str


class ReportsResult(TypedDict, total=False):
    reports: Any


class WorkbenchStateResult(TypedDict, total=False):
    # Package shape (report given) and discovery shape (no report) share
    # this one result type — total=False keeps both valid.
    mode: str
    name: str
    figures: Any
    coverage: Any
    bindings: Any
    unused_bindings: Any
    lint: Any
    exhibits: Any
    pins: Any
    code: Any
    warehouse: Any
    models: Any
    packages: Any
    error: Any
    errors: list[str]


class BuildReportResult(TypedDict, total=False):
    ok: bool
    report: str
    output_path: str
    manifest_path: str
    figures: Any
    embedded_fingerprints: list[str]
    transform_contracts: Any
    errors: list[str]


class VerifyResult(TypedDict, total=False):
    ok: bool
    verdict: str
    verdict_detail: str
    exit_code: int
    report_name: str
    schema_version: Any
    python_derived: Any
    sections: Any
    summary: Any
    errors: list[str]


# ── Gateway operations ─────────────────────────────────────────────────────


def gateway_context(model: Optional[str] = None,
                    brief: bool = False) -> ContextResult:
    """
    The semantic contract: TraceBi's vocabulary, optionally plus one
    model's schema. This is the first call an agent should make — every
    fact, dimension, measure and section it may reference is in here, and
    nothing outside it will validate.

    ``brief=True`` is the token-lean tier (~40% of the payload): the
    semantic model, the figure grammar, contracts, and conventions —
    everything the package-first loop needs. Start brief; fetch the full
    vocabulary only when writing Python against the library directly.
    """
    from tracebi.capabilities import describe

    payload = describe(brief=brief)
    if model:
        payload["model"] = _get_model(model).info()
    return payload


def gateway_models() -> ModelsResult:
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


def gateway_model_info(model: str) -> ModelInfoResult:
    """One model's full schema — tables, relationships, facts, dimensions, measures."""
    return _get_model(model).info()


def gateway_query(
    model: str,
    fact: str,
    measures: Any,
    dimensions: Optional[list[str]] = None,
    filters: Optional[dict] = None,
    having: Optional[dict] = None,
    aggregate: bool = True,
    allow_fanout: bool = False,
    order_by: Optional[list] = None,
    limit: Optional[int] = None,
    preview_rows: int = _ROW_DEFAULT,
    include_lineage: bool = True,
) -> QueryResult:
    """
    Run a star-schema query and return a **stamped** result.

    ``filters``/``having``/``order_by``/``limit`` are the query grammar — the
    same fields Python, report specs, and REST accept. ``filters`` is WHERE
    (before aggregation); ``having`` is HAVING (after) — filter on aggregated
    measures with ``having`` so a group's total stays intact, never with
    ``filters`` on a measure, which changes the totals. ``limit`` requires
    ``order_by`` ("first N" must never masquerade as "top N"). ``preview_rows`` is transport
    only: the stamp — resolved query, lineage chain, fingerprint —
    describes the *full* result; ``rows`` is a capped preview of it. So a
    number quoted from this response is verifiable even when the row that
    carried it was beyond the cap: re-run the recorded query and compare
    fingerprints.
    """
    from tracebi.model.data_model import QuerySpec

    preview_rows = max(1, min(int(preview_rows), _ROW_HARD_CAP))

    # Resolve → build the spec → execute, returning the ``{ok, errors}``
    # envelope every other tool uses on any failure — never a raised exception.
    # An agent repairs a structured, named error and retries; a stack trace
    # ends the loop. The model already names the alternatives for a bad
    # fact/dimension/filter column, so those messages pass straight through.
    try:
        m = _get_model(model)
    except KeyError as exc:
        return {"ok": False, "errors": [exc.args[0]]}
    if isinstance(measures, str):
        return {"ok": False, "errors": [
            f"measures must be a list of measure names (e.g. [{measures!r}]) or "
            f"a mapping of column to aggregation (e.g. {{{measures!r}: 'sum'}}), "
            f"not a bare string"]}
    try:
        spec = QuerySpec.from_dict({
            k: v for k, v in {
                "fact": fact,
                "measures": measures,
                "dimensions": list(dimensions or []),
                "filters": filters or None,
                "having": having or None,
                "aggregate": aggregate,
                "allow_fanout": allow_fanout,
                "order_by": order_by,
                "limit": limit,
            }.items() if v is not None
        })
    except Exception as exc:  # noqa: BLE001 — a malformed query is data, not a crash
        return {"ok": False, "errors": [f"invalid query: {exc}"]}
    try:
        with actor(_mcp_actor()):
            ds = m.execute(spec)
    except Exception as exc:  # noqa: BLE001 — a bad fact/dim/filter is data
        return {"ok": False, "errors": [str(exc)]}
    df = ds.to_pandas()
    # Echo the STAMPED resolved spec (fully resolved ordering included), so
    # what the agent cites is what replay compares against.
    stamped = spec.to_dict()
    for node in ds.lineage_to_dict():
        qs = (node.get("metadata") or {}).get("query_spec")
        if qs:
            stamped = qs
    result: QueryResult = {
        "ok": True,
        "model": model,
        "query": stamped,
        "columns": list(df.columns),
        "row_count": len(df),
        "rows": _json_rows(df, preview_rows),
        "rows_returned": min(preview_rows, len(df)),
        "truncated": len(df) > preview_rows,
        "fingerprint": ds.fingerprint(),
        "actor": _mcp_actor(),
    }
    # The fingerprint + resolved query are the stamp an agent cites and
    # re-verifies against; the full lineage chain (with timestamps) is ~600
    # extra tokens per call. Keep it by default, but let an agent exploring
    # drop it with include_lineage=false and re-query when it needs the chain.
    if include_lineage:
        result["lineage"] = ds.lineage_to_dict()
    return result


def gateway_validate_spec(spec: Any) -> ValidateResult:
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


def gateway_render_spec(spec: Any, output_dir: str = "output") -> RenderResult:
    """
    Validate, build and render a spec to a self-contained HTML artifact,
    writing the lineage manifest beside it.

    Refuses to render an invalid spec — an artifact from a spec that failed
    validation would be exactly the ungoverned output this surface exists
    to prevent.
    """
    import tempfile

    from tracebi.reports.compile_spec import compile_spec
    from tracebi.reports.template_package import TemplatePackage
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
    out_dir, out_err = _confined_output_dir(output_dir)
    if out_err:
        return {"ok": False, "errors": [out_err], "warnings": []}
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{_slug(rs.name)}.html"
        manifest_path = out_dir / f"{_slug(rs.name)}.manifest.json"

        with actor(_mcp_actor()):
            # One report form: compile the spec to the artifact package and
            # render it through the same path as a hand-authored package, so a
            # spec gets figures, badges, the receipt drawer, and a schema-2
            # manifest instead of the legacy renderer's bare HTML.
            compiled = compile_spec(rs)
            with tempfile.TemporaryDirectory() as d:
                for fname, content in compiled.files.items():
                    (Path(d) / fname).write_text(content, encoding="utf-8")
                # Pass manifest_path explicitly — render's default sidecar is
                # {out}.html.manifest.json, but this tool returns
                # {slug}.manifest.json.
                manifest = TemplatePackage(d).render(
                    models, str(html_path),
                    manifest_path=str(manifest_path),
                ).to_dict()
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
        "warnings": result["warnings"] + compiled.warnings,
    }


def gateway_reports() -> ReportsResult:
    """Reports the project exposes, from the discovery report."""
    from tracebi.web.discovery import discovery_report

    return {"reports": discovery_report()}


def gateway_verify_manifest(manifest: Any) -> VerifyResult:
    """
    Close the loop: re-run every recorded query in a rendered manifest and
    classify each section — ``reproduces`` (fingerprint matches),
    ``source_drift`` (result differs and an input fingerprint moved),
    ``unexplained`` (result differs but the inputs did not — the alarming
    case), or ``unverifiable`` (no recorded query to re-run).

    *manifest* is the manifest as a dict, or a path to the
    ``*.manifest.json`` file ``render_report_spec`` wrote. On success the
    result carries per-section classifications, a summary, and a
    receipt-level ``verdict`` with a human-readable ``verdict_detail``.
    ``ok`` is False for a drifted or unexplained receipt, and for one with
    no data-bearing section at all — nothing was verified, so nothing
    passed. Read the verdict, not just ``ok``: only ``reproduces`` means a
    number was re-run and matched, and it names any section it could not
    check, so read ``verdict_detail`` with it. ``unverifiable`` (every
    section hand-transformed or python-authored) is ``ok`` but proves
    nothing; ``refused_newer_schema`` means this tracebi declined to read
    the manifest at all, which is not the same as finding nothing in it.
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


def gateway_workbench_state(report: str = "") -> WorkbenchStateResult:
    """
    The workbench state for an artifact package: figures with provenance,
    the coverage bar, per-binding cards, the human's PINS, and the exhibit
    feed — the same JSON the workbench page renders from (v2 §2.5).

    With no *report* (or ``"_discovery"``): the DISCOVERY session's state
    instead — warehouse tables and sink-contract summaries, every model's
    declared star schema, the report packages that exist, and the
    ``_discovery`` exhibit feed and pins (``tracebi dev`` with no name).

    Read-only: this is how a driving agent sees what the human flagged in
    the portal ("steer from chat, see results in the workbench" — pointing
    happens where the evidence is). Exhibits and pins are dev-state only;
    nothing here mints a receipt.
    """
    from tracebi.workbench import DISCOVERY_NAME, collect_discovery_state, collect_state

    if not report or report == DISCOVERY_NAME:
        with actor(_mcp_actor()):
            return collect_discovery_state(os.getcwd(), _load_models())
    # A caller-supplied name must never become a path: without this,
    # report='/etc/x' or '../../x' would escape reports/ and collect_state
    # would read — and execute report.py from — an attacker-chosen directory.
    name_err = _report_name_error(report)
    if name_err:
        return {"errors": [name_err]}
    reports_dir = Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))
    pkg_dir = reports_dir / report
    if not (pkg_dir / "report.json").is_file():
        return {"errors": [
            f"no artifact package at {pkg_dir} — workbench_state applies to "
            f"reports/<name>/ packages"
        ]}
    with actor(_mcp_actor()):
        return collect_state(str(pkg_dir), _load_models())


def gateway_build_report(report: str, output_dir: str = "output") -> BuildReportResult:
    """
    Build an artifact package to one self-contained ``.html`` + manifest —
    the gateway's PUBLISH step for the package lane.

    This is the ``tracebi report build`` gate over MCP: exploration blocks
    are stripped, every figure claim is validated against the embedded
    bindings, and the receipt (manifest schema 2: figures + the
    ``transform_contracts`` join) is written beside the page. Like
    ``render_report_spec``, it writes only its own artifact and receipt —
    never source data. The dev loop itself (``tracebi dev``, snapshots,
    pins) stays on the CLI, where the human's portal lives; this tool is
    how an MCP-driving agent finishes.
    """
    from tracebi.reports.template_package import TemplatePackage

    # The name is a directory under reports/ — never a path.
    name_err = _report_name_error(report)
    if name_err:
        return {"ok": False, "errors": [name_err]}
    reports_dir = Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))
    pkg_dir = reports_dir / report
    if not ((pkg_dir / "report.json").is_file()
            and (pkg_dir / "template.html").is_file()):
        return {"ok": False, "errors": [
            f"no artifact package at {pkg_dir} — build_report applies to "
            f"reports/<name>/ packages (a .json spec renders via "
            f"render_report_spec)"
        ]}
    out_dir, out_err = _confined_output_dir(output_dir)
    if out_err:
        return {"ok": False, "errors": [out_err]}
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{report}.html"
    try:
        with actor(_mcp_actor()):
            manifest = TemplatePackage(str(pkg_dir)).render(
                _load_models(), str(output))
    except Exception as exc:  # noqa: BLE001 — a refused build is a result
        return {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
    m = manifest.to_dict()
    return {
        "ok": True,
        "report": report,
        "output_path": str(output),
        "manifest_path": str(output) + ".manifest.json",
        "figures": m.get("figures") or [],
        "embedded_fingerprints": [
            e.get("embedded_sha256") for e in m.get("embedded_data", [])
        ],
        "transform_contracts": m.get("transform_contracts") or {},
    }


def gateway_fetch_artifact(path: str) -> FetchArtifactResult:
    """Read back a rendered artifact (or its manifest) as text.

    ``render_report_spec`` and ``build_report`` return a server-side PATH; a
    remote agent driving the gateway over MCP needs the BYTES to deliver the
    report or hand the manifest to ``verify_manifest``. Pass the ``html_path``
    or ``manifest_path`` a render/build tool returned. Read-only and hard
    path-guarded: the file must sit under the working directory (or
    ``$TRACEBI_OUTPUT_ROOT``), never inside the installed package, and be one of
    the ``.html`` / ``.json`` artifacts those tools write — never arbitrary
    server files. Over ``_FETCH_MAX_BYTES`` it refuses and names the path.
    """
    resolved, err = _confined_read_path(path)
    if err:
        return {"ok": False, "errors": [err]}
    if resolved.suffix.lower() not in (".html", ".json"):
        return {"ok": False, "errors": [
            f"fetch_artifact reads only rendered .html and .json artifacts, "
            f"not {resolved.suffix!r}"]}
    size = resolved.stat().st_size
    if size > _FETCH_MAX_BYTES:
        return {"ok": False, "errors": [
            f"artifact is {size} bytes, over the {_FETCH_MAX_BYTES}-byte fetch "
            f"cap; read it from {path!r} on the server directly"]}
    try:
        content = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "errors": [f"could not read {path!r}: {exc}"]}
    ctype = "text/html" if resolved.suffix.lower() == ".html" else "application/json"
    return {"ok": True, "path": path, "content_type": ctype,
            "bytes": size, "content": content}


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
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover — exercised by hand
        raise ImportError(
            "The MCP gateway needs the 'mcp' package. "
            "Install it with: pip install 'tracebi[mcp]'"
        ) from exc

    # readOnlyHint carries the manifesto's "read-and-compute only" refusal into
    # the protocol itself: a client can see, before calling, that these tools
    # touch nothing. openWorldHint marks the ones that read the live warehouse.
    _READ = ToolAnnotations(readOnlyHint=True, idempotentHint=True,
                            openWorldHint=False)
    _READ_WAREHOUSE = ToolAnnotations(readOnlyHint=True, idempotentHint=True,
                                      openWorldHint=True)
    # render is the one tool that writes — but only its own artifact + receipt,
    # never source data, so destructiveHint is false. Re-rendering the same
    # spec reproduces the same output, so it is idempotent.
    _RENDER = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=True)

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
            "TraceBi semantic gateway. Call get_context first (start with "
            "brief=true — the token-lean tier, about half the payload) — it "
            "returns the vocabulary (models, facts, dimensions, measures, "
            "report sections) and nothing outside it will validate. Query "
            "with query_model; every response is stamped with the resolved "
            "query, lineage and a fingerprint of the full result — cite the "
            "fingerprint when you quote a number. Author reports as specs: "
            "validate_report_spec to check without executing, "
            "render_report_spec to produce the governed HTML artifact and "
            "its manifest. The loop is closed: verify_manifest re-runs a "
            "manifest's recorded queries and classifies every section as "
            "reproduces, source drift, or unexplained — a receipt you "
            "rendered is a receipt you (or anyone later) can check. Every "
            "tool returns structured output; the read tools are annotated "
            "read-only. Resources carry reference material: tracebi://guide "
            "(how to author), tracebi://spec-schema (the ReportSpec JSON "
            "Schema), tracebi://models/{name} (a model's schema). The "
            "author_report prompt walks the whole loop for a question."
        ),
    )

    # Tools. structured_output=True advertises each return's JSON Schema and
    # hands the agent structuredContent, not JSON-in-text — the stamp and the
    # verdict arrive machine-typed.
    server.tool(
        name="get_context", title="Semantic contract", annotations=_READ,
        structured_output=True,
        description=(
            "TraceBi's semantic contract: every model, section type, chart "
            "type, DataSet verb, measure kind and filter operator. Pass "
            "model=<name> to include that model's tables, dimensions and "
            "named measures. Call this first — start with brief=true for the "
            "token-lean payload (about half the size), and re-call without it "
            "only when you need a section it omits."
        ),
    )(gateway_context)
    server.tool(
        name="list_models", title="List models", annotations=_READ,
        structured_output=True,
        description="Models this project exposes, with facts, dimensions and measures.",
    )(gateway_models)
    server.tool(
        name="describe_model", title="Describe a model", annotations=_READ,
        structured_output=True,
        description="One model's full schema: tables, relationships, facts, dimensions, named measures.",
    )(gateway_model_info)
    server.tool(
        name="query_model", title="Run a stamped query",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "Run a star-schema query. measures is a list of declared "
            "measure names (ratio measures included) or a {output: spec} "
            "mapping — spec is an agg name (sum, count, mean, min, max, "
            "nunique), or {expr, agg} for a derived column (e.g. "
            "{'expr': 'market_value - cost', 'agg': 'sum'}), or "
            "{ratio: [num, den]} for a ratio of two other measures; "
            "dimensions are "
            "'dim_name.attribute' references; filters accept equality, "
            "lists (IN) and operator dicts (gte, between, contains, ...); "
            "order_by ({column, desc} or '-col') sorts the result and "
            "limit (requires order_by) keeps the top N. preview_rows caps "
            "only the transport. Returns rows plus a stamp: the resolved "
            "query, lineage chain, and a fingerprint of the full result. "
            "Quote the fingerprint with any number you cite. Pass "
            "include_lineage=false while exploring to drop the lineage chain "
            "(the fingerprint and resolved query still let you cite and "
            "re-verify) for lighter responses."
        ),
    )(gateway_query)
    server.tool(
        name="validate_report_spec", title="Validate a report spec",
        annotations=_READ, structured_output=True,
        description=(
            "Check a report spec (JSON) against the project's models without "
            "loading any data. Errors carry a path like "
            "sections[0].data.query.fact — fix and retry."
        ),
    )(gateway_validate_spec)
    server.tool(
        name="render_report_spec", title="Render a report (writes an artifact)",
        annotations=_RENDER, structured_output=True,
        description=(
            "Validate, build and render a report spec to a self-contained "
            "HTML artifact plus a lineage manifest written beside it. "
            "Refuses invalid specs."
        ),
    )(gateway_render_spec)
    server.tool(
        name="list_reports", title="List reports", annotations=_READ,
        structured_output=True,
        description="Reports the project exposes, with registration status per file.",
    )(gateway_reports)
    server.tool(
        name="workbench_state", title="Workbench state", annotations=_READ_WAREHOUSE,
        structured_output=True,
        description=(
            "The workbench state for an artifact package (reports/<name>/): "
            "figures with provenance, coverage, per-binding cards, the "
            "human's pins, and the exhibit feed. Read this to see what the "
            "human flagged in the portal before your next edit. It also "
            "serves the discovery session: call with no report while the "
            "human runs tracebi dev with no name, and it returns the "
            "project-level state instead — warehouse tables, sink-contract "
            "summaries, models, packages, and the discovery feed and pins."
        ),
    )(gateway_workbench_state)
    server.tool(
        name="build_report", title="Build an artifact package (writes the artifact)",
        annotations=_RENDER, structured_output=True,
        description=(
            "Build an artifact package (reports/<name>/) to one "
            "self-contained HTML + its manifest — the publish step. Strips "
            "exploration blocks, validates every figure claim against the "
            "embedded bindings, and returns the figure records, embedded "
            "fingerprints, and the transform_contracts join. Writes only "
            "its own artifact and receipt."
        ),
    )(gateway_build_report)
    server.tool(
        name="fetch_artifact", title="Fetch a rendered artifact",
        annotations=_READ, structured_output=True,
        description=(
            "Read back the bytes of an artifact a render/build tool wrote — "
            "pass the html_path or manifest_path it returned. The render tools "
            "return a server-side path; this delivers the actual content so a "
            "remote agent can send the report or hand the manifest to "
            "verify_manifest. Read-only, guarded to the artifact directory, "
            ".html/.json only."
        ),
    )(gateway_fetch_artifact)
    server.tool(
        name="verify_manifest", title="Verify a receipt",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "Re-run every recorded query in a rendered manifest (a dict, or "
            "a path to the *.manifest.json render_report_spec wrote) and "
            "classify each section: reproduces, source_drift (an input "
            "fingerprint moved), unexplained (result differs but inputs "
            "match), or unverifiable (no recorded query). Closes the loop "
            "on your own receipts. Check the receipt-level verdict, not "
            "just ok: only 'reproduces' means a number was re-run and "
            "matched, and a manifest with nothing to check is not a pass."
        ),
    )(gateway_verify_manifest)

    # Resources — reference material a client can pull into context. The guide
    # puts the authoring SOP on the surface itself (an MCP-only agent never
    # sees AGENTS.md); the schema makes the ReportSpec grammar obtainable
    # without a REST call; the template exposes any model as a readable doc.
    server.resource(
        "tracebi://guide", name="TraceBi authoring guide",
        mime_type="text/markdown",
        description="How to work with this gateway: the loop, the two planes, the rules.",
    )(lambda: _AUTHORING_GUIDE)

    @server.resource(
        "tracebi://spec-schema", name="ReportSpec JSON Schema",
        mime_type="application/json",
        description="The JSON Schema a report spec must satisfy — author against this.",
    )
    def _spec_schema_resource() -> str:
        from tracebi.spec import json_schema
        return json.dumps(json_schema(), indent=2, default=str)

    @server.resource(
        "tracebi://models/{name}", name="Model schema",
        mime_type="application/json",
        description="One model's full schema (tables, dimensions, measures) as a document.",
    )
    def _model_resource(name: str) -> str:
        return json.dumps(_get_model(name).info(), indent=2, default=str)

    # Prompt — the authoring SOP as one executable template.
    @server.prompt(
        name="author_report", title="Author a governed report",
        description="Walk the full loop — context, query, spec, validate, render, verify — for a question.",
    )
    def _author_report_prompt(question: str) -> str:
        return (
            f"Author a governed TraceBi report that answers: {question}\n\n"
            "Follow the loop, and do not skip a step:\n"
            "1. Call get_context (start with brief=true; add the model= you'll "
            "use) to learn the exact facts, dimensions and named measures. "
            "Nothing outside that vocabulary will validate.\n"
            "2. Use query_model to explore the numbers. Every result is "
            "stamped — keep the fingerprints for anything you cite.\n"
            "3. Read tracebi://spec-schema, then write a ReportSpec whose "
            "sections query the model (not hard-coded numbers).\n"
            "4. validate_report_spec until it returns ok:true — fix each "
            "path-scoped error, and heed the warnings: a filter or column it "
            "cannot pre-verify will fail at render if it is wrong (render then "
            "returns a clean {ok:false} naming the actual columns — act on it).\n"
            "5. render_report_spec to produce the HTML artifact and its "
            "manifest.\n"
            "6. verify_manifest on that manifest and report the verdict. "
            "Only 'reproduces' means the numbers were re-run and matched; say "
            "so honestly if anything is unverifiable."
        )

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
