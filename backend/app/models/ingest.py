from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestResult(BaseModel):
    source_id: str
    source_name: str
    parser: str
    chunk_count: int
    char_count: int
    meta: dict[str, Any] = Field(default_factory=dict)
