from __future__ import annotations

import io
import time
import uuid
import zipfile
from typing import Any
from xml.sax.saxutils import escape

from app.adapters.exporter.common import (
    citation_label,
    font_bytes,
    marker_map,
    resolve_font,
    unique_citations,
)
from app.adapters.exporter.markdown import markdown_to_html
from app.models.export import THEME_DARK, ExportDocument

_XHTML_HEAD = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    "<!DOCTYPE html>\n"
    '<html xmlns="http://www.w3.org/1999/xhtml" '
    'xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">'
    "<head><meta charset=\"utf-8\" />"
    "<title>{title}</title>"
    '<link rel="stylesheet" type="text/css" href="style.css" />'
    "</head><body>"
)

_CONTAINER_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    "<rootfiles>"
    '<rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml" />'
    "</rootfiles></container>"
)


def build_style(theme: str = "light", has_font: bool = False) -> str:
    colors = {
        "bg": "#16181d" if theme == THEME_DARK else "#ffffff",
        "fg": "#e6edf3" if theme == THEME_DARK else "#1f2328",
        "muted": "#9aa4ae" if theme == THEME_DARK else "#656d76",
        "border": "#30363d" if theme == THEME_DARK else "#d8dee4",
    }
    font_face = ""
    if has_font:
        font_face = (
            "@font-face { font-family: 'CJKExport'; font-weight: 400 700; "
            "src: url('fonts/main.ttf') format('truetype'); }\n"
        )
    return (
        font_face
        + "body { background: %(bg)s; color: %(fg)s; "
        "font-family: 'CJKExport', 'Noto Sans SC', sans-serif; "
        "line-height: 1.75; margin: 0.6em 0.8em; }\n"
        "h1 { font-size: 1.7em; line-height: 1.3; }\n"
        "h2 { font-size: 1.3em; border-bottom: 1px solid %(border)s; padding-bottom: 0.2em; }\n"
        "h3 { font-size: 1.1em; }\n"
        "p { margin: 0.5em 0; }\n"
        "blockquote { margin: 0.6em 0; padding: 0.3em 0.8em; "
        "border-left: 3px solid %(border)s; color: %(muted)s; }\n"
        "code { font-size: 0.92em; }\n"
        "pre { border: 1px solid %(border)s; padding: 0.5em; overflow-x: auto; }\n"
        "table { border-collapse: collapse; width: 100%%; }\n"
        "th, td { border: 1px solid %(border)s; padding: 0.3em 0.5em; }\n"
        ".appendix { color: %(muted)s; font-size: 0.9em; }\n"
        % colors
    )


def render(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    **kwargs: Any,
) -> bytes:
    font_path = kwargs.get("font_path") or resolve_font()
    chapters = list(document.chapters)
    files: list[tuple[str, bytes]] = []
    manifest: list[str] = [
        '<item id="nav" href="nav.xhtml" '
        'media-type="application/xhtml+xml" properties="nav" />',
        '<item id="css" href="style.css" media-type="text/css" />',
    ]
    spine: list[str] = []

    if font_path:
        files.append(("OEBPS/fonts/main.ttf", font_bytes(font_path)))
        manifest.append('<item id="font" href="fonts/main.ttf" media-type="font/ttf" />')

    nav_items: list[tuple[str, str]] = []

    if document.front_matter.strip():
        body = "<h2>" + escape(
            "Course information" if document.source_type == "series" else "Document information"
        ) + "</h2>" + markdown_to_html(document.front_matter.strip())
        files.append(("OEBPS/frontmatter.xhtml", _page(document.title, body)))
        manifest.append(
            '<item id="frontmatter" href="frontmatter.xhtml" '
            'media-type="application/xhtml+xml" />'
        )
        spine.append('<itemref idref="frontmatter" />')
        nav_items.append(("frontmatter.xhtml", "Document information"))

    for index, chapter in enumerate(chapters, start=1):
        name = f"ch{index:03d}.xhtml"
        body = (
            "<h2>"
            + escape(chapter.title or f"Chapter {index}")
            + "</h2>"
            + markdown_to_html(chapter.markdown)
        )
        files.append((f"OEBPS/{name}", _page(chapter.title or f"Chapter {index}", body)))
        manifest.append(
            f'<item id="ch{index}" href="{name}" media-type="application/xhtml+xml" />'
        )
        spine.append(f'<itemref idref="ch{index}" />')
        nav_items.append((name, chapter.title or f"Chapter {index}"))

    if include_citations:
        citations = unique_citations(chapters, document.citations)
        if citations:
            marks = marker_map(citations)
            items = []
            for citation in citations:
                marker = marks[(citation.source_id, citation.chunk_id)]
                items.append(
                    f"<li>[{marker}] {escape(citation_label(citation))}</li>"
                )
            body = (
                '<div class="appendix"><h2>References</h2><ul>'
                + "".join(items)
                + "</ul></div>"
            )
            files.append(("OEBPS/appendix.xhtml", _page("References", body)))
            manifest.append(
                '<item id="appendix" href="appendix.xhtml" '
                'media-type="application/xhtml+xml" />'
            )
            spine.append('<itemref idref="appendix" />')
            nav_items.append(("appendix.xhtml", "References"))

    files.append(
        ("OEBPS/style.css", build_style(theme, bool(font_path)).encode("utf-8"))
    )
    files.append(("OEBPS/nav.xhtml", _nav(document.title, nav_items)))
    files.append(
        (
            "OEBPS/content.opf",
            _opf(document, manifest, spine).encode("utf-8"),
        )
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            zipfile.ZipInfo("META-INF/container.xml"),
            _CONTAINER_XML,
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for name, payload in files:
            archive.writestr(
                zipfile.ZipInfo(name), payload, compress_type=zipfile.ZIP_DEFLATED
            )
    return buffer.getvalue()


def _page(title: str, body: str) -> bytes:
    text = _XHTML_HEAD.format(title=escape(title or "Untitled")) + body + "</body></html>"
    return text.encode("utf-8")


def _nav(title: str, items: list[tuple[str, str]]) -> bytes:
    entries = "".join(
        f'<li><a href="{href}">{escape(label)}</a></li>' for href, label in items
    )
    body = (
        _XHTML_HEAD.format(title=escape(title))
        + '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
        + entries
        + "</ol></nav></body></html>"
    )
    return body.encode("utf-8")


def _opf(document: ExportDocument, manifest: list[str], spine: list[str]) -> str:
    modified = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    identifier = "urn:uuid:" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"{document.source_type}:{document.source_id}")
    )
    creator = (
        f"<dc:creator>{escape(document.author)}</dc:creator>" if document.author else ""
    )
    subtitle = (
        f"<dc:description>{escape(document.subtitle)}</dc:description>"
        if document.subtitle
        else ""
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid" xml:lang="zh-CN">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{identifier}</dc:identifier>'
        f"<dc:title>{escape(document.title)}</dc:title>"
        f"{subtitle}{creator}"
        "<dc:language>zh-CN</dc:language>"
        f'<meta property="dcterms:modified">{modified}</meta>'
        "</metadata>"
        "<manifest>" + "".join(manifest) + "</manifest>"
        "<spine>" + "".join(spine) + "</spine>"
        "</package>"
    )
