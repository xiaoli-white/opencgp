from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    term: str
    definition: str = ""
    aliases: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)


class LearningStage(BaseModel):
    id: str
    title: str
    goal: str = ""
    node_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = 0


class OutlineNode(BaseModel):
    id: str
    stage_id: str = ""
    title: str
    summary: str = ""
    objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    estimated_minutes: int = 0
    lesson_id: str | None = None
    status: str = "planned"


class CourseBlueprint(BaseModel):
    course_id: str = ""
    version: int = 0
    overview: str = ""
    mode: str = "strict"
    grounded: bool = False
    learning_path: list[LearningStage] = Field(default_factory=list)
    outline: list[OutlineNode] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    provider: str = ""
    warning: str = ""
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    updated_at: float = 0.0


class LessonReview(BaseModel):
    id: str
    lesson_id: str
    action: str
    note: str = ""
    version: int = 0
    status: str = ""
    created_at: float = 0.0
