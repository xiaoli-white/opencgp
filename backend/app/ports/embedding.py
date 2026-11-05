from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class EmbeddingPort(Protocol):
    model: str
    dim: int

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...

    def healthcheck(self) -> bool:
        ...


EmbeddingProvider = EmbeddingPort
