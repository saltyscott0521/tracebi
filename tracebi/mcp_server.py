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
exist to gate it. The draft tools write under ``drafts/``, and
``publish_draft`` copies a validated draft into the library (report packages
and declarative models only, never Python). The source tools read only the
tables a person allowed agents to read; ``propose_transform`` stores SQL as a
code request, which runs only once an admin approves it, and
``export_table`` (admin) writes a warehouse table out to a connection or a
prefix.

Two layers, on purpose:

* module-level ``gateway_*`` functions — plain Python, fully testable with
  no MCP dependency installed
* :func:`build_server` — a thin registration of those functions as MCP
  tools, the only place the optional ``mcp`` package is imported

Run it with ``tracebi mcp`` (stdio, for a local agent) or
``tracebi mcp --transport http --port 8765`` (for a remote one).
"""

import base64
import functools
import hmac
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional, TypedDict

from tracebi import _gateway_log
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


def _caller() -> tuple[str, Optional[str]]:
    """``(actor, role)`` behind the tool call being served.

    With per-person sign-in the verified token names the person (their
    identity provider login) and the role their groups map to; everyone else
    (stdio, the static token) is the configured ``TRACEBI_MCP_ACTOR`` with no
    role claim. Claims come only from this process's own token verifier.
    """
    claims: dict = {}
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
        token = get_access_token()
        claims = (token.claims or {}) if token is not None else {}
    except ImportError:  # the optional mcp package is absent
        pass
    return (claims.get("tracebi_actor")
            or f"mcp:{os.environ.get('TRACEBI_MCP_ACTOR', 'agent')}",
            claims.get("tracebi_role"))


def _caller_groups() -> tuple:
    """The sign-in groups behind the tool call being served (see :func:`_caller`)."""
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token
        token = get_access_token()
        return tuple((token.claims or {}).get("tracebi_groups") or ()) if token else ()
    except ImportError:
        return ()


def _mcp_actor() -> str:
    """The identity recorded against this gateway's work."""
    return _caller()[0]


def _acting():
    """The audit actor scope for one gateway operation: the person, with role."""
    who, role = _caller()
    return actor(who, role=role, groups=_caller_groups())


#: Tools that write (an artifact, pins.json, a draft) or publish. A viewer
#: reads and computes; these are refused for that role. Tests check this set
#: against the tools' own readOnlyHint, so a new write tool cannot be forgotten.
_WRITE_TOOLS = frozenset({
    "render_report_spec", "resolve_pin", "build_report", "start_draft",
    "write_draft_file", "preview_draft", "publish_draft", "decide_publish_request",
    "propose_transform", "export_table",
})

#: Write tools only an admin calls (or a caller with no sign-in role, who
#: acts as admin everywhere): they write outside the workspace's own files.
_ADMIN_TOOLS = frozenset({"export_table"})


def _models_dir() -> Path:
    return Path(os.environ.get("TRACEBI_MODELS_DIR", "models"))


class _LoadedModels(dict):
    """Models keyed by name, plus the files that failed to load.

    A dict so every caller that already treats the return as a mapping
    keeps working. ``skipped`` is what ``list_models`` shows an agent.
    """

    def __init__(self, models: dict, skipped: list):
        super().__init__(models)
        self.skipped = skipped


def _one_line_error(exc: BaseException) -> str:
    """Exception type plus the first line of its message. Not a traceback."""
    message = str(exc).splitlines()[0] if str(exc) else ""
    line = f"{type(exc).__name__}: {message}"
    return line.rstrip(": ") if not message else line


def _model_file(directory: Path, stem: str) -> str:
    ext = "json" if (directory / f"{stem}.json").is_file() else "py"
    return f"{directory.name}/{stem}.{ext}"


def _load_models() -> _LoadedModels:
    """Every project model, keyed both by ``model.name`` and file stem.

    A file that fails to load is not dropped. It is recorded under
    ``skipped`` as ``{"file", "error"}`` — one line, exception type plus
    message — so the others still load and the agent can see what it broke.
    """
    from tracebi import model_registry

    models: dict = {}
    skipped: list = []
    seen: set[str] = set()
    d = _models_dir()
    if d.is_dir():
        for stem in model_registry.auto_discover(str(d)):
            seen.add(stem)
            try:
                m = model_registry.get_model(stem)
            except Exception as exc:  # noqa: BLE001 — a broken file shouldn't hide the others
                skipped.append({
                    "file": _model_file(d, stem),
                    "error": _one_line_error(exc),
                })
                continue
            models[m.name] = m
            models.setdefault(stem, m)
    # Explicitly registered models (tests, notebooks) participate too.
    for name in model_registry.list_models():
        if name in models or name in seen:
            continue
        try:
            models[name] = model_registry.get_model(name)
        except Exception as exc:  # noqa: BLE001
            path = model_registry.model_path(name)
            skipped.append({
                "file": _model_file(Path(path).parent, Path(path).stem) if path else name,
                "error": _one_line_error(exc),
            })
    return _LoadedModels(models, skipped)


def _skipped_error(models, name: str) -> Optional[str]:
    """The load error for *name*, if that file failed and is not loaded."""
    for item in getattr(models, "skipped", ()):
        file = item.get("file", "")
        if name == file or name == Path(file).stem:
            return item.get("error")
    return None


def _get_model(name: str):
    models = _load_models()
    if name not in models:
        failed = _skipped_error(models, name)
        if failed:
            raise KeyError(failed)
        raise KeyError(
            f"Model '{name}' not found. Available: {sorted(set(models))}"
        )
    return models[name]


def _json_rows(df, limit: int) -> list[dict]:
    """First *limit* rows as JSON-safe dicts (numpy scalars and dates included)."""
    return json.loads(df.head(limit).to_json(orient="records", date_format="iso"))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "report"


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
_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_PDF_MEDIA_TYPE = "application/pdf"
# fetch_artifact returns text for these; .xlsx and .pdf are base64 because
# neither is text. Every other suffix stays refused.
_FETCH_TEXT_TYPES = {".html": "text/html", ".json": "application/json"}
_XLSX_NOTE = (
    "The spreadsheet carries no trace and is not verifiable. "
    "The checkable artifact is the HTML at output_path and its manifest "
    "at manifest_path."
)
_PDF_NOTE = (
    "The PDF is a print of the built HTML. Its last pages, \"How these "
    "numbers were made\", print each figure's query in one line and a short "
    "fingerprint, the sink contracts, the build time and git SHA, and the "
    "tracebi verify command; the PDF itself is not verifiable. The checkable "
    "artifact is the HTML at output_path and its manifest at manifest_path."
)


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
    if not resolved.is_file() or _belongs_to_hidden_report(resolved):
        return None, f"no file at {path!r}"
    return resolved, None


_ARTIFACT_SUFFIXES = (".manifest.json", ".json", ".html", ".xlsx", ".pdf")


def _belongs_to_hidden_report(file: Path) -> bool:
    """Is *file* a report's source or build (``<out>/<name>.html`` and its
    manifest, workbook or PDF, or a file inside ``reports/<name>/``) of a
    report in a folder the caller cannot view? Built outputs inherit the
    folder's permissions; this is the check for the fetch tools, which read
    by path."""
    from tracebi.permissions import can
    from tracebi.report_paths import report_name_error
    from tracebi.web.discovery import discovery_report

    stem = file.as_posix()
    for suffix in _ARTIFACT_SUFFIXES:        # pack.html.manifest.json -> pack
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    for entry in discovery_report():
        name = entry.get("module")
        if (isinstance(name, str) and report_name_error(name) is None
                and not can("view", name)
                and (stem.endswith("/" + name) or f"/{name}/" in file.as_posix())):
            return True
    return False


#: The authoring SOP, served as the ``tracebi://guide`` resource. An agent
#: reaching TraceBi only over MCP never sees AGENTS.md or the repo docs, so the
#: essential rules have to live on the surface itself.
_AUTHORING_GUIDE = """\
# Working with the TraceBi gateway

TraceBi is a trust layer for AI-generated analytics: every number you put in
front of a person should carry a trace. This gateway is how you produce one.

## The loop
1. **get_context** — first call. Returns the whole vocabulary: models, facts,
   dimensions, named measures, the `presentation` block (the `data-tb-*`
   figure grammar, tokens, formats) and `transform_contracts`. Nothing
   outside it validates. A lesson body is the resource
   `tracebi://knowledge/{slug}` (the index is `analyst_knowledge.lessons`).
2. **query_model** — ask star-schema questions. Every result is *stamped*: the
   resolved query, the lineage chain, and a SHA-256 fingerprint of the full
   result. Cite the fingerprint with any number you quote. The response's
   `binding` object is the value of `data.<name>` in report.json — paste
   it there under a name you choose. "Top N" is
   `order_by` + `limit` in the query — declarative, in the trace.
3. **author the report** — the report form is an ARTIFACT PACKAGE
   (`reports/<name>/`): `report.json` names query bindings; `template.html`
   is your page, where every figure claims a binding via
   `data-tb-figure` + `data-tb-binding` (or is honestly
   `data-tb-unverified` — no third state). Any element works, including a
   `<span>` inside a sentence: bind prose numbers instead of typing them.
   Blocks marked `data-tb-stage="exploration"` die at build. Interactive
   objects are declarative too: `data-tb-filter` recomputes every figure it
   reaches by re-running its query on the page (a figure's number is only
   ever a query result), `data-tb-search` narrows the rows shown,
   tables scroll past `data-tb-rows`, `data-tb-download` exports the
   stamped CSV verbatim, tabs via `data-tb-tab`, layouts via
   `.tb-cols-2/3`; every built page carries the trace drawer. Details
   in get_context's `presentation` block.
   (A JSON ReportSpec is the same thing as a serialization — read
   `tracebi://spec-schema`, then **validate_report_spec** →
   **render_report_spec**, which refuses invalid specs. Heed validate's
   warnings, not just its errors: a filter/column it cannot pre-verify fails
   at render if it is wrong — render returns a clean `{ok:false}` to act on.)
4. **workbench_state** — while iterating under `tracebi dev`, read this
   before every editing pass: the human steers by leaving notes (and pins)
   in the app, and they come first. Its `pointing` is what the
   human is pointing at right now: when they say "this" or "here", that is
   the figure (`id`, `binding`, `cell`) or the element (`selector`, `text`,
   `section`) they mean. After you act on a pin, call
   **resolve_pin** with a one-line note. It moves that pin into the
   resolved list in pins.json and writes nothing else.
5. **build_report** — the publish step: builds the package to a
   self-contained HTML + manifest, validating every figure claim. Writes
   only its own artifact and manifest. `format="xlsx"` also writes
   `<name>.xlsx` beside them. The spreadsheet carries no trace and is
   not verifiable; the HTML and manifest are the checkable artifact.
   `format="pdf"` also writes `<name>.pdf`: a print of that built HTML,
   which carries no trace.
6. **fetch_artifact** — build/render return a server-side PATH, not bytes.
   The argument is `path`. `build_report` returns `output_path` (the HTML)
   and `manifest_path`; `render_report_spec` returns `html_path` and
   `manifest_path`. Pass one of those as `fetch_artifact(path=...)`. An
   xlsx build also returns `xlsx_path`, and a pdf build returns `pdf_path`
   — pass either as `fetch_artifact(path=...)`. HTML and JSON come back as
   text; an `.xlsx` or `.pdf` comes back base64-encoded with its media type.
7. **verify_manifest** — the argument is `manifest`. Pass `build_report`'s
   `manifest_path` as `verify_manifest(manifest=...)` (or
   `render_report_spec`'s `manifest_path`). It re-runs the recorded queries
   and classifies each section. Only `reproduces` means a number was
   re-run and matched; a manifest with nothing to check is not a pass.

## The two planes
- **Definition plane (git):** transforms, models, report specs are authored
  and code-reviewed in the repo. A REUSABLE measure belongs here — a reviewed
  edit to the model file, not a workaround in the report layer. But a one-off
  derived number never dead-ends the loop: `query_model` measures accept
  `{expr, agg}` and `{ratio: [num, den]}` alongside declared names, so you can
  compute it in the query itself (and promote it to a declared measure later).
- **Contract plane (this gateway):** you *use* the semantic contract; you do
  not change it here. The gateway is read-and-compute only — it never writes
  the warehouse. `render_report_spec` and `build_report` write only their
  own artifact and manifest. `resolve_pin` writes only the workbench's
  pins.json. The read tools are annotated read-only so a client can see it.

## The rules
- Never quote a number without its fingerprint.
- Never hard-code a figure a query could produce.
- Always verify before you claim done: `build_report(report=...)`, then
  pass that result's `manifest_path` as `verify_manifest(manifest=...)`,
  and read the verdict. "Built" is not "verified" — only a `reproduces`
  verdict earns the word.
- If something can't be verified, say so — an honest "unverifiable" beats a
  green badge on unchecked work.
- The trust machinery covers the model boundary onward (the query and the
  report), not the phase-① pandas that built the warehouse. A transform may
  declare a *sink contract* (checks on the tables it lands, recorded beside
  the warehouse); a report manifest's `transform_contracts` block then says
  whether each loaded table's sink satisfied its contract — `satisfied`,
  `stale` (re-sunk since checked; never green), or `no_contract`. That claim
  certifies the sink, never the pandas, and never colors a figure status.

## A worked example
Say get_context showed a fact `fact_orders` with a `revenue` measure and a
`dim_customer.region` dimension. The loop, concretely:

1. Explore — one query, stamped:
   `query_model(model="sales", fact="fact_orders", measures={"revenue":"sum"},
   dimensions=["dim_customer.region"])` → rows + a fingerprint. Need a derived
   number the model hasn't declared? Compute it inline, no model edit:
   `measures={"margin": {"expr": "revenue - cost", "agg": "sum"}}`.

2. Bind — `report.json` is one object. A complete minimal file:

   ```json
   __REPORT_JSON_EXAMPLE__
   ```

   __REPORT_JSON_LIBS_NOTE__ Paste each `query_model` result's `binding`
   object as the value of `data.<name>`.

3. Draw — template.html. Every number claims a binding; the runtime fills the
   `—` placeholder from the stamped bytes, so a hard-coded number is impossible:
   `<span data-tb-figure="value" data-tb-binding="kpis" data-tb-cell="revenue"
   data-tb-format="currency0">—</span>` and
   `<table data-tb-figure="table" data-tb-binding="region"></table>`.
   A value figure needs a one-row binding: its own query with no
   dimensions (the `kpis` binding above), or `order_by` plus `limit` 1.
   The cell may be text, such as the top sector's name.
   A figure declared in `report.json` `figures` (a chart, say) is placed with
   `{{ figure("id") }}` in the template, not hand-written markup; one never
   placed is refused by `preview_draft` and publish.
   A number with no query behind it is honest only as `data-tb-unverified` —
   never a value figure with the number typed in.

4. Publish and check — `build_report(report="sales_by_region")` returns
   `output_path` and `manifest_path`. Pass `manifest_path` as
   `verify_manifest(manifest=...)`. To read the page, pass `output_path`
   as `fetch_artifact(path=...)`. Report the verdict; only `reproduces`
   means re-run and matched.
"""


