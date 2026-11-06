from __future__ import annotations

import time
from typing import Sequence

from app.models.citation import Citation
from app.models.series import Series, Unit
from app.models.export import (
    SOURCE_SERIES,
    SOURCE_PIECE,
    ExportChapter,
    ExportDocument,
)
from app.models.piece import Piece
from app.ports.series_repository import SeriesRepository
from app.ports.piece_repository import PieceRepository
from app.services.errors import ExportSourceNotFoundError

DIFFICULTY_LABELS: dict[str, str] = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}
DEFAULT_AUTHOR = "OpenCGP"


class ExportService:
    def __init__(
        self,
        series_repository: SeriesRepository,
        piece_repository: PieceRepository,
        exporter: object | None = None,
    ) -> None:
        self.series_repository = series_repository
        self.piece_repository = piece_repository
        self.exporter = exporter

    def build_document(
        self,
        source_type: str,
        source_id: str,
        tenant_id: str | None = None,
        include_citations: bool = True,
    ) -> ExportDocument:
        if source_type == SOURCE_SERIES:
            return self._build_series(source_id, tenant_id, include_citations)
        if source_type == SOURCE_PIECE:
            return self._build_piece(source_id, tenant_id, include_citations)
        raise ExportSourceNotFoundError(f"unsupported export source type: {source_type}")

    def _build_series(
        self,
        series_id: str,
        tenant_id: str | None,
        include_citations: bool,
    ) -> ExportDocument:
        series = self.series_repository.get_series(series_id, tenant_id)
        if series is None:
            raise ExportSourceNotFoundError(f"course not found: {series_id}")
        units = [
            item
            for item in self.series_repository.list_units(series_id)
            if (item.content or "").strip()
        ]
        units.sort(key=lambda item: (item.order_index, item.created_at))
        chapters: list[ExportChapter] = []
        for unit in units:
            chapters.append(
                ExportChapter(
                    title=unit.title,
                    markdown=(unit.content or "").strip(),
                    citations=self._unit_citations(unit)
                    if include_citations
                    else [],
                )
            )
        front = self._series_front_matter(series, units)
        return ExportDocument(
            source_type=SOURCE_SERIES,
            source_id=series.id,
            title=series.title,
            subtitle=series.subtitle,
            author=DEFAULT_AUTHOR,
            created_at=series.created_at,
            front_matter=front,
            chapters=chapters,
            citations=self._unique([cite for ch in chapters for cite in ch.citations]),
            meta={
                "audience": series.audience,
                "difficulty": series.difficulty,
                "difficulty_label": DIFFICULTY_LABELS.get(
                    series.difficulty, series.difficulty
                ),
                "language": series.language,
                "unit_count": len(units),
                "updated_at": series.updated_at,
            },
        )

    def _build_piece(
        self,
        piece_id: str,
        tenant_id: str | None,
        include_citations: bool,
    ) -> ExportDocument:
        piece = self.piece_repository.get(piece_id, tenant_id)
        if piece is None:
            raise ExportSourceNotFoundError(f"long-form piece not found: {piece_id}")
        chapters: list[ExportChapter] = []
        for section in piece.outline:
            body = (section.content or "").strip()
            if not body:
                continue
            chapters.append(ExportChapter(title=section.title, markdown=body))
        document_citations = list(piece.citations or []) if include_citations else []
        if not chapters and (piece.content or "").strip():
            chapters.append(
                ExportChapter(
                    title=piece.title,
                    markdown=(piece.content or "").strip(),
                )
            )
        return ExportDocument(
            source_type=SOURCE_PIECE,
            source_id=piece.id,
            title=piece.title,
            subtitle=piece.profile.audience,
            author=DEFAULT_AUTHOR,
            created_at=piece.created_at,
            front_matter=self._piece_front_matter(piece),
            chapters=chapters,
            citations=self._unique(document_citations),
            meta={
                "genre": piece.profile.genre,
                "tone": piece.profile.tone,
                "audience": piece.profile.audience,
                "target_words": piece.target_words,
                "word_count": len((piece.content or "").strip()),
                "section_count": len(piece.outline),
                "mode": piece.last_mode,
                "updated_at": piece.updated_at,
            },
        )

    def _unit_citations(self, unit: Unit) -> list[Citation]:
        if unit.current_version <= 0:
            return []
        version = self.series_repository.get_version(
            unit.id, unit.current_version
        )
        if version is None:
            return []
        return list(version.citations or [])

    @staticmethod
    def _series_front_matter(series: Series, units: Sequence[Unit]) -> str:
        rows = [
            f"- Title: {series.title}",
            f"- Subtitle: {series.subtitle or '(not provided)'}",
            f"- Audience: {series.audience or '(not provided)'}",
            f"- Difficulty: {DIFFICULTY_LABELS.get(series.difficulty, series.difficulty)}",
            f"- Language: {series.language}",
            f"- Body chapters: {len(units)}",
            f"- Updated: {_date_of(series.updated_at)}",
        ]
        if units:
            rows.append("")
            rows.append("Chapter list:")
            for index, unit in enumerate(units, start=1):
                rows.append(f"{index}. {unit.title}")
        return "\n".join(rows)

    @staticmethod
    def _piece_front_matter(piece: Piece) -> str:
        rows = [
            f"- Genre: {piece.profile.genre}",
            f"- Tone: {piece.profile.tone or '(not provided)'}",
            f"- Audience: {piece.profile.audience or '(not provided)'}",
            f"- Target word count: {piece.target_words}",
            f"- Actual word count: {len((piece.content or '').strip())}",
            f"- Sections: {len(piece.outline)}",
            f"- Updated: {_date_of(piece.updated_at)}",
        ]
        if piece.outline:
            rows.append("")
            rows.append("Section list:")
            for index, section in enumerate(piece.outline, start=1):
                rows.append(f"{index}. {section.title}")
        return "\n".join(rows)

    @staticmethod
    def _unique(citations: Sequence[Citation]) -> list[Citation]:
        seen: set[tuple[str, str]] = set()
        out: list[Citation] = []
        for citation in citations:
            key = (citation.source_id, citation.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(citation)
        return out


def _date_of(timestamp: float) -> str:
    if not timestamp:
        return "Unknown"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))
