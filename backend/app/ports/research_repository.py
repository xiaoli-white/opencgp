from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.research import ResearchRun


@runtime_checkable
class ResearchRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def save(self, run: ResearchRun) -> ResearchRun:
        ...

    def get(self, run_id: str, tenant_id: str | None = None) -> ResearchRun | None:
        ...

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[ResearchRun]:
        ...

    def delete(self, run_id: str, tenant_id: str | None = None) -> bool:
        ...
