from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app.adapters.exporter import html as html_renderer
from app.adapters.exporter.common import PROJECT_ROOT, resolve_font
from app.models.export import ExportDocument
from app.services.errors import ExportUnavailableError


def available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True


def render(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    margin_mm: int = 18,
    **kwargs: Any,
) -> bytes:
    if not available():
        raise ExportUnavailableError(
            "PDF export is unavailable: weasyprint is missing in this environment. Install it and try again; markdown/html/epub are unaffected"
        )
    from weasyprint import HTML

    font_path = kwargs.get("font_path") or resolve_font()
    font_src = Path(font_path).as_uri() if font_path else ""
    markup = html_renderer.render_for_pdf(
        document,
        theme=theme,
        include_citations=include_citations,
        font_src=font_src,
        margin_mm=margin_mm,
    )
    buffer = io.BytesIO()
    HTML(string=markup, base_url=str(PROJECT_ROOT)).write_pdf(buffer)
    return buffer.getvalue()
