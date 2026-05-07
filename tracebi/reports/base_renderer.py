"""Abstract base renderer shared by ExcelRenderer, HTMLRenderer, etc."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from tracebi.reports.report import Report, ReportManifest


class BaseRenderer(ABC):
    """
    Abstract renderer. Subclass and implement ``_render()`` to add a new format.

    The public ``render()`` method handles directory creation, calls ``_render()``,
    builds the manifest, and optionally saves it alongside the output file.

    Usage (subclass):
        class MyRenderer(BaseRenderer):
            FORMAT = "my_format"

            def _render(self, report: Report, output_path: str) -> None:
                # write report to output_path
                ...

        manifest = MyRenderer().render(report, "output/report.myformat")
    """

    FORMAT: str = "base"

    @abstractmethod
    def _render(self, report: Report, output_path: str) -> None:
        """Write the rendered output to *output_path*."""
        ...

    def render(
        self,
        report: Report,
        output_path: str,
        save_manifest: bool = True,
        manifest_path: Optional[str] = None,
    ) -> ReportManifest:
        """
        Render *report* to *output_path* and return the manifest.

        Args:
            report:        The Report to render.
            output_path:   Destination file path.
            save_manifest: When True (default), write a ``.manifest.json``
                           alongside the output file.
            manifest_path: Override the manifest file path.

        Returns:
            ReportManifest: The manifest for this render run.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        self._render(report, output_path)
        manifest = report.build_manifest(format=self.FORMAT, output_path=output_path)
        if save_manifest:
            mp = manifest_path or output_path + ".manifest.json"
            manifest.save(mp)
        return manifest
