"""
The figure tokenizer — the ONE parser for ``data-tb-*`` markup.

Three consumers share this module, by design (architecture v2 §2.1, flaw 1):
``report build`` (figure↔binding validation), the exploration-strip, and
``verify --file`` (the offline figure cross-check). A second implementation
— and especially a regex — would be a silent-receipt-weakening vector: a
figure one parser sees and another misses vanishes from both the build
check and the offline check at once. Never parse figure markup anywhere
else.

Built on the stdlib ``html.parser`` tokenizer. Malformed nesting fails
loudly (the ``insert_before`` philosophy): a page whose figures cannot be
extracted with certainty must not build, and must not verify.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional

#: Elements that never take a closing tag; they are never pushed on the
#: nesting stack and may not host stage blocks.
_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "source", "track", "wbr",
}

#: The figure kinds the grammar knows. "custom" is the free-form escape:
#: the author's own script draws it, the receipt still covers the bytes.
FIGURE_KINDS = ("value", "chart", "table", "custom")

#: The stage vocabulary is deliberately binary (exploration content is
#: stripped at final build; everything else ships). More states would just
#: be more laundering surface.
STAGES = ("exploration", "final")


class FigureError(ValueError):
    """Figure markup that cannot be trusted: malformed or contradictory."""


@dataclass(frozen=True)
class Figure:
    """One ``data-tb-figure`` element, as extracted from the page."""
    kind: str                        # value | chart | table | custom
    id: Optional[str]                # the stable figure address (may be None pre-assignment)
    binding: Optional[str] = None    # data-tb-binding
    cell: Optional[str] = None       # data-tb-cell (value figures)
    unverified: bool = False         # data-tb-unverified present
    note: Optional[str] = None       # data-tb-note
    tag: str = "div"
    attrs: dict = field(default_factory=dict, compare=False)


class _LineIndex:
    """Convert html.parser (line, offset) positions to absolute indices."""

    def __init__(self, text: str) -> None:
        self._starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self._starts.append(i + 1)

    def abs_pos(self, lineno: int, offset: int) -> int:
        return self._starts[lineno - 1] + offset


class _FigureParser(HTMLParser):
    """
    One pass over the page collecting figures, stage-block ranges, and the
    positions needed for id assignment. convert_charrefs is left on — we
    only read attributes, never character data.
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self._lines = _LineIndex(text)
        #: full element stack of (tagname, abs_start_of_open_tag)
        self._stack: list[tuple[str, int]] = []
        #: open stage blocks: (tagname, stage, abs_start, stack_depth_at_open)
        self._stage_stack: list[tuple[str, str, int, int]] = []
        self.figures: list[Figure] = []
        #: (figure_index, insertion_abs_pos) for figures missing an id
        self.missing_id_insertions: list[tuple[int, int]] = []
        #: absolute (start, end) ranges of OUTERMOST stage-marked elements,
        #: keyed by stage name
        self.stage_ranges: dict[str, list[tuple[int, int]]] = {}
        self.stage_meta: Optional[str] = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _abs(self) -> int:
        line, off = self.getpos()
        return self._lines.abs_pos(line, off)

    def _attr_insertion_pos(self, abs_start: int) -> int:
        """The index just after ``<tagname`` in the raw source."""
        raw = self.get_starttag_text() or ""
        m = re.match(r"<\s*[^\s/>]+", raw)
        if not m:  # pragma: no cover — html.parser guarantees a tag here
            raise FigureError(f"cannot locate tag name in {raw!r}")
        return abs_start + m.end()

    def _handle_figure(self, tag: str, attrs_list, abs_start: int) -> None:
        attrs = dict(attrs_list)
        if tag == "meta" and attrs.get("name") == "tracebi-stage":
            self.stage_meta = attrs.get("content")
        if "data-tb-figure" not in attrs:
            return
        kind = attrs.get("data-tb-figure") or ""
        if kind not in FIGURE_KINDS:
            raise FigureError(
                f"unknown figure kind '{kind}' on <{tag}>. "
                f"Kinds: {', '.join(FIGURE_KINDS)}"
            )
        binding = attrs.get("data-tb-binding")
        unverified = "data-tb-unverified" in attrs
        if binding and unverified:
            raise FigureError(
                f"figure '{attrs.get('id') or kind}' carries BOTH a binding "
                f"('{binding}') and data-tb-unverified — a figure is stamped "
                f"or it is honestly unverified, never both."
            )
        fig = Figure(
            kind=kind,
            id=attrs.get("id"),
            binding=binding,
            cell=attrs.get("data-tb-cell"),
            unverified=unverified,
            note=attrs.get("data-tb-note"),
            tag=tag,
            attrs=attrs,
        )
        if fig.id is None:
            self.missing_id_insertions.append(
                (len(self.figures), self._attr_insertion_pos(abs_start))
            )
        self.figures.append(fig)

    def _handle_stage_open(self, tag: str, attrs_list, abs_start: int) -> None:
        attrs = dict(attrs_list)
        stage = attrs.get("data-tb-stage")
        if stage is None:
            return
        if stage not in STAGES:
            raise FigureError(
                f"unknown stage '{stage}' on <{tag}>. Stages: "
                f"{', '.join(STAGES)} (the vocabulary is deliberately binary)."
            )
        if tag in _VOID:
            raise FigureError(
                f"<{tag}> cannot carry data-tb-stage — a void element has no "
                f"content to stage."
            )
        self._stage_stack.append((tag, stage, abs_start, len(self._stack)))

    # ── HTMLParser hooks ─────────────────────────────────────────────────

    def handle_starttag(self, tag, attrs):
        abs_start = self._abs()
        self._handle_figure(tag, attrs, abs_start)
        self._handle_stage_open(tag, attrs, abs_start)
        if tag not in _VOID:
            self._stack.append((tag, abs_start))

    def handle_startendtag(self, tag, attrs):
        # <div ... /> — treated as open+close with no content.
        self._handle_figure(tag, attrs, self._abs())
        attrs_d = dict(attrs)
        if "data-tb-stage" in attrs_d:
            raise FigureError(
                f"self-closing <{tag}/> cannot carry data-tb-stage — it has "
                f"no content to stage."
            )

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        # Pop the element stack to the matching open tag. html.parser does
        # not enforce nesting; we do — loudly.
        if not self._stack:
            raise FigureError(
                f"</{tag}> at position {self._abs()} closes nothing — "
                f"malformed nesting; figures cannot be extracted with "
                f"certainty."
            )
        open_tag, _open_pos = self._stack.pop()
        if open_tag != tag:
            raise FigureError(
                f"</{tag}> closes <{open_tag}> — mis-nested markup; figures "
                f"cannot be extracted with certainty."
            )
        # Close any stage block opened at this depth by this element.
        if self._stage_stack and self._stage_stack[-1][3] == len(self._stack) \
                and self._stage_stack[-1][0] == tag:
            _t, stage, abs_start, _d = self._stage_stack.pop()
            end = self._text.index(">", self._abs()) + 1
            if not self._stage_stack or all(s[1] != stage
                                            for s in self._stage_stack):
                # Outermost block of this stage: record the range.
                self.stage_ranges.setdefault(stage, []).append((abs_start, end))

    def close(self):
        super().close()
        if self._stage_stack:
            tag, stage, pos, _ = self._stage_stack[-1]
            raise FigureError(
                f"<{tag} data-tb-stage=\"{stage}\"> opened at position {pos} "
                f"is never closed — malformed nesting."
            )


