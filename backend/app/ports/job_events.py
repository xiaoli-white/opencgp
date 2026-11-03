from __future__ import annotations

from typing import Any, AsyncIterator, Protocol, runtime_checkable


@runtime_checkable
class JobEventBus(Protocol):
    name: str

    def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        ...

    def subscribe(self, job_id: str) -> AsyncIterator[dict[str, Any]]:
        ...

    async def aclose(self) -> None:
        ...

    def healthcheck(self) -> bool:
        ...
