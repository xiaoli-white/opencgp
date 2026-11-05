from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation
from app.models.factcheck import CheckResult
from app.models.validation import ValidationReport


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
    validation: ValidationReport | None = None
    grounded: bool = False
    provider: str = ""
    prompt: str = ""
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)
