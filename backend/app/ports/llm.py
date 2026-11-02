"""LLM 抽象端口（LLMProvider）。

统一大模型调用接口，屏蔽具体供应商差异（OpenAI 兼容、DeepSeek、豆包、通义、
Claude、本地 vLLM 等）。M0 先提供文本补全；后续 embedding / 视觉 / 绘图会拆分为
独立端口（Embedder / ImageProducer），与设计文档「文本/视觉/绘图/embedding 分离配置」一致。

约定：
- ``messages`` 为 OpenAI 风格消息列表：``[{"role": "user", "content": "..."}, ...]``。
- ``complete`` 返回完整响应文本；``stream`` 为逐段文本增量的迭代器。
"""

from __future__ import annotations

from typing import Any, Iterator, Protocol, Sequence, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """通用大模型端口。"""

    def complete(self, messages: Sequence[dict[str, Any]], **kwargs: Any) -> str:
        """一次性补全，返回完整响应文本。"""
        ...

    def stream(
        self, messages: Sequence[dict[str, Any]], **kwargs: Any
    ) -> Iterator[str]:
        """流式补全，逐段 yield 文本增量。"""
        ...

    def healthcheck(self) -> bool:
        """探活：能否连通供应商。"""
        ...
