from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field


class CitationReference(BaseModel):
    marker: str = ""
    source_id: str
    source_name: str
    chunk_id: str
    chunk_index: int
    start: int
    end: int
    text: str
    snippet: str = ""
    score: float = 0.0
    unit_id: str = ""
    unit_title: str = ""
    section_id: str = ""
    section_title: str = ""

    @classmethod
    def from_citation(
        cls,
        citation: "Citation",
        marker: str = "",
        unit_id: str = "",
        unit_title: str = "",
        section_id: str = "",
        section_title: str = "",
    ) -> "CitationReference":
        return cls(
            marker=marker or citation.marker,
            source_id=citation.source_id,
            source_name=citation.source_name,
            chunk_id=citation.chunk_id,
            chunk_index=int(citation.chunk_index),
            start=int(citation.start),
            end=int(citation.end),
            text=citation.text or citation.snippet,
            snippet=citation.snippet or citation.text,
            score=float(citation.score or 0.0),
            unit_id=unit_id,
            unit_title=unit_title,
            section_id=section_id,
            section_title=section_title,
        )


class Citation(BaseModel):
    source_id: str
    source_name: str
    chunk_id: str
    chunk_index: int
    text: str
    snippet: str
    score: float
    start: int
    end: int
    marker: str = ""
    sources: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    keyword_score: float | None = None
    vector_score: float | None = None
    rerank_score: float | None = None
    embedding_model: str | None = None
    rerank_model: str | None = None


def build_citation_references(
    citations: Sequence[Citation],
    unit_id: str = "",
    unit_title: str = "",
    section_id: str = "",
    section_title: str = "",
) -> list[CitationReference]:
    return [
        CitationReference.from_citation(
            citation,
            marker=citation.marker or f"E{index}",
            unit_id=unit_id,
            unit_title=unit_title,
            section_id=section_id,
            section_title=section_title,
        )
        for index, citation in enumerate(citations, start=1)
    ]
