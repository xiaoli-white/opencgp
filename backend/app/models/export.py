from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation

FORMAT_MARKDOWN = "md"
FORMAT_HTML = "html"
FORMAT_EPUB = "epub"
FORMAT_PDF = "pdf"

EXPORT_FORMATS: tuple[str, ...] = (
    FORMAT_MARKDOWN,
    FORMAT_HTML,
    FORMAT_EPUB,
    FORMAT_PDF,
)

FORMAT_LABELS: dict[str, str] = {
    FORMAT_MARKDOWN: "Markdown",
    FORMAT_HTML: "HTML",
    FORMAT_EPUB: "EPUB",
    FORMAT_PDF: "PDF",
}

FORMAT_EXTENSIONS: dict[str, str] = {
    FORMAT_MARKDOWN: "md",
    FORMAT_HTML: "html",
    FORMAT_EPUB: "epub",
    FORMAT_PDF: "pdf",
}

FORMAT_CONTENT_TYPES: dict[str, str] = {
    FORMAT_MARKDOWN: "text/markdown; charset=utf-8",
    FORMAT_HTML: "text/html; charset=utf-8",
    FORMAT_EPUB: "application/epub+zip",
    FORMAT_PDF: "application/pdf",
}

SOURCE_COURSE = "course"
SOURCE_LONGFORM = "longform"
EXPORT_SOURCE_TYPES: tuple[str, ...] = (SOURCE_COURSE, SOURCE_LONGFORM)

THEME_LIGHT = "light"
THEME_DARK = "dark"
EXPORT_THEMES: tuple[str, ...] = (THEME_LIGHT, THEME_DARK)


class ExportChapter(BaseModel):
    title: str
    markdown: str = ""
    citations: list[Citation] = Field(default_factory=list)


class ExportDocument(BaseModel):
    source_type: str = SOURCE_COURSE
    source_id: str = ""
    title: str
    subtitle: str = ""
    author: str = ""
    created_at: float = 0.0
    front_matter: str = ""
    chapters: list[ExportChapter] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
