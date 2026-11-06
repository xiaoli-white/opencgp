"""Follow-up, local revision, and consolidation service (Ask & Amend).

Turns every chapter into a living document that can be questioned and locally revised:

- ``ask``: answers a follow-up using the chapter's current body + cited evidence +
  the chapter's conversation history as context, and persists both the user and
  assistant messages (even without a real key).
- ``amend``: rewrites the body from a natural-language instruction and persists a new
  version through the append-only versioning mechanism, writing the raw instruction
  into the version note; historical versions are never overwritten.
- ``amend`` supports both ``strict`` and ``loose`` modes: loose lets the model rewrite
  freely from its own knowledge, but the first line of the body must keep the
  "written by an LLM" notice.
- ``drilldown``: consolidates the answer to a follow-up into a new section of the
  body, also appending a new version (note=drilldown).

Hallucination suppression follows the generation-time convention: only the body and
evidence may be used, and anything not covered must be stated explicitly. When no real
LLM key is configured (placeholder provider), placeholder content is assembled from the
body and evidence while the chain (messages, versions, citations) stays fully verifiable.
"""

from __future__ import annotations

import re
from typing import Sequence

from app.models.citation import Citation
from app.models.series import Series, Unit
from app.models.mode import LOOSE_BANNER, GenerationMode, with_loose_notice
from app.models.thread import (
    AmendResult,
    AskResult,
    DrilldownResult,
    Message,
    Thread,
)
from app.ports.conversation_repository import ConversationRepository
from app.ports.series_repository import SeriesRepository
from app.ports.llm import LLMProvider
from app.services.errors import (
    EmptyLLMResponseError,
    UnitContentEmptyError,
    UnitNotFoundError,
    MessageNotFoundError,
    VersionConflictError,
)

DRILLDOWN_NOTE = "drilldown"
DRILLDOWN_HEADING = "Follow-up addendum"
SELECTION_CHAR_LIMIT = 1200


