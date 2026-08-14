"""
Verify a rendered report manifest against the project's models.

This closes the loop the manifest opens. Render time stamps every
data-bearing section with the resolved query spec, the full lineage chain
(including a fingerprint of every source table loaded), and a fingerprint
of the result. Verify time re-runs each recorded query against today's
models and data and classifies the outcome:

* **reproduces** — the re-run's fingerprint matches the manifest.
* **model_changed** — a table now loads from a different source/connector
  than the manifest records: a governance event, alarming (exit 1)
* **source_drift** — the result differs AND at least one recorded input
  fingerprint no longer matches the source table: the data moved.
* **unexplained** — the result differs but every input fingerprint still
  matches. The inputs did not move, so something else did — model code,
  measure definitions, engine behaviour. This is the alarming case.
* **mismatch_unknown_cause** — the result differs and the manifest recorded
  no input fingerprints (rendered before they existed), so drift cannot be
  told apart from unexplained. Reported honestly rather than guessed.
* **unverifiable** — the section carries no recorded query (python-authored
  ad hoc data), or was transformed after the query, so the query alone
  cannot reproduce it.
* **error** — the recorded query could not be re-run at all (model missing,
  query raises). Loud, never silently skipped.

The whole receipt then gets one **verdict** (:data:`VERDICT_EXIT_CODES`),
which is what the exit code and the ``ok`` boolean are both derived from.
``reproduces`` is the only verdict that means a number was re-run and
matched: a manifest with no data-bearing section (``nothing_to_verify``),
one whose every section is unverifiable (``unverifiable``), and one this
checker refused to read at all (``refused_newer_schema``) each say so in
their own words rather than borrowing the passing one's — and each says
*which* of the three it is, because "there was nothing to check" and "I
could not check it" are different facts about the receipt.

Consumed by ``tracebi verify <manifest.json>`` and by the gateway's
``verify_manifest`` MCP tool; both are thin presentation layers over
:func:`verify_manifest` here.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional, Union

# Section classifications. Plain strings, not an enum — they travel through
# JSON to the CLI, the MCP gateway, and archived verification records.
REPRODUCES = "reproduces"
SOURCE_DRIFT = "source_drift"
MODEL_CHANGED = "model_changed"
UNEXPLAINED = "unexplained"
MISMATCH_UNKNOWN = "mismatch_unknown_cause"
UNVERIFIABLE = "unverifiable"
ERROR = "error"

#: Human-facing labels for the CLI's one-line-per-section output.
STATUS_LABELS = {
    REPRODUCES:       "REPRODUCES",
    SOURCE_DRIFT:     "SOURCE DRIFT",
    MODEL_CHANGED:    "MODEL CHANGED",
    UNEXPLAINED:      "UNEXPLAINED",
    MISMATCH_UNKNOWN: "MISMATCH (cause unknown)",
    UNVERIFIABLE:     "UNVERIFIABLE",
    ERROR:            "ERROR",
}

#: Statuses that mean "this receipt could not be shown to reproduce for a
#: reason nobody has diagnosed" — the exit-1 class. An unknown-cause
#: mismatch belongs here: it *might* be drift, but the bias is toward loud
#: failure, never toward the reassuring guess.
_ALARMING = (UNEXPLAINED, MODEL_CHANGED, MISMATCH_UNKNOWN, ERROR)

# ── Receipt-level verdicts ─────────────────────────────────────────────────
# The one-line answer for a whole manifest. Section statuses say what
# happened to each number; the verdict says what the receipt as a whole
# proves. Three of them exist because "nothing was verified", "I refused to
# read this", and "everything reproduced" must never be the same answer.

#: No data-bearing section at all — there was nothing to check. A manifest
#: that records no checkable number is a broken receipt, not a passing one.
NOTHING_TO_VERIFY = "nothing_to_verify"
#: The manifest was written by a newer tracebi, so this checker declined to
#: read it. Distinct from ``nothing_to_verify``: the receipt may be full of
#: data-bearing sections, and saying otherwise would be a false answer.
REFUSED_NEWER_SCHEMA = "refused_newer_schema"
#: At least one section could not be shown to reproduce, cause undiagnosed.
NOT_REPRODUCED = "not_reproduced"

#: verdict → exit code, and the *only* place either the process exit status
#: or the ``ok`` boolean is decided (``ok`` is ``exit_code == 0``), so the
#: CLI's status and the gateway's boolean cannot disagree by construction.
VERDICT_EXIT_CODES = {
    REPRODUCES:           0,
    UNVERIFIABLE:         0,
    SOURCE_DRIFT:         2,
    NOT_REPRODUCED:       1,
    NOTHING_TO_VERIFY:    1,
    REFUSED_NEWER_SCHEMA: 1,
}

#: The one-line verdict the CLI prints and the gateway returns as
#: ``verdict_detail``.
VERDICT_LABELS = {
    REPRODUCES:
        "REPRODUCES — every checked section matches the manifest",
    UNVERIFIABLE:
        "NOTHING VERIFIED — every section is unverifiable; no number in "
        "this receipt was checked",
    NOTHING_TO_VERIFY:
        "NOTHING VERIFIED — this manifest has no data-bearing section; "
        "there was nothing to check",
    REFUSED_NEWER_SCHEMA:
        "NOT CHECKED — this manifest was written by a newer tracebi than "
        "this one; it was refused, not verified (see 'error')",
    SOURCE_DRIFT:
        "SOURCE DRIFT — section(s) differ and the inputs they load moved",
    NOT_REPRODUCED:
        "NOT REPRODUCED — section(s) could not be shown to reproduce; "
        "explain before anyone reads the number",
}


def _verdict(summary: Mapping[str, int]) -> str:
    """The receipt-level answer, derived once from the section counts."""
    if not any(summary.values()):
        return NOTHING_TO_VERIFY
    if any(summary[s] for s in _ALARMING):
        return NOT_REPRODUCED
    if summary[SOURCE_DRIFT]:
        return SOURCE_DRIFT
    if not summary[REPRODUCES]:
        return UNVERIFIABLE
    return REPRODUCES


def _verdict_fields(
    verdict: str, summary: Optional[Mapping[str, int]] = None,
) -> dict:
    """The four verdict keys every result carries, all from one lookup.

    A passing receipt that still holds unverifiable sections says how many:
    the verdict stays ``reproduces`` (nothing failed, and an unverifiable
    section is a legitimate authoring state, so exit 0 is right), but one
    checked section out of a hundred must not read like a hundred.
    """
    code = VERDICT_EXIT_CODES[verdict]
    detail = VERDICT_LABELS[verdict]
    unchecked = (summary or {}).get(UNVERIFIABLE, 0)
    if verdict == REPRODUCES and unchecked:
        checked = summary[REPRODUCES]
        detail = (
            f"REPRODUCES — {checked} of {checked + unchecked} section(s) "
            f"checked and matching; {unchecked} unverifiable, so this "
            f"receipt does not prove them"
        )
    return {
        "verdict": verdict,
        "verdict_detail": detail,
        "exit_code": code,
        "ok": code == 0,
    }


def load_models(models_dir: Union[str, Path, None] = None) -> dict:
    """
    Every project model, keyed both by ``model.name`` and file stem.

    Same discovery contract as the MCP gateway: *models_dir* (or
    ``TRACEBI_MODELS_DIR``, or ``./models``) plus anything explicitly
    registered with the model registry (tests, notebooks).
    """
    from tracebi import model_registry

    models: dict = {}
    d = Path(models_dir) if models_dir else Path(
        os.environ.get("TRACEBI_MODELS_DIR", "models")
    )
    if d.is_dir():
        for stem in model_registry.auto_discover(str(d)):
            try:
                m = model_registry.get_model(stem)
            except Exception:  # noqa: BLE001 — a broken file shouldn't hide the others
                continue
            models[m.name] = m
            models.setdefault(stem, m)
    for name in model_registry.list_models():
        if name not in models:
            try:
                models[name] = model_registry.get_model(name)
            except Exception:  # noqa: BLE001
                continue
    return models


def _walk_sections(sections: list) -> list:
    """All section dicts in order, descending into containers — every
    section that nests children records them under ``sections``, whatever
    its section_type, so nested sections aren't skipped."""
    out: list = []
    for s in sections or []:
        if not isinstance(s, dict):
            continue
        out.append(s)
        out.extend(_walk_sections(s.get("sections") or []))
    return out


