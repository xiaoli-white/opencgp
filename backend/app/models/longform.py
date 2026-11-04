from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation

GENRES = ("article", "report", "essay", "tutorial", "custom")
CITATION_POLICIES = ("required", "optional", "forbidden")
STATUS_DRAFT = "draft"
STATUS_GENERATING = "generating"
STATUS_COMPLETED = "completed"
SECTION_PLANNED = "planned"
SECTION_GENERATED = "generated"
MAX_SECTION_WORDS = 1200


class LongformProfile(BaseModel):
    genre: str = "article"
    tone: str = ""
    audience: str = ""
    pov: str = ""
    citation_policy: str = "optional"
    unit_name: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class OutlineSection(BaseModel):
    id: str
    title: str
    summary: str = ""
    target_words: int = 0
    content: str = ""
    status: str = SECTION_PLANNED


class Longform(BaseModel):
    id: str
    tenant_id: str = ""
    user_id: str = ""
    title: str
    profile: LongformProfile = Field(default_factory=LongformProfile)
    outline: list[OutlineSection] = Field(default_factory=list)
    content: str = ""
    status: str = STATUS_DRAFT
    current_version: int = 0
    target_words: int = 3000
    last_mode: str = ""
    profile_id: str = ""
    citations: list[Citation] = Field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0


class LongformVersion(BaseModel):
    id: str
    longform_id: str
    version: int
    content: str
    outline: list[OutlineSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    note: str = ""
    mode: str = ""
    created_at: float = 0.0