class ConversationService:
    def __init__(
        self,
        repository: SeriesRepository,
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
        self,
        unit_id: str,
        question: str,
        selection: str | None = None,
        llm: LLMProvider | None = None,
    ) -> AskResult:
        unit, series, citations = self._context(unit_id)
        thread = self._unit_thread(unit)
        history = self.conversations.list_messages(thread.id, limit=self.history_limit)
        selected = (selection or "").strip() or None
        prompt = self._build_ask_prompt(
            series, unit, citations, history, question, selected
        )

        llm_provider = llm or self.llm
        provider = type(llm_provider).__name__
        if getattr(llm_provider, "is_placeholder", False):
            answer = self._placeholder_answer(unit, question, citations)
        else:
            answer = (await llm_provider.complete(prompt)).strip()
            if not answer:
                raise EmptyLLMResponseError("the model returned no answer to the follow-up question")

        user_message = self.conversations.append_message(thread.id, "user", question)
        assistant_message = self.conversations.append_message(
            thread.id, "assistant", answer, citations
        )
        return AskResult(
            unit_id=unit.id,
            thread_id=thread.id,
            question=question,
            answer=answer,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            citations=citations,
            grounded=bool(citations) and bool(unit.content.strip()),
            provider=provider,
            prompt=prompt,
        )

    async def amend(
        self,
        unit_id: str,
        instruction: str,
        target: str | None = None,
        mode: str | None = None,
        expected_version: int | None = None,
        llm: LLMProvider | None = None,
    ) -> AmendResult:
        unit, series, citations = self._context(unit_id)
        if expected_version is not None and int(expected_version) != unit.current_version:
            raise VersionConflictError(int(expected_version), unit.current_version)
        current_content = unit.content.strip()
        if not current_content:
            raise UnitContentEmptyError(unit_id)
        resolved_mode = GenerationMode.normalize(mode)
        resolved_target = (target or "").strip()
        prompt = self._build_amend_prompt(
            series,
            unit,
            current_content,
            citations,
            instruction,
            resolved_target,
            resolved_mode,
        )

        llm_provider = llm or self.llm
        provider = type(llm_provider).__name__
        if getattr(llm_provider, "is_placeholder", False):
            new_content = self._placeholder_amend(
                current_content, instruction, resolved_target, resolved_mode
            )
        else:
            new_content = (await llm_provider.complete(prompt)).strip()
            if not new_content:
                raise EmptyLLMResponseError("the model returned no revised body")
        if resolved_mode is GenerationMode.loose:
            new_content = with_loose_notice(new_content)

        note = self._amend_note(instruction, resolved_target, resolved_mode)
        applied = self.repository.append_version(
            unit_id,
            content=new_content,
            citations=citations,
            note=note,
            status="amended",
            mode=resolved_mode.value,
        )
        if applied is None:
            raise UnitNotFoundError(unit_id)
        updated, record = applied

        thread = self._unit_thread(unit)
        scope = f"[{resolved_target}] " if resolved_target else ""
        self.conversations.append_message(
            thread.id, "user", f"[amend:{resolved_mode.value}] {scope}{instruction.strip()}"
        )
        self.conversations.append_message(
            thread.id,
            "assistant",
            f"Generated version {record.version} of the body from the instruction ({resolved_mode.value} mode).\n\n{updated.content}",
            citations,
        )

        return AmendResult(
            unit_id=unit_id,
            instruction=instruction,
            target=resolved_target,
            version=record.version,
            previous_version=unit.current_version,
            mode=resolved_mode.value,
            content=updated.content,
            citations=citations,
            note=record.note,
            provider=provider,
            prompt=prompt,
        )

    async def drilldown(
        self,
        unit_id: str,
        message_id: str | None = None,
        question: str | None = None,
        llm: LLMProvider | None = None,
    ) -> DrilldownResult:
        unit, _series, unit_citations = self._context(unit_id)
        thread = self.conversations.get_unit_thread(unit_id)
        if thread is None:
            raise MessageNotFoundError(unit_id)
        messages = self.conversations.list_messages(thread.id)
        source = self._select_answer(messages, message_id, question)
        if source is None:
            raise MessageNotFoundError(message_id or question or unit_id)

        source_question = self._question_before(messages, source.id) or (question or "Follow-up")
        appended = self._drilldown_section(source_question, source.content)
        base = unit.content.rstrip()
        new_content = f"{base}\n\n{appended}" if base else appended
        citations = source.citations or unit_citations

        applied = self.repository.append_version(
            unit_id,
            content=new_content,
            citations=citations,
            note=DRILLDOWN_NOTE,
            status="amended",
            mode=unit.last_mode,
        )
        if applied is None:
            raise UnitNotFoundError(unit_id)
        updated, record = applied

        return DrilldownResult(
            unit_id=unit_id,
            thread_id=thread.id,
            source_message_id=source.id,
            version=record.version,
            content=updated.content,
            appended=appended,
            citations=citations,
            note=record.note,
        )

    def _context(
        self, unit_id: str
    ) -> tuple[Unit, Series | None, list[Citation]]:
        unit = self.repository.get_unit(unit_id)
        if unit is None:
            raise UnitNotFoundError(unit_id)
        series = self.repository.get_series(unit.series_id)
        citations: list[Citation] = []
        if unit.current_version > 0:
            version = self.repository.get_version(unit_id, unit.current_version)
            if version is not None:
                citations = list(version.citations)
        return unit, series, citations

    def _unit_thread(self, unit: Unit) -> Thread:
        return self.conversations.get_or_create_unit_thread(
            unit.id, unit.series_id, f"{unit.title} · Conversation"
        )

    def _build_ask_prompt(
        self,
        series: Series | None,
        unit: Unit,
        citations: Sequence[Citation],
        history: Sequence[Message],
        question: str,
        selection: str | None = None,
    ) -> str:
        lines: list[str] = [
            "You are the teaching assistant for this course and answer reader follow-ups based on the chapter's completed body and cited evidence.",
            "",
            "## Chapter",
            f"- Series: {series.title if series else 'Untitled series'}",
            f"- Chapter {unit.order_index} · {unit.title}",
        ]
        if unit.learning_objectives:
            lines.append("- Learning objectives: " + "; ".join(unit.learning_objectives))

        lines.extend(["", "## Current body (Markdown)"])
        content = unit.content.strip()
        if content:
            lines.append(self._clip(content, self.content_char_limit))
        else:
            lines.append("(This chapter has no body yet; the body is empty)")

        lines.extend(["", "## Evidence (sources cited by the body)"])
        if citations:
            for index, citation in enumerate(citations, start=1):
                snippet = citation.text or citation.snippet
                lines.append(
                    f"[E{index}] Source: {citation.source_name} | chunk #{citation.chunk_index}"
                )
                lines.append(self._clip(snippet.strip(), self.evidence_char_limit))
                lines.append("")
        else:
            lines.extend(["(No cited evidence)", ""])

        lines.extend(["## Conversation history"])
        if history:
            for message in history:
                speaker = "Reader" if message.role == "user" else "Assistant"
                spoken = " ".join(message.content.split())
                lines.append(f"- {speaker}: {self._clip(spoken, self.history_char_limit)}")
        else:
            lines.append("- (This turn starts the conversation)")

        lines.extend(["", "## Reader follow-up"])
        if selection:
            excerpt = self._clip(selection.strip(), SELECTION_CHAR_LIMIT)
            lines.extend(
                [
                    "The user selected the following excerpt from the body:",
                    f'"""{excerpt}"""',
                    f"Answer this follow-up about the selected content: {question.strip()}",
                ]
            )
        else:
            lines.append(question.strip())

        lines.extend(
            [
                "",
                "## Answer constraints",
                "1. Answer only from the \"Current body\" and \"Evidence\"; for anything neither covers, state explicitly "
                "\"not covered by the existing body or evidence\" and point out what material is needed. Never fabricate facts, data, cases, or conclusions.",
                "2. Mark the basis of citations: write \"body\" for the body and [E1] for evidence.",
                "3. Answer concisely in Markdown, within 400 characters, using bullet lists where helpful.",
                "4. Do not restate the body in full; answer only the part asked about.",
                "",
                "## Output",
                "Output only the answer body; do not output explanations, prefaces, or commentary about the answering process.",
            ]
        )
        return "\n".join(lines)

    def _build_amend_prompt(
        self,
        series: Series | None,
        unit: Unit,
        content: str,
        citations: Sequence[Citation],
        instruction: str,
        target: str,
        mode: GenerationMode = GenerationMode.strict,
    ) -> str:
        lines: list[str] = [
            "You are a rigorous course editor responsible for making local revisions to a chapter's body according to the reader's natural-language instruction."
            if mode is GenerationMode.strict
            else "You are an experienced course editor responsible for revising a chapter's body according to the reader's natural-language instruction.",
            "",
            "## Chapter",
            f"- Series: {series.title if series else 'Untitled series'}",
            f"- Chapter {unit.order_index} · {unit.title}",
            "",
            "## Revision instruction",
            instruction.strip(),
            "",
            "## Revision scope",
            target or "the whole chapter body",
            "",
            "## Current body (Markdown)",
            self._clip(content, self.content_char_limit),
            "",
            "## Evidence (sources cited by the body)",
        ]
        if citations:
            for index, citation in enumerate(citations, start=1):
                snippet = citation.text or citation.snippet
                lines.append(
                    f"[E{index}] Source: {citation.source_name} | chunk #{citation.chunk_index}"
                )
                lines.append(self._clip(snippet.strip(), self.evidence_char_limit))
                lines.append("")
        else:
            lines.extend(["(No cited evidence)", ""])

        if mode is GenerationMode.loose:
            lines.extend(
                [
                    "## Revision constraints (free-writing mode)",
                    "1. You may add to, expand, or rewrite the parts related to the instruction from your own general knowledge; per-paragraph citations are not required.",
                    f"2. The first line of the body must keep the notice: \"{LOOSE_BANNER}\".",
                    "3. Keep the order of the remaining sections and the heading hierarchy unchanged unless the instruction explicitly asks otherwise.",
                    "4. Mark time-sensitive or disputed conclusions as \"recommend verifying\"; do not present them as verified facts.",
                    "5. Output the complete revised body; do not output a diff, explanations, or prefixes/suffixes.",
                    "",
                    "## Output",
                    "Output only the complete revised body Markdown.",
                ]
            )
        else:
            lines.extend(
                [
                    "## Revision constraints",
                    "1. Change only the parts related to the instruction; keep the other sections, citation markers [E1], heading hierarchy, and list structure unchanged.",
                    "2. Do not introduce new facts, data, cases, or conclusions beyond the body and evidence; if something really must be added, write "
                    "\"Insufficient material: <gap description>\".",
                    "3. Preserve the Markdown structure (headings, lists, code-fence blocks, and their language tags).",
                    "4. Output the complete revised body; do not output a diff, explanations, or prefixes/suffixes.",
                    "",
                    "## Output",
                    "Output only the complete revised body Markdown.",
                ]
            )
        return "\n".join(lines)

    def _placeholder_answer(
        self,
        unit: Unit,
        question: str,
        citations: Sequence[Citation],
    ) -> str:
        lines: list[str] = [
            "> Placeholder answer (no LLM API key configured): the content below is assembled directly from the chapter body and cited evidence "
            "to verify the follow-up pipeline (question, answer, and evidence are all persisted).",
            "",
            "## Your question",
            question.strip(),
            "",
            "## Relevant excerpts from the body",
        ]
        excerpts = self._relevant_excerpts(unit.content, question)
        if excerpts:
            lines.extend(f"- {excerpt}" for excerpt in excerpts)
        else:
            lines.append("- The body is empty or contains no excerpt related to the question.")

        lines.extend(["", "## Related evidence"])
        if citations:
            for index, citation in enumerate(citations[:3], start=1):
                snippet = (citation.text or citation.snippet).strip()
                lines.append(
                    f"- [E{index}] {citation.source_name} | chunk #{citation.chunk_index}: "
                    f"{self._clip(snippet, 200)}"
                )
        else:
            lines.append("- This chapter has no cited evidence yet.")

        lines.extend(
            [
                "",
                "## Uncertainty note",
                "No real model is configured, so no reasoning answer can be produced; the above is only an excerpt of the body and evidence and should not be treated as a conclusion. "
                "Once a real LLM key is configured, the same question will be answered again from the same context.",
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
        label = "non-strict (free writing)" if mode is GenerationMode.loose else "strict"
        lines: list[str] = [
            content,
            "",
            "## Pending revision (placeholder)",
            "",
            f"> Placeholder revision (no LLM API key configured, {label} mode): the instruction is recorded in this version's note; "
            "once a real model is configured, it will rewrite the body from the same instruction.",
            "",
            f"- Revision instruction: {instruction.strip()}",
            f"- Revision scope: {target or 'the whole chapter body'}",
        ]
        if mode is GenerationMode.loose:
            lines.append("- Writing mode: loose (the model may write freely from its own knowledge; the notice line must be kept)")
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
        cleaned_question = question.strip().splitlines()[0] if question.strip() else "Follow-up"
        return f"## {DRILLDOWN_HEADING}: {cleaned_question}\n\n{answer.strip()}"


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[0-9A-Za-z_]+|[\u4e00-\u9fa5]{2,}", text)
    tokens: list[str] = []
    for item in raw:
        if "\u4e00" <= item[0] <= "\u9fa5" and len(item) > 2:
            tokens.extend(item[index : index + 2] for index in range(len(item) - 1))
        else:
            tokens.append(item)
    return [token for token in tokens if token]