def authoring_guide() -> str:
    """The ``tracebi://guide`` body, with the package example filled in."""
    from tracebi.capabilities import REPORT_JSON_EXAMPLE, REPORT_JSON_LIBS_NOTE
    return (
        _AUTHORING_GUIDE
        .replace("__REPORT_JSON_EXAMPLE__",
                 json.dumps(REPORT_JSON_EXAMPLE, indent=2))
        .replace("__REPORT_JSON_LIBS_NOTE__", REPORT_JSON_LIBS_NOTE)
    )


# ── Structured output schemas ───────────────────────────────────────────────
# Typed returns so the gateway can advertise an MCP outputSchema and hand the
# agent structured content, not JSON inside a text blob — the stamp and the
# verdict become machine-typed. Plain ``typing`` only: the gateway_* layer must
# stay importable with no ``mcp`` package installed. All ``total=False`` because
# several tools share one dict between a success shape and an
# ``{ok, errors}`` envelope, and the MCP SDK drops any returned key the schema
# does not name — so every key a function can return is listed here.
#
# Every non-Any field is Optional. mcp 2.0 fills each omitted total=False key
# with null; mcp 2.3 omits those NotRequired keys instead. A schema of
# ``{"type": "string", "default": null}`` does not allow that null, and a
# schema-checking client rejects the whole result. Optional makes the
# advertised schema permit null where 2.0 emits it. There is no nested model:
# containers are Any, or
# list/dict of str whose values the tools actually return as strings (a null
# inside one of those would still fail, and none of the returns produce one).


class ContextResult(TypedDict, total=False):
    tracebi_version: Optional[str]
    semantic_model: Any
    report_sections: Any
    dataset_verbs: Any
    number_formats: Any
    conventions: Any
    cheat_sheets: Any
    model: Any  # null or absent unless model= was passed
    presentation: Any
    transform_contracts: Any
    schedule: Any
    warehouse: Any
    pins: Any
    spreadsheet: Any
    pdf: Any
    connect: Any
    analyst_knowledge: Any
    brief: Any  # the omission note; null or absent when brief=false
    house_style: Any  # reports/_style.md {file, text}; null when the workspace has none
    topic: Any  # the section's name, when topic= was passed (that section alone)
    errors: Optional[list[str]]


class ModelsResult(TypedDict, total=False):
    models: Optional[dict[str, Any]]
    skipped: Optional[list[dict[str, str]]]


class DescribeTableResult(TypedDict, total=False):
    ok: Optional[bool]
    error: Optional[str]
    connectors: Optional[list[dict[str, Any]]]
    columns: Optional[list[dict[str, Any]]]


class ModelInfoResult(TypedDict, total=False):
    error: Optional[str]
    name: Optional[str]
    label: Optional[str]
    description: Optional[str]
    synonyms: Optional[list[str]]
    questions: Optional[list[str]]
    tables: Any
    relationships: Any
    facts: Any
    dimensions: Any
    measures: Any
    connectors: Any
    filter_operators: Any
    draftable: bool
    draft_note: Optional[str]


class QueryResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    model: Optional[str]
    query: Optional[dict[str, Any]]
    columns: Optional[list[str]]
    row_count: Optional[int]
    rows: Optional[list[dict[str, Any]]]
    rows_returned: Optional[int]
    truncated: Optional[bool]
    fingerprint: Optional[str]
    lineage: Any
    actor: Optional[str]
    binding: Optional[dict[str, Any]]
    order_by_note: Optional[str]


class ValidateResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    warnings: Optional[list[str]]


class RenderResult(TypedDict, total=False):
    ok: Optional[bool]
    html_path: Optional[str]
    manifest_path: Optional[str]
    report_name: Optional[str]
    sections: Optional[int]
    dataset_fingerprints: Optional[list[str]]
    warnings: Optional[list[str]]
    errors: Optional[list[str]]


class FetchArtifactResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    path: Optional[str]
    content_type: Optional[str]
    bytes: Optional[int]
    content: Optional[str]
    encoding: Optional[str]


class ReportsResult(TypedDict, total=False):
    reports: Any


class ResolvePinResult(TypedDict, total=False):
    ok: Optional[bool]
    pin_id: Optional[str]
    resolved_note: Optional[str]
    resolved_by: Optional[str]
    errors: Optional[list[str]]


class WorkbenchStateResult(TypedDict, total=False):
    # Package shape (report given) and discovery shape (no report) share
    # this one result type — total=False keeps both valid.
    mode: Optional[str]
    name: Optional[str]
    figures: Any
    coverage: Any
    bindings: Any
    unused_bindings: Any
    lint: Any
    exhibits: Any
    pointing: Any
    pins: Any
    resolved: Any
    resolved_count: Optional[int]
    code: Any
    warehouse: Any
    models: Any
    packages: Any
    error: Any
    errors: Optional[list[str]]


class BuildReportResult(TypedDict, total=False):
    ok: Optional[bool]
    report: Optional[str]
    output_path: Optional[str]
    manifest_path: Optional[str]
    figures: Any
    embedded_fingerprints: Optional[list[str]]
    transform_contracts: Any
    xlsx_path: Optional[str]
    spreadsheet_note: Optional[str]
    pdf_path: Optional[str]
    pdf_note: Optional[str]
    note: Optional[str]
    errors: Optional[list[str]]


class VerifyResult(TypedDict, total=False):
    ok: Optional[bool]
    verdict: Optional[str]
    verdict_detail: Optional[str]
    exit_code: Optional[int]
    report_name: Optional[str]
    schema_version: Any
    python_derived: Any
    sections: Any
    summary: Any
    errors: Optional[list[str]]


# ── Gateway operations ─────────────────────────────────────────────────────


def gateway_context(model: Optional[str] = None,
                    brief: bool = False, topic: str = "") -> ContextResult:
    """
    The semantic contract: TraceBi's vocabulary, optionally plus one
    model's schema. This is the first call an agent should make — every
    fact, dimension, measure and section it may reference is in here, and
    nothing outside it will validate.

    ``brief=True`` is the token-lean tier (at most 45% of the payload): the
    semantic model, contracts, conventions and drafts. It names what it
    leaves out as topics; ``topic=<name>`` returns that one section
    (``presentation``, the page grammar, before writing a page).
    """
    from tracebi.capabilities import describe

    from tracebi.reports.stack import project_house_style

    if topic:
        try:
            return describe(topic=topic)
        except ValueError as exc:
            return {"errors": [str(exc)]}
    payload = describe(brief=brief)
    payload["house_style"] = project_house_style()
    if model:
        from tracebi.capabilities import describe_model
        payload["model"] = describe_model(_get_model(model), brief=brief)
    return payload


def _connector_key(connector) -> tuple:
    described = connector.describe()
    kind = described.get("type")
    if kind == "DuckDBConnector":
        db = described.get("database") or ""
        if isinstance(db, str) and db and db != ":memory:":
            return ("duckdb", os.path.abspath(db))
        return ("duckdb-memory", id(connector))
    if kind == "SQLConnector":
        return ("sql", described.get("url") or id(connector))
    return (kind, getattr(connector, "name", ""), id(connector))


def _warehouse_connectors() -> list:
    """Connectors declared on loaded models, plus ``data/warehouse.duckdb``
    when that file exists and no model already points at it."""
    found: list = []
    seen: set[tuple] = set()
    seen_models: set[int] = set()
    for model in _load_models().values():
        if id(model) in seen_models:
            continue
        seen_models.add(id(model))
        try:
            declared = model.connectors()
        except Exception:  # noqa: BLE001 — a broken model is already in skipped
            continue
        for connector in declared:
            key = _connector_key(connector)
            if key in seen:
                continue
            seen.add(key)
            found.append(connector)
    default = Path("data") / "warehouse.duckdb"
    if default.is_file():
        key = ("duckdb", str(default.resolve()))
        if key not in seen:
            from tracebi.connectors.duckdb_connector import DuckDBConnector
            found.append(DuckDBConnector("warehouse", database=str(default)))
    return found


def _connector_error(connector, exc: BaseException) -> dict:
    """One connector's failure, in the listing shape. Not a traceback."""
    return {
        "name": connector.name,
        "type": type(connector).__name__,
        "error": _one_line_error(exc),
    }


def _columns_from(connector, table: str) -> Optional[dict]:
    """Where each column of a warehouse table comes from, as the certificate
    of the SQL transform that wrote it records DuckDB's parse
    (``tracebi.contracts.columns_from``); None for anything else."""
    from tracebi.contracts import columns_from, read_contracts

    try:
        wh = getattr(connector, "warehouse", None)
        target = wh.sink if wh is not None else connector.describe().get("database")
        return columns_from(read_contracts(target), table) if target else None
    except Exception:  # noqa: BLE001 — no certificate to read is no lineage, never an error
        return None


def gateway_describe_table(table: str = "", connector: str = "") -> DescribeTableResult:
    """Column names and types from connector metadata. Never returns rows.

    With no *table*, list each connector's tables. With *table*, describe
    that table's columns. *connector* limits both to one connector name.

    A connector that raises is reported in place (``name``, ``type``,
    ``error`` — exception type plus the first message line) and the others
    still list. One unreachable warehouse does not fail the call.
    """
    connectors = _warehouse_connectors()
    if connector:
        connectors = [c for c in connectors if c.name == connector]
        if not connectors:
            return {"ok": False, "error": f"Connector '{connector}' not found."}
    if not table:
        listed = []
        for c in connectors:
            try:
                tables = c.list_tables()
            except Exception as exc:  # noqa: BLE001 — one warehouse must not hide the rest
                listed.append(_connector_error(c, exc))
                continue
            listed.append({
                "name": c.name,
                "type": type(c).__name__,
                "tables": tables,
            })
        return {"ok": True, "connectors": listed}
    matches = []
    failed = []
    for c in connectors:
        try:
            names = c.list_tables()
        except Exception as exc:  # noqa: BLE001 — one warehouse must not hide the rest
            failed.append(_connector_error(c, exc))
            continue
        # None means this connector cannot list a catalog. Do not probe
        # column_schema: a miss there raises, and a hit would still be a guess.
        if names is None or table not in names:
            continue
        try:
            schema = c.column_schema(table)
        except Exception as exc:  # noqa: BLE001 — one warehouse must not hide the rest
            failed.append(_connector_error(c, exc))
            continue
        if schema is None:
            continue
        match = {
            "connector": c.name,
            "table": table,
            "columns": schema,
        }
        lineage = _columns_from(c, table)
        if lineage:
            match["columns_from"] = lineage
        matches.append(match)
    if not matches:
        out: DescribeTableResult = {
            "ok": False,
            "error": f"Table '{table}' not found.",
        }
        if failed:
            out["connectors"] = failed
        return out
    out = {"ok": True, "columns": matches}
    if failed:
        out["connectors"] = failed
    return out