def _parse(html_text: str) -> _FigureParser:
    p = _FigureParser(html_text)
    p.feed(html_text)
    p.close()
    return p


# ── Public API ──────────────────────────────────────────────────────────────


def extract_figures(html_text: str) -> list[Figure]:
    """
    Every ``data-tb-figure`` element in the page, in document order.

    Raises :class:`FigureError` on markup that cannot be trusted: unknown
    kinds, a figure carrying both a binding and the unverified mark,
    duplicate figure ids, or mis-nested tags.
    """
    figures = _parse(html_text).figures
    seen: dict[str, int] = {}
    for f in figures:
        if f.id is not None:
            if f.id in seen:
                raise FigureError(
                    f"duplicate figure id '{f.id}' — ids are the stable "
                    f"figure address and must be unique."
                )
            seen[f.id] = 1
    return figures


def assign_figure_ids(html_text: str) -> tuple[str, list[str]]:
    """
    Insert ``id="fig-<n>"`` on figure elements that lack one.

    Returns the (possibly rewritten) page and a warning per assignment —
    authors should set ids, because ids are how humans redirect agents.
    Counter skips ids already present.
    """
    parsed = _parse(html_text)
    if not parsed.missing_id_insertions:
        return html_text, []
    taken = {f.id for f in parsed.figures if f.id is not None}
    warnings: list[str] = []
    n = 1
    edits: list[tuple[int, str]] = []
    for fig_index, pos in parsed.missing_id_insertions:
        while f"fig-{n}" in taken:
            n += 1
        new_id = f"fig-{n}"
        taken.add(new_id)
        fig = parsed.figures[fig_index]
        edits.append((pos, f' id="{new_id}"'))
        warnings.append(
            f"figure ({fig.kind}"
            + (f", binding '{fig.binding}'" if fig.binding else "")
            + f") had no id — assigned '{new_id}'. Set ids: they are how "
            f"humans redirect agents."
        )
    out = html_text
    for pos, insertion in sorted(edits, reverse=True):
        out = out[:pos] + insertion + out[pos:]
    return out, warnings


def strip_stage(html_text: str, stage: str = "exploration") -> str:
    """
    Remove every outermost element carrying ``data-tb-stage="<stage>"`` —
    the final build deleting the exploration blocks, not a rewrite.

    Raises :class:`FigureError` on mis-nested markup rather than guessing
    at what to remove.
    """
    parsed = _parse(html_text)
    out = html_text
    for start, end in sorted(parsed.stage_ranges.get(stage, ()), reverse=True):
        out = out[:start] + out[end:]
    return out


def read_stage_meta(html_text: str) -> Optional[str]:
    """The ``<meta name="tracebi-stage">`` content, if the page carries one."""
    return _parse(html_text).stage_meta
