from __future__ import annotations

import base64
import glob
import os
from pathlib import Path
from typing import Sequence

from app.models.citation import Citation
from app.models.export import ExportChapter

CJK_SAMPLE = "向量检索课程内容学习目标参考来源章节"
MIN_CJK_FONT_BYTES = 1_000_000
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ASSET_ROOT = Path(__file__).resolve().parents[5]

_SYSTEM_CANDIDATES = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)
_GLOB_CANDIDATES = (
    "/usr/share/fonts/**/NotoSansCJK*SC*.tt*",
    "/usr/share/fonts/**/NotoSerifCJK*SC*.tt*",
    "/usr/share/fonts/**/wqy*.tt*",
    "/usr/share/fonts/**/DroidSansFallback*.ttf",
)


def resolve_font(configured: Sequence[str] | str = "") -> str:
    seen: set[str] = set()
    candidates: list[str] = []
    for path in _iter_candidates(configured):
        if not path or path in seen:
            continue
        seen.add(path)
        candidates.append(path)
    ordered = [item for item in candidates if not _is_collection(item)]
    ordered += [item for item in candidates if _is_collection(item)]
    for path in ordered:
        if _is_cjk_font(path):
            return path
    return ""


def _is_collection(path: str) -> bool:
    return path.lower().endswith(".ttc")


def _iter_candidates(configured: Sequence[str] | str):
    if isinstance(configured, str):
        configured = [configured]
    for item in configured:
        if item:
            yield item
    yield str(ASSET_ROOT / "wqy-microhei.ttc")
    yield str(ASSET_ROOT / "fonts" / "NotoSansSC-Regular.ttf")
    yield str(ASSET_ROOT / "fonts" / "NotoSansSC-Bold.ttf")
    yield str(PROJECT_ROOT / "wqy-microhei.ttc")
    yield str(PROJECT_ROOT / "fonts" / "NotoSansSC-Regular.ttf")
    yield str(PROJECT_ROOT / "fonts" / "NotoSansSC-Bold.ttf")
    for pattern in _GLOB_CANDIDATES:
        for path in sorted(glob.glob(pattern, recursive=True)):
            yield path
    for path in _SYSTEM_CANDIDATES:
        yield path


def _is_cjk_font(path: str) -> bool:
    try:
        if not os.path.isfile(path):
            return False
        if os.path.getsize(path) < MIN_CJK_FONT_BYTES:
            return False
    except OSError:
        return False
    try:
        from fontTools.ttLib import TTFont
    except Exception:
        return True
    try:
        font = TTFont(path, fontNumber=0)
        try:
            cmap = set(font.getBestCmap().keys())
        finally:
            font.close()
    except Exception:
        return False
    return all(ord(char) in cmap for char in CJK_SAMPLE)


def font_family_name(path: str) -> str:
    try:
        from fontTools.ttLib import TTFont

        font = TTFont(path, fontNumber=0)
        try:
            names = font["name"].names
            for record in names:
                if record.nameID == 4:
                    return str(record.toUnicode())
        finally:
            font.close()
    except Exception:
        return ""
    return ""


def font_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def data_uri(path: str) -> str:
    payload = base64.b64encode(font_bytes(path)).decode("ascii")
    return f"data:font/ttf;base64,{payload}"


def unique_citations(
    chapters: Sequence[ExportChapter], extra: Sequence[Citation]
) -> list[Citation]:
    seen: set[tuple[str, str]] = set()
    out: list[Citation] = []
    for citation in list(_iter_chapter_citations(chapters)) + list(extra):
        key = (citation.source_id, citation.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(citation)
    return out


def _iter_chapter_citations(chapters: Sequence[ExportChapter]):
    for chapter in chapters:
        for citation in chapter.citations:
            yield citation


def marker_map(citations: Sequence[Citation]) -> dict[tuple[str, str], str]:
    return {
        (citation.source_id, citation.chunk_id): f"E{index}"
        for index, citation in enumerate(citations, start=1)
    }


def citation_label(citation: Citation) -> str:
    name = citation.source_name or citation.source_id or "未知来源"
    return f"{name} · 片段#{citation.chunk_index + 1}"


def format_appendix(citations: Sequence[Citation]) -> list[str]:
    marks = marker_map(citations)
    lines: list[str] = []
    for citation in citations:
        marker = marks[(citation.source_id, citation.chunk_id)]
        lines.append(f"[{marker}] {citation_label(citation)}")
    return lines
