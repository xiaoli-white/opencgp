from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    source_id: str
    source_name: str
    chunk_index: int
    text: str
    start: int
    end: int
    meta: dict[str, Any] = Field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        return f"{self.source_id}:{self.chunk_index}"
