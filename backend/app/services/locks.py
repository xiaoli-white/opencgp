from __future__ import annotations

import secrets
import time

from app.models.quota import LessonLock
from app.ports.lock_repository import LockRepository
from app.services.errors import (
    LessonLockLostError,
    LessonLockedError,
    LockTokenMismatchError,
)


class LockService:
    def __init__(self, repository: LockRepository, ttl_seconds: int = 120) -> None:
        self.repository = repository
        self.ttl_seconds = max(10, int(ttl_seconds))

    def get(self, lesson_id: str) -> LessonLock | None:
        lock = self.repository.get_lock(lesson_id)
        if lock is None:
            return None
        if lock.expires_at <= time.time():
            self.repository.delete_lock(lesson_id)
            return None
        return lock

    def acquire(
        self,
        lesson_id: str,
        tenant_id: str,
        user_id: str,
        user_name: str,
        force: bool = False,
    ) -> LessonLock:
        current = self.get(lesson_id)
        if current is not None and current.user_id != user_id:
            if not force:
                name = current.user_name or current.user_id
                raise LessonLockedError(name, current)
        now = time.time()
        lock = LessonLock(
            lesson_id=lesson_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name or user_id,
            token=secrets.token_urlsafe(16),
            heartbeat_at=now,
            expires_at=now + self.ttl_seconds,
        )
        return self.repository.save_lock(lock)

    def heartbeat(self, lesson_id: str, token: str) -> LessonLock:
        current = self.get(lesson_id)
        if current is None or current.token != (token or ""):
            raise LessonLockLostError("锁已失效，请重新获取编辑锁")
        now = time.time()
        current.heartbeat_at = now
        current.expires_at = now + self.ttl_seconds
        return self.repository.save_lock(current)

    def release(self, lesson_id: str, token: str) -> None:
        current = self.repository.get_lock(lesson_id)
        if current is None:
            return
        if current.token != (token or ""):
            raise LockTokenMismatchError("锁令牌不匹配，无法释放他人持有的编辑锁")
        self.repository.delete_lock(lesson_id)

    def guard(self, lesson_id: str, user_id: str) -> None:
        current = self.get(lesson_id)
        if current is not None and current.user_id != user_id:
            name = current.user_name or current.user_id
            raise LessonLockedError(name, current)
