from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

TERMINAL_STATUSES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED)
JOB_STATUSES = (
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELED,
)

KIND_RESEARCH = "research"
KIND_PIECE_CREATE = "piece_create"
KIND_PIECE_GENERATE = "piece_generate"
KIND_PIECE_REWRITE = "piece_rewrite"
KIND_UNIT_GENERATE = "unit_generate"
KIND_BLUEPRINT_GENERATE = "blueprint_generate"
KIND_KB_EMBED_BACKFILL = "kb_embed_backfill"

JOB_KINDS = (
    KIND_RESEARCH,
    KIND_PIECE_CREATE,
    KIND_PIECE_GENERATE,
    KIND_PIECE_REWRITE,
    KIND_UNIT_GENERATE,
    KIND_BLUEPRINT_GENERATE,
    KIND_KB_EMBED_BACKFILL,
)

QUOTA_KIND_BY_JOB_KIND = {
    KIND_RESEARCH: "research",
    KIND_PIECE_CREATE: "piece",
    KIND_PIECE_GENERATE: "piece",
    KIND_PIECE_REWRITE: "piece",
    KIND_UNIT_GENERATE: "generate",
    KIND_BLUEPRINT_GENERATE: "blueprint",
}

ERROR_MAX_CHARS = 2000


class Job(BaseModel):
    id: str
    tenant_id: str = ""
    user_id: str = ""
    kind: str = ""
    status: str = STATUS_QUEUED
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str = ""
    progress: float = 0.0
    attempts: int = 0
    cancel_requested: bool = False
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def new_id(cls) -> str:
        return f"job_{uuid.uuid4().hex[:16]}"

    @classmethod
    def create(
        cls,
        kind: str,
        payload: dict[str, Any] | None = None,
        tenant_id: str = "",
        user_id: str = "",
    ) -> "Job":
        now = time.time()
        return cls(
            id=cls.new_id(),
            tenant_id=tenant_id or "",
            user_id=user_id or "",
            kind=kind,
            status=STATUS_QUEUED,
            payload=payload or {},
            created_at=now,
            updated_at=now,
        )

    def payload_summary(self) -> dict[str, Any]:
        return self.model_dump()


def is_terminal(status: str) -> bool:
    return (status or "") in TERMINAL_STATUSES
