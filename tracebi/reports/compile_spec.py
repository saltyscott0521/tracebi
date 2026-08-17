"""
The spec → artifact compiler — ``tracebi migrate spec``.

A JSON ``ReportSpec`` survives as a *serialization*, not a lane
(architecture v2 §7): the one report form is the artifact package. This
module compiles a spec into that form — each section becomes a
default-component **figure** bound to the same ``DataRef``, so the section
enum ends its life as compile vocabulary rather than renderer control flow.

What the compile promises:

- **Every SectionType compiles.** text, table, chart, metrics, row, spacer —
  a test pins the coverage to the enum, so adding a section type without
  teaching the compiler is loud.
- **Markdown TextSections are honored** (field-notes #4): prose compiles
  through a small, deterministic markdown subset (headings, emphasis, code,
  lists, links, paragraphs) — escaped first, converted second, so content
  can never smuggle markup.
- **Numbers stay claims.** A metric whose value names a query column
  compiles to a live ``value`` figure (``data-tb-cell``); a literal value
  compiles to an honestly ``data-tb-unverified`` card. Nothing is inlined
  as dead text that reads as governed.
- **Nothing silently drops.** Presentation knobs the runtime has no
  equivalent for (totals rows, heat maps, column widths, metric deltas…)
  are reported as warnings, not swallowed.

The compiler is structural — it needs no models and executes no query. The
artifact it emits then goes through the ordinary ``report build`` gate,
where figure↔binding validation catches anything a wrong spec implied.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

from tracebi.reports.report import SectionType
from tracebi.spec import ReportSpec

# ── a small, deterministic markdown subset ──────────────────────────────────
# Escape first, convert second: content can never introduce live markup.

_MD_INLINE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\*(.+?)\*"), r"<em>\1</em>"),
    (re.compile(r"`(.+?)`"), r"<code>\1</code>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for pattern, repl in _MD_INLINE:
        out = pattern.sub(repl, out)
    return out


def md_to_html(text: str) -> str:
    """Convert the supported markdown subset to HTML, escaping everything.

    Blocks: ``#``/``##``/``###`` headings, ``-``/``*`` unordered lists,
    ``1.`` ordered lists, blank-line paragraphs. Inline: bold, italic,
    code, links. Unrecognized markdown passes through as escaped prose —
    degraded gracefully, never dropped.
    """
    blocks: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        m = re.match(r"(#{1,3})\s+(.*)", stripped)
        if m:
            level = len(m.group(1)) + 1          # '#' → h2: h1 is the page's
            blocks.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"[-*]\s+", lines[i].strip()):
                items.append(f"<li>{_inline(lines[i].strip()[2:])}</li>")
                i += 1
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"\d+\.\s+", lines[i].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(f"<li>{_inline(item)}</li>")
                i += 1
            blocks.append("<ol>" + "".join(items) + "</ol>")
            continue
        para = []
        while i < len(lines) and lines[i].strip():
            para.append(lines[i].strip())
            i += 1
        blocks.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(blocks)


# ── the compile ─────────────────────────────────────────────────────────────


@dataclass
class CompiledPackage:
    """What ``compile_spec`` returns: the package files plus honesty notes."""
    name: str
    files: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s or "section"


class _Compiler:
    def __init__(self, spec: ReportSpec) -> None:
        self.spec = spec
        self.bindings: dict[str, dict] = {}
        self.warnings: list[str] = []
        self._fig_ids: set[str] = set()

    # ── helpers ─────────────────────────────────────────────────────────

    def _binding_for(self, raw: dict, where: str) -> str:
        """Register the section's DataRef under a stable binding name."""
        base = _slug(raw.get("id") or raw.get("title") or where)
        name, n = base, 2
        while name in self.bindings and self.bindings[name] != raw["data"]:
            name, n = f"{base}_{n}", n + 1
        self.bindings[name] = raw["data"]
        return name

    def _fig_id(self, base: str) -> str:
        fid, n = f"fig-{base}", 2
        while fid in self._fig_ids:
            fid, n = f"fig-{base}-{n}", n + 1
        self._fig_ids.add(fid)
        return fid

    def _warn_dropped(self, raw: dict, where: str, knobs: tuple[str, ...]) -> None:
        dropped = [k for k in knobs if raw.get(k) not in (None, [], {}, False)]
        if dropped:
            self.warnings.append(
                f"{where}: no runtime equivalent for {', '.join(sorted(dropped))} "
                f"— restyle in style.css / script.js (config can restyle, "
                f"never re-source)"
            )

    @staticmethod
    def _title(raw: dict) -> str:
        t = raw.get("title")
        return f"    <h2>{html.escape(t)}</h2>\n" if t else ""

    # ── per-section compilers (one per SectionType; the test pins this) ──

    def compile_section(self, raw: dict, where: str) -> str:
        stype = raw.get("type")
        fn = {
            SectionType.TEXT.value:    self._text,
            SectionType.TABLE.value:   self._table,
            SectionType.CHART.value:   self._chart,
            SectionType.METRICS.value: self._metrics,
            SectionType.ROW.value:     self._row,
            SectionType.SPACER.value:  self._spacer,
        }.get(stype)
        if fn is None:
            raise ValueError(
                f"{where}: cannot compile unknown section type '{stype}'."
            )
        return fn(raw, where)

    def _text(self, raw: dict, where: str) -> str:
        style = raw.get("style", "normal")
        content = raw.get("content", "")
        title = self._title(raw)
        if style == "heading1":
            return f"  <h2>{_inline(raw.get('title') or content)}</h2>\n"
        if style == "heading2":
            return f"  <h3>{_inline(raw.get('title') or content)}</h3>\n"
        body = md_to_html(content)
        if style == "note":
            return f"{title}  <div class=\"tb-note\">{body}</div>\n"
        if style == "callout":
            return f"{title}  <div class=\"tb-callout\">{body}</div>\n"
        return f"{title}  <div>{body}</div>\n"

    def _table(self, raw: dict, where: str) -> str:
        if "data" not in raw:
            self.warnings.append(
                f"{where}: table has no data reference — compiled as an "
                f"empty placeholder"
            )
            return f"{self._title(raw)}  <table></table>\n"
        binding = self._binding_for(raw, where)
        attrs = ['data-tb-figure="table"', f'data-tb-binding="{binding}"',
                 f'id="{self._fig_id(binding)}"']
        if raw.get("columns"):
            cols = ",".join(raw["columns"])
            attrs.append(f'data-tb-columns="{html.escape(cols)}"')
        cls = {"striped": "tb-table--striped",
               "compact": "tb-table--compact"}.get(raw.get("style"))
        if cls:
            attrs.append(f'class="{cls}"')
        self._warn_dropped(raw, where, (
            "column_labels", "number_formats", "totals", "max_rows",
            "highlight_negatives", "color_scale", "column_widths",
        ))
        return (f"{self._title(raw)}"
                f"  <div class=\"tb-card\">\n"
                f"    <table {' '.join(attrs)}></table>\n"
                f"  </div>\n")

    def _chart(self, raw: dict, where: str) -> str:
        if "data" not in raw:
            self.warnings.append(
                f"{where}: chart has no data reference — compiled as an "
                f"empty placeholder"
            )
            return f"{self._title(raw)}  <div></div>\n"
        binding = self._binding_for(raw, where)
        y = raw.get("y")
        y_list = y if isinstance(y, list) else ([y] if y else [])
        attrs = ['data-tb-figure="chart"', f'data-tb-binding="{binding}"',
                 f'data-tb-type="{html.escape(str(raw.get("chart_type", "bar")))}"',
                 f'id="{self._fig_id(binding)}"']
        if raw.get("x"):
            attrs.append(f'data-tb-x="{html.escape(str(raw["x"]))}"')
        if y_list:
            attrs.append(f'data-tb-y="{html.escape(",".join(map(str, y_list)))}"')
        if raw.get("color"):
            attrs.append(f'data-tb-color="{html.escape(str(raw["color"]))}"')
        if raw.get("palette"):
            attrs.append(
                f'data-tb-palette="{html.escape(",".join(raw["palette"]))}"'
            )
        self._warn_dropped(raw, where, (
            "xlabel", "ylabel", "figsize", "show_values",
        ))
        return (f"{self._title(raw)}"
                f"  <div class=\"tb-card\">\n"
                f"    <div {' '.join(attrs)}></div>\n"
                f"  </div>\n")

    def _metrics(self, raw: dict, where: str) -> str:
        binding = self._binding_for(raw, where) if raw.get("data") else None
        cards: list[str] = []
        for j, m in enumerate(raw.get("metrics", [])):
            label = html.escape(str(m.get("label", "")))
            value = m.get("value")
            fmt = m.get("format")
            if m.get("delta") is not None:
                self.warnings.append(
                    f"{where}.metrics[{j}]: delta has no runtime equivalent "
                    f"— dropped; recompute it as a bound cell if it matters"
                )
            live = binding is not None and isinstance(value, str)
            if live:
                fid = self._fig_id(f"{binding}-{_slug(value)}")
                attrs = ['class="tb-kpi"', 'data-tb-figure="value"',
                         f'data-tb-binding="{binding}"',
                         f'data-tb-cell="{html.escape(value)}"',
                         f'id="{fid}"']
                if fmt:
                    attrs.append(f'data-tb-format="{html.escape(str(fmt))}"')
                cards.append(
                    f"    <div {' '.join(attrs)}>\n"
                    f"      <span class=\"tb-kpi-label\">{label}</span>\n"
                    f"      <span class=\"tb-kpi-value\"></span>\n"
                    f"    </div>\n"
                )
            else:
                # A literal card value is exactly what the unverified mark is
                # for: shown, and honestly not a claim against any binding.
                fid = self._fig_id(f"{_slug(m.get('label') or 'metric')}")
                cards.append(
                    f"    <div class=\"tb-kpi\" data-tb-figure=\"value\" "
                    f"data-tb-unverified data-tb-note=\"literal spec value\" "
                    f"id=\"{fid}\">\n"
                    f"      <span class=\"tb-kpi-label\">{label}</span>\n"
                    f"      <span class=\"tb-kpi-value\">"
                    f"{html.escape(str(value))}</span>\n"
                    f"    </div>\n"
                )
        return (f"{self._title(raw)}"
                f"  <div class=\"tb-grid\">\n{''.join(cards)}  </div>\n")

    def _row(self, raw: dict, where: str) -> str:
        if raw.get("widths"):
            self.warnings.append(
                f"{where}: widths has no runtime equivalent — children "
                f"compile to an equal-width tb-grid; adjust in style.css"
            )
        children = "".join(
            self.compile_section(s, f"{where}.sections[{i}]")
            for i, s in enumerate(raw.get("sections", []))
        )
        return f"{self._title(raw)}  <div class=\"tb-grid\">\n{children}  </div>\n"

    def _spacer(self, raw: dict, where: str) -> str:
        height = raw.get("height", 1)
        try:
            rem = max(1, int(height))
        except (TypeError, ValueError):
            rem = 1
        return f'  <div style="height:{rem}rem"></div>\n'


