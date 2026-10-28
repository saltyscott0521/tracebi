"""A project's brand (``tracebi.yaml`` ``brand:``) compiled to CSS tokens.

``project_config.brand()`` reads and checks the block; :func:`brand_css`
turns it into the tokens every report page takes, injected right after
``tracebi.css`` and before ``reports/_theme.css`` (``stack.py``), so a
project's hand-written theme, a report's ``theme`` and its ``style.css``
still win, in that order.

What a brand sets, and nothing else:

- ``accent``: ``--tb-accent``, and from it, for contrast on each ground,
  ``--tb-accent-text`` (small text on the card and the accent wash),
  ``--tb-on-accent`` (text on an accent fill), ``--tb-surface-accent``, and
  the dark ground's pair ``--tb-dark-accent`` / ``--tb-dark-accent-text``,
  and the accent as a tile that carries text on either ground
  (``--tb-accent-fill`` / ``--tb-on-accent-fill``: Signal's lead KPI).
- ``palette``: ``--tb-chart-1..8`` (cycled to eight), and on the dark ground
  each colour lifted just enough to read there.
- ``font``: an inlined ``@font-face`` that ``--tb-font`` (and so the charts,
  ``--tb-chart-font``) names first, Geist after it.
- ``logo`` and ``name``: the firm mark in the masthead's mark slot
  (``.tb-masthead-mark``): the logo (``--tb-brand-logo``), then the name in
  small type beside it. The kicker stays the model's label.

A brand layers over the page's house theme (``tracebi/reports/house.py``):
the dark ground's colours are lifted against that theme's own dark card.

Presentation only: a brand changes how a page looks, never a number.
Reference: ``docs/reference/tracebi-yaml.md`` (``brand``).
"""

from __future__ import annotations

import base64
import os
import re

#: The grounds a colour is checked against: the house card in each mode.
LIGHT_CARD = "#ffffff"
DARK_CARD = "#141417"
_INK = "#18181b"
_DARK_INK = "#0d0f12"

