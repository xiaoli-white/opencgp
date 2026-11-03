from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.quota import LessonLock


@runtime_checkable
class LockRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get_lock(self, lesson_id: str) -> LessonLock | None:
        ...

    def save_lock(self, lock: LessonLock) -> LessonLock:
        ...

    def delete_lock(self, lesson_id: str) -> None:
        ...

    def delete_by_user(self, user_id: str) -> int:
        ...
