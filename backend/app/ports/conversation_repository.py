"""对话线持久化端口（ConversationRepository）。

课程 / 讲级对话线（thread）与消息（message）的仓库接口。业务代码只依赖本协议，
SQL 方言与驱动由 adapter 实现。

约定：
- 一讲对应一条讲级线程：``get_or_create_lesson_thread`` 幂等，重复调用返回同一条。
- 消息只追加不修改，保证对话线可回放、可审计。
- 消息按 ``created_at`` 升序返回，同一线程内时间戳单调递增。
- 找不到实体时返回 ``None``，由上层决定错误语义。
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.thread import Message, Thread


@runtime_checkable
class ConversationRepository(Protocol):
    def get_or_create_lesson_thread(
        self, lesson_id: str, course_id: str = "", title: str = ""
    ) -> Thread:
        ...

    def get_thread(self, thread_id: str) -> Thread | None:
        ...

    def get_lesson_thread(self, lesson_id: str) -> Thread | None:
        ...

    def list_lesson_threads(self, lesson_id: str) -> list[Thread]:
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
        self, course_ids: Sequence[str] | None = None, limit: int = 200
    ) -> list[Thread]:
        ...

    def update_thread_title(self, thread_id: str, title: str) -> Thread | None:
        ...

    def delete_thread(self, thread_id: str) -> int:
        ...
