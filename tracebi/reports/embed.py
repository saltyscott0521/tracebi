"""
Trust-kernel primitives for the report generator (architecture §3.1, §5).

Two jobs, kept together because they are two halves of one contract:

* :func:`embed_json` — the **safe** JSON embedder. Model data carries
  attacker-influencable strings (issuer names parsed from prose), so a cell
  containing ``</script><img onerror=…>`` must not break out of the ``<script>``
  and execute in a file a third party opens offline. The block is
  ``type="application/json"`` (non-executable) and the client reads it with
  ``JSON.parse(el.textContent)`` only — never ``innerHTML``.

* :func:`stamp` and the canonical triple — the bytes a reviewer rehashes.
  ``frame_fingerprint`` (``dataset.py``) is SHA-256 over exactly three strings::

      repr(list(df.columns))
      repr([str(t) for t in df.dtypes])
      df.to_csv(index=False)

  Embedding those *exact strings* (not a records-JSON round-trip, which drifts
  by a ULP and loses dtypes) lets the offline checker recompute the fingerprint
  from the shipped bytes **without rebuilding a DataFrame**, and get the stored
  value back to the character. There is **one** fingerprint algorithm; this
  module never introduces a second.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from tracebi.model.dataset import DataSet, LineageNode, last_query_node


# ── Self-contained page assembly (shared by both render lanes) ──────────────
#
# The CSP, the charting-library inliner, and the loud string-insertion helper
# below are the *one* implementation of the self-contained-file contract. The
# governed HTMLRenderer and the freeform TemplatePackage both build the same
# emailed, offline ``.html`` — CSP in the head, an inlined ECharts bundle and
# safe embedded data in the body — so this logic lives here, next to the safe
# embedder it belongs with, rather than being copied per lane.

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

#: Charting libraries the generator can inline. Their minified IIFE bundles live
#: in ``tracebi/reports/assets/<name>.min.js`` and expose a global of the name.
KNOWN_LIBS = {"echarts"}

#: The strict CSP embedded in every generated page (architecture §5). Inline
#: script/style are unavoidable in a static self-contained file; ``connect-src
#: 'none'`` is the real win — a bundled library cannot phone home with the
#: embedded data. JavaScript ``'unsafe-eval'`` is NOT granted (ECharts needs
#: none, and neither does the runtime).
#:
#: Three grants serve the artifact's worker engine, which decodes embedded
#: Parquet off the main thread: ``worker-src blob:`` and ``script-src blob:``
#: let the runtime start the inlined worker from a blob URL (the only way to
#: run a worker in a self-contained file with no sidecar), and
#: ``'wasm-unsafe-eval'`` permits compiling the inlined WebAssembly module.
#: ``'wasm-unsafe-eval'`` is strictly narrower than ``'unsafe-eval'``: it allows
#: WebAssembly compilation ONLY — it does not enable ``eval()`` or
#: ``new Function()`` on JavaScript strings. ``connect-src 'none'`` still holds,
#: so the engine cannot phone home either.
CSP = (
    "default-src 'none'; "
    "script-src 'unsafe-inline' 'wasm-unsafe-eval' blob:; "
    "worker-src blob:; "
    "style-src 'unsafe-inline'; "
    "img-src data:; font-src data:; connect-src 'none'; base-uri 'none'; "
    "form-action 'none'"
)


def csp_meta() -> str:
    """The §5 CSP as a ``<meta>`` element, ready to insert into ``<head>``."""
    return f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'


def read_lib(name: str) -> str:
    """The minified IIFE bundle for a charting library, to inline verbatim."""
    path = os.path.join(_ASSETS_DIR, f"{name}.min.js")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Charting library '{name}' is declared but its bundle is missing "
            f"at {path}. Rebuild it (see web/ui/echarts-bundle.js)."
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


def insert_before(html: str, tag: str, snippet: str) -> str:
    """Insert *snippet* immediately before *tag*, matched case-insensitively.

    Fails loudly when the tag is absent: the whole point of string injection is
    that a forgotten placeholder cannot silently swallow the data (or the CSP).
    """
    idx = html.lower().find(tag)
    if idx == -1:
        raise ValueError(
            f"The rendered document has no {tag} — cannot inject the report's "
            f"data/style/script. The page must be a complete HTML document with "
            f"<head> and <body>."
        )
    return html[:idx] + snippet + html[idx:]


def embed_json(obj: Any, elem_id: str) -> str:
    """Serialise *obj* into a non-executable ``<script>`` block (architecture §5).

    Escaping happens here in Python, before the string reaches any template:
    the custom-template Jinja env is ``autoescape=False``, so there is no safe
    embedder to inherit. ``&``, ``<``, ``>`` and the two line separators
    U+2028/U+2029 (which break a JS string literal but not JSON) are replaced
    with their ``\\uXXXX`` escapes — each a valid JSON escape, so the block is
    still parseable by ``JSON.parse`` and round-trips the exact bytes.
    """
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    safe = (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )
    return f'<script id="{elem_id}" type="application/json">{safe}</script>'


def canonical_triple(df) -> dict:
    """The three exact strings ``frame_fingerprint`` hashes, verbatim.

    Keys ``columns`` / ``dtypes`` / ``csv``. Shipping these — rather than a
    records payload — is what makes the embedded data checkable offline.
    """
    from tracebi.model.dataset import canonical_dtypes_repr

    return {
        "columns": repr(list(df.columns)),
        # The one dtype rule (pandas 2↔3 string-dtype rename) — shared with
        # frame_fingerprint so the offline rehash of these shipped strings
        # can never disagree with the live fingerprint.
        "dtypes": canonical_dtypes_repr(df),
        "csv": df.to_csv(index=False),
    }


def fingerprint_triple(triple: dict) -> str:
    """SHA-256 over the canonical triple's three strings, in fixed order.

    Identical bytes and order to ``frame_fingerprint``: columns, then dtypes,
    then CSV. The offline checker calls this on strings it recovered from the
    ``.html`` — no DataFrame is rebuilt — and gets the stored fingerprint back.
    """
    h = hashlib.sha256()
    h.update(triple["columns"].encode("utf-8"))
    h.update(triple["dtypes"].encode("utf-8"))
    h.update(triple["csv"].encode("utf-8"))
    return h.hexdigest()


@dataclass(frozen=True)
class StampedData:
    """A resolved, fingerprinted dataset ready to embed and record.

    Fields:
        name:        The binding name (how a report refers to this dataset).
        dataset:     The stamped :class:`DataSet` — its last lineage node
                     carries the resolved ``query_spec`` and ``model``.
        fingerprint: ``dataset.fingerprint()`` == ``fingerprint_triple(triple)``.
        triple:      ``{columns, dtypes, csv}`` — the exact fingerprinted bytes,
                     and the *only* data the page draws from. There is no
                     separate unverified display copy: the page parses the same
                     ``csv`` the receipt covers, so a displayed number cannot
                     silently diverge from a verified one.
        query_spec:  The resolved query spec recovered from lineage, or None.
        model:       The model name recovered from lineage, or None.
    """

    name: str
    dataset: DataSet
    fingerprint: str
    triple: dict
    query_spec: Optional[dict]
    model: Optional[str]


def _query_metadata(ds: DataSet) -> dict:
    """The ``{model, query_spec}`` metadata ``DataModel.execute`` stamped.

    ``execute`` appends the query node last; :func:`last_query_node`
    (``dataset.py``) — the one shared recovery rule — recovers it robustly.
    """
    node = last_query_node(ds.lineage_to_dict())
    return node["metadata"] if node else {}


def stamp_dataset(ds: DataSet, name: str = "data") -> StampedData:
    """Package an already-resolved :class:`DataSet` as :class:`StampedData`.

    Fingerprints *ds* and recovers the ``{model, query_spec}`` metadata its
    lineage carries (present when it came from ``DataModel.execute``, absent for
    a hand-built frame). The governed HTMLRenderer stamps a ChartSection's
    resolved dataset through this — the same canonical triple + fingerprint the
    freeform lane produces, so both lanes' embedded data is file-checkable by
    the one algorithm.
    """
    df = ds.to_pandas()
    triple = canonical_triple(df)
    md = _query_metadata(ds)
    return StampedData(
        name=name,
        dataset=ds,
        fingerprint=ds.fingerprint(),
        triple=triple,
        query_spec=md.get("query_spec"),
        model=md.get("model"),
    )


def stamp(model, query, name: str = "data") -> StampedData:
    """Resolve *query* against *model*, fingerprint it, and package it.

    ``model.execute(query)`` stamps the resolved query spec, model, and input
    fingerprints into lineage; :func:`stamp_dataset` then packages the result
    into everything the embedder and the manifest need, computed once.
    """
    return stamp_dataset(model.execute(query), name=name)


def stamp_frame(
    df, name: str = "data",
    description: str = "report.py output (python-derived)",
) -> StampedData:
    """Package a python-derived DataFrame as :class:`StampedData` (architecture §8-M3).

    The escape hatch's *output*: a ``report.py`` computed *df* from stamped
    inputs, so it flows through the *same* embed/fingerprint kernel as a
    declarative binding — the canonical triple is embedded and hashed, and
    ``verify --file`` catches tampering of it. But it carries **no** query
    spec or model: arbitrary Python is not reproducible by replaying a query,
    so ``query_spec``/``model`` are ``None`` and the lineage node is marked
    ``python_derived`` — which is why ``verify_manifest`` classifies it
    UNVERIFIABLE and never lets it read as reproduced.
    """
    node = LineageNode(
        operation="transform",
        description=description,
        metadata={"python_derived": True},
    )
    ds = DataSet(df=df, name=name, lineage=[node])
    frame = ds.to_pandas()
    return StampedData(
        name=name,
        dataset=ds,
        fingerprint=ds.fingerprint(),
        triple=canonical_triple(frame),
        query_spec=None,
        model=None,
    )


#: How a binding's data is embedded. Both formats carry the SAME receipt — the
#: fingerprint is the frame's ``{columns, dtypes, csv}`` content triple either
#: way (Parquet round-trips it exactly), so this is a transport choice, not a
#: trust one, and ``verify`` handles both.
#:
#: ``"csv"``     — the triple inline. No engine needed: the runtime parses it
#:                 directly, so the artifact stays small (KBs). Right for the
#:                 aggregate-shaped dashboards that are the common case.
#: ``"parquet"`` — compact columnar data (≈50× smaller than JSON) decoded by the
#:                 inlined worker engine. Costs ~9 MB of engine, and is what
#:                 makes large-detail, client-side-filterable artifacts possible.
EMBED_FORMAT_CSV = "csv"
EMBED_FORMAT_PARQUET = "parquet"

#: The default transport for a generated artifact. CSV keeps the common
#: aggregate dashboard small; a report that embeds large detail opts into
#: Parquet (see ``docs/large-detail-artifacts.md``).
DEFAULT_EMBED_FORMAT = EMBED_FORMAT_CSV


def embed_block(stamped: StampedData, elem_id: Optional[str] = None,
                fmt: Optional[str] = None) -> str:
    """The ``<script type="application/json">`` data block for one binding.

    With ``fmt="csv"`` (the default) the block carries the canonical triple —
    the exact bytes the checker hashes and the same bytes the page parses to
    draw. With ``fmt="parquet"`` it carries the data as Parquet for the worker
    engine (:func:`embed_block_parquet`); the receipt is identical either way.
    Embedded through :func:`embed_json` so any hostile cell value is neutralised.
    """
    if (fmt or DEFAULT_EMBED_FORMAT) == EMBED_FORMAT_PARQUET:
        return embed_block_parquet(stamped, elem_id)
    payload = {
        "name": stamped.name,
        "columns": stamped.triple["columns"],
        "dtypes": stamped.triple["dtypes"],
        "csv": stamped.triple["csv"],
    }
    return embed_json(payload, elem_id or f"tracebi-data-{stamped.name}")


def embed_block_parquet(stamped: StampedData, elem_id: Optional[str] = None) -> str:
    """A binding's data embedded as **Parquet** (base64) — the transport the
    client-side worker engine (parquet-wasm + Arquero) decodes to draw and
    filter, and ≈50× smaller than the CSV triple on real data.

    The receipt is **unchanged**: the binding's ``embedded_sha256`` is still the
    ``{columns, dtypes, csv}`` content fingerprint, which survives the Parquet
    round-trip exactly (``tests/test_parquet_embed.py``). ``verify`` decodes this
    block and recomputes the same triple — Parquet is transport, not the hashed
    thing. Emitted through :func:`embed_json` so the base64 payload cannot break
    out of the ``<script>`` block.
    """
    import base64

    from tracebi.reports.parquet_embed import to_parquet_bytes

    frame = stamped.dataset.to_pandas()
    payload = {
        "name": stamped.name,
        "format": "parquet",
        "parquet_b64": base64.b64encode(to_parquet_bytes(frame)).decode("ascii"),
    }
    return embed_json(payload, elem_id or f"tracebi-data-{stamped.name}")


#: Element ids the runtime (``tracebi.js``) reads to start the worker engine.
ENGINE_WORKER_ID = "tracebi-engine-worker"
ENGINE_WASM_ID = "tracebi-engine-wasm"


def engine_blocks_html() -> str:
    """The inlined worker-engine assets, as the two blocks the runtime reads.

    A self-contained artifact carries its own query engine: the bundled worker
    source (started from a blob URL — the only way to run a worker with no
    sidecar file) and the gzipped ``parquet-wasm`` module, base64'd and
    decompressed in the browser via ``DecompressionStream``. Together they let a
    figure decode and filter its embedded Parquet **offline, with no network**
    (see ``assets/ENGINE_NOTICE.md``).

    Emitted only for artifacts that embed Parquet — a CSV artifact would pay
    megabytes for an engine it never starts.
    """
    # Read from _ASSETS_DIR directly rather than stack.read_asset: stack
    # imports from this module, so importing back would be circular.
    with open(os.path.join(_ASSETS_DIR, "tracebi-engine.worker.js"),
              encoding="utf-8") as fh:
        worker_src = fh.read()
    with open(os.path.join(_ASSETS_DIR, "parquet_wasm_bg.wasm.gz"), "rb") as fh:
        wasm_b64 = base64.b64encode(fh.read()).decode("ascii")
    # The worker source goes in a non-executable text block (the runtime reads
    # its textContent and builds the blob); "</script" is neutralised the same
    # way embed_json neutralises it in data.
    safe_worker = worker_src.replace("</script", "<\\/script")
    return (
        f'<script type="text/plain" id="{ENGINE_WORKER_ID}">{safe_worker}</script>\n'
        f'<script type="application/base64" id="{ENGINE_WASM_ID}">{wasm_b64}</script>\n'
    )


def embedded_record(stamped: StampedData, verifiable: bool = True) -> dict:
    """The per-binding entry for the manifest's ``embedded_data`` block.

    ``embedded_sha256`` is the canonical-triple hash, which equals both
    ``stamped.fingerprint`` and the section's ``dataset_fingerprint`` — the
    single value the offline checker rehashes the shipped bytes against.

    *verifiable* is ``False`` for a ``report.py`` output (architecture §4):
    its bytes are still fingerprinted and file-checkable, but the output is
    not query-reproducible, so the receipt says so explicitly. The key is
    omitted when ``True`` so a declarative binding's record keeps the exact
    shape it had before the escape hatch existed.
    """
    rec = {
        "name": stamped.name,
        "embedded_sha256": stamped.fingerprint,
        "query_spec": stamped.query_spec,
        "model": stamped.model,
    }
    if not verifiable:
        rec["verifiable"] = False
    return rec
