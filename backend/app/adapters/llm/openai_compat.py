"""LLM 占位实现（OpenAI 兼容，M0 未实现）。

实现 :class:`app.ports.llm.LLMProvider` 端口。当前为占位：可正常构造，
调用 ``complete`` / ``stream`` 时抛出 :class:`NotImplementedError`。
后续接入真实 OpenAI 兼容接口（DeepSeek / 豆包 / 通义 / vLLM 等）。
"""

from __future__ import annotations

from typing import Any, Iterator, Sequence

from app.ports.llm import LLMProvider


class OpenAICompatLLM(LLMProvider):
    """OpenAI 兼容协议的 LLM 占位实现。"""

    def __init__(
        self, base_url: str = "", api_key: str = "", model: str = ""
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def complete(self, messages: Sequence[dict[str, Any]], **kwargs: Any) -> str:
        raise NotImplementedError("LLM adapter 尚未在 M0 Sprint 0 实现")

    def stream(
        self, messages: Sequence[dict[str, Any]], **kwargs: Any
    ) -> Iterator[str]:
        raise NotImplementedError("LLM adapter 尚未在 M0 Sprint 0 实现")
        yield ""  # pragma: no cover - 使函数成为生成器

    def healthcheck(self) -> bool:
        return False
