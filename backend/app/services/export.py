from __future__ import annotations

import time
from typing import Sequence

from app.models.citation import Citation
from app.models.course import Course, Lesson
from app.models.export import (
    SOURCE_COURSE,
    SOURCE_LONGFORM,
    ExportChapter,
    ExportDocument,
)
from app.models.longform import Longform
from app.ports.course_repository import CourseRepository
from app.ports.longform_repository import LongformRepository
from app.services.errors import ExportSourceNotFoundError

DIFFICULTY_LABELS: dict[str, str] = {
    "beginner": "入门",
    "intermediate": "进阶",
    "advanced": "高级",
}
DEFAULT_AUTHOR = "AI 课程工作室"


class ExportService:
    def __init__(
        self,
        course_repository: CourseRepository,
        longform_repository: LongformRepository,
        exporter: object | None = None,
    ) -> None:
        self.course_repository = course_repository
        self.longform_repository = longform_repository
        self.exporter = exporter

    def build_document(
        self,
        source_type: str,
        source_id: str,
        tenant_id: str | None = None,
        include_citations: bool = True,
    ) -> ExportDocument:
        if source_type == SOURCE_COURSE:
            return self._build_course(source_id, tenant_id, include_citations)
        if source_type == SOURCE_LONGFORM:
            return self._build_longform(source_id, tenant_id, include_citations)
        raise ExportSourceNotFoundError(f"不支持的导出来源类型: {source_type}")

    def _build_course(
        self,
        course_id: str,
        tenant_id: str | None,
        include_citations: bool,
    ) -> ExportDocument:
        course = self.course_repository.get_course(course_id, tenant_id)
        if course is None:
            raise ExportSourceNotFoundError(f"课程不存在: {course_id}")
        lessons = [
            item
            for item in self.course_repository.list_lessons(course_id)
            if (item.content or "").strip()
        ]
        lessons.sort(key=lambda item: (item.order_index, item.created_at))
        chapters: list[ExportChapter] = []
        for lesson in lessons:
            chapters.append(
                ExportChapter(
                    title=lesson.title,
                    markdown=(lesson.content or "").strip(),
                    citations=self._lesson_citations(lesson)
                    if include_citations
                    else [],
                )
            )
        front = self._course_front_matter(course, lessons)
        return ExportDocument(
            source_type=SOURCE_COURSE,
            source_id=course.id,
            title=course.title,
            subtitle=course.subtitle,
            author=DEFAULT_AUTHOR,
            created_at=course.created_at,
            front_matter=front,
            chapters=chapters,
            citations=self._unique([cite for ch in chapters for cite in ch.citations]),
            meta={
                "audience": course.audience,
                "difficulty": course.difficulty,
                "difficulty_label": DIFFICULTY_LABELS.get(
                    course.difficulty, course.difficulty
                ),
                "language": course.language,
                "lesson_count": len(lessons),
                "updated_at": course.updated_at,
            },
        )

    def _build_longform(
        self,
        longform_id: str,
        tenant_id: str | None,
        include_citations: bool,
    ) -> ExportDocument:
        longform = self.longform_repository.get(longform_id, tenant_id)
        if longform is None:
            raise ExportSourceNotFoundError(f"长篇不存在: {longform_id}")
        chapters: list[ExportChapter] = []
        for section in longform.outline:
            body = (section.content or "").strip()
            if not body:
                continue
            chapters.append(ExportChapter(title=section.title, markdown=body))
        document_citations = list(longform.citations or []) if include_citations else []
        if not chapters and (longform.content or "").strip():
            chapters.append(
                ExportChapter(
                    title=longform.title,
                    markdown=(longform.content or "").strip(),
                )
            )
        return ExportDocument(
            source_type=SOURCE_LONGFORM,
            source_id=longform.id,
            title=longform.title,
            subtitle=longform.profile.audience,
            author=DEFAULT_AUTHOR,
            created_at=longform.created_at,
            front_matter=self._longform_front_matter(longform),
            chapters=chapters,
            citations=self._unique(document_citations),
            meta={
                "genre": longform.profile.genre,
                "tone": longform.profile.tone,
                "audience": longform.profile.audience,
                "target_words": longform.target_words,
                "word_count": len((longform.content or "").strip()),
                "section_count": len(longform.outline),
                "mode": longform.last_mode,
                "updated_at": longform.updated_at,
            },
        )

    def _lesson_citations(self, lesson: Lesson) -> list[Citation]:
        if lesson.current_version <= 0:
            return []
        version = self.course_repository.get_version(
            lesson.id, lesson.current_version
        )
        if version is None:
            return []
        return list(version.citations or [])

    @staticmethod
    def _course_front_matter(course: Course, lessons: Sequence[Lesson]) -> str:
        rows = [
            f"- 标题：{course.title}",
            f"- 副标题：{course.subtitle or '（未填写）'}",
            f"- 受众：{course.audience or '（未填写）'}",
            f"- 难度：{DIFFICULTY_LABELS.get(course.difficulty, course.difficulty)}",
            f"- 语言：{course.language}",
            f"- 正文讲数：{len(lessons)}",
            f"- 更新日期：{_date_of(course.updated_at)}",
        ]
        if lessons:
            rows.append("")
            rows.append("讲次目录：")
            for index, lesson in enumerate(lessons, start=1):
                rows.append(f"{index}. {lesson.title}")
        return "\n".join(rows)

    @staticmethod
    def _longform_front_matter(longform: Longform) -> str:
        rows = [
            f"- 体裁：{longform.profile.genre}",
            f"- 语气：{longform.profile.tone or '（未填写）'}",
            f"- 受众：{longform.profile.audience or '（未填写）'}",
            f"- 目标字数：{longform.target_words}",
            f"- 实际字数：{len((longform.content or '').strip())}",
            f"- 章节数：{len(longform.outline)}",
            f"- 更新日期：{_date_of(longform.updated_at)}",
        ]
        if longform.outline:
            rows.append("")
            rows.append("章节目录：")
            for index, section in enumerate(longform.outline, start=1):
                rows.append(f"{index}. {section.title}")
        return "\n".join(rows)

    @staticmethod
    def _unique(citations: Sequence[Citation]) -> list[Citation]:
        seen: set[tuple[str, str]] = set()
        out: list[Citation] = []
        for citation in citations:
            key = (citation.source_id, citation.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(citation)
        return out


def _date_of(timestamp: float) -> str:
    if not timestamp:
        return "未知"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))
