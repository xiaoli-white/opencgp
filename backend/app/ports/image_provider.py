from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ImageProvider(Protocol):
    name: str
    is_placeholder: bool

    async def generate(
        self, prompt: str, size: str = "1024x1024", n: int = 1
    ) -> list[bytes]:
        ...

    def healthcheck(self) -> bool:
        ...
