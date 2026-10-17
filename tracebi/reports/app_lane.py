"""
The React lane: a report package whose page is an ``app.jsx`` component.

The page is a React app compiled in the browser from TraceBi's fixed kit
(React, Recharts, lucide-react, Tailwind and the ``tracebi`` module); there is
no Node and no server. The data is the same: ``report.json`` bindings stamped
and fingerprinted at build. What changes is how the page is written.

Numbers keep their receipts when they are shown through the kit's figure
components (``Kpi``, ``Value``, ``Chart``, ``Spark``, ``Table``): each renders
the same ``data-tb-*`` element a template would hold and the runtime fills it
from the stamped rows. This module reads those components' literal props out
of the source so the build can record the claims — and refuse a binding or a
column that does not exist — without running the app. A number the app's own
code computes is not a claim; the page says so in its About block.

The attribute names and figure ids here mirror ``assets/_react_src/kit.jsx``.
"""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass, field

APP_JSX = "app.jsx"

#: What an app.jsx may import. Anything else fails the build.
KIT_MODULES = ("react", "react-dom", "react-dom/client", "react/jsx-runtime",
               "recharts", "lucide-react", "tracebi")

#: Kit components that are figures, and the figure kind each renders.
FIGURE_TAGS = {"Kpi": "value", "Value": "value", "Chart": "chart",
               "Spark": "chart", "Table": "table"}


class AppError(ValueError):
    """An app.jsx the build cannot ship, with the fix in the message."""


@dataclass
class KitFigure:
    tag: str
    props: dict = field(default_factory=dict)   # literal props only
    line: int = 0

    @property
    def kind(self) -> str:
        return FIGURE_TAGS[self.tag]


# ── Imports ────────────────────────────────────────────────────────────────

_IMPORT = re.compile(
    r"""^\s*import\s+(?:(?P<what>[\w*\s{},$]+?)\s+from\s+)?["'](?P<mod>[^"']+)["']""",
    re.MULTILINE)
_DYNAMIC = re.compile(r"""\b(?:import|require)\s*\(""")


def _strip_comments(src: str) -> str:
    """Blank out // and /* */ comments, keeping line numbers and strings."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", src[i:j]))
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def scan_imports(src: str) -> dict[str, list[str]]:
    """``{module: [imported names]}`` — refusing anything outside the kit."""
    code = _strip_comments(src)
    if _DYNAMIC.search(code):
        raise AppError(f"{APP_JSX}: dynamic import() / require() is not "
                       f"allowed; import from the kit at the top of the file.")
    found: dict[str, list[str]] = {}
    for m in _IMPORT.finditer(code):
        mod = m.group("mod")
        if mod not in KIT_MODULES:
            line = code.count("\n", 0, m.start()) + 1
            raise AppError(
                f"{APP_JSX} line {line}: imports \"{mod}\", which is not in the "
                f"TraceBi kit. A report is one offline file, so it can import "
                f"only: {', '.join(KIT_MODULES)}.")
        names = found.setdefault(mod, [])
        what = (m.group("what") or "").strip()
        brace = re.search(r"\{([^}]*)\}", what)
        if brace:
            for part in brace.group(1).split(","):
                name = part.strip().split(" as ")[0].strip()
                if name:
                    names.append(name)
        if "*" in what:
            names.append("*")
    return found


def icon_nodes(imports: dict[str, list[str]]) -> dict:
    """The lucide icons app.jsx imports, as data, refusing unknown names."""
    names = imports.get("lucide-react") or []
    if not names:
        return {}
    if "*" in names:
        raise AppError(f"{APP_JSX}: import icons by name — "
                       f"`import {{ TrendingUp }} from \"lucide-react\"` — so the "
                       f"page carries only those, not all of lucide.")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "assets", "lucide-icons.json")
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)["icons"]
    out = {}
    for name in names:
        base = name[:-4] if name.endswith("Icon") and name not in catalog else name
        if base not in catalog:
            raise AppError(f"{APP_JSX}: lucide-react has no icon \"{name}\".")
        out[base] = catalog[base]
    return out


# ── Kit figures ─────────────────────────────────────────────────────────────

def _skip_string(s: str, i: int) -> int:
    q = s[i]
    j = i + 1
    while j < len(s) and s[j] != q:
        j += 2 if s[j] == "\\" else 1
    return j + 1


def _skip_braces(s: str, i: int) -> int:
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c in "\"'`":
            j = _skip_string(s, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return j


_LITERAL_EXPR = re.compile(
    r"""^\{\s*(?:"([^"\\]*)"|'([^'\\]*)'|(-?\d+(?:\.\d+)?)|(true|false)|\[([^\[\]{}]*)\])\s*\}$""")