def _query_node(lineage: list) -> Optional[dict]:
    """The lineage node that stamps the resolved query, or None.

    Same recovery rule as ``tracebi.spec._data_ref_of``: last node whose
    metadata carries a ``query_spec``.
    """
    for node in reversed(lineage or []):
        if not isinstance(node, dict):
            continue
        md = node.get("metadata")
        if isinstance(md, dict) and md.get("query_spec"):
            return node
    return None


def _input_index(lineage: list) -> dict[str, list[str]]:
    """``{table: sorted [fingerprints]}`` from a lineage chain's load nodes.

    A list per table, not a scalar: one query may load the same table more
    than once (e.g. as both fact and dimension) with different pushdown, and
    dimension-load order is not stable across processes — so comparison is
    by table name over sorted fingerprint sets, never by position.
    """
    out: dict[str, list[str]] = {}
    for node in lineage or []:
        if not isinstance(node, dict):
            continue
        md = node.get("metadata")
        if not isinstance(md, dict):
            continue
        inp = md.get("input")
        if not isinstance(inp, dict):
            continue
        if inp.get("fingerprint"):
            out.setdefault(str(inp.get("table")), []).append(inp["fingerprint"])
    for fps in out.values():
        fps.sort()
    return out


def _mapping_index(lineage: list) -> dict[str, list[str]]:
    """``{table: sorted ["connector:source"]}`` from a chain's load nodes.

    The drift diagnosis must not credit a mismatch to "the data moved" when
    what actually moved is the *model* — a table remapped to a different
    source or connector is a governance event, not a data refresh.
    """
    out: dict[str, list[str]] = {}
    for node in lineage or []:
        if not isinstance(node, dict):
            continue
        md = node.get("metadata")
        if not isinstance(md, dict):
            continue
        inp = md.get("input")
        if not isinstance(inp, dict) or not inp.get("table"):
            continue
        conn = node.get("connector")
        cname = conn.get("connector_name") if isinstance(conn, dict) else None
        out.setdefault(str(inp["table"]), []).append(
            f"{cname}:{node.get('source')}"
        )
    for v in out.values():
        v.sort()
    return out


