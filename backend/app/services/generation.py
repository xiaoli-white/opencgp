"""带引用的单讲生成服务（grounded writing）。

流程：检索 → 组装证据 → 约束提示词 → LLM 写作 → 落版本。
硬约束通过提示词与结构双重保证：

- 写作只允许使用检索到的证据，每段必须带 ``[En]`` 来源标记。
- 检索不到证据时不调用 LLM，直接返回「资料不足」而不是让模型自由发挥。
- 未配置真实 LLM key 时（占位 provider），正文由证据直接编排为占位草稿，
  引用链路仍然完整可验证。
"""

from __future__ import annotations

from typing import Sequence

from app.models.citation import Citation
from app.models.course import Course, Lesson
from app.models.generation import Evidence, GenerationResult
from app.ports.course_repository import CourseRepository
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore

NO_EVIDENCE_NOTICE = (
    "资料不足：知识库中未检索到与本节主题相关的证据，暂不生成正文。\n\n"
    "请先上传相关资料到知识库，或调整本节主题后重试。"
)


class LessonNotFoundError(LookupError):
    pass


class GenerationService:
    def __init__(
        self,
        repository: CourseRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 5,
        evidence_char_limit: int = 600,
        max_evidence: int = 8,
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.default_top_k = default_top_k
        self.evidence_char_limit = evidence_char_limit
        self.max_evidence = max_evidence

    async def generate_lesson(
        self,
        lesson_id: str,
        topic: str | None = None,
        top_k: int | None = None,
        note: str = "",
        source_ids: Sequence[str] | None = None,
    ) -> GenerationResult:
        lesson = self.repository.get_lesson(lesson_id)
        if lesson is None:
            raise LessonNotFoundError(lesson_id)
        course = self.repository.get_course(lesson.course_id)

        resolved_topic = (topic or lesson.title).strip()
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        citations = await self.vectorstore.search(
            self._build_query(resolved_topic, lesson),
            top_k=resolved_top_k,
            source_ids=source_ids,
        )
        citations = citations[: self.max_evidence]
        evidence = [
            Evidence(marker=f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]

        if not evidence:
            content = NO_EVIDENCE_NOTICE
            prompt = ""
            provider_name = ""
            grounded = False
        else:
            prompt = self._build_prompt(course, lesson, resolved_topic, evidence)
            provider_name = type(self.llm).__name__
            if getattr(self.llm, "is_placeholder", False):
                content = self._placeholder_draft(lesson, resolved_topic, evidence)
            else:
                content = await self.llm.complete(prompt)
            grounded = bool(content)

        applied = self.repository.append_version(
            lesson_id,
            content=content,
            citations=citations,
            note=note or ("generate" if evidence else "generate:no-evidence"),
            status="generated" if evidence else lesson.status,
        )
        assert applied is not None
        updated, version = applied

        return GenerationResult(
            lesson_id=lesson_id,
            version=version.version,
            topic=resolved_topic,
            top_k=resolved_top_k,
            content=updated.content,
            citations=citations,
            evidence=evidence,
            grounded=grounded,
            provider=provider_name,
            prompt=prompt,
        )

    def _build_query(self, topic: str, lesson: Lesson) -> str:
        parts = [topic]
        if lesson.learning_objectives:
            parts.append(" ".join(lesson.learning_objectives))
        return " ".join(part for part in parts if part).strip()

    def _build_prompt(
        self,
        course: Course | None,
        lesson: Lesson,
        topic: str,
        evidence: Sequence[Evidence],
    ) -> str:
        lines: list[str] = [
            "你是严谨的课程作者，负责为一门课程撰写其中一讲的正文。",
            "",
            "## 讲次信息",
            f"- 课程：{course.title if course else '未命名课程'}",
            f"- 讲次：第 {lesson.order_index} 讲 · {lesson.title}",
            f"- 本节主题：{topic}",
        ]
        if lesson.learning_objectives:
            lines.append("- 学习目标：" + "；".join(lesson.learning_objectives))
        if lesson.prerequisites:
            lines.append("- 前置知识：" + "；".join(lesson.prerequisites))

        lines.extend(
            [
                "",
                "## 写作硬约束",
                "1. 只能使用「证据」中明确陈述的内容，不得引入证据之外的事实、数据、案例、人物或结论。",
                "2. 每个自然段至少标注一个来源标记，格式为 [E1]；一段引用多条证据时写作 [E1][E3]。",
                "3. 证据不足以支撑的小节，必须显式写明「资料不足：<缺口说明>」，禁止用常识或推测补全。",
                "4. 输出 Markdown：用二级标题组织小节，正文 600-1200 字，术语首次出现时给出简要解释。",
                "5. 结尾追加「## 延伸问题」小节，列出 2-3 个需要补充资料才能回答的问题。",
                "",
                "## 证据",
            ]
        )
        for item in evidence:
            citation = item.citation
            snippet = citation.text or citation.snippet
            if len(snippet) > self.evidence_char_limit:
                snippet = snippet[: self.evidence_char_limit] + "…"
            lines.append(f"[{item.marker}] 来源：{citation.source_name}｜片段 #{citation.chunk_index}")
            lines.append(snippet)
            lines.append("")
        lines.append("## 输出")
        lines.append("只输出正文 Markdown，不要输出解释、前言或对写作过程的说明。")
        return "\n".join(lines)

    def _placeholder_draft(
        self, lesson: Lesson, topic: str, evidence: Sequence[Evidence]
    ) -> str:
        lines: list[str] = [
            f"# {lesson.title}",
            "",
            "> 占位草稿（未配置 LLM API key）：正文由检索证据直接编排，用于验证带引用的写作链路。",
            "",
            "## 本节主题",
            topic,
            "",
        ]
        if lesson.learning_objectives:
            lines.append("## 学习目标")
            lines.extend(f"- {item}" for item in lesson.learning_objectives)
            lines.append("")

        lines.append("## 证据要点")
        lines.append("")
        for item in evidence:
            snippet = (item.citation.text or item.citation.snippet).strip()
            if len(snippet) > self.evidence_char_limit:
                snippet = snippet[: self.evidence_char_limit] + "…"
            lines.append(f"### 要点 {item.marker[1:]}")
            lines.append(f"{snippet} [{item.marker}]")
            lines.append(f"来源：{item.citation.source_name}｜片段 #{item.citation.chunk_index}")
            lines.append("")

        lines.append("## 资料不足说明")
        lines.append(
            f"本节仅覆盖检索到的 {len(evidence)} 条证据，尚未对主题做完整展开；"
            "配置真实模型后将基于同一批证据生成连贯正文。"
        )
        lines.append("")
        lines.append("## 延伸问题")
        lines.append("- 这些证据之间是否存在相互矛盾或适用条件差异？")
        lines.append("- 该主题在真实项目中还有哪些证据未覆盖的场景？")
        return "\n".join(lines)
