from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.models.citation import (
    Citation,
    CitationReference,
    build_citation_references,
)
from app.models.factcheck import CheckResult
from app.models.validation import CitationCoverage, CitationGap, ValidationReport


class Evidence(BaseModel):
    marker: str
    citation: Citation


class GenerationResult(BaseModel):
    unit_id: str
    version: int
    topic: str
    top_k: int
    mode: str = "strict"
    content: str
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    factcheck: list[CheckResult] = Field(default_factory=list)
    validation: ValidationReport | None = None
    citation_coverage: CitationCoverage | None = None
    missing_evidence: list[CitationGap] = Field(default_factory=list)
    grounded: bool = False
    provider: str = ""
    prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def citation_references(self) -> list[CitationReference]:
        if self.evidence:
            return [
                CitationReference.from_citation(item.citation, marker=item.marker)
                for item in self.evidence
            ]
        return build_citation_references(self.citations)
