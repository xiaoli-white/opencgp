from __future__ import annotations

from typing import Sequence


class NoneReranker:
    name = "none"

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int
    ) -> list[float]:
        return []

    def healthcheck(self) -> bool:
        return True
