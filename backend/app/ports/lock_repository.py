from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.quota import UnitLock


@runtime_checkable
class LockRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get_lock(self, unit_id: str) -> UnitLock | None:
        ...

    def save_lock(self, lock: UnitLock) -> UnitLock:
        ...

    def delete_lock(self, unit_id: str) -> None:
        ...

    def delete_by_user(self, user_id: str) -> int:
        ...
