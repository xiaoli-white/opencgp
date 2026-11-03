from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.generation import Evidence
from app.models.longform import (
    MAX_SECTION_WORDS,
    SECTION_GENERATED,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    Longform,
    LongformProfile,
    LongformVersion,
    OutlineSection,
)
from app.models.mode import GenerationMode, LOOSE_NOTICE, with_loose_notice
from app.ports.llm import LLMProvider
from app.ports.longform_repository import LongformRepository
from app.ports.vectorstore import VectorStore
from app.services.errors import (
    LongformNotFoundError,
    LongformSectionNotFoundError,
    VersionConflictError,
)

DEFAULT_SECTIONS = (
    ("introduction", "引子", "用一段场景或问题引出主题，说明读者为什么要读下去。"),
    ("background", "背景", "交代主题的来龙去脉、现有做法与主要争议。"),
    ("core-1", "核心展开（一）", "展开第一个关键论点，给出机制、步骤或判断标准。"),
    ("core-2", "核心展开（二）", "展开第二个关键论点，补充案例与反例。"),
    ("conclusion", "结论", "收敛全文，给出可执行的结论与下一步建议。"),
)

NO_EVIDENCE_NOTICE = (
    "资料不足：知识库中未检索到与本节相关的证据，暂不展开正文。"
    "如需模型自由写作，请改用 loose 模式。"
)
SECTION_CHAR_LIMIT = MAX_SECTION_WORDS * 3


