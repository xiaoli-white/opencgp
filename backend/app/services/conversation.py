"""追问、局部修改与沉淀服务（Ask & Amend）。

让每一讲成为可追问、可局部修改的活文档：

- ``ask``：以该讲当前正文 + 引用证据 + 该讲对话线历史为上下文回答追问，
  并保证 user / assistant 两条消息都落库（即使没有真实 key）。
- ``amend``：按自然语言指令重写正文，走 Sprint 3 的追加式版本机制落新版本，
  指令原文写入版本 note，历史版本永不覆盖。
- ``amend`` 支持 ``strict`` / ``loose`` 两种模式：loose 允许模型基于自身知识自由改写，
  但正文首行强制保留「由大模型编写」声明。
- ``drilldown``：把某次追问的回答沉淀为正文新章节，同样追加新版本（note=drilldown）。

幻觉抑制沿用生成期的约定：只允许使用正文与证据，覆盖不到就显式说明。
未配置真实 LLM key 时（占位 provider）由正文与证据编排占位内容，
链路（消息、版本、引用）仍然完整可验证。
"""

from __future__ import annotations

import re
from typing import Sequence

from app.models.citation import Citation
from app.models.course import Course, Lesson
from app.models.mode import LOOSE_BANNER, GenerationMode, with_loose_notice
from app.models.thread import (
    AmendResult,
    AskResult,
    DrilldownResult,
    Message,
    Thread,
)
from app.ports.conversation_repository import ConversationRepository
from app.ports.course_repository import CourseRepository
from app.ports.llm import LLMProvider
from app.services.errors import (
    EmptyLLMResponseError,
    LessonContentEmptyError,
    LessonNotFoundError,
    MessageNotFoundError,
    VersionConflictError,
)

DRILLDOWN_NOTE = "drilldown"
DRILLDOWN_HEADING = "追问补充"
SELECTION_CHAR_LIMIT = 1200


