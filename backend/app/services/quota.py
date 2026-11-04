from __future__ import annotations

import time

from app.models.quota import (
    GENERATION_KINDS,
    QuotaLimits,
    QuotaUsage,
)
from app.ports.quota_repository import QuotaRepository
from app.services.errors import QuotaExceededError


class QuotaService:
    def __init__(self, repository: QuotaRepository) -> None:
        self.repository = repository

    def period(self) -> tuple[str, float]:
        now = time.localtime()
        start = time.mktime((now.tm_year, now.tm_mon, 1, 0, 0, 0, 0, 0, -1))
        return time.strftime("%Y-%m", now), float(start)

    def usage(self, tenant_id: str) -> QuotaUsage:
        name, start = self.period()
        usage = self.repository.usage(tenant_id, start)
        usage.period = name
        return usage

    def usage_by_kind(self, tenant_id: str) -> dict[str, int]:
        _name, start = self.period()
        return self.repository.usage_by_kind(tenant_id, start)

    def limits(self, tenant_id: str) -> QuotaLimits:
        return self.repository.get_limits(tenant_id)

    def set_limits(
        self,
        tenant_id: str,
        monthly_generations: int,
        monthly_uploads: int,
        storage_bytes: int,
    ) -> QuotaLimits:
        limits = QuotaLimits(
            monthly_generations=int(monthly_generations),
            monthly_uploads=int(monthly_uploads),
            storage_bytes=int(storage_bytes),
        )
        return self.repository.save_limits(tenant_id, limits)

    @staticmethod
    def _unlimited(cap: int) -> bool:
        return int(cap) <= 0

    def unlimited(self, tenant_id: str) -> dict[str, bool]:
        limits = self.limits(tenant_id)
        return {
            "generations": self._unlimited(limits.monthly_generations),
            "uploads": self._unlimited(limits.monthly_uploads),
            "storage": self._unlimited(limits.storage_bytes),
        }

    def remaining(self, tenant_id: str) -> dict[str, int]:
        limits = self.limits(tenant_id)
        usage = self.usage(tenant_id)
        return {
            "generations": -1
            if self._unlimited(limits.monthly_generations)
            else max(0, limits.monthly_generations - usage.generations),
            "uploads": -1
            if self._unlimited(limits.monthly_uploads)
            else max(0, limits.monthly_uploads - usage.uploads),
            "storage_bytes": -1
            if self._unlimited(limits.storage_bytes)
            else max(0, limits.storage_bytes - usage.storage_bytes),
        }

    def check_and_record(
        self,
        tenant_id: str,
        user_id: str,
        kind: str,
        units: int = 1,
        ref_id: str = "",
    ) -> QuotaUsage:
        resolved = (kind or "").strip().lower()
        amount = int(units)
        if resolved in GENERATION_KINDS:
            amount = max(1, amount)
        elif resolved in ("upload", "storage"):
            amount = max(0, amount)
        else:
            raise ValueError(f"不支持的用量类型: {kind!r}")
        limits = self.limits(tenant_id)
        usage = self.usage(tenant_id)
        if resolved in GENERATION_KINDS:
            used, cap = usage.generations, limits.monthly_generations
        elif resolved == "upload":
            used, cap = usage.uploads, limits.monthly_uploads
        else:
            used, cap = usage.storage_bytes, limits.storage_bytes
        if not self._unlimited(cap) and used + amount > cap:
            raise QuotaExceededError(f"本月已达上限 {used}/{cap}，请升级或联系管理员")
        self.repository.record(tenant_id, user_id, resolved, amount, ref_id)
        return self.usage(tenant_id)
