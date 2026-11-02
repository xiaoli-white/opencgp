"""向量检索占位实现（关键词 + 朴素余弦向量，M0 未实现）。

实现 :class:`app.ports.vectorstore.VectorStore` 端口。当前为占位：
可正常构造，调用 ``add`` / ``vector_search`` / ``keyword_search`` 时抛出
:class:`NotImplementedError`。后续以「关键词匹配 + 朴素余弦相似度」落地，
生产再切 pgvector / Qdrant / Milvus。
"""

from __future__ import annotations

from typing import Any, Sequence

from app.ports.vectorstore import VectorStore


class SimpleVectorStore(VectorStore):
    """关键词 + 朴素向量的占位实现。"""

    def __init__(self, path: str = "data/vectorstore") -> None:
        self.path = path

    def add(
        self,
        documents: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]],
    ) -> list[str]:
        raise NotImplementedError("VectorStore adapter 尚未在 M0 Sprint 0 实现")

    def vector_search(
        self, query_vector: Sequence[float], top_k: int = 10
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("VectorStore adapter 尚未在 M0 Sprint 0 实现")

    def keyword_search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError("VectorStore adapter 尚未在 M0 Sprint 0 实现")

    def healthcheck(self) -> bool:
        return False