def _verify_section(section: dict, models: Mapping[str, Any], label: str) -> dict:
    """Classify one data-bearing manifest section."""
    from tracebi.model.data_model import QuerySpec

    expected = section["dataset_fingerprint"]
    lineage = section.get("dataset_lineage") or []
    base: dict[str, Any] = {
        "section": label,
        "section_type": section.get("section_type"),
        "expected_fingerprint": expected,
    }

    node = _query_node(lineage)
    if node is None:
        return {**base, "status": UNVERIFIABLE,
                "detail": "no recorded query in lineage (python-authored ad hoc data)"}
    # `DataModel.execute()` stamps the query node last, so anything after it
    # means the dataset was transformed post-query — the recorded query alone
    # cannot reproduce the section's fingerprint, and claiming drift or
    # unexplained from it would be a guess.
    if lineage[-1] is not node:
        return {**base, "status": UNVERIFIABLE,
                "detail": "dataset was transformed after the recorded query; "
                          "the query alone cannot reproduce it"}

    md = node.get("metadata") or {}
    model_name = md.get("model")
    base["model"] = model_name
    base["query_spec"] = md.get("query_spec")
    if model_name not in models:
        return {**base, "status": ERROR,
                "detail": f"model '{model_name}' not found "
                          f"(available: {sorted(set(models))})"}

    try:
        ds = models[model_name].execute(QuerySpec.from_dict(md["query_spec"]))
    except Exception as exc:  # noqa: BLE001 — reported per section, loudly
        return {**base, "status": ERROR,
                "detail": f"recorded query failed to re-run: "
                          f"{type(exc).__name__}: {exc}"}

    actual = ds.fingerprint()
    recorded_inputs = _input_index(lineage)
    current_inputs = _input_index(ds.lineage_to_dict())
    inputs = [
        {
            "table": t,
            "recorded": recorded_inputs.get(t),
            "current": current_inputs.get(t),
            "match": recorded_inputs.get(t) == current_inputs.get(t),
        }
        for t in sorted(set(recorded_inputs) | set(current_inputs))
    ]
    base.update(actual_fingerprint=actual, inputs=inputs)

    if actual == expected:
        return {**base, "status": REPRODUCES,
                "detail": "result fingerprint matches the manifest"}
    if not recorded_inputs:
        return {**base, "status": MISMATCH_UNKNOWN,
                "detail": "result differs and no input fingerprints recorded "
                          "(manifest predates input fingerprinting); cannot "
                          "distinguish source drift from unexplained"}
    recorded_map = _mapping_index(lineage)
    current_map = _mapping_index(ds.lineage_to_dict())
    remapped = [
        t for t in sorted(set(recorded_map) | set(current_map))
        if recorded_map.get(t) != current_map.get(t)
    ]
    if remapped and recorded_map:
        return {**base, "status": MODEL_CHANGED,
                "detail": "table(s) now load from a different source or "
                          "connector than the manifest records: "
                          + ", ".join(remapped)
                          + " — a model change, not a data refresh"}
    drifted = [i["table"] for i in inputs if not i["match"]]
    if drifted:
        return {**base, "status": SOURCE_DRIFT,
                "detail": "input fingerprint(s) for table(s) "
                          + ", ".join(drifted)
                          + " differ — the inputs this model loads changed"}
    return {**base, "status": UNEXPLAINED,
            "detail": "result differs but every input fingerprint matches — "
                      "the data did not move; the model, measures, or engine did"}