def _draft_fields(names) -> dict:
    """``draftable`` and, when false, ``draft_note``: the same decision
    start_draft makes (drafts.model_draft_status), over every name a model
    answers to, so the listing and the refusal cannot disagree."""
    from tracebi import drafts

    statuses = [drafts.model_draft_status(n) for n in names]
    if any(ok for ok, _ in statuses):
        return {"draftable": True}
    return {"draftable": False, "draft_note": statuses[0][1]}


def gateway_models() -> ModelsResult:
    """
    Models this workspace exposes, with table/fact/dimension counts.

    The registry indexes each model under both its file stem and its
    ``.name``; listing both as separate models made an agent's world look
    twice its size, so aliases are collapsed to one entry with every name
    that resolves to it.
    """
    loaded = _load_models()
    by_id: dict[int, tuple[Any, list[str]]] = {}
    for name, m in loaded.items():
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
            "label": info.get("label"),
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
            **_draft_fields(names),
        }
    return {"models": out, "skipped": list(getattr(loaded, "skipped", []))}


def gateway_model_info(model: str) -> ModelInfoResult:
    """One model's full schema — tables, relationships, facts, dimensions, measures.

    A file that failed to load returns that error instead of "not found".
    """
    loaded = _load_models()
    failed = _skipped_error(loaded, model)
    if failed and model not in loaded:
        return {"error": failed}
    m = _get_model(model)
    from tracebi.capabilities import describe_model
    return {**describe_model(m), **_draft_fields([model, getattr(m, "name", model)])}


_BINDING_QUERY_KEYS = (
    "fact", "measures", "dimensions", "filters", "having",
    "order_by", "limit", "aggregate", "allow_fanout", "allow_rate_agg",
)


def _binding_stub(model: str, stamped: dict) -> dict:
    """The value of one ``report.json`` ``data.<name>`` entry.

    Paste the returned object under ``data.<name>``. The response key is
    ``binding``; ``report.json`` stores it under ``data``. It is the
    resolved query, not a transcription of the rows.
    """
    query = {}
    for key in _BINDING_QUERY_KEYS:
        if key not in stamped:
            continue
        value = stamped[key]
        if value is None or value == [] or value == {}:
            continue
        query[key] = value
    query["fact"] = stamped.get("fact")
    if "measures" in stamped:
        query["measures"] = stamped["measures"]
    return {"model": model, "query": query}


