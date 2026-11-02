"""课程文档仓库的数据库实现（基于 Database 端口）。

只依赖 :class:`app.ports.database.Database`，因此 SQLite（M0 默认）与
PostgreSQL（生产）共用同一份实现，切换只改配置。

存储约定：结构化字段以 JSON 文本落库（``learning_objectives`` /
``prerequisites`` / ``citations_json``），换库时无需 JSONB 迁移。
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.course import Course, Lesson, LessonVersion
from app.ports.course_repository import CourseRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS courses (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        subtitle TEXT NOT NULL DEFAULT '',
        audience TEXT NOT NULL DEFAULT '',
        difficulty TEXT NOT NULL DEFAULT 'intermediate',
        language TEXT NOT NULL DEFAULT 'zh',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lessons (
        id TEXT PRIMARY KEY,
        course_id TEXT NOT NULL,
        order_index INTEGER NOT NULL DEFAULT 0,
        title TEXT NOT NULL,
        learning_objectives TEXT NOT NULL DEFAULT '[]',
        prerequisites TEXT NOT NULL DEFAULT '[]',
        content TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        current_version INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id, order_index)",
    """
    CREATE TABLE IF NOT EXISTS lesson_versions (
        id TEXT PRIMARY KEY,
        lesson_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        citations_json TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        UNIQUE (lesson_id, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lesson_versions_lesson ON lesson_versions(lesson_id, version)",
    """
    CREATE TABLE IF NOT EXISTS threads (
        id TEXT PRIMARY KEY,
        course_id TEXT,
        lesson_id TEXT,
        title TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations_json TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at)",
)


class DatabaseCourseRepository(CourseRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def create_course(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "",
        difficulty: str = "intermediate",
        language: str = "zh",
    ) -> Course:
        self.ensure_schema()
        now = time.time()
        course = Course(
            id=_new_id(),
            title=title,
            subtitle=subtitle,
            audience=audience,
            difficulty=difficulty,
            language=language,
            created_at=now,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO courses (id, title, subtitle, audience, difficulty, language,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                course.id,
                course.title,
                course.subtitle,
                course.audience,
                course.difficulty,
                course.language,
                course.created_at,
                course.updated_at,
            ),
        )
        return course

    def get_course(self, course_id: str) -> Course | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM courses WHERE id = ?", (course_id,))
        return _to_course(row) if row else None

    def list_courses(self) -> list[Course]:
        self.ensure_schema()
        rows = self.database.fetchall("SELECT * FROM courses ORDER BY created_at ASC")
        return [_to_course(row) for row in rows]

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
        self.ensure_schema()
        now = time.time()
        resolved_index = order_index if order_index is not None else self._next_order_index(course_id)
        lesson = Lesson(
            id=_new_id(),
            course_id=course_id,
            order_index=resolved_index,
            title=title,
            learning_objectives=list(learning_objectives or []),
            prerequisites=list(prerequisites or []),
            content=content,
            status=status,
            current_version=0,
            created_at=now,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO lessons (id, course_id, order_index, title, learning_objectives,"
            " prerequisites, content, status, current_version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lesson.id,
                lesson.course_id,
                lesson.order_index,
                lesson.title,
                _dump_list(lesson.learning_objectives),
                _dump_list(lesson.prerequisites),
                lesson.content,
                lesson.status,
                lesson.current_version,
                lesson.created_at,
                lesson.updated_at,
            ),
        )
        return lesson

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM lessons WHERE id = ?", (lesson_id,))
        return _to_lesson(row) if row else None

    def list_lessons(self, course_id: str) -> list[Lesson]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM lessons WHERE course_id = ? ORDER BY order_index ASC, created_at ASC",
            (course_id,),
        )
        return [_to_lesson(row) for row in rows]

    def update_lesson(
        self,
        lesson_id: str,
        title: str | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        status: str | None = None,
    ) -> Lesson | None:
        self.ensure_schema()
        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None
        assignments: list[str] = []
        params: list[Any] = []
        if title is not None:
            assignments.append("title = ?")
            params.append(title)
        if learning_objectives is not None:
            assignments.append("learning_objectives = ?")
            params.append(_dump_list(learning_objectives))
        if prerequisites is not None:
            assignments.append("prerequisites = ?")
            params.append(_dump_list(prerequisites))
        if status is not None:
            assignments.append("status = ?")
            params.append(status)
        if not assignments:
            return lesson
        assignments.append("updated_at = ?")
        params.append(time.time())
        params.append(lesson_id)
        self.database.execute(
            f"UPDATE lessons SET {', '.join(assignments)} WHERE id = ?", tuple(params)
        )
        return self.get_lesson(lesson_id)

    def append_version(
        self,
        lesson_id: str,
        content: str,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        status: str | None = None,
    ) -> tuple[Lesson, LessonVersion] | None:
        self.ensure_schema()
        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None
        version = lesson.current_version + 1
        now = time.time()
        record = LessonVersion(
            id=_new_id(),
            lesson_id=lesson_id,
            version=version,
            content=content,
            citations=list(citations or []),
            note=note,
            created_at=now,
        )
        self.database.execute(
            "INSERT INTO lesson_versions (id, lesson_id, version, content, citations_json,"
            " note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.lesson_id,
                record.version,
                record.content,
                _dump_list([citation.model_dump() for citation in record.citations]),
                record.note,
                record.created_at,
            ),
        )
        self.database.execute(
            "UPDATE lessons SET content = ?, current_version = ?, status = ?, updated_at = ?"
            " WHERE id = ?",
            (
                content,
                version,
                status or lesson.status,
                now,
                lesson_id,
            ),
        )
        updated = self.get_lesson(lesson_id)
        assert updated is not None
        return updated, record

    def list_versions(self, lesson_id: str) -> list[LessonVersion]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM lesson_versions WHERE lesson_id = ? ORDER BY version DESC",
            (lesson_id,),
        )
        return [_to_version(row) for row in rows]

    def get_version(self, lesson_id: str, version: int) -> LessonVersion | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM lesson_versions WHERE lesson_id = ? AND version = ?",
            (lesson_id, version),
        )
        return _to_version(row) if row else None

    def revert_to_version(
        self, lesson_id: str, version: int, note: str = ""
    ) -> tuple[Lesson, LessonVersion] | None:
        target = self.get_version(lesson_id, version)
        if target is None:
            return None
        resolved_note = note or f"revert to v{version}"
        return self.append_version(
            lesson_id,
            content=target.content,
            citations=target.citations,
            note=resolved_note,
            status="reverted",
        )

    def _next_order_index(self, course_id: str) -> int:
        row = self.database.fetchone(
            "SELECT MAX(order_index) AS max_index FROM lessons WHERE course_id = ?",
            (course_id,),
        )
        if not row or row["max_index"] is None:
            return 1
        return int(row["max_index"]) + 1


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_list(values: Sequence[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _to_course(row: Mapping[str, Any]) -> Course:
    return Course(
        id=str(row["id"]),
        title=str(row["title"]),
        subtitle=str(row["subtitle"] or ""),
        audience=str(row["audience"] or ""),
        difficulty=str(row["difficulty"] or "intermediate"),
        language=str(row["language"] or "zh"),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _to_lesson(row: Mapping[str, Any]) -> Lesson:
    return Lesson(
        id=str(row["id"]),
        course_id=str(row["course_id"]),
        order_index=int(row["order_index"]),
        title=str(row["title"]),
        learning_objectives=[str(item) for item in _load_list(row["learning_objectives"])],
        prerequisites=[str(item) for item in _load_list(row["prerequisites"])],
        content=str(row["content"] or ""),
        status=str(row["status"] or "draft"),
        current_version=int(row["current_version"]),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _to_version(row: Mapping[str, Any]) -> LessonVersion:
    citations = [Citation(**item) for item in _load_list(row["citations_json"])]
    return LessonVersion(
        id=str(row["id"]),
        lesson_id=str(row["lesson_id"]),
        version=int(row["version"]),
        content=str(row["content"] or ""),
        citations=citations,
        note=str(row["note"] or ""),
        created_at=float(row["created_at"]),
    )