#: An accent is a fill (bars, the focus ring, the hero): 3:1 against the
#: card it sits on, the WCAG floor for a graphic.
ACCENT_MIN = 3.0
_TEXT_MIN = 4.5
_DARK_ACCENT_MIN = 5.0
_DARK_TEXT_MIN = 7.0
_DARK_CHART_MIN = 3.5

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def is_hex(value) -> bool:
    return isinstance(value, str) and bool(_HEX.match(value.strip()))


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def luminance(hex_colour: str) -> float:
    def lin(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_colour)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """*a* moved *t* of the way to *b* (sRGB)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(x + (y - x) * t for x, y in zip(ra, rb))


def toward(colour: str, end: str, ground: str, minimum: float) -> str:
    """*colour* moved toward *end* (black or white) only as far as it takes
    to read at *minimum* against *ground*: the same hue, deepened or lifted."""
    colour = _hex(_rgb(colour))
    if contrast(colour, ground) >= minimum:
        return colour
    for step in range(1, 101):
        c = mix(colour, end, step / 100)
        if contrast(c, ground) >= minimum:
            return c
    return end


def check_accent(accent: str, where: str) -> None:
    """Refuse an accent that does not read as a fill on the card, naming a
    shade of the same hue that does."""
    ratio = contrast(accent, LIGHT_CARD)
    if ratio < ACCENT_MIN:
        fix = toward(accent, "#000000", LIGHT_CARD, ACCENT_MIN + 0.1)
        raise ValueError(
            f"{where}: brand.accent {accent} reads at {ratio:.1f}:1 on the white card; "
            f"an accent is a fill (bars, the focus ring, the hero) and needs "
            f"{ACCENT_MIN:.0f}:1. Use a deeper shade of it, such as {fix}.")


def accent_tokens(accent: str, dark_card: str = DARK_CARD) -> dict[str, str]:
    """The accent and what each ground needs from it."""
    accent = _hex(_rgb(accent))
    wash = mix(accent, "#ffffff", 0.92)
    text = toward(accent, "#000000", wash, _TEXT_MIN)
    dark = toward(accent, "#ffffff", dark_card, _DARK_ACCENT_MIN)
    dark_text = toward(dark, "#ffffff", dark_card, _DARK_TEXT_MIN)
    on = "#ffffff" if contrast("#ffffff", accent) >= _TEXT_MIN else _INK
    return {"--tb-accent": accent, "--tb-accent-text": text, "--tb-on-accent": on,
            "--tb-surface-accent": wash, "--tb-dark-accent": dark,
            "--tb-dark-accent-text": dark_text, **fill_tokens(accent)}


def fill_tokens(accent: str) -> dict[str, str]:
    """The accent as a tile that carries text, the same on both grounds."""
    accent = _hex(_rgb(accent))
    on = "#ffffff" if contrast("#ffffff", accent) >= _TEXT_MIN else _INK
    return {"--tb-accent-fill": accent, "--tb-on-accent-fill": on}


def palette_tokens(palette: list[str],
                   dark_card: str = DARK_CARD) -> tuple[dict[str, str], dict[str, str]]:
    """``--tb-chart-1..8`` for the light ground and the dark one: the brand's
    colours in its order, cycled to eight; on the dark card each is lifted
    only as far as it takes to read there."""
    light = [_hex(_rgb(c)) for c in palette]
    light = [light[i % len(light)] for i in range(8)]
    dark = [toward(c, "#ffffff", dark_card, _DARK_CHART_MIN) for c in light]
    name = "--tb-chart-{}".format
    return ({name(i + 1): c for i, c in enumerate(light)},
            {name(i + 1): c for i, c in enumerate(dark)})


_FONT_FORMAT = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
_IMAGE_TYPE = {".svg": "image/svg+xml", ".png": "image/png"}
#: The family name an inlined brand face is declared under.
BRAND_FAMILY = "TraceBi Brand"


def _data_uri(path: str, mime: str) -> str:
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"


def _block(selector: str, tokens: dict[str, str]) -> str:
    body = "".join(f"  {k}: {v};\n" for k, v in tokens.items())
    return f"{selector} {{\n{body}}}\n"


#: The firm mark in the masthead's mark slot (``.tb-brand``, written by the
#: build on a template page and by the kit's ``<Masthead>`` on an app page):
#: the logo, then the name in small type beside it, in the masthead's own ink
#: (so it reads on a banner and the editorial hero too). Never the kicker.
_MARK_CSS = (
    ".tb-brand { display: flex; width: fit-content; align-items: center; gap: var(--tb-space-2);"
    " margin-bottom: var(--tb-space-2); }\n"
    '.tb-masthead[data-tb-title="center"] .tb-brand { margin-inline: auto; }\n'
    ".tb-brand-name { font-family: var(--tb-font); font-size: var(--tb-text-sm);"
    " font-weight: 600; line-height: 1.2; letter-spacing: -0.005em; color: inherit; }\n"
    '.tb-masthead[data-tb-title="nav"] .tb-brand-name { font-size: var(--tb-text-xs); }\n')

#: The logo, drawn from ``--tb-brand-logo`` at its own aspect ratio; on a
#: filled ground (the hero, a banner) in the ground's own ink.
_LOGO_CSS = (
    ".tb-brand-logo { flex: none; display: block; height: 32px; aspect-ratio: RATIO;"
    " background: var(--tb-brand-logo) left center / contain no-repeat; }\n"
    '.tb-masthead[data-tb-title="nav"] .tb-brand-logo { height: 28px; }\n'
    ':root:not([data-tb-mode="dark"]) :where(.tb-article-head, '
    '.tb-masthead[data-tb-title="banner"]) .tb-brand-logo'
    " { filter: brightness(0) invert(1); }\n"
    ':root[data-tb-mode="dark"] .tb-masthead[data-tb-title="banner"] '
    ".tb-brand-logo { filter: brightness(0); }\n"
    '@media (prefers-color-scheme: dark) {\n'
    '  :root[data-tb-mode="auto"] .tb-article-head .tb-brand-logo { filter: none; }\n'
    '  :root[data-tb-mode="auto"] .tb-masthead[data-tb-title="banner"] '
    ".tb-brand-logo { filter: brightness(0); }\n}\n")


def logo_ratio(path: str) -> str:
    """The logo's width / height, as CSS ``aspect-ratio``: an SVG's
    ``viewBox`` (else its ``width`` and ``height``), a PNG's header; ``1``
    when the file does not say."""
    import struct

    with open(path, "rb") as f:
        head = f.read(65536)
    w = h = None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        w, h = struct.unpack(">II", head[16:24])
    else:
        text = head.decode("utf-8", "replace")
        tag = re.search(r"<svg\b[^>]*>", text, re.S)
        if tag:
            box = re.search(r'viewBox\s*=\s*["\']\s*[-\d.e]+[\s,]+[-\d.e]+[\s,]+([\d.e]+)[\s,]+([\d.e]+)',
                            tag.group(0))
            if box:
                w, h = float(box.group(1)), float(box.group(2))
            else:
                ww = re.search(r'\swidth\s*=\s*["\']([\d.]+)(?:px)?["\']', tag.group(0))
                hh = re.search(r'\sheight\s*=\s*["\']([\d.]+)(?:px)?["\']', tag.group(0))
                if ww and hh:
                    w, h = float(ww.group(1)), float(hh.group(1))
    if not w or not h:
        return "1"
    return f"{w:g} / {h:g}"


def brand_css(brand: dict, dark_card: str = DARK_CARD) -> str:
    """The brand as CSS: tokens on ``:root``, the palette and the accent
    tile again for the dark ground (the dark blocks of tracebi.css and of a
    house theme name their own), the font face, and the masthead mark, its
    dark-ground colours lifted against *dark_card* (the house theme's).
    ``""`` for no brand."""
    brand = {k: v for k, v in brand.items() if k != "theme"}
    if not brand:
        return ""
    out = ["/* the workspace's brand (tracebi.yaml brand:) */\n"]
    root: dict[str, str] = {}
    if brand.get("font"):
        ext = os.path.splitext(brand["font"])[1].lower()
        out.append(
            f'@font-face{{font-family:"{BRAND_FAMILY}";font-style:normal;font-display:swap;'
            f'font-weight:100 900;src:url("{_data_uri(brand["font"], "font/" + ext[1:])}") '
            f'format("{_FONT_FORMAT[ext]}")}}\n')
        root["--tb-font"] = (f'"{BRAND_FAMILY}", "Geist", system-ui, -apple-system, '
                             f'"Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif')
    dark: dict[str, str] = {}
    if brand.get("accent"):
        root.update(accent_tokens(brand["accent"], dark_card))
        dark.update(fill_tokens(brand["accent"]))
    if brand.get("palette"):
        light, dark_palette = palette_tokens(brand["palette"], dark_card)
        root.update(light)
        dark.update(dark_palette)
    if brand.get("logo"):
        mime = _IMAGE_TYPE[os.path.splitext(brand["logo"])[1].lower()]
        root["--tb-brand-logo"] = f'url("{_data_uri(brand["logo"], mime)}")'
    if root:
        out.append(_block(":root", root))
    if dark:
        out.append(_block(':root[data-tb-mode="dark"]', dark))
        out.append("@media (prefers-color-scheme: dark) {\n"
                   + _block(':root[data-tb-mode="auto"]', dark) + "}\n")
    if brand.get("name") or brand.get("logo"):
        out.append(_MARK_CSS)
    if brand.get("logo"):
        out.append(_LOGO_CSS.replace("RATIO", logo_ratio(brand["logo"])))
    return "".join(out)
