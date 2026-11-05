from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    sources: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
