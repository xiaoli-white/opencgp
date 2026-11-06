from __future__ import annotations

import html
import re
import time
from typing import Any, Sequence

from app.adapters.exporter.common import format_appendix, unique_citations
from app.models.export import ExportDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ORDERED = re.compile(r"^(\d+)[.)]\s+(.*)$")
_BULLET = re.compile(r"^[-*+]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\|?[\s:|-]+\|[\s:|-]*$")


def render(
    document: ExportDocument,
    theme: str = "light",
    include_citations: bool = True,
    **_: Any,
) -> bytes:
    lines: list[str] = [f"# {document.title}"]
    if document.subtitle:
        lines.extend(["", f"> {document.subtitle}"])
    meta_bits: list[str] = []
    if document.author:
        meta_bits.append(f"Author: {document.author}")
    if document.created_at:
        meta_bits.append(f"Created: {_date(document.created_at)}")
    if document.chapters:
        meta_bits.append(f"Chapters: {len(document.chapters)}")
    if meta_bits:
        lines.extend(["", " · ".join(meta_bits)])

    if document.front_matter.strip():
        lines.extend(["", "## Course information" if document.source_type == "series" else "## Document information"])
        lines.extend(["", document.front_matter.strip()])

    for chapter in document.chapters:
        lines.extend(["", f"## {chapter.title}", "", chapter.markdown.strip()])

    if include_citations:
        citations = unique_citations(document.chapters, document.citations)
        if citations:
            lines.extend(["", "## References", ""])
            for line in format_appendix(citations):
                lines.append(f"- {line}")

    text = "\n".join(lines).strip() + "\n"
    return text.encode("utf-8")


def markdown_to_html(text: str) -> str:
    blocks: list[str] = []
    lines = (text or "").replace("\r\n", "\n").split("\n")
    index = 0
    total = len(lines)
    while index < total:
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            index += 1
            code_lines: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            blocks.append(
                "<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>"
            )
            continue
        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if stripped.startswith("|"):
            table_lines: list[str] = []
            while index < total and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            blocks.append(_table(table_lines))
            continue
        if _BULLET.match(stripped):
            items: list[str] = []
            while index < total and _BULLET.match(lines[index].strip()):
                items.append(_BULLET.match(lines[index].strip()).group(1))
                index += 1
            blocks.append(
                "<ul>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ul>"
            )
            continue
        if _ORDERED.match(stripped):
            items = []
            while index < total and _ORDERED.match(lines[index].strip()):
                items.append(_ORDERED.match(lines[index].strip()).group(2))
                index += 1
            blocks.append(
                "<ol>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + "</ol>"
            )
            continue
        if stripped.startswith(">"):
            quotes: list[str] = []
            while index < total and lines[index].strip().startswith(">"):
                quotes.append(lines[index].strip()[1:].strip())
                index += 1
            blocks.append(f"<blockquote>{_inline(' '.join(quotes))}</blockquote>")
            continue
        if set(stripped) <= {"-", "*", "_"} and len(stripped) >= 3:
            blocks.append("<hr />")
            index += 1
            continue
        paragraph: list[str] = []
        while index < total:
            candidate = lines[index].strip()
            if (
                not candidate
                or _HEADING.match(candidate)
                or _BULLET.match(candidate)
                or _ORDERED.match(candidate)
                or candidate.startswith("```")
                or candidate.startswith(">")
                or candidate.startswith("|")
            ):
                break
            paragraph.append(candidate)
            index += 1
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
        else:
            index += 1
    return "\n".join(blocks)


def _table(rows: Sequence[str]) -> str:
    body_rows = [row for row in rows if not _TABLE_SEP.match(row)]
    if not body_rows:
        return ""
    head_cells = _cells(body_rows[0])
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in head_cells)
    body = []
    for row in body_rows[1:]:
        cells = _cells(row)
        body.append(
            "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in cells) + "</tr>"
        )
    return (
        "<table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def _cells(row: str) -> list[str]:
    text = row.strip().strip("|")
    return [cell.strip() for cell in text.split("|")]


_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_EVIDENCE = re.compile(r"\[(E\d+)\]")


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC.sub(r"<em>\1</em>", escaped)
    escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    escaped = _EVIDENCE.sub(r'<span class="evidence">[\1]</span>', escaped)
    return escaped


def _date(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))