def verify_manifest(manifest: dict, models: Mapping[str, Any]) -> dict:
    """
    Re-run every recorded query in *manifest* and classify each section.

    Returns a structured result::

        {
          "report_name": ..., "schema_version": ...,
          "sections": [{"section", "status", "detail",
                        "expected_fingerprint", "actual_fingerprint",
                        "model", "query_spec", "inputs"}, ...],
          "summary": {status: count, ...},
          "verdict": "reproduces" | "unverifiable" | "nothing_to_verify"
                     | "refused_newer_schema" | "source_drift"
                     | "not_reproduced",
          "verdict_detail": str,
          "exit_code": 0 | 1 | 2,
          "ok": bool,     # exit_code == 0
        }

    Only data-bearing sections (those carrying a ``dataset_fingerprint``)
    are classified; presentation-only sections have nothing to verify.
    The verdict is the receipt-level answer and the only input to the exit
    code (see :data:`VERDICT_EXIT_CODES`): 0 when at least one section
    reproduced and none failed, or when every section is honestly
    unverifiable; 2 for diagnosed source drift only; 1 when anything is
    unexplained, of unknown cause, errored, when there was nothing to check
    at all, or when the manifest was refused as too new. ``reproduces`` is
    the only verdict meaning a number in this receipt was re-run and
    matched, and it names any sections it could not check.
    """
    from tracebi.reports.report import MANIFEST_SCHEMA_VERSION

    sv = manifest.get("schema_version")
    if isinstance(sv, int) and sv > MANIFEST_SCHEMA_VERSION:
        # A newer writer may have changed semantics this checker does not
        # know; pretending to verify it would be a reassuring guess.
        return {
            "report_name": manifest.get("report_name"),
            "schema_version": sv,
            "sections": [],
            "summary": {status: 0 for status in STATUS_LABELS},
            **_verdict_fields(REFUSED_NEWER_SCHEMA),
            "error": (
                f"manifest schema_version {sv} is newer than this tracebi "
                f"supports ({MANIFEST_SCHEMA_VERSION}); upgrade tracebi to "
                f"verify it"
            ),
        }

    results: list[dict] = []
    for i, s in enumerate(_walk_sections(manifest.get("sections") or []), start=1):
        if not s.get("dataset_fingerprint"):
            continue
        label = s.get("id") or s.get("title") or f"section[{i}]"
        results.append(_verify_section(s, models, label))

    summary = {status: 0 for status in STATUS_LABELS}
    for r in results:
        summary[r["status"]] += 1

    return {
        "report_name": manifest.get("report_name"),
        "schema_version": manifest.get("schema_version"),
        "sections": results,
        "summary": summary,
        **_verdict_fields(_verdict(summary), summary),
    }


