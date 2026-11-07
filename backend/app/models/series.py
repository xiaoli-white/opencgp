from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from app.models.citation import (
    Citation,
    CitationReference,
    build_citation_references,
)


class Series(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    brief: str = ""
    audience: str = ""
    difficulty: str = "intermediate"
    language: str = "zh"
    language_explicit: bool = True
    user_id: str = ""
    profile_id: str = ""
    created_at: float
    updated_at: float


class Unit(BaseModel):
    id: str
    series_id: str
    order_index: int = 0
    title: str
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    content: str = ""
    status: str = "draft"
    current_version: int = 0
    last_mode: str = ""
    created_at: float
    updated_at: float


class UnitVersion(BaseModel):
    id: str
    unit_id: str
    version: int
    content: str
    citations: list[Citation] = Field(default_factory=list)
    mode: str = ""
    note: str = ""
    created_at: float

    @computed_field
    @property
    def citation_references(self) -> list[CitationReference]:
        return build_citation_references(self.citations, unit_id=self.unit_id)