def _literal(expr: str):
    """A prop's value when it is a literal; ``None`` when it is code."""
    m = _LITERAL_EXPR.match(expr.strip())
    if not m:
        return None
    s1, s2, num, boolean, arr = m.groups()
    if s1 is not None or s2 is not None:
        return s1 if s1 is not None else s2
    if num is not None:
        return num
    if boolean is not None:
        return boolean == "true"
    items = re.findall(r"""["']([^"']*)["']""", arr)
    return ",".join(items)


def scan_figures(src: str) -> list[KitFigure]:
    """Every kit figure tag in *src*, with its literal props."""
    code = _strip_comments(src)
    figs: list[KitFigure] = []
    for m in re.finditer(r"<(%s)\b" % "|".join(FIGURE_TAGS), code):
        tag, i = m.group(1), m.end()
        props: dict = {}
        dynamic: set[str] = set()
        while i < len(code):
            while i < len(code) and code[i].isspace():
                i += 1
            if code.startswith("/>", i) or code.startswith(">", i):
                break
            if code.startswith("{", i):          # {...spread}
                i = _skip_braces(code, i)
                dynamic.add("...")
                continue
            nm = re.match(r"[A-Za-z_][\w-]*", code[i:])
            if not nm:
                i += 1
                continue
            name = nm.group(0)
            i += len(name)
            if not code.startswith("=", i):
                props[name] = True
                continue
            i += 1
            if code[i] in "\"'":
                j = _skip_string(code, i)
                props[name] = code[i + 1:j - 1]
                i = j
            elif code[i] == "{":
                j = _skip_braces(code, i)
                value = _literal(code[i:j])
                if value is None:
                    dynamic.add(name)
                else:
                    props[name] = value
                i = j
        line = code.count("\n", 0, m.start()) + 1
        for key in ("binding",) + (("cell",) if FIGURE_TAGS[tag] == "value" else ()) \
                + (("x", "y") if FIGURE_TAGS[tag] == "chart" else ()) + ("id",):
            if key in dynamic:
                raise AppError(
                    f"{APP_JSX} line {line}: <{tag}> {key}= must be a literal "
                    f"string, so the receipt can name what this figure shows. "
                    f"Compute the choice outside the figure (one figure per "
                    f"binding), or show the value with your own markup — it "
                    f"will not be a checked figure.")
        if "binding" not in props:
            raise AppError(f"{APP_JSX} line {line}: <{tag}> needs binding=\"…\" "
                           f"(a name under report.json \"data\").")
        figs.append(KitFigure(tag, props, line))
    return figs


def _join(v) -> str:
    return v if isinstance(v, str) else ""


def figure_id(kind: str, binding: str, key: str = "") -> str:
    """Mirror of kit.jsx ``figureId``."""
    parts = [p for p in ("fig", kind, binding, key) if p]
    return re.sub(r"-+$", "", re.sub(r"[^A-Za-z0-9_-]+", "-", "-".join(parts)))


def _humanise(ref: str) -> str:
    from tracebi.reports.derive import humanise
    return humanise(str(ref))


def _claim_element(f: KitFigure) -> str:
    """The data-tb-* element a kit figure renders, as the build writes it for
    the page's no-JavaScript view (and reads it as a claim)."""
    p = f.props
    esc = lambda v: html.escape(str(v), quote=True)  # noqa: E731

    def attrs_of(d: dict) -> str:
        return " ".join(f'{k}="{esc(v)}"' for k, v in d.items()
                        if isinstance(v, str) and v != "")
    if f.kind == "value":
        fid = p.get("id") or figure_id("value", p["binding"], _join(p.get("cell")))
        attrs = attrs_of({"data-tb-figure": "value", "data-tb-binding": p["binding"],
                          "data-tb-cell": p.get("cell"), "data-tb-format": p.get("format")})
        if f.tag == "Kpi":
            label = p.get("label") if isinstance(p.get("label"), str) else \
                _humanise(_join(p.get("cell")) or p["binding"])
            context = p.get("context") if isinstance(p.get("context"), str) else ""
            cls = "tb-kpi tb-kpi--lead" if p.get("lead") is True else "tb-kpi"
            return (f'<div class="{cls}" id="{esc(fid)}" {attrs}>'
                    f'<span class="tb-kpi-label">{html.escape(label)}</span>'
                    '<span class="tb-kpi-value"></span>'
                    + (f'<span class="tb-kpi-context">{html.escape(context)}</span>'
                       if context else "") + "</div>")
        label = _humanise(_join(p.get("cell")) or p["binding"])
        return (f'<li><span class="tb-kpi-label">{html.escape(label)}</span> '
                f'<span id="{esc(fid)}" {attrs}></span></li>')
    if f.kind == "chart":
        kind = "spark" if f.tag == "Spark" else "chart"
        fid = p.get("id") or figure_id(kind, p["binding"], _join(p.get("y")))
        attrs = attrs_of({"data-tb-figure": "chart", "data-tb-binding": p["binding"],
                          "data-tb-type": p.get("type") or ("area" if kind == "spark" else "bar"),
                          "data-tb-x": p.get("x"), "data-tb-y": p.get("y"),
                          "data-tb-color": p.get("color"),
                          "data-tb-value-format": p.get("valueFormat")})
        spark = ' class="tb-spark"' if kind == "spark" else ""
        return f'<div id="{esc(fid)}"{spark} {attrs}></div>'
    fid = p.get("id") or figure_id("table", p["binding"])
    attrs = attrs_of({"data-tb-figure": "table", "data-tb-binding": p["binding"],
                      "data-tb-columns": p.get("columns")})
    return f'<table id="{esc(fid)}" {attrs}></table>'


