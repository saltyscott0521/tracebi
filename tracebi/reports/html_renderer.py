"""
HTML renderer — produces clean, self-contained single-file HTML reports.

Features:
- Fully self-contained (no external CSS/JS dependencies)
- Responsive layout
- Styled tables with alternating rows and totals
- Charts rendered as inline SVG (no matplotlib needed)
- Cover section with report metadata
- Collapsible lineage section at the bottom
- Print-friendly CSS (also used as base for PDF via WeasyPrint)

Styling and page structure are overridable — see
``tracebi.reports.theme`` (Theme, custom shell templates) and the
``section_renderers`` argument for adding block types.

Optional: pip install weasyprint  (for PDF export)
          pip install jinja2      (only for custom shell templates)
"""

from __future__ import annotations

import base64
import io
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from tracebi.reports.base_renderer import BaseRenderer
from tracebi.reports.report import (
    Report, SectionType,
    TextSection, TableSection, ChartSection,
    MetricSection, RowSection,
    resolve_number_format,
)

logger = logging.getLogger(__name__)

# ── CSS ───────────────────────────────────────────────────────────────────

# The stylesheet moved to tracebi.reports.theme so it can be swapped or
# overridden without editing the renderer. Alias kept for compatibility.
from tracebi.reports.theme import DEFAULT_CSS as _CSS  # noqa: E402
from tracebi.reports.derive import (  # noqa: E402
    derive_column_labels, derive_number_formats,
)