def _query(
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
    from tracebi.model.engine import statement_timeout

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
        # An agent's query stops at the project's statement timeout
        # (tracebi.yaml engine.query_timeout_s); the error names the limit.
        with _acting(), statement_timeout():
            ds = m.execute(spec)
    except Exception as exc:  # noqa: BLE001 — a bad fact/dim/filter is data
        return {"ok": False, "errors": [str(exc)]}
    df = ds.to_pandas()
    # Echo the STAMPED resolved spec (fully resolved ordering included), so
    # what the agent cites is what replay compares against. The extra
    # tie-break keys stay in that spec: stripping them would make the
    # paste-ready binding disagree with the receipt verify re-runs.
    stamped = spec.to_dict()
    for node in ds.lineage_to_dict():
        qs = (node.get("metadata") or {}).get("query_spec")
        if qs:
            stamped = qs
    result: QueryResult = {
        "ok": True,
        "model": model,
        "query": stamped,
        "binding": _binding_stub(model, stamped),
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
    resolved_order = stamped.get("order_by") or []
    if len(resolved_order) > len(spec.order_by):
        result["order_by_note"] = (
            "The gateway appends the remaining result columns, dimension "
            "columns first, as ascending tie-breakers so the order is "
            "deterministic. They were not in the order_by you passed. The "
            "trace records them so a replay matches; paste binding as-is."
        )
    return result


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
    result = _query(model, fact, measures, dimensions, filters, having,
                    aggregate, allow_fanout, order_by, limit, preview_rows,
                    include_lineage)
    if result.get("ok"):
        q = result["query"]
        by = ", ".join(q.get("dimensions") or [])
        _show_action("query_model",
                     f"Queried {model}: {', '.join(map(str, q.get('measures') or []))}"
                     + (f" by {by}" if by else ""),
                     frame={"columns": result["columns"],
                            "shape": [result["row_count"], len(result["columns"])],
                            "rows": result["rows"][:50]})
    return result


gateway_query.__doc__ = _query.__doc__


def _project_relative(path: str) -> str:
    """*path* relative to the project when it is inside it, as the feed shows it."""
    rel = os.path.relpath(path, os.getcwd())
    return path if rel.startswith(os.pardir) else rel


def _show_action(tool: str, text: str, frame: Optional[dict] = None) -> None:
    """Show the person with the app open what the agent just did."""
    from tracebi.workbench import post_agent_action
    post_agent_action(tool, text, frame)


def gateway_validate_spec(spec: Any) -> ValidateResult:
    """
    Check a report spec against the workspace's models without loading a row.

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


def _render_spec(spec: Any, output_dir: str = "output") -> RenderResult:
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

        with _acting():
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


def gateway_render_spec(spec: Any, output_dir: str = "output") -> RenderResult:
    result = _render_spec(spec, output_dir)
    if result.get("ok"):
        _show_action("render_report_spec",
                     f"Rendered {result['report_name']} → "
                     f"{_project_relative(result['html_path'])}")
    else:
        _show_action("render_report_spec",
                     "Render refused: " + "; ".join(map(str, result.get("errors") or [])))
    return result


gateway_render_spec.__doc__ = _render_spec.__doc__


def gateway_reports() -> ReportsResult:
    """Reports the workspace exposes, from the discovery report."""
    from tracebi.permissions import can
    from tracebi.report_paths import report_name_error
    from tracebi.web.discovery import discovery_report

    # A folder the caller cannot see is not listed (hidden reads as absent).
    return {"reports": [
        e for e in discovery_report()
        if not (isinstance(e.get("module"), str)
                and report_name_error(e["module"]) is None
                and not can("view", e["module"]))]}


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
    report-level ``verdict`` with a human-readable ``verdict_detail``.
    ``ok`` is False for a drifted or unexplained manifest, and for one with
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
        if not p.is_file() or _belongs_to_hidden_report(p.resolve()):
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
        with _acting():
            return verify_manifest(manifest, load_models())
    except Exception as exc:  # noqa: BLE001 — corrupt receipts are data, not crashes
        return {"ok": False, "errors": [
            f"manifest could not be verified: {type(exc).__name__}: {exc}"
        ]}


def gateway_workbench_state(report: str = "") -> WorkbenchStateResult:
    """
    The workbench state for an artifact package: figures with provenance,
    the coverage bar, per-binding cards, the human's PINS, and the exhibit
    feed — the same state the app's Build panel and the classic workbench
    page render from (v2 §2.5).

    With no *report* (or ``"_discovery"``): the DISCOVERY session's state
    instead — warehouse tables and sink-contract summaries, every model's
    declared star schema, the report packages that exist, and the
    ``_discovery`` exhibit feed and pins (``tracebi dev`` with no name).

    Read-only: this is how a driving agent sees what the human flagged in
    the portal ("steer from chat, see results in the workbench" — pointing
    happens where the evidence is). Exhibits and pins are dev-state only;
    nothing here mints a trace.
    """
    from tracebi.workbench import DISCOVERY_NAME, collect_discovery_state, collect_state

    if not report or report == DISCOVERY_NAME:
        with _acting():
            return collect_discovery_state(os.getcwd(), _load_models())
    # A caller-supplied name must never become a path: without this,
    # report='/etc/x' or '../../x' would escape reports/ and collect_state
    # would read — and execute report.py from — an attacker-chosen directory.
    from tracebi.report_paths import open_report
    opened = open_report(report, purpose="view")
    if opened.name_error:
        return {"errors": [opened.name_error]}
    if opened.package_dir is None:
        return {"errors": [
            f"no artifact package at {opened.path} — workbench_state applies to "
            f"reports/<name>/ packages"
        ]}
    with _acting():
        return collect_state(str(opened.package_dir), _load_models())


def gateway_resolve_pin(report: str, pin_id: str, note: str = "") -> ResolvePinResult:
    """Move one open pin into the resolved list.

    Writes only the workbench's ``pins.json`` — never the report and never
    the warehouse. ``resolved_by`` is the current audit actor (the MCP
    actor, inside this call). An unknown id is an error, not a delete.
    """
    from tracebi.workbench import DISCOVERY_NAME, resolve_pin, workbench_dir

    if not pin_id:
        return {"ok": False, "errors": ["missing pin id"]}
    if not report or report == DISCOVERY_NAME:
        name = DISCOVERY_NAME
    else:
        from tracebi.report_paths import open_report
        opened = open_report(report, purpose="manage")
        if opened.name_error:
            return {"ok": False, "errors": [opened.name_error]}
        if opened.package_dir is None:
            return {"ok": False, "errors": [
                f"no artifact package at {opened.path} — resolve_pin applies to "
                f"reports/<name>/ packages"
            ]}
        name = report
    wb = os.environ.get("TRACEBI_WORKBENCH_DIR") or workbench_dir(os.getcwd(), name)
    try:
        with _acting():
            moved = resolve_pin(wb, pin_id, note=note)
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)]}
    return {
        "ok": True,
        "pin_id": pin_id,
        "resolved_note": moved.get("resolved_note") or "",
        "resolved_by": moved.get("resolved_by") or "",
    }


def _build_report(
    report: str, output_dir: str = "output", format: str = "html",
) -> BuildReportResult:
    """
    Build an artifact package to one self-contained ``.html`` + manifest —
    the gateway's PUBLISH step for the package lane.

    This is the ``tracebi report build`` gate over MCP: exploration blocks
    are stripped, every figure claim is validated against the embedded
    bindings, and the manifest (schema 2: figures + the
    ``transform_contracts`` join) is written beside the page. Like
    ``render_report_spec``, it writes only its own artifact and manifest —
    never source data. The dev loop itself (``tracebi dev``, snapshots,
    pins) stays on the CLI, where the human's portal lives; this tool is
    how an MCP-driving agent finishes.

    ``format="xlsx"`` also writes ``<name>.xlsx`` in the same confined
    directory, via the library's :class:`ExcelRenderer` (the web download
    path, ``save_manifest=False``). A spreadsheet cannot carry a trace:
    the result says so and points at the HTML and manifest, which remain
    the checkable artifact.

    ``format="pdf"`` also writes ``<name>.pdf``: a print of the built HTML
    (headless Chromium) whose appendix says how each number was made; it
    is not verifiable, and ``pdf_note`` points at the HTML and manifest.
    """
    from tracebi.reports.template_package import TemplatePackage

    if format not in ("html", "xlsx", "pdf"):
        return {"ok": False, "errors": [
            f"format must be 'html', 'xlsx', or 'pdf', not {format!r}"
        ]}
    # The name is a directory under reports/ (a folder path at most), and
    # can never climb out of it.
    from tracebi.report_paths import open_report
    opened = open_report(report, purpose="build")
    if opened.name_error:
        return {"ok": False, "errors": [opened.name_error]}
    if not (opened.package_dir is not None and opened.has_template):
        return {"ok": False, "errors": [
            f"no artifact package at {opened.path} — build_report applies to "
            f"reports/<name>/ packages (a .json spec renders via "
            f"render_report_spec)"
        ]}
    out_dir, out_err = _confined_output_dir(output_dir)
    if out_err:
        return {"ok": False, "errors": [out_err]}
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{report}.html"          # keeps the report's folders
    xlsx = out_dir / f"{report}.xlsx"
    pdf = out_dir / f"{report}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _acting():
            package = TemplatePackage(str(opened.package_dir))
            models = _load_models()
            manifest = package.render(models, str(output))
            if format == "xlsx":
                # The carrier Report holds one table per binding — the same
                # object the web Excel download renders. A second resolve:
                # render() does not hand the carrier back.
                from tracebi.reports.excel_renderer import ExcelRenderer
                carrier, _stamped = package.build(models)
                ExcelRenderer().render(carrier, str(xlsx), save_manifest=False)
            elif format == "pdf":
                from tracebi.reports.pdf import print_pdf
                print_pdf(str(output), str(pdf))
    except Exception as exc:  # noqa: BLE001 — a refused build is a result
        return {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
    m = manifest.to_dict()
    result: BuildReportResult = {
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
    if format == "xlsx":
        result["xlsx_path"] = str(xlsx)
        result["spreadsheet_note"] = _XLSX_NOTE
    if format == "pdf":
        result["pdf_path"] = str(pdf)
        result["pdf_note"] = _PDF_NOTE
    from tracebi.state import try_record_report_build
    note = try_record_report_build(
        report, str(output),
        manifest_path=str(output) + ".manifest.json",
        cover=manifest.cover,
    )
    if note:
        result["note"] = f"report build was not recorded: {note}"
    return result


def gateway_build_report(
    report: str, output_dir: str = "output", format: str = "html",
) -> BuildReportResult:
    result = _build_report(report, output_dir, format)
    if result.get("ok"):
        _show_action("build_report",
                     f"Built {report} → {_project_relative(result['output_path'])}")
    else:
        _show_action("build_report", f"Build of {report} refused: "
                     + "; ".join(map(str, result.get("errors") or [])))
    return result


gateway_build_report.__doc__ = _build_report.__doc__


def gateway_fetch_artifact(path: str) -> FetchArtifactResult:
    """Read back a rendered artifact (or its manifest).

    ``render_report_spec`` and ``build_report`` return a server-side PATH; a
    remote agent driving the gateway over MCP needs the BYTES to deliver the
    report or hand the manifest to ``verify_manifest``. The argument is
    ``path``. Pass ``build_report``'s ``output_path`` or ``manifest_path``,
    ``render_report_spec``'s ``html_path`` or ``manifest_path``,
    ``build_report``'s ``xlsx_path``, or the ``pdf_path`` a pdf build
    returns (``build_report(..., format="pdf")``). Read-only and hard
    path-guarded: the file must sit under the working directory (or
    ``$TRACEBI_OUTPUT_ROOT``), never inside the installed package, and be one of
    the ``.html`` / ``.json`` / ``.xlsx`` / ``.pdf`` artifacts those tools write — never
    arbitrary server files. HTML and JSON come back as text. A workbook or
    PDF is not text, so ``.xlsx`` and ``.pdf`` come back base64-encoded
    (``encoding="base64"``) with their media type. Over ``_FETCH_MAX_BYTES``
    it refuses and names the path.
    """
    resolved, err = _confined_read_path(path)
    if err:
        return {"ok": False, "errors": [err]}
    suffix = resolved.suffix.lower()
    if suffix not in _FETCH_TEXT_TYPES and suffix not in (".xlsx", ".pdf"):
        return {"ok": False, "errors": [
            "fetch_artifact reads only rendered .html, .json, .xlsx, and .pdf "
            f"artifacts, not {suffix!r}"]}
    size = resolved.stat().st_size
    if size > _FETCH_MAX_BYTES:
        return {"ok": False, "errors": [
            f"artifact is {size} bytes, over the {_FETCH_MAX_BYTES}-byte fetch "
            f"cap; read it from {path!r} on the server directly"]}
    try:
        if suffix == ".xlsx":
            content = base64.b64encode(resolved.read_bytes()).decode("ascii")
            encoding = "base64"
            ctype = _XLSX_MEDIA_TYPE
        elif suffix == ".pdf":
            content = base64.b64encode(resolved.read_bytes()).decode("ascii")
            encoding = "base64"
            ctype = _PDF_MEDIA_TYPE
        else:
            content = resolved.read_text(encoding="utf-8")
            encoding = ""
            ctype = _FETCH_TEXT_TYPES[suffix]
    except (OSError, UnicodeDecodeError) as exc:
        return {"ok": False, "errors": [f"could not read {path!r}: {exc}"]}
    result: FetchArtifactResult = {
        "ok": True, "path": path, "content_type": ctype,
        "bytes": size, "content": content,
    }
    if encoding:
        result["encoding"] = encoding
    return result


# ── MCP registration ───────────────────────────────────────────────────────


class DraftResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    drafts: Optional[list[dict]]
    owner: Optional[str]
    kind: Optional[str]
    path: Optional[str]
    url: Optional[str]
    files: Any
    updated: Optional[str]
    differs_from_published: Optional[bool]
    impact: Optional[dict]
    version: Optional[str]
    previous: Optional[str]
    note: Optional[str]
    status: Optional[str]
    request: Optional[dict]
    requests: Optional[list[dict]]


def _draft_owner() -> str:
    """The acting principal as a draft owner: the MCP actor, ``mcp:`` dropped."""
    from tracebi.drafts import slug_owner
    return slug_owner(_mcp_actor().removeprefix("mcp:"))


def _draft_call(fn, *args, **kwargs) -> DraftResult:
    """Run one draft operation as the MCP actor; a refusal is a result."""
    from tracebi.drafts import DraftError
    try:
        with _acting():
            return {"ok": True, **fn(*args, **kwargs)}
    except DraftError as exc:
        impact = getattr(exc, "impact", None)    # a refused publish carries what it would change
        return {"ok": False, "errors": [str(exc)], **({"impact": impact} if impact else {})}


def gateway_list_drafts() -> DraftResult:
    from tracebi import drafts
    return _draft_call(lambda: {"drafts": [
        {**d, "url": drafts.draft_url(d["owner"], d["kind"], d["path"])}
        for d in drafts.list_drafts(_draft_owner())]})


def gateway_start_draft(kind: str, path: str,
                        from_published: Optional[bool] = None, theme: str = "") -> DraftResult:
    from tracebi import drafts
    owner = _draft_owner()
    return _draft_call(lambda: {
        **drafts.start_draft(owner, kind, path, from_published, theme or None),
        "url": drafts.draft_url(owner, kind, path)})


def gateway_read_draft(kind: str, path: str) -> DraftResult:
    from tracebi import drafts
    return _draft_call(drafts.read_draft, _draft_owner(), kind, path)


def gateway_write_draft_file(kind: str, path: str, file: str,
                             content: str) -> DraftResult:
    from tracebi import drafts
    return _draft_call(drafts.write_draft_file, _draft_owner(), kind, path,
                       file, content)


def gateway_preview_draft(kind: str, path: str) -> DraftResult:
    from tracebi import drafts

    def preview():
        owner = _draft_owner()
        drafts.render_preview(owner, kind, path)
        return {"url": drafts.draft_url(owner, kind, path)}
    try:
        return _draft_call(preview)
    except Exception as exc:  # noqa: BLE001 — a package that will not render is a result
        return {"ok": False, "errors": [_one_line_error(exc)]}


def gateway_model_impact(path: str) -> DraftResult:
    from tracebi import drafts
    return _draft_call(lambda: {"impact": drafts.model_impact(
        _draft_owner(), path, _load_models())})


def gateway_publish_draft(kind: str, path: str, note: str = "",
                          accept_impact: bool = False, folder: str = "") -> DraftResult:
    from tracebi import drafts
    result = _draft_call(lambda: drafts.publish_draft(
        _draft_owner(), kind, path, _mcp_actor(), note or None, _load_models(),
        accept_impact, folder or None))
    _show_action("publish_draft", (
        f"Publish of {kind}/{path} refused: " + "; ".join(result["errors"])
        if not result.get("ok") else
        f"Asked to publish {kind}/{path} (waiting for approval)"
        if result["status"] == "requested" else f"Published {kind}/{path}"))
    return result


def gateway_list_publish_requests(status: str = "") -> DraftResult:
    from tracebi import drafts
    return _draft_call(lambda: {"requests": drafts.list_requests(status or None)})


def gateway_decide_publish_request(request_id: str, approve: bool,
                                   note: str = "") -> DraftResult:
    from tracebi import drafts
    result = _draft_call(lambda: drafts.decide_request(
        request_id, approve, _mcp_actor(), note or None, _load_models()))
    _show_action("decide_publish_request", (
        f"Request {request_id} {result['status']}" if result.get("ok") else
        f"Request {request_id} not decided: " + "; ".join(result["errors"])))
    return result


# ── Sources an agent may read, and what it may propose ───────────────────
#
# A person sets up a connection in the app and ticks which of its tables
# agents may read (``agents:`` in connections/<name>.yaml). These tools see
# only those, and a table outside the list answers exactly as a missing one
# does: the gateway never confirms what it may not show. Reads go through the
# table API's own code (tracebi/web/api/routers/tables.py), never new SQL.
# What an agent makes of them is a proposal: a transform stored as a code
# request, which runs only once an admin approves it.

class ProjectResult(TypedDict, total=False):
    summary: Optional[dict]
    nodes: Optional[list[dict]]
    edges: Optional[list[list[str]]]
    edge_facts: Optional[list[dict]]


def gateway_describe_project() -> ProjectResult:
    """The workspace as one graph, as the app's map draws it (``GET
    /api/graph``): every source, transform, warehouse table, model and
    report, the facts that wire them, and what an agent may read of each."""
    import sys

    from tracebi.graph import project_graph
    from tracebi.registry import registry

    if "tracebi.web.api.main" not in sys.modules:
        # No web app in this process (the stdio gateway), so no live
        # discovery fills the registry: bring it in line with the project on
        # disk, as the server's own scan does.
        from tracebi.connections import connections_dir
        from tracebi.web.discovery import rescan_library

        rescan_library(str(_models_dir()), os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"),
                       str(connections_dir()))
    graph = project_graph(registry)
    # What only the app's map draws (its lane, chip, subtitle, page) is left
    # out; every fact the map shows is in the rest.
    graph["nodes"] = [{k: v for k, v in n.items() if k not in _MAP_ONLY}
                      for n in graph["nodes"]]
    return graph


#: Node fields only the app's map uses; ``describe_project`` leaves them out.
_MAP_ONLY = frozenset({"lane", "chip", "sub", "open"})


class SourcesResult(TypedDict, total=False):
    ok: Optional[bool]
    error: Optional[str]
    errors: Optional[list[str]]
    reason: Optional[str]
    variable: Optional[str]
    note: Optional[str]
    connections: Optional[list[dict]]
    skipped: Optional[list[dict]]
    connection: Optional[str]
    table: Optional[str]
    tables: Optional[list[dict]]
    columns: Optional[list[dict]]
    sample: Optional[list[dict]]
    total: Optional[int]
    total_exact: Optional[bool]
    profile: Optional[dict]


class ProposeResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    request_id: Optional[str]
    status: Optional[str]
    files: Optional[list[str]]
    review_url: Optional[str]
    dry_run: Optional[dict]
    note: Optional[str]


class ExportResult(TypedDict, total=False):
    ok: Optional[bool]
    errors: Optional[list[str]]
    source: Optional[str]
    table: Optional[str]
    to: Optional[str]
    rows: Optional[int]
    written: Optional[str]
    run_id: Optional[int]


def _agent_may_read(connection, table: str) -> bool:
    """The one allowlist check, :func:`tracebi.connections.agent_may_read`
    (*connection* a connector or a connection's name). Imported at call time;
    a build without it lets agents read nothing."""
    try:
        from tracebi.connections import agent_may_read
    except ImportError:
        return False
    try:
        return bool(agent_may_read(connection, table))
    except Exception:  # noqa: BLE001 — a connection that will not load opens nothing
        return False


def _connections() -> "tuple[dict, list]":
    """``({name: (type, connector)}, skipped)`` for every
    ``connections/<name>.yaml``. Loading resolves no credential."""
    from tracebi.connections import (
        SUFFIXES, connections_dir, load_connection, read_connection_doc,
    )

    found: dict = {}
    skipped: list = []
    d = connections_dir()
    for path in sorted(d.iterdir()) if d.is_dir() else []:
        if path.suffix not in SUFFIXES:
            continue
        try:
            found[path.stem] = (read_connection_doc(path)["type"], load_connection(path))
        except Exception as exc:  # noqa: BLE001 — a broken file must not hide the others
            skipped.append({"file": f"{d.name}/{path.name}", "error": _one_line_error(exc)})
    return found, skipped


def _allowlist(connector) -> Any:
    """What a connection lets agents read: ``"*"``, a list of names, or []."""
    tables = getattr(connector, "agent_tables", None) or []
    return "*" if list(tables) == ["*"] else list(tables)


def gateway_list_connections() -> SourcesResult:
    """Every declared connection, its type, and the tables agents may read."""
    found, skipped = _connections()
    listed = []
    for name, (ctype, connector) in found.items():
        entry = {"name": name, "type": ctype, "agent_tables": _allowlist(connector)}
        if getattr(connector, "label", None):
            entry["label"] = connector.label
        listed.append(entry)
    out: SourcesResult = {"ok": True, "connections": listed, "skipped": skipped}
    if not any(c["agent_tables"] for c in listed):
        out["note"] = ("No connection lets agents read a table yet. A person ticks "
                       "the tables agents may read on the Sources page of the app.")
    return out


def gateway_list_source_tables(connection: str) -> SourcesResult:
    """The tables of *connection* agents may read, with row estimates and columns."""
    from tracebi.sources import connection_tables

    found, _ = _connections()
    if connection not in found:
        return {"ok": False, "error": f"Connection '{connection}' not found."}
    connector = found[connection][1]
    if not _allowlist(connector):
        return {"ok": True, "connection": connection, "tables": [],
                "note": "Agents may read none of this connection's tables."}
    listing = connection_tables(connector)
    if not listing.get("connected"):
        return {"ok": False, "connection": connection,
                **{k: listing[k] for k in ("reason", "variable") if listing.get(k)}}
    return {"ok": True, "connection": connection,
            "tables": [t for t in listing.get("tables") or []
                       if _agent_may_read(connector, t["name"])]}


def gateway_describe_source_table(connection: str, table: str,
                                  sample: int = 20) -> SourcesResult:
    """One allowlisted source table: columns, a profile, and *sample* rows."""
    from tracebi.web.api.routers.tables import (
        NotConnected, NotInCatalog, Unsupported, open_table, profile_table, read_rows,
    )

    missing: SourcesResult = {
        "ok": False, "error": f"Table '{table}' not found in connection '{connection}'."}
    found, _ = _connections()
    if connection not in found or not _agent_may_read(found[connection][1], table):
        return missing
    limit = max(0, min(int(sample), _ROW_HARD_CAP))
    try:
        with open_table(found[connection][1], table) as reader:
            page = read_rows(reader, limit=limit)
            profile = profile_table(reader)
    except NotInCatalog:
        return missing
    except NotConnected as exc:
        return {"ok": False, "connection": connection, **exc.answer}
    except Unsupported as exc:
        return {"ok": False, "error": f"A {exc} source is not read here."}
    names = [c["name"] for c in page["columns"]]
    return {"ok": True, "connection": connection, "table": table,
            "columns": page["columns"],
            "sample": [dict(zip(names, row)) for row in page["rows"]],
            "total": page["total"], "total_exact": page["total_exact"],
            "profile": profile}


class TransformResult(TypedDict, total=False):
    ok: Optional[bool]
    error: Optional[str]
    name: Optional[str]
    form: Optional[str]
    file: Optional[str]
    text: Optional[str]
    contract_file: Optional[str]
    contract_yaml: Optional[str]
    tables: Optional[list[str]]
    last_run: Optional[dict]
    lineage: Optional[dict]
    change: Optional[str]


def _certificate_record(name: str) -> Optional[dict]:
    """The latest sink-certificate record a transform's checks wrote, or None."""
    from tracebi.contracts import read_contracts
    from tracebi.project_config import sink_target
    from tracebi.sources import _contract_owners

    try:
        certs = (read_contracts(sink_target()) or {}).get("transforms") or {}
    except Exception:  # noqa: BLE001 — an unreadable warehouse config records nothing
        return None
    records = [certs[r] for r, owner in _contract_owners().items() if owner == name and r in certs]
    return max(records, key=lambda r: r.get("checked_at") or "", default=None)


def gateway_read_transform(name: str) -> TransformResult:
    """A transform's code and what its last run recorded; never a row."""
    from tracebi import code_requests, transforms

    missing: TransformResult = {"ok": False, "error": f"Transform '{name}' not found in transforms/."}
    if not isinstance(name, str) or not code_requests.is_code_path(f"transforms/{name}.sql"):
        return missing
    try:
        path = transforms.find_transform(name)
    except transforms.TransformError as exc:
        return {"ok": False, "error": str(exc)}
    if path is None or path.stem != name or path.suffix not in transforms.FORMS:
        return missing
    form = transforms.transform_form(path)
    beside = transforms.contract_file(path)
    text = path.read_text(encoding="utf-8")
    blocked = transforms.sources_agents_may_not_read(text) if form == "sql" else []
    rec = _certificate_record(name) or {}
    lineage = rec.get("lineage")
    tables = (sorted(lineage) if lineage else
              sorted({c["table"] for c in rec.get("checks") or []}
                     | {v["name"] for v in rec.get("views") or []}))
    last_run = None
    if rec:
        last_run = {"at": rec.get("checked_at"), "checks": len(rec.get("checks") or []),
                    "sources": [{
                        "ref": ref, "connection": src.get("connection"), "table": src.get("table"),
                        "method": src.get("method"), "rows": src.get("rows"),
                        "fingerprint": src.get("fingerprint"), "loaded_at": src.get("loaded_at"),
                        "snapshot": src.get("fallback") if src.get("source_fallback") else None,
                    } for ref, src in (rec.get("sources") or {}).items()]}
    return {
        "ok": True, "name": name, "form": form, "file": f"transforms/{path.name}",
        "text": text,
        "contract_file": f"transforms/{beside.name}" if beside else None,
        "contract_yaml": beside.read_text(encoding="utf-8") if beside else None,
        "tables": tables, "last_run": last_run, "lineage": lineage,
        "change": (f"propose_transform(name={name!r}, sql, contract_yaml, note, change=true)"
                   if form == "sql" and not blocked else
                   f"not proposable while it reads a table agents may not read "
                   f"({'; '.join(blocked)}): a person ticks it on the Sources page "
                   f"(agents: in connections/<name>.yaml) first"
                   if form == "sql" else
                   f"a {form} transform is changed by a person from a laptop with tracebi "
                   f"push; an agent proposes SQL only"),
    }


def _models_reading(tables: set) -> list[tuple[str, str]]:
    """``[(model, table)]`` for each loaded model that reads one of *tables*
    (lower-case names) from a warehouse."""
    from tracebi.sources import is_warehouse

    found: list[tuple[str, str]] = []
    seen: set[int] = set()
    for model in _load_models().values():
        if id(model) in seen:
            continue
        seen.add(id(model))
        try:
            connectors = {c.name: c for c in model.connectors()}
        except Exception:  # noqa: BLE001 — a model that will not load is in skipped
            continue
        try:
            declared = model.info().get("tables") or []
        except Exception:  # noqa: BLE001 — a model that will not describe itself is in skipped
            declared = []
        finally:
            # Describing opened the warehouse read-only; let go, or the
            # approval's run (here or in the server) cannot write it.
            for c in connectors.values():
                if hasattr(c, "disconnect"):
                    c.disconnect()
        for t in declared:
            conn = connectors.get(t.get("connector"))
            if (conn is not None and is_warehouse(conn.describe())
                    and str(t.get("source", "")).lower() in tables):
                found.append((model.name, t["source"]))
    return sorted(set(found))


def _change_errors(name: str, sql: str) -> list[str]:
    """Why *sql* cannot replace ``transforms/<name>``: it is not there, it is
    not SQL, or it stops writing a table a model reads today."""
    from tracebi import transforms

    try:
        path = transforms.find_transform(name)
    except transforms.TransformError as exc:
        return [str(exc)]
    if path is None:
        return [f"name: transforms/{name} does not exist; propose it as a new transform "
                f"(change=false)"]
    form = transforms.transform_form(path)
    if form != "sql":
        return [f"name: transforms/{path.name} is a {form} transform. An agent proposes SQL "
                f"only; a person changes a {form} transform from a laptop with tracebi push"]
    today = transforms.sink_names(path.read_text(encoding="utf-8"))
    today |= {t.lower() for t in ((_certificate_record(name) or {}).get("lineage") or {})}
    dropped = today - transforms.sink_names(sql)
    return [f"transforms/{name}.sql: the change no longer writes {table}, which model "
            f"{model} reads. Keep writing it, or change the model first as a draft "
            f"(start_draft(kind='models', path={model!r}, from_published=true)) and propose "
            f"this once it is published"
            for model, table in _models_reading(dropped)]


def _proposal_errors(name: str, sql: str, contract_yaml: str,
                     change: bool = False) -> list[str]:
    """Why a proposed transform cannot be stored, checked before anything is:
    the SQL parses in DuckDB (when it does not, that error is the only one),
    the name is a new stem (or, for a change, an existing SQL transform whose
    change keeps every table a model reads), every
    ``-- source:`` is a table agents may read, and the contract file declares
    checks in the closed vocabulary."""
    import tempfile

    import duckdb

    from tracebi import code_requests, transforms
    from tracebi.contracts import ContractSpecError, read_contract_file

    if not isinstance(name, str) or not code_requests.is_code_path(f"transforms/{name}.sql"):
        return [f"name: {name!r} is not a transform name (letters, digits, _ and -; "
                f"no suffix)"]
    where = f"transforms/{name}.sql"
    # The SQL itself first: text that does not parse is the one thing to fix,
    # and nothing read from it (what it no longer writes) would be true.
    errors = []
    try:
        directives = transforms.source_directives(sql, where)
        text = transforms.render_sql(sql, os.getcwd(), where)
    except transforms.TransformError as exc:
        return [str(exc)]
    con = duckdb.connect(":memory:")
    try:
        parsed = json.loads(con.execute("SELECT json_serialize_sql(?)", [text]).fetchone()[0])
        statements = duckdb.extract_statements(text) if parsed.get("error_type") != "parser" else None
    finally:
        con.close()
    if statements is None:
        return [f"{where}: does not parse: {parsed.get('error_message')}"]
    if not statements:
        return [f"{where}: holds no statement; end by creating the tables it sinks"]
    if change:
        errors += _change_errors(name, sql)
        if errors and errors[0].startswith("name:"):
            return errors
    else:
        try:
            exists = transforms.find_transform(name) is not None
        except transforms.TransformError:
            exists = True
        if exists or (transforms.transforms_dir() / f"{name}.contract.yaml").exists():
            errors.append(f"name: transforms/{name} already exists; propose a new name, or "
                          f"pass change=true to propose a change to it (read_transform "
                          f"shows it)")
    for src in directives:
        if not _agent_may_read(src["connection"], src["table"]):
            errors.append(f"-- source: {src['ref']}: there is no table {src['ref']} among "
                          f"those agents may read (list_source_tables("
                          f"{src['connection']!r}) lists them)")
    contract_where = f"transforms/{name}.contract.yaml"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.contract.yaml"
        path.write_text(contract_yaml if isinstance(contract_yaml, str) else "", encoding="utf-8")
        try:
            spec = read_contract_file(path, name)
        except ContractSpecError as exc:
            errors.append(str(exc).replace(str(path), contract_where))
        else:
            if not spec["checks"]:
                errors.append(f"{contract_where}: declare at least one check (rows, unique, "
                              f"not_null, foreign_key, values, reconcile) on a table it sinks")
    return errors


def gateway_propose_transform(name: str, sql: str, contract_yaml: str,
                              note: str, change: bool = False) -> ProposeResult:
    """Store ``transforms/<name>.sql`` and its contract as a code request
    (*change*: a change to the existing SQL transform of that name), then
    dry-run it once against a throwaway copy (:mod:`tracebi.dryrun`)."""
    from tracebi import code_requests, dryrun
    from tracebi.drafts import DraftError

    errors = _proposal_errors(name, sql, contract_yaml, change=bool(change))
    if not errors:
        files = {f"transforms/{name}.sql": sql,
                 f"transforms/{name}.contract.yaml": contract_yaml}
        try:
            with _acting():
                req = code_requests.create_request(files, note, _mcp_actor())
        except DraftError as exc:
            errors = [str(exc)]
    if errors:
        _show_action("propose_transform", f"Transform {name} not proposed: " + "; ".join(errors))
        return {"ok": False, "errors": errors}
    result = dryrun.run(sql, contract_yaml, name, dryrun.dryrun_dir(req["id"]))
    code_requests.record_dry_run(req["id"], result)
    what = "a change to transform" if change else "transform"
    _show_action("propose_transform", f"Proposed {what} {name} (waiting for an admin). "
                                      f"{result['summary']}")
    if result["ok"]:
        from tracebi.transforms import sink_names
        readers = sorted({m for m, _ in _models_reading(sink_names(sql))})
        draft = (" or ".join(f"start_draft(kind='models', path={m!r}, from_published=true)"
                             for m in readers) if readers else "start_draft(kind='models', path=<a new model name>)")
        said = ("Its dry run passed against a throwaway copy; nothing real was written. An "
                "admin reviews the diff and the dry run in the app and, on approval, the "
                "files go into transforms/ and the transform runs once. Tell the person it "
                "waits for that; then draft the model over the tables it sinks "
                f"({draft}).")
    else:
        said = ("Stored, but its dry run did not pass, so it cannot be approved. Read "
                "dry_run.error and dry_run.checks, fix the SQL or the contract, and propose "
                "again" + (" with change=true" if change else "") + "; the newer proposal is "
                "the one to approve.")
    return {"ok": True, "request_id": req["id"], "status": req["status"],
            "files": sorted(files), "review_url": code_requests.review_url(),
            "dry_run": result, "note": said}


def gateway_export_table(source: str, table: str, to: str) -> ExportResult:
    """Write a warehouse table or view to a connection or an object prefix."""
    from tracebi.exports import ExportError, export_table
    from tracebi.sources import is_warehouse

    connector = next((c for c in _warehouse_connectors()
                      if c.name == source and is_warehouse(c.describe())), None)
    if connector is None:
        return {"ok": False, "errors": [f"No warehouse '{source}'."]}
    try:
        with _acting():
            done = export_table(connector, table, to)
    except ExportError as exc:
        return {"ok": False, "errors": [str(exc)]}
    _show_action("export_table", f"Exported {source}.{table} to {to} ({done['rows']} rows)")
    return {"ok": True, **done}


def build_server(token: Optional[str] = None, oauth=None):
    """
    Register the gateway operations as MCP tools.

    With *token*, the streamable-http transport requires
    ``Authorization: Bearer <token>`` on every request (401 otherwise),
    via the SDK's own ``token_verifier`` hook; stdio ignores it. With
    *oauth* (a ``tracebi.mcp_oauth.GatewayOAuth``) every request needs a
    TraceBi access token for a signed-in person, and *token*, if also given,
    stays accepted for automation (as ``TRACEBI_MCP_ACTOR``, role analyst).

    The only place the optional ``mcp`` package is imported, per the
    fail-loudly rule for optional dependencies.
    """
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
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
    # render is the one tool that writes an artifact — but only its own
    # artifact + receipt, never source data, so destructiveHint is false.
    # Re-rendering the same spec reproduces the same output, so it is
    # idempotent. resolve_pin is the other write: pins.json only.
    _RENDER = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                              idempotentHint=True, openWorldHint=True)
    _WRITE_PINS = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                  idempotentHint=False, openWorldHint=False)

    auth_kwargs: dict[str, Any] = {}
    if oauth is not None:
        auth_kwargs = {
            "token_verifier": oauth.verifier(
                StaticTokenVerifier(token) if token else None),
            "auth": oauth.auth_settings(),
        }
    elif token is not None:
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
            "the data-tb-* figure grammar) and nothing outside it will "
            "validate. Query with query_model; every response is stamped "
            "with the resolved query and a fingerprint of the full result — "
            "cite the fingerprint when you quote a number, and paste the "
            "result's binding object as the value of data.<name> in "
            "report.json instead of transcribing numbers. A report is a "
            "package, reports/<name>/: report.json "
            "names the bindings, template.html claims them with "
            "data-tb-figure + data-tb-binding. build_report(report=...) "
            "publishes it and returns output_path and manifest_path; pass "
            "manifest_path as verify_manifest(manifest=...) and output_path "
            "as fetch_artifact(path=...). render_report_spec returns "
            "html_path and manifest_path — pass that manifest_path the same "
            "way. Only 'reproduces' means the numbers matched. Column names "
            "come from describe_table. Lessons are get_context's "
            "analyst_knowledge.lessons; a lesson body is the "
            "tracebi://knowledge/{slug} resource. A file that failed to load is under "
            "list_models (skipped) or list_reports. Under "
            "tracebi dev, read workbench_state first — the "
            "person's pins come before anything else — and resolve_pin each "
            "one you act on. Without file access, or for a fixed layout, a "
            "JSON ReportSpec is the simpler lane: validate_report_spec, then "
            "render_report_spec. Resources: tracebi://guide (how to author), "
            "tracebi://spec-schema, tracebi://models/{name}, "
            "tracebi://knowledge/{slug}. Prompts: "
            "author_report, answer_question, address_pins. To author a "
            "report or declarative model remotely: start_draft, "
            "write_draft_file, preview_draft (give the person its url), "
            "then publish_draft once they agree. With no model yet, start "
            "from the data: describe_project (the whole workspace as a "
            "graph), read_transform for a transform that exists, "
            "list_connections, list_source_tables, describe_source_table, "
            "then propose_transform (new, or change=true for an existing SQL "
            "transform): it is dry-run against a throwaway copy, so read "
            "dry_run and re-propose until it passes; an admin approves it "
            "and it runs once) before drafting the model."
        ),
    )

    # Every tool registers through here, so the opt-in call log
    # (TRACEBI_MCP_LOG=1) wraps them all in one place. The log stays inside:
    # it records the original exception. Outside it, a plain exception becomes
    # a ToolError whose one-line message reaches the client. On current mcp a
    # plain exception is masked to "Error executing tool <name>".
    def _tool(**kwargs):
        def register(fn):
            @functools.wraps(fn)
            def guarded(*args, **kw):
                if kwargs["name"] in _WRITE_TOOLS and _caller()[1] == "viewer":
                    raise PermissionError(
                        f"your role (viewer) may read and query but not call "
                        f"{kwargs['name']}, which writes. Ask an admin to map "
                        f"your group to analyst.")
                role = _caller()[1]
                if kwargs["name"] in _ADMIN_TOOLS and role not in (None, "admin"):
                    raise PermissionError(
                        f"your role ({role}) may not call {kwargs['name']}; "
                        f"only an admin may. Ask one to do it in the app.")
                # The person's name, role and groups, for the folder check in
                # open_report and for everything the tool records.
                with _acting():
                    return fn(*args, **kw)

            logged = _gateway_log.logged(kwargs["name"], guarded, _mcp_actor)

            @functools.wraps(logged)
            def visible(*args, **kw):
                try:
                    return logged(*args, **kw)
                except Exception as exc:  # noqa: BLE001 — the client must see why
                    raise ToolError(_one_line_error(exc)) from exc

            return server.tool(**kwargs)(visible)
        return register

    # Tools. structured_output=True advertises each return's JSON Schema and
    # hands the agent structuredContent, not JSON-in-text — the stamp and the
    # verdict arrive machine-typed.
    _tool(
        name="get_context", title="Semantic contract", annotations=_READ,
        structured_output=True,
        description=(
            "TraceBi's semantic contract: every model, section type, chart "
            "type, DataSet verb, measure kind and filter operator. Pass "
            "model=<name> to include that model's tables, dimensions and "
            "named measures; model is null or absent unless you pass it. "
            "Call this first — start with brief=true, the lean tier for "
            "discovering, querying and drafting. brief=true leaves out the "
            "sections its brief.omitted names (null or absent here); fetch "
            "one with get_context(topic=<name>), which returns that section "
            "alone — topic='presentation' (the data-tb-* figure grammar, the "
            "kit, report.json) before you write a page. brief=false returns "
            "everything, and its brief field is null or absent. house_style is the workspace's "
            "reports/_style.md (null when there is none): the team's design "
            "rules — follow them over the defaults when you build a page."
        ),
    )(gateway_context)
    _tool(
        name="list_models", title="List models", annotations=_READ,
        structured_output=True,
        description=(
            "Models this workspace exposes, with facts, dimensions and measures. "
            "draftable says whether start_draft can copy it remotely: a "
            "declarative .yaml/.yml/.json model can, a Python model cannot "
            "(draft_note gives the reason). A model that failed to load is "
            "listed under skipped with its error; fix the file and call again "
            "(models reload when the file changes)."
        ),
    )(gateway_models)
    _tool(
        name="describe_table", title="Describe a warehouse table",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "Column names and types of a warehouse table, from connector "
            "metadata. Pass table to describe one table; omit it to list "
            "tables. connector limits the lookup to one connector name. "
            "Never returns rows. A connector that raises is reported in "
            "place (name, type, error: exception type plus the first "
            "message line); the others still list. Use this before writing "
            "a model or an ad-hoc measure, instead of learning column "
            "names from errors."
        ),
    )(gateway_describe_table)
    _tool(
        name="describe_model", title="Describe a model", annotations=_READ,
        structured_output=True,
        description=(
            "One model's full schema: tables, relationships, facts, dimensions, "
            "named measures, the semantic layer's words (description and "
            "synonyms on the model, dimensions, attribute_info and measures; "
            "questions: example questions it answers), and draftable (with draft_note when false: a "
            "Python model is edited from a laptop). A name that failed to load "
            "returns that error instead of not found."
        ),
    )(gateway_model_info)
    _tool(
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
            "limit (requires order_by) keeps the top N. When order_by is "
            "set, the resolved query and binding also list ascending "
            "tie-breakers on the remaining result columns (dimensions "
            "first) so the order is deterministic; order_by_note says so. "
            "preview_rows caps "
            "only the transport. Returns rows plus a stamp: the resolved "
            "query, lineage chain, and a fingerprint of the full result. "
            "Quote the fingerprint with any number you cite. The "
            "response includes binding: paste that object as the value of "
            "data.<name> in report.json (the response key is binding; the "
            "report.json key is data). Do not transcribe the number into "
            "HTML. Pass "
            "include_lineage=false while exploring to drop the lineage chain "
            "(the fingerprint and resolved query still let you cite and "
            "re-verify) for lighter responses."
        ),
    )(gateway_query)
    _tool(
        name="validate_report_spec", title="Validate a report spec",
        annotations=_READ, structured_output=True,
        description=(
            "Check a report spec (JSON) against the workspace's models without "
            "loading any data. Errors carry a path like "
            "sections[0].data.query.fact — fix and retry. Warnings marked "
            "'design —' flag layout mistakes (unsorted bars, too many KPIs or "
            "columns, oversized pies) and name the lesson to read; they never "
            "block, but fix them before calling the report done."
        ),
    )(gateway_validate_spec)
    _tool(
        name="render_report_spec", title="Render a report (writes an artifact)",
        annotations=_RENDER, structured_output=True,
        description=(
            "Validate, build and render a report spec to a self-contained "
            "HTML artifact plus a lineage manifest written beside it. "
            "Refuses invalid specs."
        ),
    )(gateway_render_spec)
    _tool(
        name="list_reports", title="List reports", annotations=_READ,
        structured_output=True,
        description=("Reports the workspace exposes, with registration status per file. A "
                     "report is named by its path; its first segment is its project (a "
                     "top-level library folder, named for the model it reads)."),
    )(gateway_reports)
    _tool(
        name="workbench_state", title="Workbench state", annotations=_READ_WAREHOUSE,
        structured_output=True,
        description=(
            "The workbench state for an artifact package (reports/<name>/): "
            "figures with provenance, coverage, per-binding cards, the "
            "human's pins, the exhibit feed, and `pointing`: what the human "
            "is pointing at right now (when they say \"this\", that is it). "
            "Read this to see what the human flagged in the app before "
            "your next edit. It also "
            "serves the discovery session: call with no report while the "
            "human runs tracebi dev with no name, and it returns the "
            "workspace-level state instead — warehouse tables, sink-contract "
            "summaries, models, packages, and the workspace feed (your "
            "show() exhibits) and the human's notes."
        ),
    )(gateway_workbench_state)
    _tool(
        name="resolve_pin", title="Resolve a workbench pin (writes pins.json)",
        annotations=_WRITE_PINS, structured_output=True,
        description=(
            "Move one open pin into the resolved list in the workbench's "
            "pins.json. The pin is kept, with resolved_at, resolved_by "
            "(the current actor) and the note. Nothing is deleted, and "
            "nothing but pins.json is written — not the report, not the "
            "warehouse. An unknown id is an error. workbench_state then "
            "lists open pins only."
        ),
    )(gateway_resolve_pin)
    _tool(
        name="build_report", title="Build an artifact package (writes the artifact)",
        annotations=_RENDER, structured_output=True,
        description=(
            "Build an artifact package (reports/<name>/) to one "
            "self-contained HTML + its manifest — the publish step. The "
            "argument is report (the package name). Returns output_path "
            "(the HTML) and manifest_path. Pass manifest_path as "
            "verify_manifest(manifest=...) and output_path as "
            "fetch_artifact(path=...). Strips exploration blocks, validates "
            "every figure claim against the embedded bindings, and returns "
            "the figure records, embedded fingerprints, and the "
            "transform_contracts join. Writes only its own artifact and "
            "manifest. format='xlsx' also writes <name>.xlsx and returns "
            "xlsx_path; pass that as fetch_artifact(path=...). The "
            "spreadsheet carries no trace and is not verifiable; the HTML "
            "and manifest are the checkable artifact (see spreadsheet_note). "
            "format='pdf' also writes <name>.pdf and returns pdf_path; pass "
            "that as fetch_artifact(path=...). The PDF is a print of the "
            "built HTML; its appendix prints each figure's query and fingerprint, "
            "but it is not verifiable (see pdf_note)."
        ),
    )(gateway_build_report)
    _tool(
        name="fetch_artifact", title="Fetch a rendered artifact",
        annotations=_READ, structured_output=True,
        description=(
            "Read back the bytes of an artifact a render/build tool wrote. "
            "The argument is path. Pass build_report's output_path or "
            "manifest_path, render_report_spec's html_path or "
            "manifest_path, build_report's xlsx_path, or build_report's "
            "pdf_path. This delivers the actual content so a remote agent "
            "can send the report or hand the manifest to "
            "verify_manifest(manifest=...). HTML and JSON come back as "
            "text. An .xlsx or .pdf comes back base64-encoded "
            "(encoding='base64') with its media type. Read-only, guarded to "
            "the artifact directory. Every other suffix is refused."
        ),
    )(gateway_fetch_artifact)
    _tool(
        name="verify_manifest", title="Verify a manifest",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "Re-run every recorded query in a rendered manifest. The "
            "argument is manifest: a dict, or build_report's manifest_path, "
            "or render_report_spec's manifest_path. Classifies each "
            "section: reproduces, source_drift (an input "
            "fingerprint moved), unexplained (result differs but inputs "
            "match), or unverifiable (no recorded query). Closes the loop "
            "on your own builds. Check the report-level verdict, not "
            "just ok: only 'reproduces' means a number was re-run and "
            "matched, and a manifest with nothing to check is not a pass."
        ),
    )(gateway_verify_manifest)

    # Drafts: the remote-authoring lane. Writes land in drafts/<owner>/ only;
    # publish_draft is the one that changes what the project serves.
    _DRAFT_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                   idempotentHint=True, openWorldHint=False)
    _PUBLISH = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                               idempotentHint=False, openWorldHint=False)
    _tool(
        name="list_drafts", title="List your drafts", annotations=_READ,
        structured_output=True,
        description=(
            "The caller's drafts: kind, path, url, updated, and whether the "
            "draft differs from what is published."
        ),
    )(gateway_list_drafts)
    _tool(
        name="start_draft", title="Start a draft (writes drafts/)",
        annotations=_DRAFT_WRITE, structured_output=True,
        description=(
            "Create a draft: kind is 'reports' (a package: report.json, "
            "template.html, style.css, script.js) or 'models' (one declarative "
            "<name>.yaml, or <name>.json; a new model draft starts as "
            "YAML). path is a report path like finance/weekly, or a "
            "model name [a-z0-9_]+. A path that is published starts as a "
            "copy of the published one (from_published defaults to that; "
            "false starts empty); a published report with a report.py cannot be "
            "drafted remotely. theme (a new report only): ledger, nightdesk or "
            "signal, the house theme; its report.json starts as {\"theme\": …}, "
            "so keep that key when you write report.json. Returns the draft's "
            "url: give it to the person once. Writes only under drafts/."
        ),
    )(gateway_start_draft)
    _tool(
        name="read_draft", title="Read a draft", annotations=_READ,
        structured_output=True,
        description="The draft's files as {name: text}, with its url's path.",
    )(gateway_read_draft)
    _tool(
        name="write_draft_file", title="Write a draft file (writes drafts/)",
        annotations=_DRAFT_WRITE, structured_output=True,
        description=(
            "Replace one file of an existing draft with content (UTF-8 text, "
            "at most 512 KB). file is report.json, template.html, app.jsx, "
            "style.css or script.js for a report (script.js runs only in the "
            "reader's sandboxed browser frame, never on the server); <name>.yaml or <name>.json for a model "
            "(one form at a time: writing the other replaces the draft's "
            "file). Nothing else is accepted. Writes only under drafts/; nothing is published."
        ),
    )(gateway_write_draft_file)
    _tool(
        name="preview_draft", title="Preview a draft", annotations=_READ_WAREHOUSE,
        structured_output=True,
        description=(
            "Render the draft in memory against the workspace's models (no "
            "file, no manifest) and return ok, errors, and the draft's url, "
            "where the person sees it. A model draft is validated, with no "
            "page."
        ),
    )(gateway_preview_draft)
    _tool(
        name="model_impact", title="Impact of a model draft on reports",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "For a model draft (path = the model name): re-run the recorded "
            "queries of every published report that reads that model against "
            "the draft, compared with each report's last build. Returns "
            "impact.reports, each unchanged, moves (figures with old and new "
            "values), breaks (the error) or not_built (listed, never "
            "unchanged), and impact.needs_acceptance. Writes nothing. "
            "publish_draft of a model that moves or breaks reports is "
            "refused until the person has seen this and you pass "
            "accept_impact=true."
        ),
    )(gateway_model_impact)
    _tool(
        name="publish_draft", title="Publish a draft (changes the workspace)",
        annotations=_PUBLISH, structured_output=True,
        description=(
            "Validate the draft (a report must render), keep the version it "
            "replaces under .tracebi/history/, copy the draft into the "
            "library and record a publish run with this actor and the note. "
            "The draft is kept. The person's go-ahead comes first: this "
            "changes what the app serves. A model draft that would move or "
            "break published reports is refused (ok=false, with impact) "
            "unless accept_impact=true; a break needs accepting too, and "
            "the accepted impact is recorded in the publish run. A report "
            "goes to 'folder' (a library path: a project such as saas_model, "
            "or a folder inside one; created if needed; default: the draft's "
            "own path). With only Build on that folder the "
            "result is status='requested' with a request for someone with "
            "Publish there (decide_publish_request); a folder that "
            "accepts only checkable reports refuses one that is not."
        ),
    )(gateway_publish_draft)
    _tool(
        name="list_publish_requests", title="List publish requests",
        annotations=_READ, structured_output=True,
        description=(
            "Requests to publish a draft into a folder: the ones you made, "
            "and those into folders where you hold Publish (yours to "
            "decide). Each has id, owner, path, destination, requested_by, "
            "requested_at, status (pending/approved/rejected) and, once "
            "decided, decided_by and decided_at. status filters."
        ),
    )(gateway_list_publish_requests)
    _tool(
        name="decide_publish_request",
        title="Approve or reject a publish request (changes the workspace)",
        annotations=_PUBLISH, structured_output=True,
        description=(
            "Approve (publishes exactly what was requested, recording who "
            "approved and when) or reject (note required) a pending request. "
            "Needs Publish on the destination folder now; the requester "
            "cannot decide their own unless they hold Publish. The person's "
            "go-ahead comes first."
        ),
    )(gateway_decide_publish_request)

    # Sources: what a person allowed agents to read, a transform proposed from
    # it (a code request an admin approves), and saving a result back out.
    _PROPOSE = ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                               idempotentHint=False, openWorldHint=False)
    _EXPORT = ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                              idempotentHint=True, openWorldHint=True)
    _tool(
        name="describe_project", title="Describe the workspace", annotations=_READ_WAREHOUSE,
        structured_output=True,
        description=(
            "The workspace as a graph: every source, transform, table, model "
            "and report, what feeds what, and what you may read. Call it "
            "first on a workspace you have not seen. nodes carry id (kind:name), "
            "kind, lane (0 sources … 4 reports), label, sub, open (the app "
            "page) and a passport: origin, readers, writers, moved {at, how}, "
            "trust {state, text}, agents {state, text}; gap names a node "
            "wired on one side only. edges are [from, to] ids, facts never "
            "guesses: a transform's file names the source, the sink "
            "certificate names the tables it wrote, a model reads them, a "
            "report's bindings read the model. A source table you may read "
            "has agents.state ok; read it with describe_source_table. A "
            "transform node's agents.tools names the tools that take its name "
            "(read_transform, and propose_transform(change=true) for SQL)."
        ),
    )(gateway_describe_project)
    # The same tool under the workspace's own word: the graph describes the
    # workspace (one tracebi.yaml), and describe_project keeps its name.
    _tool(
        name="describe_workspace", title="Describe the workspace", annotations=_READ_WAREHOUSE,
        structured_output=True,
        description=(
            "The same as describe_project, under the workspace's name: the "
            "workspace as a graph, every source, transform, table, model and "
            "report, what feeds what, and what you may read. Either name "
            "returns the same result."
        ),
    )(gateway_describe_project)
    _tool(
        name="list_connections", title="List connections", annotations=_READ,
        structured_output=True,
        description=(
            "The workspace's connections (connections/<name>.yaml), each with "
            "its type and agent_tables: the tables a person allowed agents to "
            "read ('*' for all, [] for none). Only those can be listed, "
            "described or named in a proposed transform's -- source: line. "
            "A file that does not load is under skipped. Credentials are "
            "never resolved or shown."
        ),
    )(gateway_list_connections)
    _tool(
        name="list_source_tables", title="List a connection's tables",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "The tables of one connection that agents may read, each with "
            "columns ({name, type}) and rows (exact for DuckDB, the catalog's "
            "estimate with rows_exact=false for a database that keeps one, "
            "else null). Other tables are not listed. A connection that "
            "cannot be reached answers ok=false with reason (and variable "
            "when an unset ${VAR} is why)."
        ),
    )(gateway_list_source_tables)
    _tool(
        name="describe_source_table", title="Describe a source table",
        annotations=_READ_WAREHOUSE, structured_output=True,
        description=(
            "One table agents may read: columns, a profile of each (nulls, "
            "distinct, min, max, mean, commonest values) and a sample of "
            "rows (sample, default 20, at most 500), with total. A table "
            "agents may not read is 'not found', as a missing one is. Use "
            "this to write a transform's SQL from real column names."
        ),
    )(gateway_describe_source_table)
    _tool(
        name="propose_transform",
        title="Propose a transform (a code request an admin approves)",
        annotations=_PROPOSE, structured_output=True,
        description=(
            "Propose transforms/<name>.sql and transforms/<name>.contract.yaml "
            "as one code request. sql is DuckDB statements, top to bottom: a "
            "header line -- source: <connection>.<table> per table it reads "
            "(only tables agents may read), then CREATE OR REPLACE TABLE for "
            "each star-schema table it sinks. contract_yaml declares checks "
            "(name, note, checks: - rows: fact_x / at_least: 1 …; the closed "
            "vocabulary rows, unique, not_null, foreign_key, values, "
            "reconcile), at least one. note says why, for the reviewer. "
            "change=true proposes a change to the existing SQL transform of "
            "that name (read_transform it first): the review diffs it against "
            "the published files, and it must keep writing every table a "
            "model reads (else refused, naming the model and table; change "
            "the model first as a draft). A Python transform is not "
            "proposable (a person uses tracebi push). Checked before it is "
            "stored: the name, SQL that parses, allowed sources, a valid "
            "contract. Then it is dry-run once against a throwaway copy: a "
            "scratch DuckDB with the warehouse attached READ_ONLY and the "
            "-- source: tables loaded as the real run loads them, nothing "
            "written anywhere, a -- sink: line not sent. dry_run says per "
            "created table its columns, rows and first 20 rows; per check "
            "passed and failing_rows; the column lineage; elapsed_ms; and "
            "any error with its statement. A proposal whose dry run fails is "
            "stored but cannot be approved: fix it and propose again. An "
            "admin reviews it at review_url and approving runs it once (and "
            "commits it when the workspace is a git repository); until then "
            "its tables do not exist. Then draft the model over them."
        ),
    )(gateway_propose_transform)
    _tool(
        name="read_transform", title="Read a transform", annotations=_READ,
        structured_output=True,
        description=(
            "One transform in transforms/: its file text and its "
            ".contract.yaml (contract_yaml, null when it has none), form "
            "(sql, python or notebook), the tables it writes, last_run (when "
            "its sink last satisfied its contract, and the sources that run "
            "read, each with method scanner|arrow|pandas and snapshot when a "
            "committed snapshot stood in) and lineage (per table and column, "
            "the columns DuckDB's parse proves it is computed from; SQL "
            "only). change says how to change it. A name not in transforms/ "
            "is 'not found'. It reads code, never rows."
        ),
    )(gateway_read_transform)
    _tool(
        name="export_table",
        title="Export a warehouse table (admin; writes outside the workspace)",
        annotations=_EXPORT, structured_output=True,
        description=(
            "Write a warehouse table or view (source: the warehouse's name, "
            "as describe_table lists it; table) to 'to': a connection's name "
            "(the table, replaced there, through its connector) or an object "
            "prefix (s3://bucket/path or a folder inside the workspace; "
            "<prefix>/<table>.parquet). Admin only. Records an export run. "
            "The person's go-ahead comes first."
        ),
    )(gateway_export_table)

    # Resources — reference material a client can pull into context. The guide
    # puts the authoring SOP on the surface itself (an MCP-only agent never
    # sees AGENTS.md); the schema makes the ReportSpec grammar obtainable
    # without a REST call; the template exposes any model as a readable doc.
    server.resource(
        "tracebi://guide", name="TraceBi authoring guide",
        mime_type="text/markdown",
        description="How to work with this gateway: the loop, the two planes, the rules.",
    )(authoring_guide)

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

    @server.resource(
        "tracebi://knowledge/{slug}", name="Analyst lesson",
        mime_type="text/markdown",
        description=(
            "One analyst-knowledge lesson body, the same text as "
            "`tracebi knowledge <slug>`. Slugs are get_context's "
            "analyst_knowledge.lessons."
        ),
    )
    def _knowledge_resource(slug: str) -> str:
        from mcp.shared.exceptions import MCPError
        from mcp.types import INVALID_PARAMS
        from tracebi.knowledge import get_lesson
        lesson = get_lesson(slug)
        if lesson is None:
            raise MCPError(
                INVALID_PARAMS,
                f"No lesson '{slug}'. Lessons are listed in get_context "
                f"under analyst_knowledge.lessons.",
            )
        return f"# {lesson.title}\n\n{lesson.body}\n"

    # Prompts — the authoring SOP and its two neighbours as executable
    # templates.
    @server.prompt(
        name="author_report", title="Author a governed report",
        description=("Walk the full loop — context, query, package (files, or drafts over "
                     "the gateway), build, verify — for a question; with no model yet, "
                     "first explore the allowed sources and propose a transform."),
    )
    def _author_report_prompt(question: str) -> str:
        from tracebi.reports.house import OFFER
        return (
            f"Author a governed TraceBi report that answers: {question}\n\n"
            "Pick the page structure that fits the question instead of "
            "designing one. A page someone reads (once, emailed, printed) "
            "is a report — editorial by default, brief when the answer is "
            "one finding, tabbed when it serves two jobs. A page someone "
            "works in (checked daily, views, drill-downs) is a dashboard. "
            "Ask only if a person is in the loop and the choice is not "
            "obvious. With a shell, `tracebi new-report \"<Name>\" --layout "
            "<recipe>` or `tracebi new-dashboard \"<Name>\"` writes the "
            "skeleton. With only the gateway, write the page yourself "
            "from that recipe's pieces:\n"
            "- editorial — a report to read top to bottom (template.html): "
            "<article class=\"tb-article\">, a .tb-kicker, an <h1> that "
            "states the finding, a .tb-dek, a .tb-byline with data-tb-built, "
            "a bound .tb-lede, prose sections, <figure class=\"tb-figure\"> "
            "with a <figcaption>, a .tb-pullstat, a table, the methodology. "
            "`tracebi new-report \"<Name>\"` (lesson design-editorial-report)\n"
            "- brief — template.html: .tb-lede, a few .tb-kpi cards, one "
            "chart in one .tb-card. `tracebi new-report \"<Name>\" --layout brief`\n"
            "- dashboard — an app.jsx (presentation.app): the title, a KPI "
            "strip with a lead (<Kpi lead>), a <Chart> beside its <Table> "
            "ranking, a filterable detail; navigation if asked. For a page "
            "that must read with JavaScript off (emailed, printed), the "
            "template.html version: brief, then .tb-cols-2-1. "
            "`tracebi new-dashboard \"<Name>\"` (--html for the template)\n"
            "- tabbed — the same header, then .tb-tabs / data-tb-tab "
            "(Overview and Detail). "
            "`tracebi new-report \"<Name>\" --layout tabbed`\n\n"
            "Ask how it should look before you build, once, in one short "
            "message, when a person is in the loop: the title and where it "
            "sits (left, centred, a banner, or at the top of a sidebar); "
            "one page, top tabs or a sidebar; light, dark or the reader's "
            "choice; comfortable or compact. Offer the look of their last "
            "report first and skip what they already said. With nobody in "
            "the loop, use the defaults. The answers are attributes "
            "(presentation.layout.look in get_context): data-tb-mode, "
            "data-tb-density and data-tb-width on <html>, data-tb-nav=\"side\" "
            "on .tb-tabs, and the .tb-title header with data-tb-title and "
            "data-tb-built — or, for an app, report.json \"look\" plus the "
            "app's own navigation and title. The house theme is report.json "
            "\"theme\": ledger, nightdesk or signal (start_draft theme=, "
            "new-report --theme). " + OFFER + " Pick a theme or use the "
            "workspace's brand; never hard-code a colour. "
            "If get_context returns a house_style, it is the "
            "team's rules: follow them over these defaults. Read the lessons "
            "design-dashboard-feel and, for an app, design-app-dashboards.\n\n"
            "If no model answers the question yet, start from the data, "
            "in this order, before the loop below:\n"
            "a. describe_workspace, then read_transform(name) on the "
            "transforms that exist (their SQL, contract and what their last "
            "run read). list_connections, list_source_tables(connection) and "
            "describe_source_table(connection, table) on the tables a person "
            "allowed agents to read. Only those exist for you.\n"
            "b. propose_transform(name, sql, contract_yaml, note): SQL that "
            "reads them through -- source: lines and sinks clean star-schema "
            "tables, with a contract of checks on those tables; change=true "
            "to change an existing SQL transform. Read the dry_run it "
            "returns; while it fails, fix it and propose again.\n"
            "c. Wait for the approval. Tell the person the request id and "
            "its review_url; an admin approves it and it runs once. Its "
            "tables do not exist until then, so do not go on without it.\n"
            "d. start_draft(kind='models', path=<name>): a declarative model "
            "over the sunk tables (describe_table gives their columns); a "
            "model that is published starts from its published copy. "
            "write_draft_file the model file, preview_draft, model_impact(path) "
            "for a model that exists (show the person what moves), then "
            "publish_draft(kind='models', path, note) once the person agrees "
            "(accept_impact=true only after they have seen the impact). "
            "Publish the model before a report that uses it.\n\n"
            "Follow the loop, and do not skip a step:\n"
            "1. Call get_context (start with brief=true; add the model= you'll "
            "use) to learn the exact facts, dimensions and named measures, "
            "then get_context(topic='presentation') for the data-tb-* figure "
            "grammar before you write a page. Nothing outside that vocabulary "
            "will validate. A measure the question needs and the model lacks "
            "is a model draft (step d), published first.\n"
            "2. Use query_model to explore the numbers. Every result is "
            "stamped — keep the fingerprints for anything you cite — and "
            "carries a binding object.\n"
            "3. Write the package: paste each binding "
            "object as the value of data.<name> in report.json, and in "
            "template.html give every "
            "number an element with data-tb-figure + data-tb-binding (or "
            "mark it data-tb-unverified) — in an app.jsx, show it through "
            "the tracebi kit (<Kpi>, <Value>, <Chart>, <Table>) with literal "
            "binding/cell. Never type a number a query produced. Two routes "
            "to the same package:\n"
            "   - with the workspace's files (a laptop, tracebi dev): write "
            "reports/<project>/<name>/ yourself;\n"
            "   - with only the gateway: start_draft(kind='reports', "
            "path='<project>/<name>') (a published path starts from its "
            "published copy), write_draft_file(kind='reports', path, "
            "'report.json', ...) and write_draft_file(..., 'template.html' "
            "or 'app.jsx', ...), preview_draft(kind='reports', path) until "
            "ok:true and give the person its url, then "
            "publish_draft(kind='reports', path, note) once they agree.\n"
            "4. build_report(report=<the package's path>) to publish the "
            "self-contained HTML and its manifest. It returns output_path "
            "and manifest_path. It refuses a figure whose claim does not "
            "match its binding — fix the claim (in the draft, on the "
            "gateway route: write, preview, publish again) and build again.\n"
            "5. verify_manifest(manifest=<the manifest_path from step 4>) "
            "and report the verdict. Only 'reproduces' means the numbers "
            "were re-run and matched; say so honestly if anything is "
            "unverifiable. To read the page, fetch_artifact(path=<the "
            "output_path from step 4>).\n\n"
            "For a fixed layout, a JSON ReportSpec is the simpler lane (read "
            "tracebi://spec-schema), validate_report_spec until ok:true — "
            "heed its warnings too — then render_report_spec, which returns "
            "html_path and manifest_path. Pass that manifest_path as "
            "verify_manifest(manifest=...)."
        )

    @server.prompt(
        name="answer_question", title="Answer a question from the model",
        description="Answer in plain words, each number beside its fingerprint and measure; never estimate.",
    )
    def _answer_question_prompt(question: str, model: str = "") -> str:
        ctx = f"get_context (brief=true, model={model!r})" if model else \
            "get_context (brief=true)"
        return (
            f"Answer this question from the TraceBi model: {question}\n\n"
            f"1. Call {ctx} to learn which facts, dimensions and named "
            "measures exist.\n"
            "2. Call query_model with the measures and dimensions that answer "
            "it. Prefer a declared measure over an ad-hoc one.\n"
            "3. Answer in plain words. Quote each number beside its "
            "fingerprint and the measure it came from, for example "
            "\"revenue (measure: revenue) was 1,250 — fingerprint 3f9a…\".\n\n"
            "Rules:\n"
            "- Never estimate. Every number you state comes from a "
            "query_model result in this conversation.\n"
            "- If the model cannot answer — no measure or dimension fits — "
            "say so plainly and name what is missing. Do not approximate "
            "from a nearby measure.\n"
            "- Do not build a report unless you are asked to."
        )

    @server.prompt(
        name="address_pins", title="Act on the person's workbench pins",
        description="Read workbench_state, act on each open pin in order, rebuild, verify, then resolve each pin.",
    )
    def _address_pins_prompt(report: str) -> str:
        return (
            f"Act on the open workbench pins for the report {report!r}.\n\n"
            f"1. Call workbench_state(report={report!r}). Its pins are the "
            "person's requests, oldest first; they come before any other "
            "change.\n"
            "2. Act on each open pin in order by editing the package "
            f"reports/{report}/:\n"
            "   - kind \"promote\" (Keep this): the request field names the "
            "exhibit and the code behind it. Re-express it as a report.json "
            "binding plus a figure in template.html when the model can, "
            "else compute it in report.py (marked python-derived).\n"
            "   - kind \"message\": the person's note — treat it as an "
            "instruction.\n"
            "   - a pin on a figure: its note says what to change about that "
            "figure.\n"
            f"3. build_report(report={report!r}). If it refuses, fix the "
            "package and build again.\n"
            "4. verify_manifest(manifest=<the manifest_path build_report "
            "returned>). Only a reproduces verdict means the numbers were "
            "re-run and matched. If it does not reproduce, fix the package "
            "and build again before resolving pins.\n"
            "5. resolve_pin each pin you acted on, with a one-line note of "
            "what you did. If you could not act on one, leave it open and "
            "say why."
        )

    _log_rejected_arguments(server)
    return server


