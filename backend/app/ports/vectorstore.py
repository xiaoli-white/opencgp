from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.chunk import Chunk
from app.models.citation import Citation


@runtime_checkable
class VectorStore(Protocol):
    async def add_chunks(
        self, source_id: str, chunks: Sequence[Chunk], tenant_id: str = ""
    ) -> int:
        ...

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
        tenant_id: str = "",
        min_score: float | None = None,
        embedding_provider: object | None = None,
        provider_id: str = "",
        vector_weight: float | None = None,
        return_meta: bool = False,
    ):
        ...

    async def search_vector(
        self, tenant_id: str, query_vec: Sequence[float], limit: int = 10
    ) -> list[tuple[str, float]]:
        ...

    async def upsert_embeddings(self, rows: Sequence[dict]) -> int:
        ...

    async def list_chunks(
        self, tenant_id: str = "", source_id: str = ""
    ) -> list[dict]:
        ...

    async def embedded_index(
        self, tenant_id: str = "", source_id: str = "", provider_id: str = ""
    ) -> dict[str, tuple[str, int]]:
        ...

    async def embedding_status(
        self,
        tenant_id: str = "",
        model: str = "",
        dim: int = 0,
        provider_id: str = "",
    ) -> dict:
        ...

    async def purge_stale_embeddings(
        self, tenant_id: str, model: str, dim: int, provider_id: str = ""
    ) -> dict:
        ...

    async def delete_by_source(self, source_id: str, tenant_id: str = "") -> int:
        ...

    async def list_sources(self, tenant_id: str = "") -> list[dict]:
        ...

    async def rename_source(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        ...

    def healthcheck(self) -> bool:
        ...
