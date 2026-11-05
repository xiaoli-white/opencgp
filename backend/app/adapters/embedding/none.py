from __future__ import annotations

from typing import Sequence


class NoneEmbedding:
    model = ""
    dim = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return []

    async def embed_query(self, text: str) -> list[float]:
        return []

    def healthcheck(self) -> bool:
        return False
