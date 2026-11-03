from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.quota import QuotaLimits, QuotaUsage


@runtime_checkable
class QuotaRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get_limits(self, tenant_id: str) -> QuotaLimits:
        ...

    def save_limits(self, tenant_id: str, limits: QuotaLimits) -> QuotaLimits:
        ...

    def usage(self, tenant_id: str, period_start: float) -> QuotaUsage:
        ...

    def record(
        self,
        tenant_id: str,
        user_id: str,
        kind: str,
        units: int = 1,
        ref_id: str = "",
    ) -> None:
        ...
