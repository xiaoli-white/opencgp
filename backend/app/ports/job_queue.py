from __future__ import annotations

from typing import Awaitable, Callable, Protocol, runtime_checkable

JobHandler = Callable[[str], Awaitable[None]]


@runtime_checkable
class JobQueue(Protocol):
    name: str

    def enqueue(self, job_id: str) -> None:
        ...

    def start(self, handler: JobHandler) -> None:
        ...

    async def aclose(self) -> None:
        ...

    def stats(self) -> dict[str, int]:
        ...
