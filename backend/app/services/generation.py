"""单讲生成服务：严格（grounded）与非严格（loose）两种写作模式。

流程：检索 → 组装证据 → 模式化提示词 → LLM 写作 → 落版本。

``strict``（默认）沿用 grounded writing，硬约束通过提示词与结构双重保证：

- 写作只允许使用检索到的证据，每段必须带 ``[En]`` 来源标记。
- 检索不到证据时不调用 LLM，直接返回「资料不足」而不是让模型自由发挥。
- 未配置真实 LLM key 时（占位 provider），正文由证据直接编排为占位草稿，
  引用链路仍然完整可验证。

``loose`` 允许模型基于自身通用知识自由写作，证据仅作可选参考：

- 检索结果照常返回，但缺失证据不阻断生成，也不要求逐段引用。
- 正文首行强制写入「本文由大模型编写，未经知识库证据核实」声明，
  由服务端在落库前统一注入，不依赖模型自觉遵守。
"""

from __future__ import annotations

from typing import Sequence

from app.models.citation import Citation
from app.models.course import Course, Lesson
from app.models.factcheck import CheckResult
from app.models.generation import Evidence, GenerationResult
from app.models.mode import GenerationMode, with_loose_notice
from app.ports.course_repository import CourseRepository
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore
from app.services.errors import LessonNotFoundError, VersionConflictError
from app.services.factcheck import FactCheckService

NO_EVIDENCE_NOTICE = (
    "资料不足：知识库中未检索到与本节主题相关的证据，暂不生成正文。\n\n"
    "请先上传相关资料到知识库，或调整本节主题后重试；"
    "如需模型基于自身知识自由写作，请改用 loose 模式。"
)


def _diversify(citations: Sequence[Citation], limit: int, per_source: int = 3) -> list[Citation]:
    kept: list[Citation] = []
    counts: dict[str, int] = {}
    for citation in citations:
        key = citation.source_id or citation.source_name
        if counts.get(key, 0) >= per_source:
            continue
        counts[key] = counts.get(key, 0) + 1
        kept.append(citation)
        if len(kept) >= limit:
            break
    return kept


