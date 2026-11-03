from __future__ import annotations

from pydantic import BaseModel, Field


class WebResult(BaseModel):
    title: str = ""
    url: str = ""
    snippet: str = ""
    sources: list[str] = Field(default_factory=list)
