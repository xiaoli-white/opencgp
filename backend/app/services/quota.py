from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.quota import (
    GENERATION_KINDS,
    HISTORY_DEFAULT_DAYS,
    HISTORY_MAX_DAYS,
    QuotaLimits,
    QuotaUsage,
)
from app.ports.quota_repository import QuotaRepository
from app.services.errors import QuotaExceededError


class QuotaService:
    def __init__(self, repository: QuotaRepository) -> None:
        self.repository = repository

    def period(self) -> tuple[str, float]:
        now = datetime.now(QUOTA_TZ)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start.strftime("%Y-%m"), start.timestamp()

    def history(self, tenant_id: str, days: int = HISTORY_DEFAULT_DAYS) -> dict[str, Any]:
        span = max(1, min(int(days or HISTORY_DEFAULT_DAYS), HISTORY_MAX_DAYS))
        today = datetime.now(QUOTA_TZ).date()
        start_day = today - timedelta(days=span - 1)
        since = datetime(
            start_day.year, start_day.month, start_day.day, tzinfo=QUOTA_TZ
        ).timestamp()
        buckets: dict[str, dict[str, int]] = {}
        for offset in range(span):
            key = (start_day + timedelta(days=offset)).isoformat()
            buckets[key] = _empty_bucket()
        for row in self.repository.daily_usage(tenant_id, since):
            bucket = buckets.get(str(row.get("date") or ""))
            if bucket is None:
                continue
            _accumulate(bucket, str(row.get("kind") or ""), int(row.get("units") or 0))
        totals = _empty_bucket()
        ordered: list[dict[str, Any]] = []
        for key in sorted(buckets):
            item = {"date": key, **buckets[key]}
            ordered.append(item)
            for field, value in buckets[key].items():
                totals[field] = totals[field] + value
        return {
            "period": self.period()[0],
            "days": ordered,
            "totals": totals,
        }

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
            raise ValueError(f"unsupported usage kind: {kind!r}")
        limits = self.limits(tenant_id)
        usage = self.usage(tenant_id)
        if resolved in GENERATION_KINDS:
            used, cap = usage.generations, limits.monthly_generations
        elif resolved == "upload":
            used, cap = usage.uploads, limits.monthly_uploads
        else:
            used, cap = usage.storage_bytes, limits.storage_bytes
        if not self._unlimited(cap) and used + amount > cap:
            raise QuotaExceededError(f"monthly limit reached ({used}/{cap}); upgrade your plan or contact the administrator")
        self.repository.record(tenant_id, user_id, resolved, amount, ref_id)
        return self.usage(tenant_id)


QUOTA_TZ = timezone(timedelta(hours=8))


def _empty_bucket() -> dict[str, int]:
    return {"generations": 0, "uploads": 0, "storage_bytes": 0, "exec": 0, "image": 0}


def _accumulate(bucket: dict[str, int], kind: str, units: int) -> None:
    if kind in ("image",):
        bucket["image"] = bucket["image"] + units
    elif kind == "exec":
        bucket["exec"] = bucket["exec"] + units
    elif kind == "upload":
        bucket["uploads"] = bucket["uploads"] + units
    elif kind == "storage":
        bucket["storage_bytes"] = bucket["storage_bytes"] + units
    elif kind in GENERATION_KINDS:
        bucket["generations"] = bucket["generations"] + units
