"""向量检索抽象端口（VectorStore）。

统一「向量 + 关键词」混合检索接口，是 RAG 的底层能力，也是幻觉抑制的检索兜底。
M0 内置简单实现（关键词匹配 + 朴素余弦向量），生产可切 pgvector / Qdrant / Milvus。

约定：
- ``documents`` 元素形如 ``{"id": str, "text": str, "metadata": dict}``。
- 检索结果形如 ``{"id": str, "score": float, "text": str, "metadata": dict}``。
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """通用向量检索端口。"""

    def add(
        self,
        documents: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
    ) -> list[str]:
        """写入文档及其对应向量，返回写入的 id 列表。"""
        ...

    def vector_search(
        self, query_vector: Sequence[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        """按向量相似度检索，返回 top_k 条结果。"""
        ...

    def keyword_search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """按关键词检索，返回 top_k 条结果。"""
        ...

    def healthcheck(self) -> bool:
        """探活：能否对后端执行一次最小读写。"""
        ...
