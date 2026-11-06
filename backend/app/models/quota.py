from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_MONTHLY_GENERATIONS = 200
DEFAULT_MONTHLY_UPLOADS = 100
DEFAULT_STORAGE_BYTES = 100 * 1024 * 1024

GENERATION_KINDS = (
    "generate",
    "amend",
    "ask",
    "blueprint",
    "research",
    "piece",
    "image",
    "exec",
)
TEXT_GENERATION_KINDS = ("generate", "amend", "ask", "blueprint", "research", "piece")
HISTORY_MAX_DAYS = 90
HISTORY_DEFAULT_DAYS = 30
IMAGE_KINDS = ("image",)
UPLOAD_KINDS = ("upload",)
STORAGE_KINDS = ("storage",)
QUOTA_KINDS = GENERATION_KINDS + UPLOAD_KINDS + STORAGE_KINDS


class QuotaLimits(BaseModel):
    monthly_generations: int = DEFAULT_MONTHLY_GENERATIONS
    monthly_uploads: int = DEFAULT_MONTHLY_UPLOADS
    storage_bytes: int = DEFAULT_STORAGE_BYTES


class QuotaUsage(BaseModel):
    period: str = ""
    generations: int = 0
    uploads: int = 0
    storage_bytes: int = 0


class UnitLock(BaseModel):
    unit_id: str
    tenant_id: str = ""
    user_id: str = ""
    user_name: str = ""
    token: str = ""
    heartbeat_at: float = 0.0
    expires_at: float = 0.0


class UsageDay(BaseModel):
    date: str = ""
    generations: int = 0
    uploads: int = 0
    storage_bytes: int = 0
    exec: int = 0
    image: int = 0


class UsageHistory(BaseModel):
    period: str = ""
    days: list[UsageDay] = []
    totals: UsageDay = Field(default_factory=UsageDay)
