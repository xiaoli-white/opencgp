from __future__ import annotations

from app.models.web_search import WebResult
from app.ports.web_search import WebSearchPort


class NullWebSearch(WebSearchPort):
    name = "none"

    async def search(self, query: str, limit: int = 5) -> list[WebResult]:
        return []

    def healthcheck(self) -> bool:
        return False
