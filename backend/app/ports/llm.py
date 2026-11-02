from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        ...

    def stream_complete(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        ...

    def healthcheck(self) -> bool:
        ...
