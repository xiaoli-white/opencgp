from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


class ResearchFinding(BaseModel):
    title: str = ""
    detail: str = ""
    evidence: list[str] = Field(default_factory=list)


class ResearchContradiction(BaseModel):
    claim: str = ""
    evidence: list[str] = Field(default_factory=list)


class ResearchBrief(BaseModel):
    summary: str = ""
    findings: list[ResearchFinding] = Field(default_factory=list)
    contradictions: list[ResearchContradiction] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ResearchRun(BaseModel):
    id: str
    tenant_id: str = ""
    user_id: str = ""
    topic: str
    depth: int = 2
    status: str = STATUS_QUEUED
    brief: ResearchBrief = Field(default_factory=ResearchBrief)
    citations: list[Citation] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    provider: str = ""
    warning: str = ""
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    web_used: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
