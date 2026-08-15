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

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from tracebi.model.dataset import DataSet, LineageNode


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
    return {
        "columns": repr(list(df.columns)),
        "dtypes": repr([str(t) for t in df.dtypes]),
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

    ``execute`` appends the query node last; the same last-node-with-a-
    ``query_spec`` rule ``verify.py`` uses recovers it robustly.
    """
    for node in reversed(ds.lineage_to_dict()):
        md = node.get("metadata") if isinstance(node, dict) else None
        if isinstance(md, dict) and md.get("query_spec"):
            return md
    return {}


def stamp(model, query, name: str = "data") -> StampedData:
    """Resolve *query* against *model*, fingerprint it, and package it.

    ``model.execute(query)`` stamps the resolved query spec, model, and input
    fingerprints into lineage. The returned :class:`StampedData` carries the
    canonical triple (the fingerprinted bytes) alongside a display ``records``
    payload — everything the embedder and the manifest need, computed once.
    """
    ds = model.execute(query)
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


def embed_block(stamped: StampedData, elem_id: Optional[str] = None) -> str:
    """The ``<script type="application/json">`` data block for one binding.

    Carries only the canonical triple — the exact bytes the checker hashes and
    the same bytes the page parses to draw. Embedded through :func:`embed_json`
    so any hostile cell value is neutralised.
    """
    payload = {
        "name": stamped.name,
        "columns": stamped.triple["columns"],
        "dtypes": stamped.triple["dtypes"],
        "csv": stamped.triple["csv"],
    }
    return embed_json(payload, elem_id or f"tracebi-data-{stamped.name}")


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