# ── Offline file check (report generator, architecture §3.1 / §3.2) ─────────
#
# A wholly separate check from ``verify_manifest`` above: that one re-runs the
# recorded queries against the *models* (query → model); this one never touches
# a model. It opens the shipped ``.html``, recovers the exact bytes the
# fingerprint was taken over from each embedded data block, rehashes them
# *without rebuilding a DataFrame*, and compares to the manifest's
# ``embedded_sha256`` (embedded bytes → manifest). Neither check implies the
# other, and a tampered number in the file passes ``verify_manifest`` while
# failing here — which is the whole reason this exists.

#: A data block's embedded bytes hash to the manifest value — the number
#: shipped in this file is exactly what was fingerprinted at render time.
FILE_MATCHES = "matches"
#: The embedded bytes no longer hash to the recorded value: the data in the
#: file was edited after it was rendered. The alarming case.
FILE_TAMPERED = "tampered"
#: The manifest records a binding for which the file carries no data block.
FILE_MISSING = "missing_in_file"
#: The file carries a data block the manifest does not record — an embed with
#: no receipt, which the receipt cannot vouch for.
FILE_UNRECORDED = "unrecorded_in_manifest"
#: The embedded bytes match the manifest binding, but no report section carries
#: that fingerprint — an internally inconsistent manifest (its sections were
#: stripped or never recorded), so nothing in the receipt actually vouches for
#: the number. A broken receipt, not a passing one.
FILE_UNBACKED = "unbacked_by_section"

FILE_STATUS_LABELS = {
    FILE_MATCHES:    "MATCHES",
    FILE_TAMPERED:   "TAMPERED",
    FILE_MISSING:    "MISSING IN FILE",
    FILE_UNRECORDED: "UNRECORDED IN MANIFEST",
    FILE_UNBACKED:   "UNBACKED BY SECTION",
}

#: Receipt-level verdicts for the file check.
FILE_INTACT = "file_intact"
FILE_ALTERED = "file_altered"
FILE_NOTHING = "file_nothing_embedded"

FILE_VERDICT_EXIT_CODES = {
    FILE_INTACT:   0,
    FILE_ALTERED:  1,
    FILE_NOTHING:  1,
}

FILE_VERDICT_LABELS = {
    FILE_INTACT:
        "FILE INTACT — every embedded data block matches the manifest; the "
        "numbers shipped in this file are exactly what was fingerprinted",
    FILE_ALTERED:
        "FILE ALTERED — an embedded data block does not match the manifest; "
        "the data in this file is not what was recorded",
    FILE_NOTHING:
        "NOTHING EMBEDDED — this manifest records no embedded data and the "
        "file carries none; there was nothing to check",
}

#: The ``<script type="application/json">`` blocks the embedder emits. Captures
#: the ``id`` (the binding fallback name) and the raw JSON text between the tags.
_DATA_BLOCK_RE = re.compile(
    r'<script\s+id="(?P<id>[^"]*)"\s+type="application/json"\s*>'
    r'(?P<body>.*?)</script>',
    re.DOTALL,
)


def _fingerprint_triple(triple: Mapping[str, str]) -> str:
    """SHA-256 over the canonical triple — one algorithm, shared with the embedder."""
    from tracebi.reports.embed import fingerprint_triple

    return fingerprint_triple(dict(triple))


