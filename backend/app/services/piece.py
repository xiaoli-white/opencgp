from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Callable, Mapping, Sequence

from app.models.auth import AuthContext
from app.models.citation import Citation
from app.models.generation import Evidence
from app.models.piece import (
    MAX_SECTION_WORDS,
    SECTION_GENERATED,
    SECTION_PLANNED,
    STATUS_COMPLETED,
    STATUS_DRAFT,
    Piece,
    PieceProfile,
    PieceVersion,
    OutlineSection,
)
from app.models.mode import GenerationMode, LOOSE_NOTICE, with_loose_notice
from app.models.work_profile import ProfileSpec
from app.ports.llm import LLMProvider
from app.ports.piece_repository import PieceRepository
from app.ports.vectorstore import VectorStore
from app.services.assets import PLACEHOLDER, AssetMaterializer
from app.services.errors import (
    PieceNotFoundError,
    PieceSectionNotFoundError,
    VersionConflictError,
    InsufficientEvidenceError,
)
from app.services.evidence_gate import (
    EvidenceGate,
    build_evidence_gate,
    markers_of,
    text_cites_markers,
)
from app.services.prompting import (
    citation_taxonomy_lines,
    extra_requirement,
    policy_of,
    prompt_values,
    unit_name,
)
from app.services.retrieval_providers import RetrievalContext
from app.services.web_evidence import (
    WebEvidenceService,
    resolve_evidence,
)

DEFAULT_SECTIONS = (
    ("introduction", "Introduction", "Open with a scenario or question that introduces the topic and explains why the reader should keep reading."),
    ("background", "Background", "Explain where the topic came from, current practice, and the main debates."),
    ("core-1", "Core discussion (one)", "Develop the first key argument, giving the mechanism, steps, or criteria."),
    ("core-2", "Core discussion (two)", "Develop the second key argument, adding cases and counterexamples."),
    ("conclusion", "Conclusion", "Bring the piece together with actionable conclusions and next steps."),
)

NO_EVIDENCE_NOTICE = (
    "Insufficient material: no evidence related to this section was found in the knowledge base, so the body will not be developed yet. "
    "If you want the model to write freely, switch to loose mode."
)
SECTION_CHAR_LIMIT = MAX_SECTION_WORDS * 3
_CN_DIGITS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _cn_number(value: int) -> str:
    if 1 <= value <= len(_CN_DIGITS):
        return _CN_DIGITS[value - 1]
    return str(value)


