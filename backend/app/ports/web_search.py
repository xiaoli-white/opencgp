from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.web_search import WebResult


@runtime_checkable
class WebSearchPort(Protocol):
    name: str

    async def search(self, query: str, limit: int = 5) -> list[WebResult]:
        ...

    def healthcheck(self) -> bool:
        ...
