"""Score an agent's first-build attempt. Does not call an LLM.

    python evals/agent/score.py <project-dir>

Looks in the project copy for the report each case names, then checks the
package. Prints one row per case and the first-build success rate.
Exit 0 when every case passes, 1 when any fails, 2 when the scorer itself
cannot run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_CASES = Path(__file__).resolve().parent / "cases"
_FIGURE_RE = re.compile(
    r"<(div|span|table|section|p|h[1-6]|td|th)\b[^>]*\bdata-tb-figure="
    r"(['\"])[^'\"]+\2[^>]*>.*?</\1>",
    re.I | re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")
_MUSTACHE_RE = re.compile(r"\{\{.*?\}\}", re.S)
_REFUSAL_RE = re.compile(
    r"cannot|can't|does not|doesn't|not in the model|no such|unable",
    re.I,
)


def _queries(doc: dict):
    for binding in (doc.get("data") or {}).values():
        if isinstance(binding, dict) and isinstance(binding.get("query"), dict):
            yield binding["query"]


def _figure_kinds(doc: dict, template: str) -> set[str]:
    kinds = set(re.findall(r'data-tb-figure="([^"]+)"', template))
    kinds |= set(re.findall(r"data-tb-figure='([^']+)'", template))
    for fig in (doc.get("figures") or {}).values():
        if isinstance(fig, dict) and fig.get("kind"):
            kinds.add(str(fig["kind"]))
    return kinds


def _chart_types(doc: dict, template: str) -> set[str]:
    types = set(re.findall(r'data-tb-type="([^"]+)"', template))
    for fig in (doc.get("figures") or {}).values():
        if isinstance(fig, dict) and fig.get("chart_type"):
            types.add(str(fig["chart_type"]))
    return types


def _measures(doc: dict) -> set[str]:
    found = set()
    for query in _queries(doc):
        measures = query.get("measures")
        if isinstance(measures, list):
            found.update(str(m) for m in measures)
        elif isinstance(measures, dict):
            found.update(str(m) for m in measures)
    return found


def _dimensions(doc: dict) -> set[str]:
    found = set()
    for query in _queries(doc):
        for dim in query.get("dimensions") or []:
            found.add(str(dim))
    return found


def _text_outside_figures(template: str) -> str:
    stripped = _FIGURE_RE.sub(" ", template)
    stripped = _MUSTACHE_RE.sub(" ", stripped)
    return _TAG_RE.sub(" ", stripped)


def _tracebi(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tracebi.cli", *args],
        cwd=cwd, capture_output=True, text=True,
    )


def _check_refusal(project: Path, case: dict, report: str) -> str | None:
    answer = project / case.get("answer", f"reports/{report}/REFUSAL.md")
    if not answer.is_file():
        return "no refusal written"
    text = answer.read_text(encoding="utf-8")
    if not _REFUSAL_RE.search(text):
        return "refusal does not say the model cannot answer"
    if re.search(r"\d", text):
        return "refusal invents a number"
    if (project / "reports" / report / "report.json").is_file():
        return "built a report instead of refusing"
    return None


def _check_package(project: Path, case: dict, report: str) -> str | None:
    pkg = project / "reports" / report
    if not (pkg / "report.json").is_file() or not (pkg / "template.html").is_file():
        return "report folder missing"
    doc = json.loads((pkg / "report.json").read_text(encoding="utf-8"))
    template = (pkg / "template.html").read_text(encoding="utf-8")
    blob = template + "\n" + json.dumps(doc)

    missing_kinds = [k for k in case.get("figures") or [] if k not in _figure_kinds(doc, template)]
    if missing_kinds:
        return f"missing figure kind {missing_kinds[0]}"
    missing_types = [k for k in case.get("chart_types") or [] if k not in _chart_types(doc, template)]
    if missing_types:
        return f"missing chart type {missing_types[0]}"
    have_measures = _measures(doc)
    missing_measures = [m for m in case.get("measures") or [] if m not in have_measures]
    if missing_measures:
        return f"missing measure {missing_measures[0]}"
    have_dims = _dimensions(doc)
    missing_dims = [d for d in case.get("dimensions") or [] if d not in have_dims]
    if missing_dims:
        return f"missing dimension {missing_dims[0]}"
    if "limit" in case:
        limits = [q.get("limit") for q in _queries(doc)]
        if case["limit"] not in limits:
            return f"missing limit {case['limit']}"
    for key in case.get("filters") or []:
        if not any(key in (q.get("filters") or {}) for q in _queries(doc)):
            return f"missing filter {key}"
    for banned in case.get("forbid") or []:
        if banned in blob:
            return f"forbidden {banned}"
    if case.get("no_numeric_literals", True) and re.search(r"\d", _text_outside_figures(template)):
        return "numeric literal outside a figure"
    if case.get("build", True):
        built = _tracebi("report", "build", report, cwd=project)
        if built.returncode != 0:
            return "build failed"
        if case.get("verify_strict", True):
            manifest = project / "output" / f"{report}.html.manifest.json"
            verified = _tracebi("verify", str(manifest), "--strict", cwd=project)
            if verified.returncode != 0:
                return "verify --strict did not reproduce"
    return None


def score_case(project: Path, case_id: str, case: dict) -> tuple[bool, str]:
    report = case.get("report") or case_id
    if case.get("expect") == "refusal":
        reason = _check_refusal(project, case, report)
    else:
        reason = _check_package(project, case, report)
    return (reason is None, reason or "")


def load_cases(cases_dir: Path) -> list[tuple[str, dict]]:
    found = []
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        md = path.with_suffix(".md")
        if not md.is_file():
            raise SystemExit(f"{path.name} has no sibling {md.name}")
        found.append((path.stem, case))
    if not found:
        raise SystemExit(f"no cases in {cases_dir}")
    return found


def score_all(project: Path, cases_dir: Path = _CASES) -> list[tuple[str, bool, str]]:
    rows = []
    for case_id, case in load_cases(cases_dir):
        ok, reason = score_case(project, case_id, case)
        rows.append((case_id, ok, reason))
    return rows


def format_table(rows: list[tuple[str, bool, str]]) -> str:
    name_w = max(len("case"), *(len(r[0]) for r in rows))
    lines = [f"{'case':<{name_w}}  result  first failing check"]
    passed = 0
    for case_id, ok, reason in rows:
        if ok:
            passed += 1
        result = "pass" if ok else "fail"
        lines.append(f"{case_id:<{name_w}}  {result:<6}  {reason}")
    rate = 100.0 * passed / len(rows)
    lines.append(f"first-build success: {passed}/{len(rows)} ({rate:.0f}%)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python evals/agent/score.py <project-dir> [--cases DIR]",
              file=sys.stderr)
        return 2
    project = Path(args[0]).resolve()
    cases_dir = _CASES
    if "--cases" in args:
        cases_dir = Path(args[args.index("--cases") + 1]).resolve()
    if not project.is_dir():
        print(f"project not found: {project}", file=sys.stderr)
        return 2
    rows = score_all(project, cases_dir)
    print(format_table(rows))
    return 0 if all(ok for _, ok, _ in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
