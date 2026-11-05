from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class RerankPort(Protocol):
    name: str

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int
    ) -> list[float]:
        ...

    def healthcheck(self) -> bool:
        ...
