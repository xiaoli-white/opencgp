from __future__ import annotations

import secrets
import time

from app.models.quota import UnitLock
from app.ports.lock_repository import LockRepository
from app.services.errors import (
    UnitLockLostError,
    UnitLockedError,
    LockTokenMismatchError,
)


class LockService:
    def __init__(self, repository: LockRepository, ttl_seconds: int = 120) -> None:
        self.repository = repository
        self.ttl_seconds = max(10, int(ttl_seconds))

    def get(self, unit_id: str) -> UnitLock | None:
        lock = self.repository.get_lock(unit_id)
        if lock is None:
            return None
        if lock.expires_at <= time.time():
            self.repository.delete_lock(unit_id)
            return None
        return lock

    def acquire(
        self,
        unit_id: str,
        tenant_id: str,
        user_id: str,
        user_name: str,
        force: bool = False,
    ) -> UnitLock:
        current = self.get(unit_id)
        if current is not None and current.user_id != user_id:
            if not force:
                name = current.user_name or current.user_id
                raise UnitLockedError(name, current)
        now = time.time()
        lock = UnitLock(
            unit_id=unit_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name or user_id,
            token=secrets.token_urlsafe(16),
            heartbeat_at=now,
            expires_at=now + self.ttl_seconds,
        )
        return self.repository.save_lock(lock)

    def heartbeat(self, unit_id: str, token: str) -> UnitLock:
        current = self.get(unit_id)
        if current is None or current.token != (token or ""):
            raise UnitLockLostError("the lock is no longer valid; acquire the edit lock again")
        now = time.time()
        current.heartbeat_at = now
        current.expires_at = now + self.ttl_seconds
        return self.repository.save_lock(current)

    def release(self, unit_id: str, token: str) -> None:
        current = self.repository.get_lock(unit_id)
        if current is None:
            return
        if current.token != (token or ""):
            raise LockTokenMismatchError("lock token mismatch; cannot release an edit lock held by someone else")
        self.repository.delete_lock(unit_id)

    def guard(self, unit_id: str, user_id: str) -> None:
        current = self.get(unit_id)
        if current is not None and current.user_id != user_id:
            name = current.user_name or current.user_id
            raise UnitLockedError(name, current)
