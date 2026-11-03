from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.models.job import Job


@runtime_checkable
class JobRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, job: Job) -> Job:
        ...

    def get(self, job_id: str) -> Job | None:
        ...

    def list(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[Job]:
        ...

    def update_status(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> Job | None:
        ...

    def update_progress(self, job_id: str, progress: float) -> None:
        ...

    def request_cancel(self, job_id: str) -> Job | None:
        ...

    def has_cancel_request(self, job_id: str) -> bool:
        ...

    def recover_stale(self) -> int:
        ...

    def counts(self, tenant_id: str | None = None) -> dict[str, int]:
        ...

    def delete(self, job_id: str) -> bool:
        ...