class ConversationService:
    def __init__(
        self,
        repository: CourseRepository,
        conversations: ConversationRepository,
        llm: LLMProvider,
        history_limit: int = 20,
        history_char_limit: int = 400,
        content_char_limit: int = 6000,
        evidence_char_limit: int = 600,
    ) -> None:
        self.repository = repository
        self.conversations = conversations
        self.llm = llm
        self.history_limit = history_limit
        self.history_char_limit = history_char_limit
        self.content_char_limit = content_char_limit
        self.evidence_char_limit = evidence_char_limit

    async def ask(
        self, lesson_id: str, question: str, selection: str | None = None
    ) -> AskResult:
        lesson, course, citations = self._context(lesson_id)
        thread = self._lesson_thread(lesson)
        history = self.conversations.list_messages(thread.id, limit=self.history_limit)
        selected = (selection or "").strip() or None
        prompt = self._build_ask_prompt(
            course, lesson, citations, history, question, selected
        )

        provider = type(self.llm).__name__
        if getattr(self.llm, "is_placeholder", False):
            answer = self._placeholder_answer(lesson, question, citations)
        else:
            answer = (await self.llm.complete(prompt)).strip()
            if not answer:
                raise EmptyLLMResponseError("模型未返回追问回答")

        user_message = self.conversations.append_message(thread.id, "user", question)
        assistant_message = self.conversations.append_message(
            thread.id, "assistant", answer, citations
        )
        return AskResult(
            lesson_id=lesson.id,
            thread_id=thread.id,
            question=question,
            answer=answer,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            citations=citations,
            grounded=bool(citations) and bool(lesson.content.strip()),
            provider=provider,
            prompt=prompt,
        )

    async def amend(
        self,
        lesson_id: str,
        instruction: str,
        target: str | None = None,
        mode: str | None = None,
        expected_version: int | None = None,
    ) -> AmendResult:
        lesson, course, citations = self._context(lesson_id)
        if expected_version is not None and int(expected_version) != lesson.current_version:
            raise VersionConflictError(int(expected_version), lesson.current_version)
        current_content = lesson.content.strip()
        if not current_content:
            raise LessonContentEmptyError(lesson_id)
        resolved_mode = GenerationMode.normalize(mode)
        resolved_target = (target or "").strip()
        prompt = self._build_amend_prompt(
            course,
            lesson,
            current_content,
            citations,
            instruction,
            resolved_target,
            resolved_mode,
        )

        provider = type(self.llm).__name__
        if getattr(self.llm, "is_placeholder", False):
            new_content = self._placeholder_amend(
                current_content, instruction, resolved_target, resolved_mode
            )
        else:
            new_content = (await self.llm.complete(prompt)).strip()
            if not new_content:
                raise EmptyLLMResponseError("模型未返回修改后的正文")
        if resolved_mode is GenerationMode.loose:
            new_content = with_loose_notice(new_content)

        note = self._amend_note(instruction, resolved_target, resolved_mode)
        applied = self.repository.append_version(
            lesson_id,
            content=new_content,
            citations=citations,
            note=note,
            status="amended",
            mode=resolved_mode.value,
        )
        if applied is None:
            raise LessonNotFoundError(lesson_id)
        updated, record = applied

        thread = self._lesson_thread(lesson)
        scope = f"[{resolved_target}] " if resolved_target else ""
        self.conversations.append_message(
            thread.id, "user", f"[amend:{resolved_mode.value}] {scope}{instruction.strip()}"
        )
        self.conversations.append_message(
            thread.id,
            "assistant",
            f"已按指令生成第 {record.version} 版正文（{resolved_mode.value} 模式）。\n\n{updated.content}",
            citations,
        )

        return AmendResult(
            lesson_id=lesson_id,
            instruction=instruction,
            target=resolved_target,
            version=record.version,
            previous_version=lesson.current_version,
            mode=resolved_mode.value,
            content=updated.content,
            citations=citations,
            note=record.note,
            provider=provider,
            prompt=prompt,
        )

    async def drilldown(
        self,
        lesson_id: str,
        message_id: str | None = None,
        question: str | None = None,
    ) -> DrilldownResult:
        lesson, _course, lesson_citations = self._context(lesson_id)
        thread = self.conversations.get_lesson_thread(lesson_id)
        if thread is None:
            raise MessageNotFoundError(lesson_id)
        messages = self.conversations.list_messages(thread.id)
        source = self._select_answer(messages, message_id, question)
        if source is None:
            raise MessageNotFoundError(message_id or question or lesson_id)

        source_question = self._question_before(messages, source.id) or (question or "追问")
        appended = self._drilldown_section(source_question, source.content)
        base = lesson.content.rstrip()
        new_content = f"{base}\n\n{appended}" if base else appended
        citations = source.citations or lesson_citations

        applied = self.repository.append_version(
            lesson_id,
            content=new_content,
            citations=citations,
            note=DRILLDOWN_NOTE,
            status="amended",
            mode=lesson.last_mode,
        )
        if applied is None:
            raise LessonNotFoundError(lesson_id)
        updated, record = applied

        return DrilldownResult(
            lesson_id=lesson_id,
            thread_id=thread.id,
            source_message_id=source.id,
            version=record.version,
            content=updated.content,
            appended=appended,
            citations=citations,
            note=record.note,
        )

    def _context(
        self, lesson_id: str
    ) -> tuple[Lesson, Course | None, list[Citation]]:
        lesson = self.repository.get_lesson(lesson_id)
        if lesson is None:
            raise LessonNotFoundError(lesson_id)
        course = self.repository.get_course(lesson.course_id)
        citations: list[Citation] = []
        if lesson.current_version > 0:
            version = self.repository.get_version(lesson_id, lesson.current_version)
            if version is not None:
                citations = list(version.citations)
        return lesson, course, citations

    def _lesson_thread(self, lesson: Lesson) -> Thread:
        return self.conversations.get_or_create_lesson_thread(
            lesson.id, lesson.course_id, f"{lesson.title} · 对话"
        )

    def _build_ask_prompt(
        self,
        course: Course | None,
        lesson: Lesson,
        citations: Sequence[Citation],
        history: Sequence[Message],
        question: str,
        selection: str | None = None,
    ) -> str:
        lines: list[str] = [
            "你是这门课程的助教，负责基于这一讲已写好的正文与引用证据回答读者追问。",
            "",
            "## 讲次",
            f"- 课程：{course.title if course else '未命名课程'}",
            f"- 讲次：第 {lesson.order_index} 讲 · {lesson.title}",
        ]
        if lesson.learning_objectives:
            lines.append("- 学习目标：" + "；".join(lesson.learning_objectives))

        lines.extend(["", "## 当前正文（Markdown）"])
        content = lesson.content.strip()
        if content:
            lines.append(self._clip(content, self.content_char_limit))
        else:
            lines.append("（该讲尚无正文，正文为空）")

        lines.extend(["", "## 证据（正文引用来源）"])
        if citations:
            for index, citation in enumerate(citations, start=1):
                snippet = citation.text or citation.snippet
                lines.append(
                    f"[E{index}] 来源：{citation.source_name}｜片段 #{citation.chunk_index}"
                )
                lines.append(self._clip(snippet.strip(), self.evidence_char_limit))
                lines.append("")
        else:
            lines.extend(["（无引用证据）", ""])

        lines.extend(["## 对话历史"])
        if history:
            for message in history:
                speaker = "读者" if message.role == "user" else "助教"
                spoken = " ".join(message.content.split())
                lines.append(f"- {speaker}：{self._clip(spoken, self.history_char_limit)}")
        else:
            lines.append("- （本轮为对话起点）")

        lines.extend(["", "## 读者追问"])
        if selection:
            excerpt = self._clip(selection.strip(), SELECTION_CHAR_LIMIT)
            lines.extend(
                [
                    "用户选中了正文中的以下片段：",
                    f'"""{excerpt}"""',
                    f"请针对这段选中内容回答：{question.strip()}",
                ]
            )
        else:
            lines.append(question.strip())

        lines.extend(
            [
                "",
                "## 回答约束",
                "1. 只能依据「当前正文」与「证据」作答；两者都未覆盖的内容，明确说明"
                "「现有正文与证据未覆盖」，并指出需要补充什么资料，禁止编造事实、数据、案例或结论。",
                "2. 引用依据时标注来源：正文写「正文」，证据写 [E1] 形式。",
                "3. 用 Markdown 简洁作答，控制在 400 字内，必要时用要点列表。",
                "4. 不要整段复述正文，只回答被追问的部分。",
                "",
                "## 输出",
                "只输出回答正文，不要输出解释、前言或对回答过程的说明。",
            ]
        )
        return "\n".join(lines)

    def _build_amend_prompt(
        self,
        course: Course | None,
        lesson: Lesson,
        content: str,
        citations: Sequence[Citation],
        instruction: str,
        target: str,
        mode: GenerationMode = GenerationMode.strict,
    ) -> str:
        lines: list[str] = [
            "你是严谨的课程编辑，负责按读者的自然语言指令对一讲正文做局部修改。"
            if mode is GenerationMode.strict
            else "你是经验丰富的课程编辑，负责按读者的自然语言指令修改一讲正文。",
            "",
            "## 讲次",
            f"- 课程：{course.title if course else '未命名课程'}",
            f"- 讲次：第 {lesson.order_index} 讲 · {lesson.title}",
            "",
            "## 修改指令",
            instruction.strip(),
            "",
            "## 修改范围",
            target or "整讲正文",
            "",
            "## 当前正文（Markdown）",
            self._clip(content, self.content_char_limit),
            "",
            "## 证据（正文引用来源）",
        ]
        if citations:
            for index, citation in enumerate(citations, start=1):
                snippet = citation.text or citation.snippet
                lines.append(
                    f"[E{index}] 来源：{citation.source_name}｜片段 #{citation.chunk_index}"
                )
                lines.append(self._clip(snippet.strip(), self.evidence_char_limit))
                lines.append("")
        else:
            lines.extend(["（无引用证据）", ""])

        if mode is GenerationMode.loose:
            lines.extend(
                [
                    "## 修改约束（自由写作模式）",
                    "1. 允许基于自身通用知识补充、扩写或重写与指令相关的部分，不强制逐段引用证据。",
                    f"2. 正文第一行必须保留声明：「{LOOSE_BANNER}」。",
                    "3. 其余章节的顺序与标题层级保持原样，除非指令明确要求调整。",
                    "4. 对时效性或争议性结论标注「建议核实」，不要伪装成已核实事实。",
                    "5. 输出修改后的完整正文，不要输出 diff、解释或前后缀。",
                    "",
                    "## 输出",
                    "只输出修改后的完整正文 Markdown。",
                ]
            )
        else:
            lines.extend(
                [
                    "## 修改约束",
                    "1. 只改与指令相关的部分，其余章节、引用标记 [E1]、标题层级与列表结构保持原样。",
                    "2. 不得引入正文与证据之外的新事实、数据、案例或结论；确实需要补充时写"
                    "「资料不足：<缺口说明>」。",
                    "3. 保留 Markdown 结构（标题、列表、代码块围栏及其语言标注）。",
                    "4. 输出修改后的完整正文，不要输出 diff、解释或前后缀。",
                    "",
                    "## 输出",
                    "只输出修改后的完整正文 Markdown。",
                ]
            )
        return "\n".join(lines)

    def _placeholder_answer(
        self,
        lesson: Lesson,
        question: str,
        citations: Sequence[Citation],
    ) -> str:
        lines: list[str] = [
            "> 占位回答（未配置 LLM API key）：以下内容由该讲正文与引用证据直接编排，"
            "用于验证追问链路（问题、回答、证据均已落库）。",
            "",
            "## 你的问题",
            question.strip(),
            "",
            "## 正文中的相关片段",
        ]
        excerpts = self._relevant_excerpts(lesson.content, question)
        if excerpts:
            lines.extend(f"- {excerpt}" for excerpt in excerpts)
        else:
            lines.append("- 正文为空或未命中与问题相关的片段。")

        lines.extend(["", "## 相关证据"])
        if citations:
            for index, citation in enumerate(citations[:3], start=1):
                snippet = (citation.text or citation.snippet).strip()
                lines.append(
                    f"- [E{index}] {citation.source_name}｜片段 #{citation.chunk_index}："
                    f"{self._clip(snippet, 200)}"
                )
        else:
            lines.append("- 该讲暂无引用证据。")

        lines.extend(
            [
                "",
                "## 不确定说明",
                "未配置真实模型，无法给出推理型回答；以上仅为正文与证据的摘录，不应视为结论。"
                "配置真实 LLM key 后，同一问题会基于同一上下文重新作答。",
            ]
        )
        return "\n".join(lines)

    def _placeholder_amend(
        self,
        content: str,
        instruction: str,
        target: str,
        mode: GenerationMode = GenerationMode.strict,
    ) -> str:
        label = "非严格（自由写作）" if mode is GenerationMode.loose else "严格"
        lines: list[str] = [
            content,
            "",
            "## 待应用修改（占位）",
            "",
            f"> 占位修改（未配置 LLM API key，{label}模式）：指令已记录在该版本 note 中，"
            "配置真实模型后由模型按同一指令重写正文。",
            "",
            f"- 修改指令：{instruction.strip()}",
            f"- 修改范围：{target or '整讲正文'}",
        ]
        if mode is GenerationMode.loose:
            lines.append("- 写作模式：loose（允许模型基于自身知识自由写作，需保留声明行）")
        return "\n".join(lines)

    @staticmethod
    def _amend_note(
        instruction: str, target: str, mode: GenerationMode = GenerationMode.strict
    ) -> str:
        head = f"amend[{target}]" if target else "amend"
        return f"{head}[{mode.value}]: {instruction.strip()}"

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        if limit <= 0 or len(text) <= limit:
            return text
        return text[:limit] + "…"

    @staticmethod
    def _relevant_excerpts(content: str, question: str, limit: int = 2) -> list[str]:
        body = content.strip()
        if not body:
            return []
        tokens = _tokens(question)
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", body) if part.strip()]
        scored: list[tuple[int, int, str]] = []
        for index, paragraph in enumerate(paragraphs):
            if paragraph.startswith("#") and len(paragraph) < 40:
                continue
            score = sum(1 for token in tokens if token and token in paragraph)
            if score:
                scored.append((score, -index, paragraph))
        scored.sort(reverse=True)
        picked = [item[2] for item in scored[:limit]]
        if picked:
            return [ConversationService._clip(item.replace("\n", " "), 240) for item in picked]
        fallback = [part for part in paragraphs if not part.startswith("#")]
        return [
            ConversationService._clip(part.replace("\n", " "), 240)
            for part in fallback[:limit]
        ]

    @staticmethod
    def _select_answer(
        messages: Sequence[Message], message_id: str | None, question: str | None
    ) -> Message | None:
        if message_id:
            for message in messages:
                if message.id == message_id:
                    return message if message.role == "assistant" else None
            return None
        answers = [message for message in messages if message.role == "assistant"]
        if not answers:
            return None
        if question:
            needle = question.strip()
            for message in reversed(answers):
                paired = ConversationService._question_before(messages, message.id) or ""
                if needle and (needle in paired or needle in message.content):
                    return message
            return None
        return answers[-1]

    @staticmethod
    def _question_before(messages: Sequence[Message], message_id: str) -> str | None:
        previous: Message | None = None
        for message in messages:
            if message.id == message_id:
                return previous.content.strip() if previous else None
            if message.role == "user":
                previous = message
        return None

    @staticmethod
    def _drilldown_section(question: str, answer: str) -> str:
        cleaned_question = question.strip().splitlines()[0] if question.strip() else "追问"
        return f"## {DRILLDOWN_HEADING}：{cleaned_question}\n\n{answer.strip()}"


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[0-9A-Za-z_]+|[\u4e00-\u9fa5]{2,}", text)
    tokens: list[str] = []
    for item in raw:
        if "\u4e00" <= item[0] <= "\u9fa5" and len(item) > 2:
            tokens.extend(item[index : index + 2] for index in range(len(item) - 1))
        else:
            tokens.append(item)
    return [token for token in tokens if token]
