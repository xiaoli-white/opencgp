"""Conversation-thread persistence port (ConversationRepository).

Repository interface for course / chapter-level conversation threads and messages.
Business code depends only on this protocol; the SQL dialect and driver are
implemented by the adapter.

Conventions:
- One chapter maps to one chapter-level thread: ``get_or_create_unit_thread`` is
  idempotent and repeated calls return the same thread.
- Messages are append-only, so threads stay replayable and auditable.
- Messages are returned in ascending ``created_at`` order; timestamps increase
  monotonically within a thread.
- Return ``None`` when an entity is not found; the caller decides the error semantics.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.thread import Message, Thread


@runtime_checkable
class ConversationRepository(Protocol):
    def get_or_create_unit_thread(
        self, unit_id: str, series_id: str = "", title: str = ""
    ) -> Thread:
        ...

    def get_thread(self, thread_id: str) -> Thread | None:
        ...

    def get_unit_thread(self, unit_id: str) -> Thread | None:
        ...

    def list_unit_threads(self, unit_id: str) -> list[Thread]:
        ...

    def append_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        citations: Sequence[Citation] | None = None,
    ) -> Message:
        ...

    def get_message(self, message_id: str) -> Message | None:
        ...

    def list_messages(self, thread_id: str, limit: int | None = None) -> list[Message]:
        ...

    def count_messages(self, thread_id: str) -> int:
        ...

    def list_threads(
        self, series_ids: Sequence[str] | None = None, limit: int = 200
    ) -> list[Thread]:
        ...

    def update_thread_title(self, thread_id: str, title: str) -> Thread | None:
        ...

    def delete_thread(self, thread_id: str) -> int:
        ...
