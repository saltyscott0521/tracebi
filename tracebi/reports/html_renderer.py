"""
HTML renderer — produces clean, self-contained single-file HTML reports.

Features:
- Fully self-contained (no external CSS/JS dependencies)
- Responsive layout
- Styled tables with alternating rows and totals
- Charts rendered as inline SVG via matplotlib
- Cover section with report metadata
- Collapsible lineage section at the bottom
- Print-friendly CSS (also used as base for PDF via WeasyPrint)

Requires: pip install matplotlib
Optional: pip install weasyprint  (for PDF export)
"""

from __future__ import annotations

import base64
import io
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from tracebi.reports.base_renderer import BaseRenderer
from tracebi.reports.report import (
    Report, SectionType,
    TextSection, TableSection, ChartSection,
)

# ── CSS ───────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background: #f5f7fa;
    padding: 0;
}
.page {
    max-width: 1100px;
    margin: 0 auto;
    background: #ffffff;
    box-shadow: 0 2px 16px rgba(0,0,0,0.08);
    padding: 48px 56px 64px 56px;
}
/* Cover */
.cover {
    background: linear-gradient(135deg, #1F3864 0%, #2E74B5 100%);
    color: #fff;
    padding: 48px;
    border-radius: 6px;
    margin-bottom: 40px;
}
.cover h1 { font-size: 28px; font-weight: 700; margin-bottom: 10px; }
.cover p  { font-size: 14px; opacity: 0.85; margin-bottom: 6px; }
.cover .meta-table { margin-top: 20px; border-collapse: collapse; }
.cover .meta-table td {
    padding: 5px 18px 5px 0;
    font-size: 12px;
    opacity: 0.9;
}
.cover .meta-table td:first-child { font-weight: 600; opacity: 1; }

/* Sections */
.section { margin-bottom: 36px; }

/* Text styles */
.text-heading1 {
    font-size: 20px; font-weight: 700;
    color: #1F3864;
    border-bottom: 2px solid #2E74B5;
    padding-bottom: 6px;
    margin-bottom: 18px;
}
.text-heading2 {
    font-size: 15px; font-weight: 600;
    color: #2E74B5;
    margin-bottom: 12px;
}
.text-normal { font-size: 13px; line-height: 1.6; color: #333; }
.text-note {
    background: #FFF2CC;
    border-left: 4px solid #F5C518;
    padding: 10px 14px;
    font-size: 12px;
    border-radius: 0 4px 4px 0;
}
.text-callout {
    background: #DEEBF7;
    border-left: 4px solid #2E74B5;
    padding: 10px 14px;
    font-size: 12px;
    border-radius: 0 4px 4px 0;
}
.section-title {
    font-size: 14px; font-weight: 600;
    color: #1F3864;
    margin-bottom: 10px;
}

/* Tables */
.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-top: 4px;
}
.data-table thead tr {
    background: #1F3864;
    color: #fff;
}
.data-table thead th {
    padding: 9px 12px;
    text-align: left;
    font-weight: 600;
    letter-spacing: 0.3px;
    white-space: nowrap;
}
.data-table thead th.num { text-align: right; }
.data-table tbody tr:nth-child(even) { background: #EBF0F7; }
.data-table tbody tr:hover { background: #d6e4f0; }
.data-table tbody td {
    padding: 7px 12px;
    border-bottom: 1px solid #dde4ef;
}
.data-table tbody td.num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table tfoot tr {
    background: #D6DCE4;
    font-weight: 700;
    color: #1F3864;
}
.data-table tfoot td {
    padding: 8px 12px;
    border-top: 2px solid #1F3864;
}
.data-table tfoot td.num { text-align: right; }

/* Charts */
.chart-container {
    text-align: center;
    margin: 8px 0;
}
.chart-container img { max-width: 100%; height: auto; }

/* Lineage */
.lineage-toggle {
    margin-top: 48px;
    border-top: 1px solid #dde4ef;
    padding-top: 20px;
}
.lineage-toggle summary {
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    color: #2E74B5;
    padding: 6px 0;
    list-style: none;
}
.lineage-toggle summary::-webkit-details-marker { display: none; }
.lineage-toggle summary::before { content: "▶  "; }
details[open] summary::before { content: "▼  "; }
.lineage-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin-top: 12px;
}
.lineage-table th {
    background: #2F5496;
    color: #fff;
    padding: 6px 10px;
    text-align: left;
}
.lineage-table td {
    padding: 5px 10px;
    border-bottom: 1px solid #eee;
    vertical-align: top;
}
.lineage-table tr:nth-child(even) td { background: #f5f7fa; }
.badge {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}
.badge-load      { background: #DEEBF7; color: #1F3864; }
.badge-filter    { background: #E2EFDA; color: #375623; }
.badge-transform { background: #FFF2CC; color: #7D6608; }
.badge-join      { background: #FCE4D6; color: #843C0C; }
.badge-sort      { background: #EAD1DC; color: #4A235A; }
.badge-select    { background: #D9EAD3; color: #274E13; }
.badge-rename    { background: #CFE2F3; color: #1C4587; }
.badge-other     { background: #eeeeee; color: #333; }

/* Print */
@media print {
    body { background: #fff; }
    .page { box-shadow: none; padding: 20px; }
    .lineage-toggle { display: none; }
    details { display: none; }
}
"""


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

    def __init__(self, chart_dpi: int = 120, chart_style: str = "seaborn-v0_8-whitegrid"):
        """
        Args:
            chart_dpi:    DPI for embedded chart images (default 120).
            chart_style:  Matplotlib style for all charts.
        """
        self.chart_dpi = chart_dpi
        self.chart_style = chart_style

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

    def _build_html(self, report: Report) -> str:
        sections_html = "\n".join(
            self._render_section(s) for s in report.sections
        )
        lineage_html = self._render_lineage(report)
        cover_html = self._render_cover(report)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{self._esc(report.name)}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="page">
  {cover_html}
  {sections_html}
  {lineage_html}
</div>
</body>
</html>"""

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
        if section.section_type == SectionType.TEXT:
            return self._render_text(section)
        elif section.section_type == SectionType.TABLE:
            return self._render_table(section)
        elif section.section_type == SectionType.CHART:
            return self._render_chart(section)
        elif section.section_type == SectionType.SPACER:
            return f'<div style="height:{section.height * 16}px"></div>'
        return ""

    def _render_text(self, section: TextSection) -> str:
        style = section.style
        css_class = {
            "heading1": "text-heading1",
            "heading2": "text-heading2",
            "note":     "text-note",
            "callout":  "text-callout",
        }.get(style, "text-normal")

        if style in ("heading1", "heading2"):
            content = section.title or section.content
        else:
            title_html = ""
            if section.title:
                title_html = f'<div class="section-title">{self._esc(section.title)}</div>'
            content_html = f'<div class="{css_class}">{self._esc(section.content)}</div>'
            return f'<div class="section">{title_html}{content_html}</div>'

        return f'<div class="section"><div class="{css_class}">{self._esc(content)}</div></div>'

    def _render_table(self, section: TableSection) -> str:
        df = section.get_display_df()
        if df.empty:
            return '<div class="section"><em>No data</em></div>'

        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        # Determine numeric columns
        numeric_cols = set(df.select_dtypes(include="number").columns)

        # Number format map (adjusted for display column names)
        fmt_map = {}
        if section.number_formats:
            for orig, fmt in section.number_formats.items():
                disp = (section.column_labels or {}).get(orig, orig)
                fmt_map[disp] = fmt

        # Header
        headers = ""
        for col in df.columns:
            align_cls = ' class="num"' if col in numeric_cols else ""
            headers += f"<th{align_cls}>{self._esc(str(col))}</th>"

        # Body
        rows_html = ""
        for _, row in df.iterrows():
            cells = ""
            for col, val in row.items():
                is_num = col in numeric_cols
                align_cls = ' class="num"' if is_num else ""
                if is_num and col in fmt_map and pd.notna(val):
                    try:
                        display_val = fmt_map[col].format(val)
                    except Exception:
                        display_val = str(val) if pd.notna(val) else ""
                else:
                    display_val = str(val) if pd.notna(val) else ""
                cells += f"<td{align_cls}>{self._esc(display_val)}</td>"
            rows_html += f"<tr>{cells}</tr>"

        # Totals
        tfoot_html = ""
        if section.totals:
            totals_cells = ""
            first = True
            for col in df.columns:
                disp_col = (section.column_labels or {}).get(col, col)
                is_num = col in numeric_cols
                align_cls = ' class="num"' if is_num else ""
                if first:
                    totals_cells += f'<td{align_cls}><strong>Total</strong></td>'
                    first = False
                    continue
                if disp_col in section.totals or col in section.totals:
                    try:
                        total_val = df[col].sum()
                        if col in fmt_map:
                            display_total = fmt_map[col].format(total_val)
                        else:
                            display_total = f"{total_val:,.2f}" if isinstance(total_val, float) else str(total_val)
                        totals_cells += f'<td{align_cls}><strong>{self._esc(display_total)}</strong></td>'
                    except Exception:
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
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return '<div class="section"><em>matplotlib required for charts: pip install matplotlib</em></div>'

        df = section.dataset.to_pandas() if section.dataset else pd.DataFrame()
        if df.empty or not section.x:
            return ""

        title_html = ""
        if section.title:
            title_html = f'<div class="section-title">{self._esc(section.title)}</div>'

        try:
            plt.style.use(self.chart_style)
        except Exception:
            pass

        fig, ax = plt.subplots(figsize=section.figsize)

        y_cols = [section.y] if isinstance(section.y, str) else list(section.y or [])
        palette = section.palette or [
            "#2E74B5", "#ED7D31", "#A9D18E", "#FFC000",
            "#5B9BD5", "#70AD47", "#FF0000", "#7030A0",
        ]

        chart_type = section.chart_type.lower()

        try:
            if chart_type == "pie" and y_cols:
                ax.pie(
                    df[y_cols[0]],
                    labels=df[section.x],
                    autopct="%1.1f%%",
                    colors=palette[:len(df)],
                    startangle=140,
                )
            elif chart_type == "line":
                for i, col in enumerate(y_cols):
                    ax.plot(
                        df[section.x], df[col],
                        label=col,
                        color=palette[i % len(palette)],
                        linewidth=2,
                        marker="o",
                        markersize=4,
                    )
                ax.legend()
                ax.set_xlabel(section.xlabel or section.x)
                ax.set_ylabel(section.ylabel or (y_cols[0] if len(y_cols) == 1 else ""))
            elif chart_type in ("bar", "barh"):
                x_positions = range(len(df))
                width = 0.8 / max(len(y_cols), 1)
                for i, col in enumerate(y_cols):
                    offset = [x + i * width - (len(y_cols) - 1) * width / 2
                               for x in x_positions]
                    if chart_type == "barh":
                        ax.barh(offset, df[col], height=width,
                                color=palette[i % len(palette)], label=col)
                    else:
                        ax.bar(offset, df[col], width=width,
                               color=palette[i % len(palette)], label=col)
                tick_fn = ax.set_yticks if chart_type == "barh" else ax.set_xticks
                label_fn = ax.set_yticklabels if chart_type == "barh" else ax.set_xticklabels
                tick_fn(list(x_positions))
                label_fn(df[section.x].tolist(), rotation=30 if chart_type != "barh" else 0,
                         ha="right" if chart_type != "barh" else "right")
                if len(y_cols) > 1:
                    ax.legend()
                ax.set_xlabel(section.xlabel or (section.x if chart_type != "barh" else ""))
                ax.set_ylabel(section.ylabel or (y_cols[0] if len(y_cols) == 1 else ""))
            elif chart_type == "scatter" and len(y_cols) >= 1:
                ax.scatter(df[section.x], df[y_cols[0]],
                           color=palette[0], alpha=0.7)
                ax.set_xlabel(section.xlabel or section.x)
                ax.set_ylabel(section.ylabel or y_cols[0])
            else:
                # fallback: bar
                df.plot(x=section.x, y=y_cols, kind="bar", ax=ax,
                        color=palette[:len(y_cols)])
        except Exception as e:
            ax.text(0.5, 0.5, f"Chart error: {e}", transform=ax.transAxes,
                    ha="center", va="center")

        if section.title:
            ax.set_title(section.title, fontsize=13, fontweight="bold", pad=12)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=self.chart_dpi, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()

        return f"""
  <div class="section">
    {title_html}
    <div class="chart-container">
      <img src="data:image/png;base64,{img_b64}" alt="{self._esc(section.title or 'chart')}">
    </div>
  </div>"""

    def _render_lineage(self, report: Report) -> str:
        rows_html = ""
        for section in report.sections:
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
    def _esc(text: str) -> str:
        """HTML-escape a string."""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
