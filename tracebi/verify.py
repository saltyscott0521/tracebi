"""
Verify a rendered report manifest against the project's models.

This closes the loop the manifest opens. Render time stamps every
data-bearing section with the resolved query spec, the full lineage chain
(including a fingerprint of every source table loaded), and a fingerprint
of the result. Verify time re-runs each recorded query against today's
models and data and classifies the outcome:

* **reproduces** — the re-run's fingerprint matches the manifest.
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

Consumed by ``tracebi verify <manifest.json>`` and by the gateway's
``verify_manifest`` MCP tool; both are thin presentation layers over
:func:`verify_manifest` here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional, Union

# Section classifications. Plain strings, not an enum — they travel through
# JSON to the CLI, the MCP gateway, and archived verification records.
REPRODUCES = "reproduces"
SOURCE_DRIFT = "source_drift"
UNEXPLAINED = "unexplained"
MISMATCH_UNKNOWN = "mismatch_unknown_cause"
UNVERIFIABLE = "unverifiable"
ERROR = "error"

#: Human-facing labels for the CLI's one-line-per-section output.
STATUS_LABELS = {
    REPRODUCES:       "REPRODUCES",
    SOURCE_DRIFT:     "SOURCE DRIFT",
    UNEXPLAINED:      "UNEXPLAINED",
    MISMATCH_UNKNOWN: "MISMATCH (cause unknown)",
    UNVERIFIABLE:     "UNVERIFIABLE",
    ERROR:            "ERROR",
}

#: Statuses that mean "this receipt could not be shown to reproduce for a
#: reason nobody has diagnosed" — the exit-1 class. An unknown-cause
#: mismatch belongs here: it *might* be drift, but the bias is toward loud
#: failure, never toward the reassuring guess.
_ALARMING = (UNEXPLAINED, MISMATCH_UNKNOWN, ERROR)


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
    """All section dicts in order, descending into row containers —
    mirrors ``Report.data_sections()`` so nested sections aren't skipped."""
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
        md = node.get("metadata") or {}
        if md.get("query_spec"):
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
        md = node.get("metadata") or {}
        inp = md.get("input") or {}
        if inp.get("fingerprint"):
            out.setdefault(str(inp.get("table")), []).append(inp["fingerprint"])
    for fps in out.values():
        fps.sort()
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
    drifted = [i["table"] for i in inputs if not i["match"]]
    if drifted:
        return {**base, "status": SOURCE_DRIFT,
                "detail": "input fingerprint(s) changed for table(s): "
                          + ", ".join(drifted)}
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
          "exit_code": 0 | 1 | 2,
          "ok": bool,     # exit_code == 0
        }

    Only data-bearing sections (those carrying a ``dataset_fingerprint``)
    are classified; presentation-only sections have nothing to verify.
    Exit code: 0 when everything reproduces or is unverifiable, 2 when the
    only failures are diagnosed source drift, 1 when anything is
    unexplained, of unknown cause, or errored.
    """
    results: list[dict] = []
    for i, s in enumerate(_walk_sections(manifest.get("sections") or []), start=1):
        if not s.get("dataset_fingerprint"):
            continue
        label = s.get("id") or s.get("title") or f"section[{i}]"
        results.append(_verify_section(s, models, label))

    summary = {status: 0 for status in STATUS_LABELS}
    for r in results:
        summary[r["status"]] += 1

    if any(summary[s] for s in _ALARMING):
        exit_code = 1
    elif summary[SOURCE_DRIFT]:
        exit_code = 2
    else:
        exit_code = 0

    return {
        "report_name": manifest.get("report_name"),
        "schema_version": manifest.get("schema_version"),
        "sections": results,
        "summary": summary,
        "exit_code": exit_code,
        "ok": exit_code == 0,
    }