class GenerationService:
    def __init__(
        self,
        repository: CourseRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 5,
        evidence_char_limit: int = 600,
        max_evidence: int = 8,
        default_mode: str = "strict",
        min_score: float = 0.15,
        factcheck: FactCheckService | None = None,
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.default_top_k = default_top_k
        self.evidence_char_limit = evidence_char_limit
        self.max_evidence = max_evidence
        self.default_mode = GenerationMode.normalize(default_mode).value
        self.min_score = float(min_score)
        self.factcheck = factcheck

    async def generate_lesson(
        self,
        lesson_id: str,
        topic: str | None = None,
        top_k: int | None = None,
        note: str = "",
        source_ids: Sequence[str] | None = None,
        mode: str | None = None,
        expected_version: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
    ) -> GenerationResult:
        lesson = self.repository.get_lesson(lesson_id)
        if lesson is None:
            raise LessonNotFoundError(lesson_id)
        if expected_version is not None and int(expected_version) != lesson.current_version:
            raise VersionConflictError(int(expected_version), lesson.current_version)
        course = self.repository.get_course(lesson.course_id)
        resolved_mode = GenerationMode.normalize(mode or self.default_mode)

        resolved_topic = (topic or lesson.title).strip()
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        is_strict = resolved_mode is GenerationMode.strict
        citations = await self.vectorstore.search(
            self._build_query(resolved_topic, lesson),
            top_k=resolved_top_k,
            source_ids=source_ids,
            tenant_id=tenant_id,
            min_score=self.min_score if is_strict else None,
        )
        citations = _diversify(citations, self.max_evidence, per_source=3)
        evidence = [
            Evidence(marker=f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]

        provider = llm or self.llm
        if resolved_mode is GenerationMode.loose:
            content, prompt, provider_name, grounded = await self._write_loose(
                course, lesson, resolved_topic, evidence, provider
            )
        else:
            content, prompt, provider_name, grounded = await self._write_strict(
                course, lesson, resolved_topic, evidence, provider
            )

        checks = await self._run_factcheck(content, tenant_id, provider, is_strict)
        note_value = note or self._default_note(resolved_mode, evidence)
        if checks:
            note_value = f"{note_value};factcheck:{self.factcheck.summarize(checks)}"

        applied = self.repository.append_version(
            lesson_id,
            content=content,
            citations=citations,
            note=note_value,
            status="generated"
            if resolved_mode is GenerationMode.loose or evidence
            else lesson.status,
            mode=resolved_mode.value,
        )
        assert applied is not None
        updated, version = applied

        return GenerationResult(
            lesson_id=lesson_id,
            version=version.version,
            topic=resolved_topic,
            top_k=resolved_top_k,
            mode=resolved_mode.value,
            content=updated.content,
            citations=citations,
            evidence=evidence,
            grounded=grounded,
            provider=provider_name,
            prompt=prompt,
            factcheck=checks,
        )

    async def _run_factcheck(
        self,
        content: str,
        tenant_id: str,
        provider: LLMProvider,
        is_strict: bool,
    ) -> list[CheckResult]:
        if not is_strict or self.factcheck is None or not content:
            return []
        claims = self.factcheck.extract_claims(content)
        if not claims:
            return []
        try:
            return await self.factcheck.check(claims, tenant_id=tenant_id)
        except Exception:
            return []

    async def _write_strict(
        self,
        course: Course | None,
        lesson: Lesson,
        topic: str,
        evidence: Sequence[Evidence],
        llm: LLMProvider,
    ) -> tuple[str, str, str, bool]:
        if not evidence:
            return NO_EVIDENCE_NOTICE, "", "", False
        prompt = self._build_strict_prompt(course, lesson, topic, evidence)
        provider_name = type(llm).__name__
        if getattr(llm, "is_placeholder", False):
            content = self._strict_placeholder_draft(lesson, topic, evidence)
        else:
            content = await llm.complete(prompt)
        return content, prompt, provider_name, bool(content)

    async def _write_loose(
        self,
        course: Course | None,
        lesson: Lesson,
        topic: str,
        evidence: Sequence[Evidence],
        llm: LLMProvider,
    ) -> tuple[str, str, str, bool]:
        prompt = self._build_loose_prompt(course, lesson, topic, evidence)
        provider_name = type(llm).__name__
        if getattr(llm, "is_placeholder", False):
            content = self._loose_placeholder_draft(lesson, topic, evidence)
        else:
            content = await llm.complete(prompt)
        return with_loose_notice(content), prompt, provider_name, False

    @staticmethod
    def _default_note(mode: GenerationMode, evidence: Sequence[Evidence]) -> str:
        if mode is GenerationMode.loose:
            return "generate:loose"
        return "generate" if evidence else "generate:no-evidence"

    def _build_query(self, topic: str, lesson: Lesson) -> str:
        parts = [topic]
        if lesson.learning_objectives:
            parts.append(" ".join(lesson.learning_objectives))
        return " ".join(part for part in parts if part).strip()

    def _build_strict_prompt(
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
        lines.extend(self._lesson_context(lesson))

        lines.extend(
            [
                "",
                "## 写作硬约束",
                "1. 只能使用「证据」中明确陈述的内容，不得引入证据之外的事实、数据、案例、人物或结论。",
                "2. 每个自然段至少标注一个来源标记，格式为 [E1]；一段引用多条证据时写作 [E1][E3]。",
                "3. 证据不足以支撑的小节，必须显式写明「资料不足：<缺口说明>」，禁止用常识或推测补全。",
                "4. 输出 Markdown：用二级标题组织小节，正文 600-1200 字，术语首次出现时给出简要解释。",
                "4.1 语气要求：面向读者直接讲解，像老师在讲，不要反复使用「证据指出」「这说明」「由此可见」这类转述句式；事实直接陈述，句末保留来源标记即可。",
                "5. 结尾追加「## 延伸问题」小节，列出 2-3 个需要补充资料才能回答的问题。",
                "",
                "## 证据",
            ]
        )
        lines.extend(self._evidence_block(evidence))
        lines.append("## 输出")
        lines.append("只输出正文 Markdown，不要输出解释、前言或对写作过程的说明。")
        return "\n".join(lines)

    def _build_loose_prompt(
        self,
        course: Course | None,
        lesson: Lesson,
        topic: str,
        evidence: Sequence[Evidence],
    ) -> str:
        lines: list[str] = [
            "你是经验丰富的课程作者，负责为一门课程撰写其中一讲的正文。",
            "本节使用「自由写作」模式：允许你基于自身通用知识展开，不要求逐段引用知识库证据。",
            "",
            "## 讲次信息",
            f"- 课程：{course.title if course else '未命名课程'}",
            f"- 讲次：第 {lesson.order_index} 讲 · {lesson.title}",
            f"- 本节主题：{topic}",
        ]
        lines.extend(self._lesson_context(lesson))

        lines.extend(
            [
                "",
                "## 写作要求",
                "1. 可以使用自身的通用知识、常见实践与教学经验自由组织内容，不必局限于「参考证据」。",
                "2. 正文第一行必须输出声明：「> ⚠️ 本文由大模型编写，未经知识库证据核实」。",
                "3. 不强制逐段标注来源；若引用了参考证据中的具体说法，可选择性标注 [E1]。",
                "4. 输出 Markdown：用二级标题组织小节，正文 800-1500 字，术语首次出现时给出简要解释。",
                "5. 对不确定或时效性强的结论，用「建议核实」等方式提示读者，不要伪装成已核实事实。",
                "6. 结尾追加「## 延伸阅读建议」小节，列出 2-3 个可进一步查证的方向。",
                "",
                "## 参考证据（可选，缺失时忽略）",
            ]
        )
        if evidence:
            lines.extend(self._evidence_block(evidence))
        else:
            lines.extend(["（本次未检索到相关知识库证据，可完全依据模型自身知识写作）", ""])
        lines.append("## 输出")
        lines.append("只输出正文 Markdown，不要输出解释、前言或对写作过程的说明。")
        return "\n".join(lines)

    @staticmethod
    def _lesson_context(lesson: Lesson) -> list[str]:
        lines: list[str] = []
        if lesson.learning_objectives:
            lines.append("- 学习目标：" + "；".join(lesson.learning_objectives))
        if lesson.prerequisites:
            lines.append("- 前置知识：" + "；".join(lesson.prerequisites))
        return lines

    def _evidence_block(self, evidence: Sequence[Evidence]) -> list[str]:
        lines: list[str] = []
        for item in evidence:
            citation = item.citation
            snippet = citation.text or citation.snippet
            if len(snippet) > self.evidence_char_limit:
                snippet = snippet[: self.evidence_char_limit] + "…"
            lines.append(f"[{item.marker}] 来源：{citation.source_name}｜片段 #{citation.chunk_index}")
            lines.append(snippet)
            lines.append("")
        return lines

    def _strict_placeholder_draft(
        self, lesson: Lesson, topic: str, evidence: Sequence[Evidence]
    ) -> str:
        lines: list[str] = [
            f"# {lesson.title}",
            "",
            "> 占位草稿（未配置 LLM API key，严格模式）：正文由检索证据直接编排，用于验证带引用的写作链路。",
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

    def _loose_placeholder_draft(
        self, lesson: Lesson, topic: str, evidence: Sequence[Evidence]
    ) -> str:
        lines: list[str] = [
            f"# {lesson.title}",
            "",
            "> 占位草稿（未配置 LLM API key，非严格模式）：本节允许模型基于自身知识自由写作，"
            "因此不承诺逐段引用；配置真实模型后将由模型生成完整正文。",
            "",
            "## 本节主题",
            topic,
            "",
            "## 写作要点（占位）",
            f"- 围绕「{topic}」给出概念定义、典型使用场景与常见误区。",
            "- 用教学化语言逐步展开，必要时补充示例与对比。",
            "- 对时效性或争议性结论标注「建议核实」。",
            "",
        ]
        if lesson.learning_objectives:
            lines.append("## 学习目标")
            lines.extend(f"- {item}" for item in lesson.learning_objectives)
            lines.append("")
        if lesson.prerequisites:
            lines.append("## 前置知识")
            lines.extend(f"- {item}" for item in lesson.prerequisites)
            lines.append("")

        lines.append("## 可选参考证据")
        if evidence:
            for item in evidence[:3]:
                snippet = (item.citation.text or item.citation.snippet).strip()
                lines.append(
                    f"- {item.citation.source_name}｜片段 #{item.citation.chunk_index}："
                    f"{snippet[:200]}…"
                )
        else:
            lines.append("- 本次未检索到证据，本节完全依赖模型自身知识。")
        lines.append("")
        lines.append("## 延伸阅读建议")
        lines.append("- 查阅该主题的官方文档与规范原文。")
        lines.append("- 对比不同实现方案的取舍与适用边界。")
        return "\n".join(lines)