def _log_rejected_arguments(server) -> None:
    """Record argument-validation failures the tool wrapper never sees."""
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool(name, arguments, context, convert_result=False):
        try:
            return await original(
                name, arguments, context, convert_result=convert_result)
        except Exception as exc:
            cause = exc.__cause__
            if type(cause).__name__ == "ValidationError":
                _gateway_log.record_rejected_arguments(
                    name, arguments, cause, _mcp_actor())
            raise

    manager.call_tool = call_tool


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(transport: str = "stdio", port: int = 8765,
          host: str = "127.0.0.1", insecure: bool = False,
          allow_insecure_bind: bool = False) -> None:
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
        # A warning is how an open gateway ships in a container log nobody
        # reads. Refuse, and require an explicit second flag.
        if (insecure and not token and not _is_loopback(host)
                and not allow_insecure_bind):
            raise GatewayAuthError(
                "Refusing to bind an unauthenticated MCP gateway on a "
                f"non-loopback host ({host}). Anyone who can reach the port "
                "gets full query access. Set TRACEBI_MCP_TOKEN, bind "
                "127.0.0.1, or pass --allow-insecure-bind to do this on purpose."
            )
        auth_mode = (
            "bearer (TRACEBI_MCP_TOKEN)" if token else "none (--insecure)"
        )
        server = build_server(token=token or None)
        # After build_server: a posture line printed before a failed build
        # would announce an auth mode that never came up.
        # stderr: on stdio the protocol owns stdout, so operator-facing
        # posture lines go to stderr on every transport for consistency.
        print(
            f"[tracebi] mcp gateway: transport=http host={host} auth={auth_mode} "
            f"actor={_mcp_actor()}",
            file=sys.stderr,
        )
        server.run(transport="streamable-http", host=host, port=port)
    else:
        server = build_server()
        server.run(transport="stdio")
