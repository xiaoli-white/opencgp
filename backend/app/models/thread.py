from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.citation import Citation


class Thread(BaseModel):
    id: str
    course_id: str = ""
    lesson_id: str = ""
    title: str = ""
    created_at: float
    updated_at: float


class Message(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: float


class LessonThreadView(BaseModel):
    lesson_id: str
    thread_id: str
    title: str
    message_count: int
    messages: list[Message] = Field(default_factory=list)


class AskResult(BaseModel):
    lesson_id: str
    thread_id: str
    question: str
    answer: str
    user_message_id: str
    assistant_message_id: str
    citations: list[Citation] = Field(default_factory=list)
    grounded: bool = False
    provider: str = ""
    prompt: str = ""


class AmendResult(BaseModel):
    lesson_id: str
    instruction: str
    target: str = ""
    version: int
    previous_version: int
    mode: str = "strict"
    content: str
    citations: list[Citation] = Field(default_factory=list)
    note: str = ""
    provider: str = ""
    prompt: str = ""


class DrilldownResult(BaseModel):
    lesson_id: str
    thread_id: str
    source_message_id: str
    version: int
    content: str
    appended: str
    citations: list[Citation] = Field(default_factory=list)
    note: str = "drilldown"
