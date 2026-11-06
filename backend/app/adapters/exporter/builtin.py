from __future__ import annotations

from typing import Any

from app.adapters.exporter import epub as epub_renderer
from app.adapters.exporter import html as html_renderer
from app.adapters.exporter import markdown as markdown_renderer
from app.adapters.exporter import pdf as pdf_renderer
from app.adapters.exporter.common import font_family_name, resolve_font
from app.models.export import (
    EXPORT_FORMATS,
    FORMAT_EPUB,
    FORMAT_HTML,
    FORMAT_MARKDOWN,
    FORMAT_PDF,
    ExportDocument,
)
from app.ports.exporter import Exporter
from app.services.errors import ExportFormatError

_RENDERERS = {
    FORMAT_MARKDOWN: markdown_renderer.render,
    FORMAT_HTML: html_renderer.render,
    FORMAT_EPUB: epub_renderer.render,
    FORMAT_PDF: pdf_renderer.render,
}


class BuiltinExporter(Exporter):
    def __init__(
        self,
        font_regular: str = "",
        font_bold: str = "",
        pdf_margin_mm: int = 18,
    ) -> None:
        self.pdf_margin_mm = int(pdf_margin_mm or 18)
        self.font_path = resolve_font([font_regular, font_bold])
        self.font_name = font_family_name(self.font_path) if self.font_path else ""

    def export(
        self,
        content: ExportDocument | dict[str, Any],
        fmt: str,
        theme: str = "light",
        include_citations: bool = True,
        **kwargs: Any,
    ) -> bytes:
        document = (
            content
            if isinstance(content, ExportDocument)
            else ExportDocument.model_validate(content)
        )
        key = (fmt or "").strip().lower()
        renderer = _RENDERERS.get(key)
        if renderer is None:
            raise ExportFormatError(
                f"unsupported export format: {fmt} (supported: {', '.join(EXPORT_FORMATS)})"
            )
        return renderer(
            document,
            theme=theme,
            include_citations=include_citations,
            font_path=self.font_path,
            margin_mm=self.pdf_margin_mm,
            **kwargs,
        )

    def available_formats(self) -> dict[str, bool]:
        return {
            fmt: (pdf_renderer.available() if fmt == FORMAT_PDF else True)
            for fmt in EXPORT_FORMATS
        }

    def healthcheck(self) -> bool:
        return True
