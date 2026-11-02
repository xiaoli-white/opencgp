from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from app.ports.llm import LLMProvider


class DummyProvider(LLMProvider):
    is_placeholder = True

    def __init__(self, delay: float = 0.01) -> None:
        self.delay = delay

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        await asyncio.sleep(self.delay)
        return f"[dummy] 收到：{prompt}"

    async def stream_complete(
        self, prompt: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        text = await self.complete(prompt, **kwargs)
        for char in text:
            await asyncio.sleep(self.delay)
            yield char

    def healthcheck(self) -> bool:
        return True
