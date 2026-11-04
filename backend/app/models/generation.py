from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.citation import Citation
from app.models.factcheck import CheckResult


class Evidence(BaseModel):
    marker: str
    citation: Citation


class GenerationResult(BaseModel):
    lesson_id: str
    version: int
    topic: str
    top_k: int
    mode: str = "strict"
    content: str
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    factcheck: list[CheckResult] = Field(default_factory=list)
    grounded: bool = False
    provider: str = ""
    prompt: str = ""
