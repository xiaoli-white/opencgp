from __future__ import annotations

import os
import time
from typing import Any

from app.adapters.exporter.common import (
    citation_label,
    data_uri,
    marker_map,
    resolve_font,
    unique_citations,
)
from app.adapters.exporter.markdown import markdown_to_html
from app.models.export import THEME_DARK, ExportDocument

_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#ffffff",
        "fg": "#1f2328",
        "muted": "#656d76",
        "border": "#d8dee4",
        "accent": "#0969da",
        "code_bg": "#f6f8fa",
        "quote_bg": "#f6f8fa",
    },
    THEME_DARK: {
        "bg": "#16181d",
        "fg": "#e6edf3",
        "muted": "#9aa4ae",
        "border": "#30363d",
        "accent": "#58a6ff",
        "code_bg": "#1f242c",
        "quote_bg": "#1f242c",
    },
}


def palette(theme: str) -> dict[str, str]:
    return _PALETTES.get(theme or "light", _PALETTES["light"])


def build_css(
    theme: str = "light",
    font_src: str = "",
    print_ready: bool = True,
    margin_mm: int = 18,
) -> str:
    colors = dict(palette(theme))
    colors["margin"] = f"{int(margin_mm)}mm {int(margin_mm)}mm {int(margin_mm) + 2}mm {int(margin_mm)}mm"
    parts: list[str] = []
    if font_src:
        parts.append(
            "@font-face { font-family: 'CJKExport'; font-weight: 400 700; "
            f"src: url({font_src}) format('truetype'); }}"
        )
    parts.append(
        """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: %(bg)s;
  color: %(fg)s;
  font-family: 'CJKExport', 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
  font-size: 11.5pt;
  line-height: 1.75;
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 18px 48px;
}
h1, h2, h3, h4 { line-height: 1.35; margin: 1.4em 0 0.6em; }
h1 { font-size: 26pt; }
h2 { font-size: 17pt; border-bottom: 1px solid %(border)s; padding-bottom: 6px; }
h3 { font-size: 13.5pt; }
p { margin: 0.6em 0; }
a { color: %(accent)s; text-decoration: none; }
code { background: %(code_bg)s; border-radius: 4px; padding: 1px 4px; font-size: 0.92em; }
pre { background: %(code_bg)s; border: 1px solid %(border)s; border-radius: 6px;
      padding: 10px 12px; overflow-x: auto; line-height: 1.5; }
pre code { background: transparent; padding: 0; }
blockquote { margin: 0.8em 0; padding: 6px 14px; border-left: 3px solid %(accent)s;
             background: %(quote_bg)s; color: %(muted)s; }
ul, ol { padding-left: 1.5em; }
table { width: 100%%; border-collapse: collapse; margin: 0.8em 0; font-size: 0.95em; }
th, td { border: 1px solid %(border)s; padding: 6px 8px; text-align: left; }
th { background: %(quote_bg)s; }
hr { border: none; border-top: 1px solid %(border)s; margin: 1.6em 0; }
.evidence { color: %(accent)s; font-size: 0.86em; }
.cover { border-bottom: 2px solid %(accent)s; margin-bottom: 1.2em; padding-bottom: 1em; }
.cover .subtitle { color: %(muted)s; font-size: 13pt; margin: 0.2em 0 0.8em; }
.cover .meta { color: %(muted)s; font-size: 10pt; }
.toc { background: %(quote_bg)s; border: 1px solid %(border)s; border-radius: 8px;
       padding: 12px 18px; margin: 1.2em 0 2em; }
.toc h2 { border: none; font-size: 13pt; margin: 0 0 0.4em; }
.toc ol { margin: 0; }
.chapter { margin-bottom: 2em; }
.appendix { border-top: 1px solid %(border)s; margin-top: 2em; padding-top: 1em;
            color: %(muted)s; font-size: 10pt; }
.appendix li { margin: 0.3em 0; }
"""
        % colors
    )
    if print_ready:
        parts.append(
            """
@page {
  size: A4;
  margin: %(margin)s;
  @bottom-center { content: counter(page); font-size: 9pt; color: #888; }
}
body { max-width: none; padding: 0; font-size: 10.5pt; }
h1 { break-before: page; }
h2 { break-after: avoid; }
pre, table, blockquote { break-inside: avoid; }
.chapter { break-before: page; }
.appendix { break-before: page; }
"""
            % colors
        )
    return "\n".join(parts)