class HTMLRenderer(BaseRenderer):
    """
    Renders a Report to a self-contained HTML file.

    Usage:
        from tracebi.reports import HTMLRenderer
        renderer = HTMLRenderer()
        manifest = renderer.render(report, "output/sales_report.html")

    To also produce a PDF (requires WeasyPrint):
        renderer = HTMLRenderer()
        renderer.render(report, "output/sales_report.html")
        renderer.render_pdf(report, "output/sales_report.pdf")
    """

    FORMAT = "html"

    def __init__(
        self,
        chart_dpi: int = 120,
        chart_style: str = "seaborn-v0_8-whitegrid",
        theme=None,
        template: Optional[str] = None,
        section_renderers: Optional[dict] = None,
        head_extra: str = "",
        body_extra: str = "",
        template_context: Optional[dict] = None,
        derive_defaults: bool = True,
    ):
        """
        Args:
            chart_dpi:    Retained for compatibility; HTML charts are SVG.
            chart_style:  Retained for compatibility; see
                          :mod:`tracebi.reports.chart`.
            theme:        A :class:`~tracebi.reports.theme.Theme`, or None for
                          the built-in one. Swap it to restyle without
                          touching code.
            template:     Jinja2 template string for the page shell. Takes
                          over the document structure (header, footer, script
                          tags) while section rendering stays intact. Requires
                          Jinja2; the built-in shell does not.
            section_renderers: ``{SectionType | str: callable(section) -> str}``
                          to add a block type or replace how one renders.
                          The extension point that used to require a fork.
            head_extra / body_extra: Markup injected into the built-in shell.
            template_context: Extra names available to a custom template.
        """
        from tracebi.reports.theme import Theme

        self.chart_dpi = chart_dpi
        self.chart_style = chart_style
        self.theme = theme or Theme.default()
        self.template = template
        self.head_extra = head_extra
        self.body_extra = body_extra
        self.template_context = dict(template_context or {})
        # Derived labels and number formats for anything the author left
        # unset. Off restores the previous raw output verbatim.
        self.derive_defaults = derive_defaults
        # Keyed by the section-type string so callers can pass either the
        # enum or a plain string, including one the framework doesn't know.
        self.section_renderers = {
            (k.value if hasattr(k, "value") else str(k)): v
            for k, v in (section_renderers or {}).items()
        }

    # ── Public API ─────────────────────────────────────────────────────────

    def _render(self, report: Report, output_path: str) -> None:
        html = self._build_html(report)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def serve(
        self,
        report: Report,
        port: int = 8080,
        output_path: Optional[str] = None,
        save_manifest: bool = False,
        open_browser: bool = True,
    ) -> str:
        """
        Render the report and serve it on a local HTTP server.

        Opens the browser automatically (pass ``open_browser=False`` to skip).
        Press Ctrl+C to stop the server.

        Args:
            report:       The Report to render.
            port:         Port to listen on (default 8080).
            output_path:  Where to write the HTML file. Defaults to a temp file.
            save_manifest: Save a manifest alongside the HTML (default False).
            open_browser: Auto-open the browser (default True).

        Returns:
            The URL being served, e.g. ``'http://localhost:8080'``.
        """
        import http.server
        import threading
        import tempfile
        import webbrowser

        if output_path is None:
            tmp = tempfile.mkdtemp()
            output_path = os.path.join(tmp, "report.html")

        self.render(report, output_path, save_manifest=save_manifest)

        directory = os.path.dirname(os.path.abspath(output_path))
        filename   = os.path.basename(output_path)
        url        = f"http://localhost:{port}/{filename}"

        class _Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, fmt, *args):  # silence request logs
                pass

        server = http.server.HTTPServer(("", port), _Handler)

        if open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()

        print(f"\n  TraceBi Report — '{report.name}'")
        print(f"  Serving at {url}")
        print(f"  Press Ctrl+C to stop.\n")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
        finally:
            server.server_close()

        return url

    def preview(
        self,
        report: Report,
        width: str = "100%",
        height: int = 800,
    ):
        """
        Render the report and display it inline in a Jupyter notebook.

        Requires: a running Jupyter kernel with IPython available.

        Args:
            report: The Report to render.
            width:  IFrame width (default ``'100%'``).
            height: IFrame height in pixels (default 800).
        """
        import tempfile

        try:
            from IPython.display import IFrame, display
        except ImportError:
            raise ImportError(
                "IPython is required for preview().\n"
                "Install with: pip install ipython"
            )

        tmp = tempfile.mkdtemp()
        output_path = os.path.join(tmp, "report.html")
        self.render(report, output_path, save_manifest=False)

        # Read and render as a srcdoc iframe so no server is needed
        with open(output_path, encoding="utf-8") as f:
            html_content = f.read()

        from IPython.display import HTML
        # Embed via srcdoc to avoid needing a running server
        escaped = html_content.replace('"', "&quot;")
        display(HTML(
            f'<iframe srcdoc="{escaped}" '
            f'width="{width}" height="{height}" '
            f'style="border:none;border-radius:6px;"></iframe>'
        ))

    def render_pdf(
        self,
        report: Report,
        output_path: str,
        save_manifest: bool = True,
        manifest_path: Optional[str] = None,
    ):
        """
        Render directly to PDF via WeasyPrint.
        Requires: pip install weasyprint
        """
        try:
            from weasyprint import HTML as WeasyHTML
        except ImportError:
            raise ImportError(
                "weasyprint is required for PDF rendering.\n"
                "Install with: pip install weasyprint"
            )
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        html_str = self._build_html(report)
        WeasyHTML(string=html_str).write_pdf(output_path)
        manifest = report.build_manifest(format="pdf", output_path=output_path)
        if save_manifest:
            mp = manifest_path or output_path + ".manifest.json"
            manifest.save(mp)
        return manifest

    # ── HTML building ──────────────────────────────────────────────────────

    def to_html(self, report: Report) -> str:
        """Return the report as a self-contained HTML string (no file I/O)."""
        return self._build_html(report)

    def _build_html(self, report: Report) -> str:
        from tracebi.reports.theme import render_shell

        return render_shell(
            title=self._esc(report.name),
            css=self.theme.css,
            cover=self._render_cover(report),
            sections="\n".join(self._render_section(s) for s in report.sections),
            lineage=self._render_lineage(report),
            template=self.template,
            head_extra=self.head_extra,
            body_extra=self.body_extra,
            context={"report": report, "theme": self.theme,
                     **self.template_context},
        )

    def _render_cover(self, report: Report) -> str:
        desc = f"<p>{self._esc(report._description)}</p>" if report._description else ""
        meta_rows = ""
        items = []
        if report._author:
            items.append(("Author", report._author))
        items.append(("Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
        for k, v in report._parameters.items():
            items.append((k.replace("_", " ").title(), str(v)))
        for label, value in items:
            meta_rows += f"""
            <tr>
              <td>{self._esc(label)}</td>
              <td>{self._esc(str(value))}</td>
            </tr>"""
        meta_table = f"""
        <table class="meta-table">
          {meta_rows}
        </table>""" if items else ""

        return f"""
  <div class="cover">
    <h1>{self._esc(report.name)}</h1>
    {desc}
    {meta_table}
  </div>"""

    def _render_section(self, section) -> str:
        # A registered renderer wins, so a caller can add a block type or
        # replace how a built-in one renders without editing this file.
        stype = getattr(section, "section_type", None)
        key = stype.value if hasattr(stype, "value") else str(stype)
        custom = self.section_renderers.get(key)
        if custom is not None:
            return custom(section)

        if section.section_type == SectionType.TEXT:
            return self._render_text(section)
        elif section.section_type == SectionType.TABLE:
            return self._render_table(section)
        elif section.section_type == SectionType.CHART:
            return self._render_chart(section)
        elif section.section_type == SectionType.SPACER:
            return f'<div style="height:{section.height * 16}px"></div>'
        elif section.section_type == SectionType.METRICS:
            return self._render_metrics(section)
        elif section.section_type == SectionType.ROW:
            return self._render_row(section)
        return ""

    def _render_metrics(self, section: MetricSection) -> str:
        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        cards = ""
        for m in section.metrics:
            delta_html = ""
            if m.delta is not None:
                up = m.delta >= 0
                cls = "good" if up == m.good_when_up else "bad"
                arrow = "▲" if up else "▼"
                delta_html = (
                    f'<div class="metric-delta {cls}">{arrow} {m.delta:+.1%}</div>'
                )
            cards += f"""
      <div class="metric-card">
        <div class="metric-label">{self._esc(m.label)}</div>
        <div class="metric-value">{self._esc(m.formatted_value())}</div>
        {delta_html}
      </div>"""

        return f"""
  <div class="section">
    {title_html}
    <div class="metric-row">{cards}
    </div>
  </div>"""

    def _render_row(self, section: RowSection) -> str:
        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        n = len(section.sections)
        weights = list(section.widths or [])
        weights += [1] * (n - len(weights))

        cols = ""
        for child, w in zip(section.sections, weights):
            cols += (
                f'<div class="layout-col" style="flex:{w}">'
                f'{self._render_section(child)}</div>'
            )

        return f"""
  <div class="section">
    {title_html}
    <div class="layout-row">{cols}
    </div>
  </div>"""

    def _render_text(self, section: TextSection) -> str:
        style = section.style
        css_class = {
            "heading1": "text-heading1",
            "heading2": "text-heading2",
            "note":     "text-note",
            "callout":  "text-callout",
        }.get(style, "text-normal")

        if style in ("heading1", "heading2"):
            # Heading text comes from the title, falling back to content when
            # only content was supplied.
            #
            # Content used to be dropped unconditionally, so callers worked
            # around it by passing the same string as both title and content.
            # Render the body only when it actually differs from the heading:
            # that recovers the genuinely-lost text without double-printing
            # the many existing call sites that use the duplication idiom.
            heading = section.title or section.content
            parts = [f'<div class="{css_class}">{self._esc(heading)}</div>']
            body = section.content
            if section.title and body and body != section.title:
                parts.append(f'<div class="text-normal">{self._esc(body)}</div>')
            return f'<div class="section">{"".join(parts)}</div>'

        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'
        content_html = f'<div class="{css_class}">{self._esc(section.content)}</div>'
        return f'<div class="section">{title_html}{content_html}</div>'

    def _render_table(self, section: TableSection) -> str:
        # Labels and formats the author did not supply, worked out from the
        # query's own metadata. Raw defaults put DIM_BRANCH.REGION and
        # 1705495.2200000002 on the page, which a human authoring one report
        # notices and something composing at volume does not. Anything set
        # explicitly on the section wins outright — see tracebi.reports.derive.
        labels = section.column_labels
        formats = section.number_formats
        if self.derive_defaults:
            raw = section.dataset.to_pandas() if section.dataset is not None else None
            cols = list(raw.columns) if raw is not None else []
            if section.columns:
                cols = [c for c in cols if c in section.columns]
            labels = derive_column_labels(cols, section.dataset, section.column_labels)
            if raw is not None:
                formats = derive_number_formats(
                    raw[cols] if cols else raw, section.dataset, section.number_formats
                )

        df = section.get_display_df(column_labels=labels)
        if df.empty:
            return '<div class="section"><em>No data</em></div>'

        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        # Determine numeric columns
        numeric_cols = set(df.select_dtypes(include="number").columns)

        # Map original column names to display names for all per-column options
        def _disp(col: str) -> str:
            return (labels or {}).get(col, col)

        fmt_map = {}
        if formats:
            for orig, fmt in formats.items():
                fmt_map[_disp(orig)] = resolve_number_format(fmt)

        neg_cols = {_disp(c) for c in (section.highlight_negatives or [])}
        width_map = {_disp(c): w for c, w in (section.column_widths or {}).items()}

        # Pre-compute min/max for color-scale columns
        scale_ranges: dict[str, tuple[float, float, str]] = {}
        for orig, hex_color in (section.color_scale or {}).items():
            disp = _disp(orig)
            if disp in numeric_cols:
                series = df[disp].dropna()
                if len(series):
                    scale_ranges[disp] = (
                        float(series.min()), float(series.max()),
                        hex_color.lstrip("#"),
                    )

        # Header
        headers = ""
        for col in df.columns:
            align_cls = ' class="num"' if col in numeric_cols else ""
            width_style = ""
            if col in width_map:
                width_style = f' style="min-width:{width_map[col] * 7}px"'
            headers += f"<th{align_cls}{width_style}>{self._esc(str(col))}</th>"

        # Body
        rows_html = ""
        for _, row in df.iterrows():
            cells = ""
            for col, val in row.items():
                is_num = col in numeric_cols
                classes = []
                if is_num:
                    classes.append("num")
                if col in neg_cols and is_num and pd.notna(val) and val < 0:
                    classes.append("neg")
                cls_attr = f' class="{" ".join(classes)}"' if classes else ""
                style_attr = ""
                if col in scale_ranges and pd.notna(val):
                    lo, hi, hex_color = scale_ranges[col]
                    style_attr = (
                        f' style="background:{self._scale_color(float(val), lo, hi, hex_color)}"'
                    )
                if is_num and col in fmt_map and pd.notna(val):
                    try:
                        display_val = fmt_map[col].format(val)
                    except Exception:
                        logger.warning(
                            "number_format %r failed for column %r value %r; "
                            "rendering raw value", fmt_map[col], col, val,
                        )
                        display_val = str(val) if pd.notna(val) else ""
                else:
                    display_val = str(val) if pd.notna(val) else ""
                cells += f"<td{cls_attr}{style_attr}>{self._esc(display_val)}</td>"
            rows_html += f"<tr>{cells}</tr>"

        # Totals
        tfoot_html = ""
        if section.totals:
            # df already carries display names, so match against display names
            # too — the same mapping fmt_map, neg_cols and width_map use.
            #
            # This used to re-apply column_labels to a name that was already a
            # label, so `totals` silently stopped working the moment a column
            # was renamed for presentation: no error, no warning, just an empty
            # cell where the total belonged. A missing total reads as "none was
            # asked for" rather than "we lost it", which is the worst way for a
            # financial report to be wrong.
            total_cols = {_disp(c) for c in section.totals} | set(section.totals)
            totals_cells = ""
            first = True
            for col in df.columns:
                is_num = col in numeric_cols
                align_cls = ' class="num"' if is_num else ""
                if first:
                    totals_cells += f'<td{align_cls}><strong>Total</strong></td>'
                    first = False
                    continue
                if col in total_cols:
                    try:
                        total_val = df[col].sum()
                        if col in fmt_map:
                            display_total = fmt_map[col].format(total_val)
                        else:
                            display_total = f"{total_val:,.2f}" if isinstance(total_val, float) else str(total_val)
                        totals_cells += f'<td{align_cls}><strong>{self._esc(display_total)}</strong></td>'
                    except Exception:
                        logger.warning(
                            "total for column %r could not be computed; "
                            "rendering empty cell", col, exc_info=True,
                        )
                        totals_cells += f'<td></td>'
                else:
                    totals_cells += f'<td></td>'
            tfoot_html = f"<tfoot><tr>{totals_cells}</tr></tfoot>"

        return f"""
  <div class="section">
    {title_html}
    <table class="data-table">
      <thead><tr>{headers}</tr></thead>
      <tbody>{rows_html}</tbody>
      {tfoot_html}
    </table>
  </div>"""

    def _render_chart(self, section: ChartSection) -> str:
        """
        Render a chart as inline SVG.

        This used to embed a base64 matplotlib PNG. SVG is diffable, can be
        restyled by the stylesheet, scales with its container, and needs no
        optional dependency — a base install previously rendered
        "matplotlib required" in place of every chart. See
        :mod:`tracebi.reports.chart`.
        """
        from tracebi.reports.chart import ChartSpec

        spec = ChartSpec.from_section(section)
        if not spec.rows or not spec.series:
            return ""

        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        return f"""
  <div class="section">
    {title_html}
    <div class="chart-container">
      {spec.to_svg()}
    </div>
  </div>"""


    def _render_lineage(self, report: Report) -> str:
        rows_html = ""
        for section in report.data_sections():
            if section.section_type not in (SectionType.TABLE, SectionType.CHART):
                continue
            ds = getattr(section, "dataset", None)
            if not ds:
                continue
            for step_idx, node in enumerate(ds.lineage, 1):
                conn = node.connector or {}
                badge_cls = f"badge-{node.operation}" if node.operation in (
                    "load", "filter", "transform", "join", "sort", "select", "rename"
                ) else "badge-other"
                rows_html += f"""
            <tr>
              <td>{self._esc(section.title or '—')}</td>
              <td>{self._esc(ds.name)}</td>
              <td>{step_idx}</td>
              <td><span class="badge {badge_cls}">{self._esc(node.operation)}</span></td>
              <td>{self._esc(node.description)}</td>
              <td>{self._esc(conn.get('connector_name', ''))}</td>
              <td>{self._esc(node.source or '')}</td>
              <td>{self._esc(node.timestamp)}</td>
            </tr>"""

        if not rows_html:
            return ""

        return f"""
  <div class="lineage-toggle">
    <details>
      <summary>Data Lineage — click to expand</summary>
      <table class="lineage-table">
        <thead>
          <tr>
            <th>Section</th><th>Dataset</th><th>Step</th>
            <th>Operation</th><th>Description</th>
            <th>Connector</th><th>Source</th><th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </details>
  </div>"""

    @staticmethod
    def _scale_color(val: float, lo: float, hi: float, hex_color: str) -> str:
        """Blend white → hex_color based on where val sits between lo and hi."""
        t = 0.0 if hi <= lo else max(0.0, min(1.0, (val - lo) / (hi - lo)))
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        blend = lambda c: int(255 + (c - 255) * t)  # noqa: E731
        return f"rgb({blend(r)},{blend(g)},{blend(b)})"

    @staticmethod
    def _esc(text: str) -> str:
        """HTML-escape a string."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
