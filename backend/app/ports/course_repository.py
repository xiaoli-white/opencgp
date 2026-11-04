"""课程文档持久化端口（CourseRepository）。

定义课程 / 讲 / 讲版本的仓库接口。业务代码（service、API）只依赖本协议，
具体的 SQL 方言与驱动由 adapter 实现，容器按配置装配。

约定：
- 版本号从 1 开始单调递增，同一 ``lesson_id`` 内唯一。
- 每次内容变更（生成、回滚）都必须新增一条 ``LessonVersion``，不覆盖历史。
- 回滚不删除历史，而是以目标版本内容追加一个新版本（类 git revert）。
- 每个版本记录生成模式 ``mode``（``strict`` 严格引用 / ``loose`` 大模型自由写作 /
  空串表示人工草稿），``lessons.last_mode`` 跟随最近一次生成模式。
- 找不到实体时返回 ``None``，由上层决定错误语义。
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.course import Course, Lesson, LessonVersion


@runtime_checkable
class CourseRepository(Protocol):
    def create_course(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "",
        difficulty: str = "intermediate",
        language: str = "zh",
        tenant_id: str = "",
    ) -> Course:
        ...

    def get_course(self, course_id: str, tenant_id: str | None = None) -> Course | None:
        ...

    def list_courses(self, tenant_id: str | None = None) -> list[Course]:
        ...

    def update_course(
        self,
        course_id: str,
        title: str | None = None,
        subtitle: str | None = None,
        audience: str | None = None,
        difficulty: str | None = None,
        language: str | None = None,
    ) -> Course | None:
        ...

    def delete_course(
        self, course_id: str, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        ...

    def create_lesson(
        self,
        course_id: str,
        title: str,
        order_index: int | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        content: str = "",
        status: str = "draft",
    ) -> Lesson:
        ...

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        ...

    def list_lessons(self, course_id: str) -> list[Lesson]:
        ...

    def update_lesson(
        self,
        lesson_id: str,
        title: str | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        status: str | None = None,
        order_index: int | None = None,
        content: str | None = None,
    ) -> Lesson | None:
        ...

    def delete_lesson(self, lesson_id: str) -> dict[str, int] | None:
        ...

    def reorder_lessons(
        self, course_id: str, lesson_ids: Sequence[str]
    ) -> list[Lesson]:
        ...

    def append_version(
        self,
        lesson_id: str,
        content: str,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        status: str | None = None,
        mode: str = "",
    ) -> tuple[Lesson, LessonVersion] | None:
        ...

    def list_versions(self, lesson_id: str) -> list[LessonVersion]:
        ...

    def get_version(self, lesson_id: str, version: int) -> LessonVersion | None:
        ...

    def revert_to_version(
        self, lesson_id: str, version: int, note: str = ""
    ) -> tuple[Lesson, LessonVersion] | None:
        ...