def compile_spec(
    spec: ReportSpec,
    theme_css: str = "",
    script_js: str = "",
) -> CompiledPackage:
    """Compile *spec* into artifact package files.

    Returns a :class:`CompiledPackage`: ``report.json`` (the same DataRefs,
    now bindings), ``template.html`` (default-component figures), plus
    ``style.css`` / ``script.js`` when the spec named a theme or script
    (pass their contents in — the compiler resolves nothing from disk).
    """
    c = _Compiler(spec)
    body = "".join(
        c.compile_section(dict(raw), f"sections[{i}]")
        for i, raw in enumerate(spec.sections)
    )

    title = html.escape(spec.name)
    page = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        f"<head><meta charset=\"utf-8\"><title>{title}</title></head>\n"
        "<body>\n"
        '<main class="tb-page">\n'
        f"  <h1>{title}</h1>\n"
        f"{body}"
        "</main>\n"
        "</body></html>\n"
    )

    report_json: dict = {"name": spec.name, "data": c.bindings}
    if spec.author:
        report_json["author"] = spec.author
    if spec.description:
        report_json["description"] = spec.description

    files = {
        "report.json": json.dumps(report_json, indent=2) + "\n",
        "template.html": page,
    }
    if theme_css:
        files["style.css"] = theme_css
    if script_js:
        files["script.js"] = script_js
    return CompiledPackage(name=spec.name, files=files, warnings=c.warnings)