class LongformService:
    def __init__(
        self,
        repository: LongformRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 6,
        max_evidence: int = 8,
        evidence_char_limit: int = 400,
        default_mode: str = "loose",
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.default_top_k = default_top_k
        self.max_evidence = max_evidence
        self.evidence_char_limit = evidence_char_limit
        self.default_mode = GenerationMode.normalize(default_mode).value

    async def create(
        self,
        title: str,
        profile: LongformProfile | None = None,
        target_words: int = 3000,
        mode: str | None = None,
        tenant_id: str = "",
        user_id: str = "",
        llm: LLMProvider | None = None,
    ) -> Longform:
        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("标题不能为空")
        resolved_profile = profile or LongformProfile()
        resolved_words = max(200, min(int(target_words or 3000), 50000))
        provider = llm or self.llm
        outline = await self._build_outline(
            provider, resolved_title, resolved_profile, resolved_words
        )
        longform = Longform(
            id=f"longform_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id or "",
            user_id=user_id or "",
            title=resolved_title,
            profile=resolved_profile,
            outline=outline,
            status=STATUS_DRAFT,
            current_version=0,
            target_words=resolved_words,
            last_mode=GenerationMode.normalize(mode or self.default_mode).value,
            created_at=time.time(),
            updated_at=time.time(),
        )
        return self.repository.create(longform)

    def get(self, longform_id: str, tenant_id: str | None = None) -> Longform | None:
        return self.repository.get(longform_id, tenant_id)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Longform]:
        return self.repository.list(tenant_id, limit)

    def list_versions(self, longform_id: str) -> list[LongformVersion]:
        return self.repository.list_versions(longform_id)

    def delete(self, longform_id: str, tenant_id: str | None = None) -> bool:
        return self.repository.delete(longform_id, tenant_id)

    async def generate_section(
        self,
        longform_id: str,
        section_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
    ) -> tuple[OutlineSection, Longform]:
        longform = self._require(longform_id)
        section = next(
            (item for item in longform.outline if item.id == section_id), None
        )
        if section is None:
            raise LongformSectionNotFoundError(section_id)
        resolved_mode = GenerationMode.normalize(mode or longform.last_mode or self.default_mode)
        provider = llm or self.llm
        citations, evidence = await self._evidence(
            longform, section, top_k, tenant_id
        )
        content = await self._write_section(
            provider, longform, section, evidence, resolved_mode, citations
        )
        merged_citations = list(longform.citations)
        known = {(item.source_id, item.chunk_index) for item in merged_citations}
        for citation in citations:
            key = (citation.source_id, citation.chunk_index)
            if key not in known:
                known.add(key)
                merged_citations.append(citation)
        updated_outline = [
            item.model_copy(
                update={"content": content, "status": SECTION_GENERATED}
            )
            if item.id == section.id
            else item
            for item in longform.outline
        ]
        applied = self.repository.append_version(
            longform_id,
            content=self._compose(longform, updated_outline),
            outline=updated_outline,
            citations=merged_citations,
            note=f"section:{section.id}",
            mode=resolved_mode.value,
        )
        if applied is None:
            raise LongformNotFoundError(longform_id)
        updated, _ = applied
        refreshed = next(
            (item for item in updated.outline if item.id == section.id), section
        )
        return refreshed, updated

    async def generate_all(
        self,
        longform_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
    ) -> Longform:
        longform = self._require(longform_id)
        resolved_mode = GenerationMode.normalize(mode or longform.last_mode or self.default_mode)
        provider = llm or self.llm
        sections: list[OutlineSection] = []
        citations: list[Citation] = []
        known: set[tuple[str, int]] = set()
        for section in longform.outline:
            found, evidence = await self._evidence(longform, section, top_k, tenant_id)
            for citation in found:
                key = (citation.source_id, citation.chunk_index)
                if key not in known:
                    known.add(key)
                    citations.append(citation)
            content = await self._write_section(
                provider, longform, section, evidence, resolved_mode, found
            )
            sections.append(
                section.model_copy(
                    update={"content": content, "status": SECTION_GENERATED}
                )
            )
        applied = self.repository.append_version(
            longform_id,
            content=self._compose(longform, sections),
            outline=sections,
            citations=citations,
            note="generate_all",
            mode=resolved_mode.value,
        )
        if applied is None:
            raise LongformNotFoundError(longform_id)
        return applied[0]

    async def rewrite(
        self,
        longform_id: str,
        instruction: str,
        mode: str | None = None,
        expected_version: int | None = None,
        llm: LLMProvider | None = None,
    ) -> Longform:
        longform = self._require(longform_id)
        if expected_version is not None and int(expected_version) != longform.current_version:
            raise VersionConflictError(int(expected_version), longform.current_version)
        resolved_mode = GenerationMode.normalize(mode or longform.last_mode or self.default_mode)
        provider = llm or self.llm
        body = longform.content.strip()
        if not body:
            raise ValueError("正文为空，请先生成或填写正文后再重写")
        if getattr(provider, "is_placeholder", False):
            text = self._rewrite_placeholder(longform, instruction)
        else:
            text = await provider.complete(self._rewrite_prompt(longform, instruction))
        if resolved_mode is GenerationMode.loose:
            text = with_loose_notice(text)
        applied = self.repository.append_version(
            longform_id,
            content=text,
            outline=longform.outline,
            citations=longform.citations,
            note=f"rewrite:{instruction[:40]}",
            mode=resolved_mode.value,
        )
        if applied is None:
            raise LongformNotFoundError(longform_id)
        return applied[0]

    def revert(
        self, longform_id: str, version: int, note: str = ""
    ) -> tuple[Longform, LongformVersion]:
        longform = self._require(longform_id)
        target = self.repository.get_version(longform_id, int(version))
        if target is None:
            raise LongformNotFoundError(f"版本不存在: {version}")
        applied = self.repository.append_version(
            longform_id,
            content=target.content,
            outline=target.outline,
            citations=target.citations,
            note=note or f"revert:{version}",
            mode=target.mode,
        )
        if applied is None:
            raise LongformNotFoundError(longform_id)
        return applied

    def _require(self, longform_id: str) -> Longform:
        longform = self.repository.get(longform_id)
        if longform is None:
            raise LongformNotFoundError(longform_id)
        return longform

    async def _build_outline(
        self,
        provider: LLMProvider,
        title: str,
        profile: LongformProfile,
        target_words: int,
    ) -> list[OutlineSection]:
        if getattr(provider, "is_placeholder", False):
            return self._template_outline(target_words)
        try:
            text = await provider.complete(
                self._outline_prompt(title, profile, target_words)
            )
        except Exception:
            return self._template_outline(target_words)
        payload = _extract_json_list(text)
        sections = _sections_from_payload(payload, target_words)
        return sections or self._template_outline(target_words)

    @staticmethod
    def _template_outline(target_words: int) -> list[OutlineSection]:
        per = max(200, target_words // len(DEFAULT_SECTIONS))
        return [
            OutlineSection(
                id=section_id,
                title=title,
                summary=summary,
                target_words=per,
            )
            for section_id, title, summary in DEFAULT_SECTIONS
        ]

    def _outline_prompt(
        self, title: str, profile: LongformProfile, target_words: int
    ) -> str:
        return "\n".join(
            [
                "你是长文写作规划员，需要为一篇单页长篇生成章节大纲。",
                f"- 标题：{title}",
                f"- 体裁：{profile.genre}；语气：{profile.tone or '中性'}；读者：{profile.audience or '通用'}；人称：{profile.pov or '第三人称'}",
                f"- 目标总字数：{target_words}",
                "要求：4-7 个章节，首尾必须包含引子与结论。",
                "只输出 JSON 数组，不要 Markdown 代码块与解释，元素结构：",
                '{"id":"section-1","title":"章节标题","summary":"本章要点","target_words":600}',
            ]
        )

    async def _evidence(
        self,
        longform: Longform,
        section: OutlineSection,
        top_k: int | None,
        tenant_id: str,
    ) -> tuple[list[Citation], list[Evidence]]:
        query = " ".join(
            part
            for part in (longform.title, section.title, section.summary)
            if part
        ).strip()
        citations = await self.vectorstore.search(
            query,
            top_k=max(1, min(int(top_k or self.default_top_k), 20)),
            tenant_id=tenant_id,
        )
        citations = citations[: self.max_evidence]
        evidence = [
            Evidence(marker=f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]
        return citations, evidence

    async def _write_section(
        self,
        provider: LLMProvider,
        longform: Longform,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        citations: Sequence[Citation],
    ) -> str:
        if mode is GenerationMode.strict and not evidence:
            return NO_EVIDENCE_NOTICE
        if getattr(provider, "is_placeholder", False):
            draft = self._placeholder_section(longform, section, evidence, mode)
            return self._finish(draft, mode)
        prompt = (
            self._strict_prompt(longform, section, evidence)
            if mode is GenerationMode.strict
            else self._loose_prompt(longform, section, evidence)
        )
        text = await provider.complete(prompt)
        return self._finish(text, mode)

    @staticmethod
    def _finish(text: str, mode: GenerationMode) -> str:
        clipped = (text or "").strip()[:SECTION_CHAR_LIMIT]
        if mode is GenerationMode.loose:
            return with_loose_notice(clipped)
        return clipped

    def _placeholder_section(
        self,
        longform: Longform,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
    ) -> str:
        lines = [
            f"## {section.title}",
            "",
            section.summary or f"本节围绕「{longform.title}」展开。",
            "",
        ]
        if evidence:
            for item in evidence[:4]:
                snippet = (item.citation.snippet or item.citation.text or "").strip()
                lines.append(f"- {snippet} [{item.marker}]")
        else:
            lines.append("- 本段为占比位正文，待接入真实模型后由证据展开。")
        return "\n".join(lines)

    def _strict_prompt(
        self,
        longform: Longform,
        section: OutlineSection,
        evidence: Sequence[Evidence],
    ) -> str:
        lines = [
            "你是严谨的长文作者，正在撰写一篇单页长篇中的某一节。",
            f"- 长篇标题：{longform.title}",
            f"- 本节标题：{section.title}",
            f"- 本节要点：{section.summary}",
            f"- 读者：{longform.profile.audience or '通用'}；语气：{longform.profile.tone or '中性'}",
            f"- 字数上限：{min(MAX_SECTION_WORDS, section.target_words or MAX_SECTION_WORDS)} 字",
            "",
            "硬约束：",
            "1. 只能使用下面证据中明确陈述的内容，不得引入证据之外的事实与数据。",
            "2. 每个自然段至少标注一个来源标记，格式 [E1]。",
            "3. 证据不足时写明「资料不足：<缺口说明>」，不要编造。",
            "",
            "证据：",
        ]
        for item in evidence:
            snippet = (item.citation.snippet or item.citation.text or "")[
                : self.evidence_char_limit
            ]
            lines.append(f"[{item.marker}] {item.citation.source_name}：{snippet}")
        lines.append("只输出本节正文 Markdown，不要输出解释。")
        return "\n".join(lines)

    def _loose_prompt(
        self,
        longform: Longform,
        section: OutlineSection,
        evidence: Sequence[Evidence],
    ) -> str:
        lines = [
            "你是经验丰富的长文作者，正在撰写一篇单页长篇中的某一节。",
            "本节使用自由写作模式：可基于自身知识展开，证据仅供参考，不强制逐段引用。",
            f"- 长篇标题：{longform.title}",
            f"- 本节标题：{section.title}",
            f"- 本节要点：{section.summary}",
            f"- 体裁：{longform.profile.genre}；读者：{longform.profile.audience or '通用'}；语气：{longform.profile.tone or '中性'}",
            f"- 字数上限：{min(MAX_SECTION_WORDS, section.target_words or MAX_SECTION_WORDS)} 字",
        ]
        if evidence:
            lines.append("")
            lines.append("参考证据：")
            for item in evidence:
                snippet = (item.citation.snippet or item.citation.text or "")[
                    : self.evidence_char_limit
                ]
                lines.append(f"[{item.marker}] {item.citation.source_name}：{snippet}")
        lines.append("只输出本节正文 Markdown，不要输出解释。")
        return "\n".join(lines)

    def _rewrite_prompt(self, longform: Longform, instruction: str) -> str:
        return "\n".join(
            [
                "你是资深编辑，请按要求重写下面这篇单页长篇，保留原有事实与结构，输出完整正文。",
                f"- 标题：{longform.title}",
                f"- 改写要求：{instruction}",
                "",
                "原文：",
                longform.content[:6000],
            ]
        )

    @staticmethod
    def _rewrite_placeholder(longform: Longform, instruction: str) -> str:
        return "\n".join(
            [
                f"> 占位重写（{instruction}）：未配置 LLM key，以下为原文摘要",
                "",
                longform.content.strip()[:SECTION_CHAR_LIMIT],
            ]
        )

    @staticmethod
    def _compose(longform: Longform, outline: Sequence[OutlineSection]) -> str:
        blocks: list[str] = [f"# {longform.title}", ""]
        loose = any(LOOSE_NOTICE in section.content for section in outline)
        for section in outline:
            body = section.content.strip()
            if not body:
                continue
            if body.startswith("#"):
                blocks.append(body)
            else:
                blocks.append(f"## {section.title}")
                blocks.append("")
                blocks.append(body)
            blocks.append("")
        composed = "\n".join(blocks).strip()
        if loose:
            return with_loose_notice(composed)
        return composed


def _extract_json_list(raw: str) -> Any:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    candidate = text[start : end + 1] if start != -1 and end > start else text
    for attempt in (candidate, _repair_json(candidate)):
        try:
            return json.loads(attempt)
        except (TypeError, ValueError):
            continue
    return None


def _repair_json(text: str) -> str:
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    repaired += "]" * max(0, repaired.count("[") - repaired.count("]"))
    repaired += "}" * max(0, repaired.count("{") - repaired.count("}"))
    return repaired


def _sections_from_payload(
    payload: Any, target_words: int
) -> list[OutlineSection]:
    if not isinstance(payload, list):
        return []
    sections: list[OutlineSection] = []
    default_target = max(200, target_words // max(1, len(payload)))
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, Mapping):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        section_id = item.get("id")
        resolved_id = (
            section_id.strip()
            if isinstance(section_id, str) and section_id.strip()
            else f"section-{index}"
        )
        summary = item.get("summary")
        try:
            section_words = int(item.get("target_words") or default_target)
        except (TypeError, ValueError):
            section_words = default_target
        sections.append(
            OutlineSection(
                id=resolved_id,
                title=title.strip(),
                summary=summary.strip() if isinstance(summary, str) else "",
                target_words=max(100, min(section_words, MAX_SECTION_WORDS)),
            )
        )
    return sections