class PieceService:
    def __init__(
        self,
        repository: PieceRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 6,
        max_evidence: int = 0,
        top_k_ceiling: int = 0,
        evidence_char_limit: int = 400,
        default_mode: str = "loose",
        asset_max_images: int = 0,
        evidence_gate: EvidenceGate | None = None,
        web_evidence: WebEvidenceService | None = None,
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.asset_max_images = max(0, int(asset_max_images or 0))
        self.default_top_k = default_top_k
        self.max_evidence = max(0, int(max_evidence or 0))
        self.top_k_ceiling = max(0, int(top_k_ceiling or 0))
        self.evidence_char_limit = evidence_char_limit
        self.default_mode = GenerationMode.normalize(default_mode).value
        self.evidence_gate = evidence_gate or build_evidence_gate()
        self.web_evidence = web_evidence

    async def create(
        self,
        title: str,
        profile: PieceProfile | None = None,
        target_words: int = 3000,
        mode: str | None = None,
        tenant_id: str = "",
        user_id: str = "",
        llm: LLMProvider | None = None,
        profile_id: str = "",
        spec: ProfileSpec | None = None,
        retrieval: RetrievalContext | None = None,
        brief: str = "",
    ) -> Piece:
        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("title must not be empty")
        resolved_profile = profile or PieceProfile()
        resolved_words = max(200, min(int(target_words or 3000), 50000))
        resolved_brief = (brief or "").strip()
        provider = llm or self.llm
        outline = await self._build_outline(
            provider, resolved_title, resolved_profile, resolved_words, spec, resolved_brief
        )
        piece = Piece(
            id=f"piece_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id or "",
            user_id=user_id or "",
            title=resolved_title,
            brief=resolved_brief,
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
        return self.repository.create(piece)

    def get(self, piece_id: str, tenant_id: str | None = None) -> Piece | None:
        return self.repository.get(piece_id, tenant_id)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Piece]:
        return self.repository.list(tenant_id, limit)

    def list_versions(self, piece_id: str) -> list[PieceVersion]:
        return self.repository.list_versions(piece_id)

    def get_version(self, piece_id: str, version: int) -> PieceVersion | None:
        return self.repository.get_version(piece_id, int(version))

    def delete(self, piece_id: str, tenant_id: str | None = None) -> bool:
        return self.repository.delete(piece_id, tenant_id)

    def update_meta(
        self,
        piece_id: str,
        title: str | None = None,
        profile: Mapping[str, Any] | None = None,
        target_words: int | None = None,
        profile_id: str | None = None,
        brief: str | None = None,
    ) -> Piece:
        piece = self._require(piece_id)
        merged_profile: PieceProfile | None = None
        if profile:
            data = piece.profile.model_dump()
            for key, value in dict(profile).items():
                if value is not None:
                    data[key] = value
            merged_profile = PieceProfile(**data)
        resolved_title = title.strip() if isinstance(title, str) and title.strip() else None
        resolved_words = (
            max(200, min(int(target_words), 50000)) if target_words is not None else None
        )
        resolved_brief = brief if brief is not None else None
        updated = self.repository.update(
            piece_id,
            title=resolved_title,
            profile=merged_profile.model_dump() if merged_profile else None,
            target_words=resolved_words,
            profile_id=profile_id,
            brief=resolved_brief,
        )
        if updated is None:
            raise PieceNotFoundError(piece_id)
        return updated

    def save_content(
        self,
        piece_id: str,
        content: str,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> tuple[Piece, PieceVersion]:
        piece = self._require(piece_id)
        if expected_version is not None and int(expected_version) != piece.current_version:
            raise VersionConflictError(int(expected_version), piece.current_version)
        applied = self.repository.append_version(
            piece_id,
            content=content,
            outline=piece.outline,
            citations=piece.citations,
            note=(note or "").strip() or "manual edit",
            mode="manual",
        )
        if applied is None:
            raise PieceNotFoundError(piece_id)
        return applied

    def add_section(
        self,
        piece_id: str,
        title: str,
        summary: str = "",
        target_words: int = 0,
        after_id: str | None = None,
    ) -> tuple[OutlineSection, Piece]:
        piece = self._require(piece_id)
        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("section title must not be empty")
        sections = list(piece.outline)
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
                raise PieceSectionNotFoundError(after_id)
            index = position + 1
        sections.insert(index, section)
        updated = self._apply_sections(piece, sections, "section:add")
        return section, updated

    def update_section(
        self,
        piece_id: str,
        section_id: str,
        title: str | None = None,
        summary: str | None = None,
        target_words: int | None = None,
        content: str | None = None,
    ) -> Piece:
        piece = self._require(piece_id)
        sections: list[OutlineSection] = []
        found = False
        for item in piece.outline:
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
            raise PieceSectionNotFoundError(section_id)
        return self._apply_sections(piece, sections, "section:edit")

    def delete_section(self, piece_id: str, section_id: str) -> Piece:
        piece = self._require(piece_id)
        if len(piece.outline) <= 1:
            raise ValueError("keep at least one section")
        sections = [item for item in piece.outline if item.id != section_id]
        if len(sections) == len(piece.outline):
            raise PieceSectionNotFoundError(section_id)
        return self._apply_sections(piece, sections, "section:delete")

    def reorder_sections(
        self, piece_id: str, section_ids: Sequence[str]
    ) -> Piece:
        piece = self._require(piece_id)
        by_id = {item.id: item for item in piece.outline}
        ordered: list[OutlineSection] = []
        seen: set[str] = set()
        for section_id in section_ids:
            item = by_id.get(str(section_id))
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            ordered.append(item)
        ordered.extend(item for item in piece.outline if item.id not in seen)
        return self._apply_sections(piece, ordered, "section:reorder")

    def _apply_sections(
        self,
        piece: Piece,
        sections: Sequence[OutlineSection],
        note: str,
    ) -> Piece:
        applied = self.repository.append_version(
            piece.id,
            content=self._compose(piece, sections),
            outline=sections,
            citations=piece.citations,
            note=note,
            mode="manual",
        )
        if applied is None:
            raise PieceNotFoundError(piece.id)
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
        piece_id: str,
        section_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
        retrieval: RetrievalContext | None = None,
        spec: ProfileSpec | None = None,
        ctx: AuthContext | None = None,
        assets: AssetMaterializer | None = None,
        allow_without_evidence: bool = False,
    ) -> tuple[OutlineSection, Piece]:
        piece = self._require(piece_id)
        section = next(
            (item for item in piece.outline if item.id == section_id), None
        )
        if section is None:
            raise PieceSectionNotFoundError(section_id)
        resolved_mode = GenerationMode.normalize(mode or piece.last_mode or self.default_mode)
        provider = llm or self.llm
        policy = self._citation_policy(piece, spec, resolved_mode.value)
        citations, evidence = await self._evidence(
            piece, section, top_k, tenant_id, retrieval
        )
        gate_query = self._section_query(piece, section)
        local_only = bool(getattr(getattr(spec, "grounding", None), "local_only", False))
        gate, citations, _web_status = await resolve_evidence(
            gate=self.evidence_gate,
            store=self.vectorstore,
            local_query=gate_query,
            citations=citations,
            topic=section.title or piece.title,
            tenant_id=tenant_id,
            mode=resolved_mode,
            citation_policy=policy,
            allow_without_evidence=allow_without_evidence,
            web_service=self.web_evidence,
            web_topic=piece.title,
            web_title=section.title,
            web_extra=section.summary,
            local_only=local_only,
        )
        if not gate.allowed:
            raise InsufficientEvidenceError(gate.payload(), gate.message)
        if resolved_mode is GenerationMode.strict and not gate.opted_out:
            citations = list(gate.usable_citations)
        elif policy == "forbidden":
            citations = []
        evidence = self._evidence_items(citations, section, policy, resolved_mode)
        content = await self._write_section(
            provider, piece, section, evidence, resolved_mode, citations, spec
        )
        if gate.grounded and not text_cites_markers(
            content, markers_of(citations)
        ):
            gate.mark_evidence_unused()
        content, asset_ids, asset_errors = await self._materialize_content(
            ctx, assets, spec, content
        )
        note = f"section:{section.id}"
        if asset_errors:
            note = f"{note};assets:error={';'.join(asset_errors)[:200]}"
        elif asset_ids:
            note = f"{note};assets:{len(asset_ids)}"
        merged_citations = list(piece.citations)
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
            for item in piece.outline
        ]
        applied = self.repository.append_version(
            piece_id,
            content=self._compose(piece, updated_outline),
            outline=updated_outline,
            citations=merged_citations,
            note=note,
            mode=resolved_mode.value,
            grounded=gate.grounded,
            gate=gate.summary(),
        )
        if applied is None:
            raise PieceNotFoundError(piece_id)
        updated, _ = applied
        if retrieval is not None:
            updated.warnings = list(retrieval.warnings)
            updated.retrieval = retrieval.summary()
        updated.warnings = [*updated.warnings, *gate.warnings]
        refreshed = next(
            (item for item in updated.outline if item.id == section.id), section
        )
        return refreshed, updated

    async def generate_all(
        self,
        piece_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        retrieval: RetrievalContext | None = None,
        spec: ProfileSpec | None = None,
        ctx: AuthContext | None = None,
        assets: AssetMaterializer | None = None,
        allow_without_evidence: bool = False,
    ) -> Piece:
        piece = self._require(piece_id)
        resolved_mode = GenerationMode.normalize(mode or piece.last_mode or self.default_mode)
        provider = llm or self.llm
        policy = self._citation_policy(piece, spec, resolved_mode.value)
        sections: list[OutlineSection] = []
        citations: list[Citation] = []
        by_key: dict[tuple[str, int], Citation] = {}
        asset_ids_total: list[str] = []
        asset_errors: list[str] = []
        gates = []
        total = max(1, len(piece.outline))
        for index, section in enumerate(piece.outline, start=1):
            found, _unused = await self._evidence(
                piece, section, top_k, tenant_id, retrieval
            )
            local_only = bool(
                getattr(getattr(spec, "grounding", None), "local_only", False)
            )
            gate, found, _web_status = await resolve_evidence(
                gate=self.evidence_gate,
                store=self.vectorstore,
                local_query=self._section_query(piece, section),
                citations=found,
                topic=section.title or piece.title,
                tenant_id=tenant_id,
                mode=resolved_mode,
                citation_policy=policy,
                allow_without_evidence=allow_without_evidence,
                web_service=self.web_evidence,
                web_topic=piece.title,
                web_title=section.title,
                web_extra=section.summary,
                local_only=local_only,
            )
            if not gate.allowed:
                raise InsufficientEvidenceError(gate.payload(), gate.message)
            gates.append(gate)
            if resolved_mode is GenerationMode.strict and not gate.opted_out:
                found = list(gate.usable_citations)
            elif policy == "forbidden":
                found = []
            evidence = self._evidence_items(found, section, policy, resolved_mode)
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
                provider, piece, section, evidence, resolved_mode, found, spec
            )
            if gate.grounded and not text_cites_markers(
                content, markers_of(found)
            ):
                gate.mark_evidence_unused()
            budget_assets = assets
            if assets is not None:
                budget_assets = assets.with_profile(spec).with_limit(
                    max(0, self.asset_max_images - len(asset_ids_total))
                )
            content, asset_ids, section_errors = await self._materialize_content(
                ctx, budget_assets, spec, content
            )
            asset_ids_total.extend(asset_ids)
            asset_errors.extend(section_errors)
            sections.append(
                section.model_copy(
                    update={"content": content, "status": SECTION_GENERATED}
                )
            )
            if on_progress is not None:
                on_progress(index, total)
        note = "generate_all"
        if asset_errors:
            note = f"{note};assets:error={';'.join(asset_errors)[:200]}"
        elif asset_ids_total:
            note = f"{note};assets:{len(asset_ids_total)}"
        overall_grounded = bool(gates) and all(item.grounded for item in gates)
        local_total = sum(int(item.local_passages) for item in gates)
        web_total = sum(int(item.web_passages) for item in gates)
        if local_total and web_total:
            evidence_origin = "mixed"
        elif web_total:
            evidence_origin = "web"
        elif local_total:
            evidence_origin = "local"
        else:
            evidence_origin = "none"
        web_statuses = [
            item.web_fallback for item in gates if item.web_fallback
        ]
        gate_payload = {
            "code": (
                "evidence_gate_passed"
                if overall_grounded
                else "evidence_gate_not_grounded"
            ),
            "grounded": overall_grounded,
            "threshold": max((item.threshold for item in gates), default=0.0),
            "min_passages": max((item.min_passages for item in gates), default=1),
            "chunks_searched": max(
                (item.chunks_searched for item in gates), default=0
            ),
            "best_score": max((item.best_score for item in gates), default=0.0),
            "usable_passages": min(
                (item.usable_passages for item in gates), default=0
            ),
            "local_passages": local_total,
            "web_passages": web_total,
            "evidence_origin": evidence_origin,
            "web_fallback": web_statuses[0] if web_statuses else {},
            "sections": [item.summary() for item in gates],
        }
        gate_warnings = [
            warning for item in gates for warning in item.warnings
        ]
        applied = self.repository.append_version(
            piece_id,
            content=self._compose(piece, sections),
            outline=sections,
            citations=citations,
            note=note,
            mode=resolved_mode.value,
            grounded=overall_grounded,
            gate=gate_payload,
        )
        if applied is None:
            raise PieceNotFoundError(piece_id)
        updated = applied[0]
        if retrieval is not None:
            updated.warnings = list(retrieval.warnings)
            updated.retrieval = retrieval.summary()
        updated.warnings = [*updated.warnings, *gate_warnings]
        return updated

    async def rewrite(
        self,
        piece_id: str,
        instruction: str,
        mode: str | None = None,
        expected_version: int | None = None,
        llm: LLMProvider | None = None,
        spec: ProfileSpec | None = None,
    ) -> Piece:
        piece = self._require(piece_id)
        if expected_version is not None and int(expected_version) != piece.current_version:
            raise VersionConflictError(int(expected_version), piece.current_version)
        resolved_mode = GenerationMode.normalize(mode or piece.last_mode or self.default_mode)
        provider = llm or self.llm
        body = piece.content.strip()
        if not body:
            raise ValueError("the body is empty; generate or fill in the body before rewriting")
        if getattr(provider, "is_placeholder", False):
            text = self._rewrite_placeholder(piece, instruction)
        else:
            text = await provider.complete(
                self._rewrite_prompt(piece, instruction, spec)
            )
        if resolved_mode is GenerationMode.loose:
            text = with_loose_notice(text)
        applied = self.repository.append_version(
            piece_id,
            content=text,
            outline=piece.outline,
            citations=piece.citations,
            note=f"rewrite:{instruction[:40]}",
            mode=resolved_mode.value,
            grounded=False,
            gate={
                "code": "rewrite_not_grounded",
                "grounded": False,
                "message": "A rewrite runs from the existing text without new evidence; this version is not marked as grounded.",
            },
        )
        if applied is None:
            raise PieceNotFoundError(piece_id)
        return applied[0]

    def revert(
        self, piece_id: str, version: int, note: str = ""
    ) -> tuple[Piece, PieceVersion]:
        piece = self._require(piece_id)
        target = self.repository.get_version(piece_id, int(version))
        if target is None:
            raise PieceNotFoundError(f"version not found: {version}")
        applied = self.repository.append_version(
            piece_id,
            content=target.content,
            outline=target.outline,
            citations=target.citations,
            note=note or f"revert:{version}",
            mode=target.mode,
            grounded=False,
            gate={
                "code": "revert_not_grounded",
                "grounded": False,
                "message": "A reverted version is restored without re-checking evidence; it is not marked as grounded.",
            },
        )
        if applied is None:
            raise PieceNotFoundError(piece_id)
        return applied

    async def _materialize_content(
        self,
        ctx: AuthContext | None,
        assets: AssetMaterializer | None,
        spec: ProfileSpec | None,
        content: str,
    ) -> tuple[str, list[str], list[str]]:
        """Replace image markers before persisting; failures only add a note."""
        materializer = assets.with_profile(spec) if assets is not None else None
        if materializer is None or ctx is None:
            return PLACEHOLDER.sub("", content).strip(), [], []
        if not materializer.has_placeholders(content):
            return content, [], []
        try:
            return await materializer.materialize(ctx, content)
        except Exception as exc:  # noqa: BLE001 - illustration must not break generation
            cleaned = PLACEHOLDER.sub("", content).strip()
            return cleaned, [], [f"{type(exc).__name__}: {exc}"[:200]]

    def _require(self, piece_id: str) -> Piece:
        piece = self.repository.get(piece_id)
        if piece is None:
            raise PieceNotFoundError(piece_id)
        return piece

    async def _build_outline(
        self,
        provider: LLMProvider,
        title: str,
        profile: PieceProfile,
        target_words: int,
        spec: ProfileSpec | None = None,
        brief: str = "",
    ) -> list[OutlineSection]:
        if getattr(provider, "is_placeholder", False):
            return self._template_outline(target_words, spec)
        try:
            text = await provider.complete(
                self._outline_prompt(title, profile, target_words, spec, brief)
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
        unit = unit_name(spec, "Section")
        per = max(200, min(int(spec.unit.default_words or 1200), MAX_SECTION_WORDS))
        try:
            desired = int(round(max(1, target_words) / float(per)))
        except Exception:
            desired = low
        count = max(low, min(high, desired))
        sections: list[OutlineSection] = []
        for index in range(count):
            if count == 1:
                title = "Body"
                summary = f"Develop this {unit} directly around the topic."
            elif index == 0:
                title = "Introduction"
                summary = "Open with a scenario or question that introduces the topic and explains why the reader should keep reading."
            elif index == count - 1:
                title = "Conclusion"
                summary = "Bring the piece together with actionable conclusions and next steps."
            else:
                title = f"Core discussion ({_cn_number(index)})"
                summary = "Develop one key argument, giving the mechanism, steps, or criteria."
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
        profile: PieceProfile,
        target_words: int,
        spec: ProfileSpec | None = None,
        brief: str = "",
    ) -> str:
        unit = unit_name(spec, profile.unit_name or "Section")
        lines = [
            "You are a long-form writing planner and need to produce a section outline for a single-page long-form piece.",
            f"- Title: {title}",
            f"- Content requirements: {(brief or '').strip() or '(not specified)'}",
            f"- Genre: {profile.genre}; tone: {profile.tone or 'neutral'}; reader: {profile.audience or 'general'}; person: {profile.pov or 'third person'}",
            f"- Target total word count: {target_words}",
        ]
        if spec is not None:
            bounds = list(spec.structure.sections_per_unit or [2, 6])
            lines.append(
                f"- Number of sections: {bounds[0]}-{bounds[-1]} {unit}s; each {unit} is about "
                f"{spec.unit.default_words} words"
            )
        lines.extend(
            [
                "",
                "## Authoring requirements (from the author, not retrieval evidence)",
                (brief or "").strip() or "(none)",
                "Use these requirements to decide section topics, emphasis, and coverage. They are not evidence and must never be cited as a source.",
            ]
        )
        lines.extend(
            [
                f"Requirements: 4-7 {unit}s; the first and last must be an introduction and a conclusion.",
                "Output only a JSON array, without Markdown code blocks or explanations; element structure:",
                '{"id":"section-1","title":"Section title","summary":"Key points of this section","target_words":600}',
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
        piece: Piece,
        section: OutlineSection,
        top_k: int | None,
        tenant_id: str,
        retrieval: RetrievalContext | None = None,
    ) -> tuple[list[Citation], list[Evidence]]:
        query = " ".join(
            part
            for part in (piece.title, section.title, section.summary)
            if part
        ).strip()
        resolved_top_k = max(1, int(top_k or self.default_top_k))
        if self.top_k_ceiling > 0:
            resolved_top_k = min(resolved_top_k, self.top_k_ceiling)
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
        if self.max_evidence > 0:
            citations = citations[: self.max_evidence]
        evidence = []
        for index, citation in enumerate(citations, start=1):
            citation.marker = f"E{index}"
            citation.meta["section_id"] = section.id
            citation.meta["section_title"] = section.title
            evidence.append(Evidence(marker=citation.marker, citation=citation))
        return citations, evidence

    @staticmethod
    def _section_query(piece: Piece, section: OutlineSection) -> str:
        return " ".join(
            part
            for part in (piece.title, section.title, section.summary)
            if part
        ).strip()

    @staticmethod
    def _citation_policy(
        piece: Piece, spec: ProfileSpec | None, mode: str
    ) -> str:
        if spec is not None:
            return policy_of(spec, mode)
        value = (piece.profile.citation_policy or "optional").strip().lower()
        return value if value in ("required", "optional", "forbidden") else "optional"

    @staticmethod
    def _evidence_items(
        citations: Sequence[Citation],
        section: OutlineSection,
        policy: str,
        mode: GenerationMode,
    ) -> list[Evidence]:
        if policy == "forbidden":
            return []
        evidence: list[Evidence] = []
        for index, citation in enumerate(citations, start=1):
            citation.marker = f"E{index}"
            citation.meta["section_id"] = section.id
            citation.meta["section_title"] = section.title
            evidence.append(Evidence(marker=citation.marker, citation=citation))
        return evidence

    async def _write_section(
        self,
        provider: LLMProvider,
        piece: Piece,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        citations: Sequence[Citation],
        spec: ProfileSpec | None = None,
    ) -> str:
        if mode is GenerationMode.strict and not evidence:
            return NO_EVIDENCE_NOTICE
        if getattr(provider, "is_placeholder", False):
            draft = self._placeholder_section(piece, section, evidence, mode)
            return self._finish(draft, mode)
        prompt = (
            self._strict_prompt(piece, section, evidence, spec)
            if mode is GenerationMode.strict
            else self._loose_prompt(piece, section, evidence, spec)
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
        piece: Piece,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
    ) -> str:
        lines = [
            f"## {section.title}",
            "",
            section.summary or f"This section develops \"{piece.title}\".",
            "",
        ]
        if evidence:
            for item in evidence[:4]:
                snippet = (item.citation.snippet or item.citation.text or "").strip()
                lines.append(f"- {snippet} [{item.marker}]")
        else:
            lines.append("- This paragraph is placeholder body text; once a real model is wired in, it will be developed from the evidence.")
        return "\n".join(lines)

    def _strict_prompt(
        self,
        piece: Piece,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        lines = [
            "You are a rigorous long-form writer working on one section of a single-page long-form piece.",
            f"- Piece title: {piece.title}",
            f"- Section title: {section.title}",
            f"- Section key points: {section.summary}",
            f"- Reader: {piece.profile.audience or 'general'}; tone: {piece.profile.tone or 'neutral'}",
            f"- Word limit: {min(MAX_SECTION_WORDS, section.target_words or MAX_SECTION_WORDS)} words",
            f"- Content requirements: {(piece.brief or '').strip() or '(not specified)'}",
            "",
            "## Authoring requirements (from the author, not retrieval evidence)",
            (piece.brief or "").strip() or "(none)",
            "Use these requirements to decide topic selection, emphasis, and coverage. They are not evidence and must never be cited as a source.",
            "",
            "Hard constraints:",
            "1. Only use content explicitly stated in the evidence below; do not introduce facts or data beyond the evidence.",
            "2. A citation marker is required only for the factual material listed in the semantic citation policy below; it is not required for code walkthroughs, procedural steps, analogies, summaries, exercises, or subjective advice.",
            "3. When the evidence is insufficient, write \"Insufficient material: <gap description>\"; do not fabricate.",
        ]
        lines.extend(citation_taxonomy_lines(mandatory=True))
        lines.extend(["", "Evidence:"])
        for item in evidence:
            snippet = (item.citation.snippet or item.citation.text or "")[
                : self.evidence_char_limit
            ]
            lines.append(f"[{item.marker}] {item.citation.source_name}: {snippet}")
        lines.append("Output only this section's body Markdown; do not output explanations.")
        lines.extend(self._asset_prompt_lines(spec))
        return "\n".join(lines)


    def _asset_prompt_lines(self, spec: ProfileSpec | None) -> list[str]:
        """Ask for illustration markers when the profile or settings allow images."""
        profile_assets = getattr(spec, "assets", None) if spec is not None else None
        max_images = getattr(profile_assets, "max_images", None)
        if max_images is None:
            max_images = self.asset_max_images
        auto_images = getattr(profile_assets, "auto_images", None)
        if auto_images is not None and not bool(auto_images):
            return []
        max_images = max(0, int(max_images or 0))
        if not max_images:
            return []
        return [
            "",
            f"You may add at most {max_images} illustration marker(s) in this section.",
            "A marker is a line that contains exactly: [[image: a short, concrete scene description]]",
            "Place it right below the paragraph it illustrates, and only where an image genuinely helps.",
            "Do not mention the marker in the prose and do not number them.",
        ]

    def _loose_prompt(
        self,
        piece: Piece,
        section: OutlineSection,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        lines = [
            "You are an experienced long-form writer working on one section of a single-page long-form piece.",
            "This section uses free-writing mode: you may develop it from your own knowledge; evidence is for reference only and per-paragraph citations are not required.",
            f"- Piece title: {piece.title}",
            f"- Section title: {section.title}",
            f"- Section key points: {section.summary}",
            f"- Genre: {piece.profile.genre}; reader: {piece.profile.audience or 'general'}; tone: {piece.profile.tone or 'neutral'}",
            f"- Word limit: {min(MAX_SECTION_WORDS, section.target_words or MAX_SECTION_WORDS)} words",
            f"- Content requirements: {(piece.brief or '').strip() or '(not specified)'}",
            "",
            "## Authoring requirements (from the author, not retrieval evidence)",
            (piece.brief or "").strip() or "(none)",
            "Follow these requirements for topic selection, emphasis, and coverage; evidence remains reference material only.",
        ]
        lines.extend(citation_taxonomy_lines(mandatory=False))
        if evidence:
            lines.append("")
            lines.append("Reference evidence:")
            for item in evidence:
                snippet = (item.citation.snippet or item.citation.text or "")[
                    : self.evidence_char_limit
                ]
                lines.append(f"[{item.marker}] {item.citation.source_name}: {snippet}")
        lines.append("Output only this section's body Markdown; do not output explanations.")
        lines.extend(self._asset_prompt_lines(spec))
        return "\n".join(lines)

    def _rewrite_prompt(
        self, piece: Piece, instruction: str, spec: ProfileSpec | None = None
    ) -> str:
        lines = [
            "You are a senior editor. Rewrite the single-page long-form piece below as instructed, preserving the existing facts and structure, and output the complete body.",
            f"- Title: {piece.title}",
            f"- Content requirements: {(piece.brief or '').strip() or '(not specified)'}",
            f"- Rewrite requirements: {instruction}",
        ]
        extra = extra_requirement(
            spec,
            "revise",
            prompt_values(
                spec,
                title=piece.title,
                unit=piece.profile.unit_name or "",
                audience=piece.profile.audience or "",
                tone=piece.profile.tone or "",
                instruction=instruction,
            ),
        )
        if extra:
            lines.extend(["", extra])
        lines.extend(["", "Original text:", piece.content.strip()])
        return "\n".join(lines)

    @staticmethod
    def _rewrite_placeholder(piece: Piece, instruction: str) -> str:
        return "\n".join(
            [
                f"> Placeholder rewrite ({instruction}): no LLM key configured; below is a summary of the original text",
                "",
                piece.content.strip()[:SECTION_CHAR_LIMIT],
            ]
        )

    @staticmethod
    def _compose(piece: Piece, outline: Sequence[OutlineSection]) -> str:
        blocks: list[str] = [f"# {piece.title}", ""]
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