def static_html(figs: list[KitFigure]) -> str:
    """The page as a reader without JavaScript sees it — an email preview, a
    phone's file viewer: the kit figures, filled by the build like any
    template figure (KPIs, the charts' static pictures, tables). It is also
    where the build reads the claims. The app replaces it when it starts."""
    seen: dict[str, int] = {}
    groups: dict[str, list[str]] = {"kpi": [], "value": [], "chart": [],
                                    "spark": [], "table": []}
    for f in figs:
        el = _claim_element(f)
        fid = re.search(r'id="([^"]*)"', el).group(1)
        if fid in seen:
            raise AppError(
                f"{APP_JSX} lines {seen[fid]} and {f.line}: two kit figures "
                f"would share the id \"{fid}\". Give one an id=\"…\" — a figure "
                f"id is the receipt's address for one number.")
        seen[fid] = f.line
        key = ("kpi" if f.tag == "Kpi" else "spark" if f.tag == "Spark"
               else f.kind)
        groups[key].append(el)
    if not seen:
        return ""
    out = ['<div class="tb-page tb-app-static">',
           '<p class="tb-note">This report is an app. Open the file in a browser '
           "to use it; below are its figures as built.</p>"]
    if groups["kpi"]:
        out.append('<div class="tb-grid">' + "".join(groups["kpi"]) + "</div>")
    if groups["value"]:
        out.append('<ul class="tb-app-static-values">' + "".join(groups["value"]) + "</ul>")
    out += [f'<div class="tb-card">{el}</div>' for el in groups["chart"] + groups["table"]]
    if groups["spark"]:
        out.append('<div hidden>' + "".join(groups["spark"]) + "</div>")
    out.append("</div>")
    return "\n".join(out) + "\n"


#: report.json "look" for an app page: the attributes a template would put
#: on its own <html>, which an app.jsx does not have.
LOOK = {"mode": ("light", "dark", "auto"), "density": ("comfortable", "compact")}


def parse_look(raw, path: str) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict) or any(k not in LOOK for k in raw):
        raise ValueError(f"{path}: 'look' is an object with {', '.join(LOOK)}.")
    for key, value in raw.items():
        if value not in LOOK[key]:
            raise ValueError(f"{path}: look.{key} is one of "
                             f"{', '.join(LOOK[key])}, not {value!r}.")
    return dict(raw)


def shell_html(title: str, figs: list[KitFigure], look: dict | None = None) -> str:
    """The template a React package renders through: a mount point and the
    claims. Everything the reader sees is drawn by the app."""
    look = look or {}
    attrs = "".join(
        [f' data-tb-mode="{look["mode"]}"' if look.get("mode") in ("dark", "auto") else "",
         ' data-tb-density="compact"' if look.get("density") == "compact" else ""])
    return (
        f"<!doctype html>\n<html lang=\"en\" data-tb-app{attrs}>\n<head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title></head>\n<body>\n"
        "<div id=\"tb-app\">\n" + static_html(figs) + "</div>\n</body></html>\n")


def app_blocks_html(source: str, icons: dict) -> str:
    """The app source and its icons, as JSON data blocks (never as markup:
    script contents are not un-escaped, so the source rides as a string)."""
    def block(obj, bid):
        text = json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
        return f'<script type="application/json" id="{bid}">{text}</script>\n'
    out = block(source, "tracebi-app")
    if icons:
        out += block(icons, "tracebi-icons")
    return out


def libs_for(imports: dict[str, list[str]]) -> list[str]:
    """The vendored bundles a page needs, in load order."""
    libs = ["tailwind", "react"]
    if "recharts" in imports:
        libs.append("recharts")
    return libs
