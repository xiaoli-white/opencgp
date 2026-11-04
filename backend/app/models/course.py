from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.citation import Citation


class Course(BaseModel):
    id: str
    title: str
    subtitle: str = ""
    audience: str = ""
    difficulty: str = "intermediate"
    language: str = "zh"
    user_id: str = ""
    created_at: float
    updated_at: float


class Lesson(BaseModel):
    id: str
    course_id: str
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


class LessonVersion(BaseModel):
    id: str
    lesson_id: str
    version: int
    content: str
    citations: list[Citation] = Field(default_factory=list)
    mode: str = ""
    note: str = ""
    created_at: float