def _extract_data_blocks(html: str) -> list[tuple[str, dict]]:
    """Every embedded data block that carries a canonical triple.

    Returns ``(name, parsed)`` pairs. A block is a data block only if its
    parsed JSON holds all three canonical-triple keys; other
    ``application/json`` blocks (a config blob, say) are skipped. ``name`` is
    the payload's own ``name`` when present, else the element id.
    """
    out: list[tuple[str, dict]] = []
    for m in _DATA_BLOCK_RE.finditer(html):
        try:
            parsed = json.loads(m.group("body"))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        if not all(k in parsed for k in ("columns", "dtypes", "csv")):
            continue
        name = parsed.get("name") or m.group("id")
        out.append((str(name), parsed))
    return out


def verify_file(html: str, manifest: dict) -> dict:
    """Rehash every embedded data block in *html* against *manifest*.

    No model is loaded and no DataFrame is rebuilt: each block's three
    canonical strings are hashed exactly as ``frame_fingerprint`` hashed them,
    and compared to the manifest's ``embedded_data[].embedded_sha256`` (which
    equals the matching section's ``dataset_fingerprint``). Returns the same
    ``verdict``/``exit_code``/``ok`` shape as :func:`verify_manifest`, so the
    CLI presents both checks uniformly.
    """
    records = {
        str(e.get("name")): e
        for e in (manifest.get("embedded_data") or [])
        if isinstance(e, dict)
    }
    # Section fingerprints, to confirm the manifest is internally consistent:
    # a recorded embedded_sha256 that no section fingerprinted would be a
    # broken receipt, not a passing one.
    section_fps = {
        s.get("dataset_fingerprint")
        for s in _walk_sections(manifest.get("sections") or [])
        if s.get("dataset_fingerprint")
    }

    results: list[dict] = []
    seen: set[str] = set()
    for name, parsed in _extract_data_blocks(html):
        computed = _fingerprint_triple(parsed)
        record = records.get(name)
        if record is None:
            results.append({
                "binding": name,
                "status": FILE_UNRECORDED,
                "computed_sha256": computed,
                "expected_sha256": None,
                "detail": "the file embeds this data block but the manifest "
                          "records no binding for it — no receipt vouches for it",
            })
            continue
        seen.add(name)
        expected = record.get("embedded_sha256")
        if computed == expected and expected in section_fps:
            results.append({
                "binding": name,
                "status": FILE_MATCHES,
                "computed_sha256": computed,
                "expected_sha256": expected,
                "detail": "embedded bytes match the manifest",
            })
        elif computed == expected:
            # The bytes match the recorded binding, but no section carries the
            # fingerprint — the manifest is internally inconsistent, so the
            # match vouches for nothing. Fail, do not merely note it.
            results.append({
                "binding": name,
                "status": FILE_UNBACKED,
                "computed_sha256": computed,
                "expected_sha256": expected,
                "detail": "embedded bytes match the manifest binding, but no "
                          "report section carries this fingerprint — the "
                          "receipt does not vouch for this number",
            })
        else:
            results.append({
                "binding": name,
                "status": FILE_TAMPERED,
                "computed_sha256": computed,
                "expected_sha256": expected,
                "detail": "embedded bytes hash to a different value than the "
                          "manifest records — the data in this file was edited "
                          "after it was rendered",
            })

    for name, record in records.items():
        if name not in seen:
            results.append({
                "binding": name,
                "status": FILE_MISSING,
                "computed_sha256": None,
                "expected_sha256": record.get("embedded_sha256"),
                "detail": "the manifest records this binding but the file "
                          "embeds no matching data block",
            })

    summary = {status: 0 for status in FILE_STATUS_LABELS}
    for r in results:
        summary[r["status"]] += 1

    if not results:
        verdict = FILE_NOTHING
    elif summary[FILE_MATCHES] == len(results):
        verdict = FILE_INTACT
    else:
        verdict = FILE_ALTERED

    code = FILE_VERDICT_EXIT_CODES[verdict]
    return {
        "report_name": manifest.get("report_name"),
        "bindings": results,
        "summary": summary,
        "verdict": verdict,
        "verdict_detail": FILE_VERDICT_LABELS[verdict],
        "exit_code": code,
        "ok": code == 0,
    }
