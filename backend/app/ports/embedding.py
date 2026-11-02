"""向量化抽象端口（EmbeddingProvider）。

为 VectorStore 预留的 embedding 扩展点：M0 默认关闭（``none``），
开启后混合检索会在关键词 bm25 之上叠加语义相似度，端口保持不变。
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """文本向量化端口。"""

    @property
    def dimension(self) -> int:
        """向量维度。"""
        ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量向量化，返回与输入等长的向量列表。"""
        ...

    def healthcheck(self) -> bool:
        """探活：模型是否可用。"""
        ...