def build_body(document: ExportDocument, include_citations: bool = True) -> str:
    blocks: list[str] = []
    cover_meta = []
    if document.author:
        cover_meta.append(f"Author: {document.author}")
    if document.created_at:
        cover_meta.append(
            "Created: " + time.strftime("%Y-%m-%d", time.localtime(document.created_at))
        )
    if document.chapters:
        cover_meta.append(f"Chapters: {len(document.chapters)}")
    cover = [f"<h1>{_esc(document.title)}</h1>"]
    if document.subtitle:
        cover.append(f'<p class="subtitle">{_esc(document.subtitle)}</p>')
    if cover_meta:
        cover.append(f'<p class="meta">{" · ".join(cover_meta)}</p>')
    blocks.append('<section class="cover">' + "".join(cover) + "</section>")

    if document.front_matter.strip():
        blocks.append(
            '<section class="front-matter">'
            + markdown_to_html(document.front_matter.strip())
            + "</section>"
        )

    if document.chapters:
        toc = ["<nav class=\"toc\"><h2>Contents</h2><ol>"]
        for index, chapter in enumerate(document.chapters, start=1):
            toc.append(
                f'<li><a href="#ch-{index}">{_esc(chapter.title or f"Chapter {index}")}</a></li>'
            )
        toc.append("</ol></nav>")
        blocks.append("".join(toc))

    for index, chapter in enumerate(document.chapters, start=1):
        blocks.append(
            f'<section class="chapter" id="ch-{index}">'
            + f"<h2>{_esc(chapter.title)}</h2>"
            + markdown_to_html(chapter.markdown)
            + "</section>"
        )

    if include_citations:
        citations = unique_citations(document.chapters, document.citations)
        if citations:
            marks = marker_map(citations)
            items = []
            for citation in citations:
                marker = marks[(citation.source_id, citation.chunk_id)]
                items.append(
                    f"<li><strong>[{marker}]</strong> {_esc(citation_label(citation))}</li>"
                )
            blocks.append(
                '<section class="appendix"><h2>References</h2><ul>'
                + "".join(items)
                + "</ul></section>"
            )
    return "\n".join(blocks)


def build_document_html(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    font_path: str = "",
    font_src: str = "",
    print_ready: bool = True,
    margin_mm: int = 18,
) -> str:
    if font_path and not font_src:
        font_src = data_uri(font_path)
    css = build_css(theme, font_src, print_ready, margin_mm)
    body = build_body(document, include_citations)
    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\" />"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />"
        f"<title>{_esc(document.title)}</title><style>{css}</style></head>"
        f"<body>{body}</body></html>"
    )


MAX_INLINE_FONT_BYTES = 2_000_000


def render(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    **kwargs: Any,
) -> bytes:
    font_path = kwargs.get("font_path") or resolve_font()
    if font_path and os.path.getsize(font_path) > MAX_INLINE_FONT_BYTES:
        font_path = ""
    html_text = build_document_html(
        document,
        theme=theme,
        include_citations=include_citations,
        font_path=font_path,
        print_ready=False,
    )
    return html_text.encode("utf-8")


def render_for_pdf(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    font_path: str = "",
    font_src: str = "",
    margin_mm: int = 18,
) -> str:
    return build_document_html(
        document,
        theme=theme,
        include_citations=include_citations,
        font_path=font_path,
        font_src=font_src,
        print_ready=True,
        margin_mm=margin_mm,
    )


def _esc(text: str) -> str:
    import html as _html

    return _html.escape(text or "")
