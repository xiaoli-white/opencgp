from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Callable, Mapping, Sequence

from app.models.citation import Citation
from app.models.generation import Evidence
from app.models.longform import (
    MAX_SECTION_WORDS,
    SECTION_GENERATED,
    SECTION_PLANNED,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    Longform,
    LongformProfile,
    LongformVersion,
    OutlineSection,
)
from app.models.mode import GenerationMode, LOOSE_NOTICE, with_loose_notice
from app.models.work_profile import ProfileSpec
from app.ports.llm import LLMProvider
from app.ports.longform_repository import LongformRepository
from app.ports.vectorstore import VectorStore
from app.services.errors import (
    LongformNotFoundError,
    LongformSectionNotFoundError,
    VersionConflictError,
)
from app.services.prompting import extra_requirement, prompt_values, unit_name
from app.services.retrieval_providers import RetrievalContext

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
_CN_DIGITS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _cn_number(value: int) -> str:
    if 1 <= value <= len(_CN_DIGITS):
        return _CN_DIGITS[value - 1]
    return str(value)


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
        profile_id: str = "",
        spec: ProfileSpec | None = None,
        retrieval: RetrievalContext | None = None,
    ) -> Longform:
        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("标题不能为空")
        resolved_profile = profile or LongformProfile()
        resolved_words = max(200, min(int(target_words or 3000), 50000))
        provider = llm or self.llm
        outline = await self._build_outline(
            provider, resolved_title, resolved_profile, resolved_words, spec
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
            profile_id=profile_id or "",
            warnings=list(retrieval.warnings) if retrieval is not None else [],
            retrieval=retrieval.summary() if retrieval is not None else {},
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

    def get_version(self, longform_id: str, version: int) -> LongformVersion | None:
        return self.repository.get_version(longform_id, int(version))

    def delete(self, longform_id: str, tenant_id: str | None = None) -> bool:
        return self.repository.delete(longform_id, tenant_id)

    def update_meta(
        self,
        longform_id: str,
        title: str | None = None,
        profile: Mapping[str, Any] | None = None,
        target_words: int | None = None,
        profile_id: str | None = None,
    ) -> Longform:
        longform = self._require(longform_id)
        merged_profile: LongformProfile | None = None
        if profile:
            data = longform.profile.model_dump()
            for key, value in dict(profile).items():
                if value is not None:
                    data[key] = value
            merged_profile = LongformProfile(**data)
        resolved_title = title.strip() if isinstance(title, str) and title.strip() else None
        resolved_words = (
            max(200, min(int(target_words), 50000)) if target_words is not None else None
        )
        updated = self.repository.update(
            longform_id,
            title=resolved_title,
            profile=merged_profile.model_dump() if merged_profile else None,
            target_words=resolved_words,
            profile_id=profile_id,
        )
        if updated is None:
            raise LongformNotFoundError(longform_id)
        return updated

    def save_content(
        self,
        longform_id: str,
        content: str,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> tuple[Longform, LongformVersion]:
        longform = self._require(longform_id)
        if expected_version is not None and int(expected_version) != longform.current_version:
            raise VersionConflictError(int(expected_version), longform.current_version)
        applied = self.repository.append_version(
            longform_id,
            content=content,
            outline=longform.outline,
            citations=longform.citations,
            note=(note or "").strip() or "manual edit",
            mode="manual",
        )
        if applied is None:
            raise LongformNotFoundError(longform_id)
        return applied

    def add_section(
        self,
        longform_id: str,
        title: str,
        summary: str = "",
        target_words: int = 0,
        after_id: str | None = None,
    ) -> tuple[OutlineSection, Longform]:
        longform = self._require(longform_id)
        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("章节标题不能为空")
        sections = list(longform.outline)
        section = OutlineSection(
            id=self._new_section_id(sections),
            title=resolved_title,
            summary=(summary or "").strip(),
            target_words=max(0, min(int(target_words or 0), MAX_SECTION_WORDS)),
        )
        index = len(sections)
        if after_id:
            position = next(
                (i for i, item in enumerate(sections) if item.id == after_id), None
            )
            if position is None:
                raise LongformSectionNotFoundError(after_id)
            index = position + 1
        sections.insert(index, section)
        updated = self._apply_sections(longform, sections, "section:add")
        return section, updated

    def update_section(
        self,
        longform_id: str,
        section_id: str,
        title: str | None = None,
        summary: str | None = None,
        target_words: int | None = None,
        content: str | None = None,
    ) -> Longform:
        longform = self._require(longform_id)
        sections: list[OutlineSection] = []
        found = False
        for item in longform.outline:
            if item.id != section_id:
                sections.append(item)
                continue
            found = True
            updates: dict[str, Any] = {}
            if isinstance(title, str) and title.strip():
                updates["title"] = title.strip()
            if summary is not None:
                updates["summary"] = summary
            if target_words is not None:
                updates["target_words"] = max(
                    0, min(int(target_words), MAX_SECTION_WORDS)
                )
            if content is not None:
                updates["content"] = content
                updates["status"] = SECTION_GENERATED if content.strip() else SECTION_PLANNED
            sections.append(item.model_copy(update=updates) if updates else item)
        if not found:
            raise LongformSectionNotFoundError(section_id)
        return self._apply_sections(longform, sections, "section:edit")

    def delete_section(self, longform_id: str, section_id: str) -> Longform:
        longform = self._require(longform_id)
        if len(longform.outline) <= 1:
            raise ValueError("至少保留一个章节")
        sections = [item for item in longform.outline if item.id != section_id]
        if len(sections) == len(longform.outline):
            raise LongformSectionNotFoundError(section_id)
        return self._apply_sections(longform, sections, "section:delete")

    def reorder_sections(
        self, longform_id: str, section_ids: Sequence[str]
    ) -> Longform:
        longform = self._require(longform_id)
        by_id = {item.id: item for item in longform.outline}
        ordered: list[OutlineSection] = []
        seen: set[str] = set()
        for section_id in section_ids:
            item = by_id.get(str(section_id))
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            ordered.append(item)
        ordered.extend(item for item in longform.outline if item.id not in seen)
        return self._apply_sections(longform, ordered, "section:reorder")

    def _apply_sections(
        self,
        longform: Longform,
        sections: Sequence[OutlineSection],
        note: str,
    ) -> Longform:
        applied = self.repository.append_version(
            longform.id,
            content=self._compose(longform, sections),
            outline=sections,
            citations=longform.citations,
            note=note,
            mode="manual",
        )
        if applied is None:
            raise LongformNotFoundError(longform.id)
        return applied[0]

    @staticmethod
    def _new_section_id(sections: Sequence[OutlineSection]) -> str:
        known = {item.id for item in sections}
        while True:
            candidate = f"sec_{uuid.uuid4().hex[:8]}"
            if candidate not in known:
                return candidate

    async def generate_section(
        self,
        longform_id: str,
        section_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
        retrieval: RetrievalContext | None = None,
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
            longform, section, top_k, tenant_id, retrieval
        )
        content = await self._write_section(
            provider, longform, section, evidence, resolved_mode, citations
        )
        merged_citations = list(longform.citations)
        by_key = {
            (item.source_id, item.chunk_index): item for item in merged_citations
        }
        for citation in citations:
            key = (citation.source_id, citation.chunk_index)
            existing = by_key.get(key)
            if existing is not None:
                existing.keyword_score = citation.keyword_score
                existing.vector_score = citation.vector_score
                existing.rerank_score = citation.rerank_score
                existing.embedding_model = citation.embedding_model
                existing.rerank_model = citation.rerank_model
                existing.meta.update(citation.meta)
                continue
            by_key[key] = citation
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
        if retrieval is not None:
            updated.warnings = list(retrieval.warnings)
            updated.retrieval = retrieval.summary()
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
        on_progress: Callable[[int, int], None] | None = None,
        retrieval: RetrievalContext | None = None,
    ) -> Longform:
        longform = self._require(longform_id)
        resolved_mode = GenerationMode.normalize(mode or longform.last_mode or self.default_mode)
        provider = llm or self.llm
        sections: list[OutlineSection] = []
        citations: list[Citation] = []
        by_key: dict[tuple[str, int], Citation] = {}
        total = max(1, len(longform.outline))
        for index, section in enumerate(longform.outline, start=1):
            found, evidence = await self._evidence(
                longform, section, top_k, tenant_id, retrieval
            )
            for citation in found:
                key = (citation.source_id, citation.chunk_index)
                existing = by_key.get(key)
                if existing is not None:
                    existing.keyword_score = citation.keyword_score
                    existing.vector_score = citation.vector_score
                    existing.rerank_score = citation.rerank_score
                    existing.embedding_model = citation.embedding_model
                    existing.rerank_model = citation.rerank_model
                    existing.meta.update(citation.meta)
                    continue
                by_key[key] = citation
                citations.append(citation)
            content = await self._write_section(
                provider, longform, section, evidence, resolved_mode, found
            )
            sections.append(
                section.model_copy(
                    update={"content": content, "status": SECTION_GENERATED}
                )
            )
            if on_progress is not None:
                on_progress(index, total)
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
        updated = applied[0]
        if retrieval is not None:
            updated.warnings = list(retrieval.warnings)
            updated.retrieval = retrieval.summary()
        return updated

    async def rewrite(
        self,
        longform_id: str,
        instruction: str,
        mode: str | None = None,
        expected_version: int | None = None,
        llm: LLMProvider | None = None,
        spec: ProfileSpec | None = None,
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
            text = await provider.complete(
                self._rewrite_prompt(longform, instruction, spec)
            )
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
        spec: ProfileSpec | None = None,
    ) -> list[OutlineSection]:
        if getattr(provider, "is_placeholder", False):
            return self._template_outline(target_words, spec)
        try:
            text = await provider.complete(
                self._outline_prompt(title, profile, target_words, spec)
            )
        except Exception:
            return self._template_outline(target_words, spec)
        payload = _extract_json_list(text)
        sections = _sections_from_payload(payload, target_words)
        return sections or self._template_outline(target_words, spec)

    @staticmethod
    def _template_outline(
        target_words: int, spec: ProfileSpec | None = None
    ) -> list[OutlineSection]:
        if spec is None:
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
        bounds = list(spec.structure.sections_per_unit or [2, 5])
        low = max(1, min(int(bounds[0]), 20))
        high = max(low, min(int(bounds[1]) if len(bounds) > 1 else low, 20))
        unit = unit_name(spec, "节")
        per = max(200, min(int(spec.unit.default_words or 1200), MAX_SECTION_WORDS))
        try:
            desired = int(round(max(1, target_words) / float(per)))
        except Exception:
            desired = low
        count = max(low, min(high, desired))
        sections: list[OutlineSection] = []
        for index in range(count):
            if count == 1:
                title = "正文"
                summary = f"围绕主题直接展开本{unit}内容。"
            elif index == 0:
                title = "引子"
                summary = "用一段场景或问题引出主题，说明读者为什么要读下去。"
            elif index == count - 1:
                title = "结论"
                summary = "收敛全文，给出可执行的结论与下一步建议。"
            else:
                title = f"核心展开（{_cn_number(index)}）"
                summary = "展开一个关键论点，给出机制、步骤或判断标准。"
            sections.append(
                OutlineSection(
                    id=f"section-{index + 1}",
                    title=title,
                    summary=summary,
                    target_words=per,
                )
            )
        return sections

    def _outline_prompt(
        self,
        title: str,
        profile: LongformProfile,
        target_words: int,
        spec: ProfileSpec | None = None,
    ) -> str:
        unit = unit_name(spec, profile.unit_name or "节")
        lines = [
            "你是长文写作规划员，需要为一篇单页长篇生成章节大纲。",
            f"- 标题：{title}",
            f"- 体裁：{profile.genre}；语气：{profile.tone or '中性'}；读者：{profile.audience or '通用'}；人称：{profile.pov or '第三人称'}",
            f"- 目标总字数：{target_words}",
        ]
        if spec is not None:
            bounds = list(spec.structure.sections_per_unit or [2, 6])
            lines.append(
                f"- 章节数量：{bounds[0]}-{bounds[-1]} 个{unit}；每个{unit}约 "
                f"{spec.unit.default_words} 字"
            )
        lines.extend(
            [
                f"要求：4-7 个{unit}，首尾必须包含引子与结论。",
                "只输出 JSON 数组，不要 Markdown 代码块与解释，元素结构：",
                '{"id":"section-1","title":"章节标题","summary":"本章要点","target_words":600}',
            ]
        )
        extra = extra_requirement(
            spec,
            "outline",
            prompt_values(
                spec,
                title=title,
                unit=unit,
                audience=profile.audience or "",
                tone=profile.tone or "",
            ),
        )
        if extra:
            lines.extend(["", extra])
        return "\n".join(lines)

    async def _evidence(
        self,
        longform: Longform,
        section: OutlineSection,
        top_k: int | None,
        tenant_id: str,
        retrieval: RetrievalContext | None = None,
    ) -> tuple[list[Citation], list[Evidence]]:
        query = " ".join(
            part
            for part in (longform.title, section.title, section.summary)
            if part
        ).strip()
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        if retrieval is not None:
            citations, _ = await retrieval.search(
                self.vectorstore,
                query,
                top_k=resolved_top_k,
                tenant_id=tenant_id,
            )
        else:
            citations = await self.vectorstore.search(
                query,
                top_k=resolved_top_k,
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

    def _rewrite_prompt(
        self, longform: Longform, instruction: str, spec: ProfileSpec | None = None
    ) -> str:
        lines = [
            "你是资深编辑，请按要求重写下面这篇单页长篇，保留原有事实与结构，输出完整正文。",
            f"- 标题：{longform.title}",
            f"- 改写要求：{instruction}",
        ]
        extra = extra_requirement(
            spec,
            "revise",
            prompt_values(
                spec,
                title=longform.title,
                unit=longform.profile.unit_name or "",
                audience=longform.profile.audience or "",
                tone=longform.profile.tone or "",
                instruction=instruction,
            ),
        )
        if extra:
            lines.extend(["", extra])
        lines.extend(["", "原文：", longform.content.strip()])
        return "\n".join(lines)

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
