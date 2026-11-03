"""向量检索抽象端口（VectorStore）。

统一「分块入库 → 关键词/向量混合检索 → 引用溯源」接口，是 RAG 的底层能力，
也是幻觉抑制的检索兜底。M0 内置 SQLite FTS5 实现（关键词 bm25），
生产可切 pgvector / Qdrant / Milvus，业务代码不感知差异。

约定：
- ``add_chunks`` 以 ``source_id`` 为文档粒度，同一 source 重复写入前应先删除旧分块。
- ``search`` 返回 :class:`app.models.citation.Citation`，必须带来源与命中片段，供写作端溯源。
- ``healthcheck`` 为同步探活，返回能否对后端执行一次最小读写。
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.chunk import Chunk
from app.models.citation import Citation


@runtime_checkable
class VectorStore(Protocol):
    """通用检索端口。"""

    async def add_chunks(
        self,
        source_id: str,
        chunks: Sequence[Chunk],
        tenant_id: str = "",
    ) -> int:
        """写入某来源的全部分块，返回写入条数。"""
        ...

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
        tenant_id: str = "",
    ) -> list[Citation]:
        """按查询检索最相关的 top_k 分块，结果按相关度降序。"""
        ...

    async def delete_by_source(self, source_id: str, tenant_id: str = "") -> int:
        """删除某来源的全部分块，返回删除条数。"""
        ...

    async def list_sources(self, tenant_id: str = "") -> list[dict]:
        """列出某租户下的全部来源摘要。"""
        ...

    async def rename_source(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        """重命名来源（同时更新分块上的冗余名），返回是否命中。"""
        ...

    def healthcheck(self) -> bool:
        """探活：能否对后端执行一次最小读写。"""
        ...
