from __future__ import annotations

import json
import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from app.models.blueprint import (
    SeriesBlueprint,
    GlossaryTerm,
    LearningStage,
    UnitReview,
    OutlineNode,
)
from app.models.series import Series, Unit
from app.models.generation import Evidence
from app.models.mode import GenerationMode
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.series_repository import SeriesRepository
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore
from app.models.work_profile import ProfileSpec
from app.services.errors import (
    BlueprintNotFoundError,
    BlueprintParseError,
    BlueprintApplyConfirmationError,
    BlueprintValidationError,
    UnitContentEmptyError,
    UnitNotFoundError,
    NoEvidenceError,
    InsufficientEvidenceError,
    VersionConflictError,
)
from app.services.evidence_gate import (
    EvidenceGate,
    build_evidence_gate,
    markers_of,
    passage_relevance,
    text_admits_missing_coverage,
    text_cites_markers,
)
from app.services.language import language_name, with_output_language
from app.services.prompting import (
    extra_requirement,
    policy_of,
    prompt_values,
    system_prefix,
    unit_name,
)
from app.services.retrieval_providers import RetrievalContext
from app.services.web_evidence import (
    WebEvidenceService,
    counts_by_origin,
    resolve_evidence,
)
from app.services.blueprint_titles import sanitize_blueprint, sanitize_payload
from app.services.blueprint_validation import validate_blueprint_for_edit
from app.services.objective_guard import (
    derive_objectives,
    extract_gaps,
    sanitize_blueprint_nodes,
)

NO_EVIDENCE_MESSAGE = (
    "No evidence related to the course topic was found in the knowledge base, so strict mode cannot generate a blueprint; upload material first or switch to loose mode"
)
PLACEHOLDER_WARNING = "No LLM key configured; the blueprint is a placeholder plan"
LOOSE_WARNING = "Non-strict mode: the blueprint was planned by an LLM from its own knowledge and has not been verified against knowledge-base evidence"
REVIEW_APPROVE = "approve"
REVIEW_REQUEST_REVISION = "request_revision"
NODE_PLANNED = "planned"
NODE_GENERATED = "generated"
NODE_APPROVED = "approved"
UNIT_NEEDS_REVISION = "needs_revision"

_STOPWORDS = {
    "\u4e00\u4e2a", "\u6211\u4eec", "\u4f60\u4eec", "\u4ed6\u4eec", "\u8fd9\u4e2a", "\u90a3\u4e2a", "\u53ef\u4ee5", "\u9700\u8981", "\u4f7f\u7528", "\u8fdb\u884c",
    "\u4ee5\u53ca", "\u56e0\u4e3a", "\u6240\u4ee5", "\u4f46\u662f", "\u5982\u679c", "\u5c31\u662f", "\u4e0d\u662f", "\u6ca1\u6709", "\u5982\u4f55", "\u4ec0\u4e48",
    "\u5185\u5bb9", "\u90e8\u5206", "\u4ee5\u4e0b", "\u4e0a\u9762", "\u4e0b\u9762", "\u65f6\u5019", "\u95ee\u9898", "\u65b9\u5f0f", "\u60c5\u51b5", "\u901a\u8fc7",
}

_STAGE_TITLE_POOL = (
    "Getting started and overview",
    "Core mechanisms",
    "Practice and advanced topics",
    "Productionizing",
    "Advanced topics",
    "Hands-on project",
    "Review and self-assessment",
    "Frontier topics",
)

_NODE_HINTS = (
    ("{title}: problem domain and value", "Explain the problem \"{title}\" solves, where it applies, and where it does not."),
    ("Core concepts and terminology map", "Organize the key concepts of \"{title}\" and how they relate to one another."),
    ("Learning path and prerequisites", "Clarify the learning order, required foundations, and self-check methods."),
    ("Key mechanism breakdown", "Break down the inputs, processing, and outputs of the core mechanism."),
    ("Typical workflow", "Walk through a complete workflow from preparation to delivery."),
    ("Common pitfalls and boundaries", "Identify misuse scenarios, failure boundaries, and troubleshooting approaches."),
    ("Hands-on: minimal runnable example", "Build a minimal runnable example and verify the result."),
    ("Productionizing and collaboration", "Discuss maintainability, collaboration, and quality assurance."),
    ("Advanced extensions and self-assessment", "Suggest extension directions and a self-assessment checklist."),
)


def _stage_titles(spec: ProfileSpec | None) -> list[str]:
    if spec is None:
        return list(_STAGE_TITLE_POOL[:3])
    depth = int(spec.structure.depth or 2)
    count = max(2, min(len(_STAGE_TITLE_POOL), depth * 2))
    return list(_STAGE_TITLE_POOL[:count])


def _node_counts(spec: ProfileSpec | None, stage_count: int) -> list[int]:
    if spec is None:
        return [3] * stage_count
    low = max(1, int(spec.unit.min_units or 1))
    high = max(low, int(spec.unit.max_units or 60))
    total = min(high, max(low, stage_count * 3))
    if total < stage_count:
        return [1] * stage_count
    base, remainder = divmod(total, stage_count)
    return [base + (1 if index < remainder else 0) for index in range(stage_count)]


@dataclass
class BlueprintApplyResult:
    blueprint: SeriesBlueprint
    created: list[Unit] = field(default_factory=list)
    updated: list[Unit] = field(default_factory=list)
    unchanged: list[Unit] = field(default_factory=list)
    removed: list[Unit] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    stage_count: int = 0
    node_count: int = 0

    @property
    def affected_unit_ids(self) -> list[str]:
        return [unit.id for unit in [*self.created, *self.updated]]

    @property
    def applied_count(self) -> int:
        return len(self.created) + len(self.updated)


class BlueprintService:
    def __init__(
        self,
        repository: BlueprintRepository,
        series_repository: SeriesRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 6,
        default_mode: str = "strict",
        max_evidence: int = 0,
        top_k_ceiling: int = 0,
        evidence_char_limit: int = 400,
        min_score: float = 0.15,
        evidence_gate: EvidenceGate | None = None,
        web_evidence: WebEvidenceService | None = None,
    ) -> None:
        self.repository = repository
        self.series_repository = series_repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.default_top_k = default_top_k
        self.default_mode = GenerationMode.normalize(default_mode).value
        self.max_evidence = max(0, int(max_evidence or 0))
        self.top_k_ceiling = max(0, int(top_k_ceiling or 0))
        self.evidence_char_limit = evidence_char_limit
        self.min_score = float(min_score)
        self.evidence_gate = evidence_gate or build_evidence_gate()
        self.web_evidence = web_evidence

    async def generate(
        self,
        series_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        source_ids: Sequence[str] | None = None,
        focus: str = "",
        tenant_id: str = "",
        llm: LLMProvider | None = None,
        spec: ProfileSpec | None = None,
        retrieval: RetrievalContext | None = None,
        progress: Callable[[float], None] | None = None,
        allow_without_evidence: bool = False,
    ) -> SeriesBlueprint:
        series = self.series_repository.get_series(series_id)
        if series is None:
            raise BlueprintNotFoundError(f"course not found: {series_id}")
        series = with_output_language(series, spec)
        resolved_mode = GenerationMode.normalize(mode or self.default_mode)
        resolved_top_k = max(1, int(top_k or self.default_top_k))
        if self.top_k_ceiling > 0:
            resolved_top_k = min(resolved_top_k, self.top_k_ceiling)
        units = self.series_repository.list_units(series_id)
        min_score = (
            self.min_score
            if (
                not self.evidence_gate.config.enabled
                and resolved_mode is GenerationMode.strict
            )
            else None
        )
        if progress is not None:
            progress(0.15)
        query = self._build_query(series, focus, units)
        if retrieval is not None:
            citations, _ = await retrieval.search(
                self.vectorstore,
                query,
                top_k=resolved_top_k,
                source_ids=source_ids,
                tenant_id=tenant_id,
                min_score=min_score,
            )
        else:
            citations = await self.vectorstore.search(
                query,
                top_k=resolved_top_k,
                source_ids=source_ids,
                tenant_id=tenant_id,
                min_score=min_score,
            )
        if self.max_evidence > 0:
            citations = citations[: self.max_evidence]
        policy = policy_of(spec, resolved_mode.value)
        local_only = bool(getattr(getattr(spec, "grounding", None), "local_only", False))
        topic_texts = self._topic_texts(series, units, focus)
        gate, citations, _web_status = await resolve_evidence(
            gate=self.evidence_gate,
            store=self.vectorstore,
            local_query=query,
            citations=citations,
            topic=series.title,
            tenant_id=tenant_id,
            source_ids=source_ids,
            mode=resolved_mode,
            citation_policy=policy,
            allow_without_evidence=allow_without_evidence,
            web_service=self.web_evidence,
            web_topic=series.title,
            web_title=(units[0].title if units else ""),
            web_extra=f"{series.subtitle} {focus}".strip(),
            local_only=local_only,
            topic_texts=topic_texts,
        )
        if not gate.allowed:
            raise InsufficientEvidenceError(gate.payload(), gate.message)
        if resolved_mode is GenerationMode.strict and not gate.opted_out:
            citations = list(gate.usable_citations)
        elif policy == "forbidden":
            citations = []
        evidence = [
            Evidence(marker=citation.marker or f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]
        if progress is not None:
            progress(0.35)

        llm_provider = llm or self.llm
        provider_name = type(llm_provider).__name__
        if getattr(llm_provider, "is_placeholder", False):
            blueprint = self._placeholder_blueprint(
                series, evidence, resolved_mode, provider_name, spec
            )
        else:
            if progress is not None:
                progress(0.45)
            payload = await self._request_payload(
                series, evidence, resolved_mode, focus, llm_provider, spec
            )
            blueprint = self._blueprint_from_payload(
                series, payload, evidence, resolved_mode, provider_name
            )
        if progress is not None:
            progress(0.85)
        if retrieval is not None:
            blueprint.warnings = list(retrieval.warnings)
            blueprint.retrieval = retrieval.summary()
        if gate.grounded:
            admitted = text_admits_missing_coverage(blueprint.overview)
            if admitted:
                gate.mark_coverage_admission(
                    "The generated overview states that the evidence does not "
                    "cover the course topic."
                )
            else:
                cited_text = " ".join(
                    [blueprint.overview]
                    + [node.summary for node in blueprint.outline]
                )
                if not text_cites_markers(
                    cited_text, markers_of([item.citation for item in evidence])
                ):
                    gate.mark_evidence_unused()
        blueprint.grounded = gate.grounded
        blueprint.evidence_count = len(evidence)
        local_used, web_used = counts_by_origin([item.citation for item in evidence])
        if local_used and web_used:
            evidence_origin = "mixed"
        elif web_used:
            evidence_origin = "web"
        elif local_used:
            evidence_origin = "local"
        else:
            evidence_origin = "none"
        blueprint.local_evidence_count = local_used
        blueprint.web_evidence_count = web_used
        blueprint.evidence_origin = evidence_origin
        blueprint.web_fallback = dict(gate.payload().get("web_fallback") or {})
        blueprint.evidence = [
            {
                "marker": item.marker,
                "source_id": item.citation.source_id,
                "source_name": item.citation.source_name,
                "chunk_id": item.citation.chunk_id,
                "chunk_index": int(item.citation.chunk_index),
                "score": round(passage_relevance(item.citation), 6),
                "snippet": (item.citation.text or item.citation.snippet or "")[:240],
                "kind": str((item.citation.meta or {}).get("kind") or "kb"),
                "origin": str((item.citation.meta or {}).get("origin") or "knowledge_base"),
                "url": str((item.citation.meta or {}).get("url") or ""),
                "retrieved_at": str((item.citation.meta or {}).get("retrieved_at") or ""),
                "citation": item.citation.model_dump(),
            }
            for item in evidence
        ]
        blueprint.gate = gate.summary()
        if gate.warnings:
            blueprint.warnings = [*blueprint.warnings, *gate.warnings]
        if gate.message and not gate.grounded:
            blueprint.warning = (
                f"{blueprint.warning}; {gate.message}"
                if blueprint.warning
                else gate.message
            )
        return self.repository.save_blueprint(blueprint)

    def get_blueprint(self, series_id: str) -> SeriesBlueprint | None:
        return self.repository.get_blueprint(series_id)

    def save_blueprint(
        self,
        series_id: str,
        blueprint: SeriesBlueprint,
        expected_version: int | None = None,
        author: str = "manual",
        note: str = "manual edit",
    ) -> SeriesBlueprint:
        """Save a hand-edited blueprint as a new, reversible version."""
        existing = self.repository.get_blueprint(series_id)
        current = existing.version if existing else 0
        if expected_version is not None and int(expected_version) != current:
            raise VersionConflictError(int(expected_version), current)
        blueprint = blueprint.model_copy(update={"series_id": series_id})
        errors = validate_blueprint_for_edit(blueprint)
        if errors:
            raise BlueprintValidationError(errors)
        blueprint = _normalize_stage_links(blueprint)
        series = self.series_repository.get_series(series_id)
        if series is not None:
            series = with_output_language(series)
            # The sanitizer now only normalises formatting; every placeholder
            # in a structured field was already rejected above, while prose
            # fields remain free to mention an evidence gap.
            blueprint, _repaired = sanitize_blueprint(blueprint, series.title)
            rejections = sanitize_blueprint_nodes(
                blueprint.outline,
                blueprint.learning_path,
                series_title=series.title,
                language=series.language,
            )
            for node in blueprint.outline:
                node.gaps = extract_gaps(node.summary)
            if rejections:
                blueprint.objective_rejections = [
                    *blueprint.objective_rejections,
                    *rejections,
                ]
        return self.repository.save_blueprint(
            blueprint,
            author=author or "manual",
            change_source="manual",
            note=note or "manual edit",
        )

    def validate_blueprint(
        self, series_id: str, blueprint: SeriesBlueprint
    ) -> list[dict[str, str]]:
        del series_id  # validation is purely structural today
        return validate_blueprint_for_edit(blueprint)

    def list_versions(self, series_id: str) -> list[dict[str, Any]]:
        return self.repository.list_blueprint_versions(series_id)

    def get_version(self, series_id: str, version: int) -> SeriesBlueprint | None:
        return self.repository.get_blueprint_version(series_id, version)

    def restore_version(
        self,
        series_id: str,
        version: int,
        expected_version: int | None = None,
        author: str = "manual",
    ) -> SeriesBlueprint:
        target = self.repository.get_blueprint_version(series_id, int(version))
        if target is None:
            raise BlueprintNotFoundError(
                f"blueprint version not found: {series_id} v{version}"
            )
        current = self.repository.get_blueprint(series_id)
        current_version = current.version if current else 0
        if expected_version is not None and int(expected_version) != current_version:
            raise VersionConflictError(int(expected_version), current_version)
        restored = target.model_copy(
            update={"series_id": series_id, "version": 0, "updated_at": time.time()}
        )
        series = self.series_repository.get_series(series_id)
        if series is not None:
            restored, _repaired = sanitize_blueprint(restored, series.title)
        return self.repository.save_blueprint(
            restored,
            author=author or "manual",
            change_source="restore",
            note=f"restored from v{int(version)}",
        )

    def apply_plan(self, series_id: str) -> dict[str, Any]:
        """Compute the diff an apply would produce, without touching units."""
        blueprint = self.repository.get_blueprint(series_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"course blueprint not found: {series_id}")
        series = self.series_repository.get_series(series_id)
        if series is None:
            raise BlueprintNotFoundError(f"course not found: {series_id}")
        series = with_output_language(series)
        units = self.series_repository.list_units(series_id)
        unit_by_id = {unit.id: unit for unit in units}
        current_ids = {node.unit_id for node in blueprint.outline if node.unit_id}
        previous = (
            self.repository.get_blueprint_version(series_id, blueprint.version - 1)
            if blueprint.version > 1
            else None
        )
        previous_ids = (
            {node.unit_id for node in previous.outline if node.unit_id}
            if previous is not None
            else set()
        )
        # Removals are only useful if they survive more than one save. Union
        # the unit ids referenced by earlier versions; units that no longer
        # exist are filtered out below.
        if previous is not None:
            try:
                for item in self.repository.list_blueprint_versions(series_id)[:50]:
                    if int(item.get("version") or 0) >= blueprint.version:
                        continue
                    older = self.repository.get_blueprint_version(
                        series_id, int(item["version"])
                    )
                    if older is not None:
                        previous_ids.update(
                            node.unit_id for node in older.outline if node.unit_id
                        )
            except Exception:
                pass
        created: list[dict[str, Any]] = []
        renamed: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        unchanged: list[dict[str, Any]] = []
        for node in blueprint.outline:
            unit = unit_by_id.get(node.unit_id or "")
            if unit is None:
                created.append(
                    {
                        "node_id": node.id,
                        "title": node.title,
                        "stage_id": node.stage_id,
                        "has_content": False,
                    }
                )
                continue
            old_title = unit.title
            if old_title != node.title:
                renamed.append(
                    {
                        "node_id": node.id,
                        "unit_id": unit.id,
                        "from": old_title,
                        "to": node.title,
                        "has_content": bool((unit.content or "").strip()),
                        "content_preserved": True,
                    }
                )
            objectives_changed = list(node.objectives) != list(unit.learning_objectives)
            prerequisites_changed = list(node.prerequisites) != list(unit.prerequisites)
            if objectives_changed or prerequisites_changed:
                updated.append(
                    {
                        "node_id": node.id,
                        "unit_id": unit.id,
                        "title": node.title,
                        "has_content": bool((unit.content or "").strip()),
                        "content_preserved": True,
                        "objectives_changed": objectives_changed,
                        "prerequisites_changed": prerequisites_changed,
                    }
                )
            if old_title == node.title and not objectives_changed and not prerequisites_changed:
                unchanged.append(
                    {
                        "node_id": node.id,
                        "unit_id": unit.id,
                        "title": node.title,
                    }
                )
        removed: list[dict[str, Any]] = []
        for unit_id in sorted(previous_ids - current_ids):
            unit = unit_by_id.get(unit_id)
            if unit is None:
                continue
            has_content = bool((unit.content or "").strip())
            removed.append(
                {
                    "unit_id": unit.id,
                    "title": unit.title,
                    "order_index": unit.order_index,
                    "has_content": has_content,
                    "content_chars": len(unit.content or ""),
                    "current_version": unit.current_version,
                }
            )
        kept_unlinked = [
            {
                "unit_id": unit.id,
                "title": unit.title,
                "has_content": bool((unit.content or "").strip()),
            }
            for unit in units
            if unit.id not in current_ids and unit.id not in previous_ids
        ]
        plan = {
            "series_id": series_id,
            "blueprint_version": blueprint.version,
            "stage_count": len(blueprint.learning_path),
            "node_count": len(blueprint.outline),
            "created": created,
            "renamed": renamed,
            "updated": updated,
            "unchanged": unchanged,
            "removed": removed,
            "kept_unlinked": kept_unlinked,
            "removals_require_confirmation": bool(removed),
            "content_loss": [
                {
                    "unit_id": item["unit_id"],
                    "title": item["title"],
                    "content_chars": item["content_chars"],
                }
                for item in removed
                if item["has_content"]
            ],
            "summary": {
                "created": len(created),
                "renamed": len(renamed),
                "updated": len(updated),
                "unchanged": len(unchanged),
                "removed": len(removed),
                "kept_unlinked": len(kept_unlinked),
            },
        }
        plan["token"] = _plan_token(plan)
        return plan

    def apply(
        self,
        series_id: str,
        *,
        confirm_removals: bool = False,
        expected_version: int | None = None,
        plan_token: str = "",
        author: str = "manual",
    ) -> BlueprintApplyResult:
        plan = self.apply_plan(series_id)
        current_version = int(plan["blueprint_version"])
        if expected_version is not None and int(expected_version) != current_version:
            raise VersionConflictError(int(expected_version), current_version)
        if plan_token and plan_token != plan.get("token"):
            raise VersionConflictError(current_version, current_version)
        if plan["removed"] and not confirm_removals:
            raise BlueprintApplyConfirmationError(plan)
        blueprint = self.repository.get_blueprint(series_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"course blueprint not found: {series_id}")
        series = self.series_repository.get_series(series_id)
        if series is None:
            raise BlueprintNotFoundError(f"course not found: {series_id}")
        series = with_output_language(series)
        blueprint, _repaired = sanitize_blueprint(blueprint, series.title)
        rejections = sanitize_blueprint_nodes(
            blueprint.outline,
            blueprint.learning_path,
            series_title=series.title,
            language=series.language,
        )
        for node in blueprint.outline:
            node.gaps = extract_gaps(node.summary)
        if rejections:
            blueprint.objective_rejections = [
                *blueprint.objective_rejections,
                *rejections,
            ]

        created: list[Unit] = []
        updated: list[Unit] = []
        unchanged: list[Unit] = []
        removed: list[Unit] = []
        failures: list[dict[str, str]] = []
        existing = self.series_repository.list_units(series_id)
        next_index = max((unit.order_index for unit in existing), default=0) + 1
        for node in blueprint.outline:
            try:
                unit: Unit | None = None
                if node.unit_id:
                    unit = self.series_repository.get_unit(node.unit_id)
                if unit is None:
                    unit = self.series_repository.create_unit(
                        series_id=series_id,
                        title=node.title,
                        order_index=next_index,
                        learning_objectives=node.objectives,
                        prerequisites=node.prerequisites,
                        status=NODE_PLANNED,
                    )
                    created.append(unit)
                    next_index += 1
                    node.unit_id = unit.id
                else:
                    changes: dict[str, Any] = {}
                    title = (node.title or "").strip()
                    if title and title != unit.title:
                        changes["title"] = title
                    if list(node.objectives) != list(unit.learning_objectives):
                        changes["learning_objectives"] = list(node.objectives)
                    if list(node.prerequisites) != list(unit.prerequisites):
                        changes["prerequisites"] = list(node.prerequisites)
                    if changes:
                        refreshed = self.series_repository.update_unit(
                            unit.id, **changes
                        )
                        if refreshed is not None:
                            unit = refreshed
                        updated.append(unit)
                    else:
                        unchanged.append(unit)
                node.status = self._node_status_for_unit(unit)
            except Exception as exc:
                failures.append(
                    {
                        "node_id": node.id,
                        "title": node.title,
                        "reason": str(exc)[:300] or type(exc).__name__,
                    }
                )
        if confirm_removals:
            for item in plan["removed"]:
                unit = self.series_repository.get_unit(item["unit_id"])
                if unit is None:
                    continue
                try:
                    self.series_repository.delete_unit(unit.id)
                    removed.append(unit)
                except Exception as exc:
                    failures.append(
                        {
                            "node_id": "",
                            "title": unit.title,
                            "reason": f"remove failed: {str(exc)[:280] or type(exc).__name__}",
                        }
                    )
        saved = self.repository.save_blueprint(
            blueprint,
            author=author or "manual",
            change_source="apply",
            note="applied to series",
        )
        recorder = getattr(self.repository, "record_application", None)
        if callable(recorder):
            recorder(series_id, blueprint.version, author)
        return BlueprintApplyResult(
            blueprint=saved,
            created=created,
            updated=updated,
            unchanged=unchanged,
            removed=removed,
            failures=failures,
            stage_count=len(blueprint.learning_path),
            node_count=len(blueprint.outline),
        )

    def set_glossary(
        self, series_id: str, terms: Sequence[GlossaryTerm]
    ) -> SeriesBlueprint:
        blueprint = self.repository.get_blueprint(series_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"course blueprint not found: {series_id}")
        blueprint.glossary = [
            term if isinstance(term, GlossaryTerm) else GlossaryTerm(**term)
            for term in terms
        ]
        return self.repository.save_blueprint(blueprint)

    def sync_statuses(self, series_id: str) -> SeriesBlueprint:
        blueprint = self.repository.get_blueprint(series_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"course blueprint not found: {series_id}")
        for node in blueprint.outline:
            if not node.unit_id:
                continue
            unit = self.series_repository.get_unit(node.unit_id)
            if unit is None:
                node.unit_id = None
                node.status = NODE_PLANNED
                continue
            node.status = self._node_status_for_unit(unit)
        return self.repository.save_blueprint(blueprint)

    def review_unit(
        self, unit_id: str, action: str, note: str = ""
    ) -> tuple[Unit, UnitReview]:
        unit = self.series_repository.get_unit(unit_id)
        if unit is None:
            raise UnitNotFoundError(unit_id)
        resolved = (action or "").strip().lower()
        if resolved == REVIEW_APPROVE:
            if not unit.content.strip():
                raise UnitContentEmptyError(unit_id)
            status = NODE_APPROVED
            action_value = REVIEW_APPROVE
        elif resolved in (REVIEW_REQUEST_REVISION, "request-revision", "revision"):
            status = UNIT_NEEDS_REVISION
            action_value = REVIEW_REQUEST_REVISION
        else:
            raise ValueError(f"unsupported review action: {action!r}")

        updated = self.series_repository.update_unit(unit_id, status=status)
        assert updated is not None
        review = self.repository.add_review(
            unit_id=unit_id,
            action=action_value,
            note=note,
            version=unit.current_version,
            status=status,
        )
        self._sync_node_status(unit.series_id, unit_id, status)
        return updated, review

    def list_reviews(self, unit_id: str) -> list[UnitReview]:
        return self.repository.list_reviews(unit_id)

    def progress(self, series_id: str) -> dict[str, Any]:
        units = self.series_repository.list_units(series_id)
        by_status: dict[str, int] = {}
        for unit in units:
            by_status[unit.status] = by_status.get(unit.status, 0) + 1
        approved = by_status.get(NODE_APPROVED, 0)
        pending_review = sum(
            1
            for unit in units
            if unit.status != NODE_APPROVED and unit.content.strip()
        )
        next_unit_id: str | None = None
        for unit in units:
            if unit.status != NODE_APPROVED:
                next_unit_id = unit.id
                break
        blueprint = self.repository.get_blueprint(series_id)
        return {
            "series_id": series_id,
            "total": len(units),
            "by_status": by_status,
            "approved": approved,
            "pending_review": pending_review,
            "next_unit_id": next_unit_id,
            "blueprint_ready": bool(blueprint and blueprint.outline),
            "blueprint_version": blueprint.version if blueprint else 0,
        }

    def _sync_node_status(self, series_id: str, unit_id: str, unit_status: str) -> None:
        blueprint = self.repository.get_blueprint(series_id)
        if blueprint is None:
            return
        node_status = (
            NODE_APPROVED if unit_status == NODE_APPROVED else NODE_GENERATED
        )
        changed = False
        for node in blueprint.outline:
            if node.unit_id == unit_id:
                node.status = node_status
                changed = True
        if changed:
            self.repository.save_blueprint(blueprint)

    @staticmethod
    def _node_status_for_unit(unit: Unit) -> str:
        if unit.status == NODE_APPROVED:
            return NODE_APPROVED
        if unit.content.strip():
            return NODE_GENERATED
        return NODE_PLANNED

    def _build_query(self, series: Series, focus: str, units: Sequence[Any] | None = None) -> str:
        parts = [series.title, series.subtitle, series.audience, focus]
        for unit in list(units or [])[:6]:
            title = getattr(unit, "title", "") or ""
            if title and title not in series.title:
                parts.append(title)
            objectives = getattr(unit, "learning_objectives", None) or []
            for objective in list(objectives)[:2]:
                parts.append(str(objective))
        seen: set[str] = set()
        ordered: list[str] = []
        for part in parts:
            text = (part or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return " ".join(ordered)

    def _topic_texts(
        self, series: Series, units: Sequence[Any] | None = None, focus: str = ""
    ) -> list[str]:
        parts = [series.title, series.subtitle]
        for unit in list(units or []):
            parts.append(getattr(unit, "title", "") or "")
            for objective in list(getattr(unit, "learning_objectives", None) or []):
                parts.append(str(objective))
        parts.append(focus)
        seen: set[str] = set()
        ordered: list[str] = []
        for part in parts:
            text = str(part or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return ordered or [series.title]

    async def _request_payload(
        self,
        series: Series,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        focus: str,
        llm: LLMProvider | None = None,
        spec: ProfileSpec | None = None,
    ) -> dict[str, Any]:
        provider = llm or self.llm
        prompt = self._build_prompt(series, evidence, mode, focus, spec)
        raw = await provider.complete(prompt)
        payload = _extract_json(raw)
        if payload is None:
            retry = (
                prompt
                + "\n\n## Important reminder\nThe previous output was not valid JSON and could not be parsed. "
                "Output only a valid JSON object; do not output code-fence blocks or any explanatory text."
            )
            raw = await provider.complete(retry)
            payload = _extract_json(raw)
        if payload is None:
            raise BlueprintParseError("the course blueprint returned by the model is not valid JSON and cannot be parsed")
        return payload

    def _build_prompt(
        self,
        series: Series,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        focus: str,
        spec: ProfileSpec | None = None,
    ) -> str:
        unit = unit_name(spec)
        stages_low, stages_high, nodes_low, nodes_high = self._plan_bounds(spec)
        values = prompt_values(
            spec,
            title=series.title,
            unit=unit,
            audience=series.audience or "",
            evidence_count=len(evidence),
        )
        lines: list[str] = []
        prefix = system_prefix(spec, values)
        if prefix:
            lines.extend([prefix, ""])
        lines.extend(
            [
                "You are a senior course architect responsible for designing an executable teaching blueprint for a course.",
                "",
                "## Course information",
                f"- Title: {series.title}",
                f"- Subtitle: {series.subtitle or '(none)'}",
                f"- Content requirements: {(series.brief or '').strip() or '(not specified)'}",
                f"- Target audience: {series.audience or '(not specified)'}",
                f"- Difficulty: {series.difficulty}",
                f"- Language: {language_name(series.language)}",
                f"- Write every prose field in {language_name(series.language)}; do not switch language.",
                f"- Writing unit: {unit}",
                f"- Additional focus: {focus.strip() or '(none)'}",
                "",
                "## Generation mode",
            ]
        )
        if mode is GenerationMode.strict:
            lines.extend(
                [
                    "strict (strict mode) hard constraints:",
                    "1. overview and the summary of every outline node may only be written from the content in the \"Evidence\" section below.",
                    "2. Paragraphs that use evidence must carry a source marker in the form [E1]; cite multiple items as [E1][E2].",
                    "3. Gap disclosure applies only to prose: the overview and each node's summary. Where the evidence does not cover a topic, write \"Insufficient material: <gap description>\" in those prose fields and never fill the gap with common knowledge or speculation.",
                    "4. Structured fields must always carry real, specific values: learning_path[].title and goal, outline[].title, objectives[], prerequisites[], glossary[].term and glossary[].definition must never contain \"Insufficient material\", \"not covered by evidence\", \"no evidence\", or an unfilled template such as \"<title>\" or \"讲 title\"; derive them from the course title and the stage plan, and keep all outline titles distinct.",
                ]
            )
        else:
            lines.extend(
                [
                    "loose (non-strict mode) requirements:",
                    "1. You may plan freely from general knowledge and teaching experience; item-by-item citations are not required.",
                    "2. The first line of overview must read \"⚠️ This blueprint was written by an LLM and has not been verified against knowledge-base evidence\".",
                    "3. Mark uncertain or time-sensitive content as \"recommend verifying\"; do not present it as verified fact.",
                ]
            )
        lines.extend(
            [
                "",
                "## Authoring requirements (from the author, not retrieval evidence)",
                (series.brief or "").strip() or "(none)",
                "Use these requirements to decide topic selection, emphasis, and coverage. They are not evidence and must never be cited as a source.",
                "",
                "## Evidence",
            ]
        )
        if evidence:
            for item in evidence:
                snippet = (item.citation.text or item.citation.snippet).strip()
                if len(snippet) > self.evidence_char_limit:
                    snippet = snippet[: self.evidence_char_limit] + "…"
                lines.append(
                    f"[{item.marker}] Source: {item.citation.source_name}"
                    f" | chunk #{item.citation.chunk_index}"
                )
                lines.append(snippet)
                lines.append("")
        else:
            lines.extend(["(No knowledge-base evidence was retrieved this time)", ""])
        lines.extend(
            [
                "## Output JSON structure",
                "{",
                '  "overview": "Overall course description",',
                '  "learning_path": [',
                '    {"id": "stage-1", "title": "Stage name", "goal": "Stage goal",'
                ' "node_ids": ["node-1"], "estimated_minutes": 60}',
                "  ],",
                '  "outline": [',
                '    {"id": "node-1", "stage_id": "stage-1", "title": "Chapter title",'
                ' "summary": "Chapter summary", "objectives": ["Learning objective"],'
                ' "prerequisites": ["Prerequisite"], "estimated_minutes": 30}',
                "  ],",
                '  "glossary": [',
                '    {"term": "Term", "definition": "Definition", "aliases": ["Alias"],'
                ' "node_ids": ["node-1"]}',
                "  ]",
                "}",
                "",
                "## Structural constraints",
                f"1. learning_path must contain {stages_low}-{stages_high} stages in learning order; ids look like stage-1.",
                f"2. Each stage has 1-5 outline nodes, and the whole course has {nodes_low}-{nodes_high} {unit}s; ids look like node-1.",
                "3. The stage_id of every outline node must reference a defined stage id.",
                "4. glossary must contain 6-12 terms with unique term values; node_ids must reference outline node ids.",
                "5. Each node has 2-3 objectives; prerequisites may be an empty array.",
            ]
        )
        if spec is not None:
            lines.append(
                f"6. This course has {nodes_low}-{nodes_high} {unit}s; "
                f"overview must explain the overall pacing and the rationale for dividing the {unit}s."
            )
        extra = extra_requirement(spec, "outline", values)
        if extra:
            lines.extend(["", extra])
        lines.extend(
            [
                "",
                "## Output",
                "Output only a single JSON object; do not output markdown code fences or any explanatory text.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _plan_bounds(spec: ProfileSpec | None) -> tuple[int, int, int, int]:
        if spec is None:
            return 4, 8, 8, 20
        stages = max(2, min(8, int(spec.structure.depth or 2) * 2))
        low = max(1, int(spec.unit.min_units or 1))
        high = max(low, int(spec.unit.max_units or 60))
        return max(2, stages - 1), stages + 1, low, high

    def _blueprint_from_payload(
        self,
        series: Series,
        payload: Mapping[str, Any],
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        provider_name: str,
    ) -> SeriesBlueprint:
        payload, _repaired = sanitize_payload(payload, series.title)
        stages = _parse_stages(payload.get("learning_path") or payload.get("stages"))
        nodes = _parse_nodes(payload.get("outline") or payload.get("nodes"))
        if not nodes:
            raise BlueprintParseError("the course blueprint returned by the model has no outline nodes and cannot be used")
        _assign_stages(stages, nodes)
        rejections = sanitize_blueprint_nodes(
            nodes,
            stages,
            series_title=series.title,
            language=series.language,
        )
        for node in nodes:
            node.gaps = extract_gaps(node.summary)
        terms = _parse_terms(payload.get("glossary"))
        if not terms:
            terms = self._placeholder_terms(series, evidence, [node.id for node in nodes])

        grounded = mode is GenerationMode.strict and bool(evidence)
        overview = _as_str(payload.get("overview"))
        if mode is GenerationMode.loose and "not verified against knowledge-base evidence" not in overview:
            overview = f"⚠️ This blueprint was written by an LLM and has not been verified against knowledge-base evidence\n\n{overview}".strip()

        return SeriesBlueprint(
            series_id=series.id,
            overview=overview,
            mode=mode.value,
            grounded=grounded,
            learning_path=stages,
            outline=nodes,
            glossary=terms,
            provider=provider_name,
            warning="" if grounded else (LOOSE_WARNING if mode is GenerationMode.loose else ""),
            objective_rejections=rejections,
            updated_at=time.time(),
        )

    def _placeholder_blueprint(
        self,
        series: Series,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        provider_name: str,
        spec: ProfileSpec | None = None,
    ) -> SeriesBlueprint:
        title = series.title
        unit = unit_name(spec)
        stage_titles = _stage_titles(spec)
        counts = _node_counts(spec, len(stage_titles))
        used_titles: set[str] = set()
        node_index = 0
        nodes: list[OutlineNode] = []
        stages: list[LearningStage] = []
        for position, stage_title in enumerate(stage_titles):
            stage_id = f"stage-{position + 1}"
            stage_node_ids: list[str] = []
            for _ in range(counts[position]):
                hint_title, hint_summary = _NODE_HINTS[node_index % len(_NODE_HINTS)]
                node_index += 1
                node_id = f"node-{node_index}"
                node_title = hint_title.format(title=title)
                if node_title in used_titles:
                    node_title = f"{stage_title}: {node_title}"
                if node_title in used_titles:
                    node_title = f"{node_title} ({node_index})"
                used_titles.add(node_title)
                summary = hint_summary.format(title=title, unit=unit)
                if evidence:
                    marker = evidence[(node_index - 1) % len(evidence)].marker
                    summary = f"{summary} (reference evidence [{marker}])"
                else:
                    summary = f"{summary} (insufficient material: no matching evidence in the knowledge base)"
                stage_node_ids.append(node_id)
                nodes.append(
                    OutlineNode(
                        id=node_id,
                        stage_id=stage_id,
                        title=node_title,
                        summary=summary,
                        objectives=derive_objectives(
                            series_title=title,
                            node_title=node_title,
                            stage_title=stage_title,
                            stage_goal="",
                            node_position=node_index,
                            stage_position=position + 1,
                            language=series.language,
                        ),
                        prerequisites=[]
                        if position == 0
                        else ["Core concepts from the previous stage"],
                        estimated_minutes=30,
                        status=NODE_PLANNED,
                    )
                )
            stages.append(
                LearningStage(
                    id=stage_id,
                    title=stage_title,
                    goal=f"Achieve the learning objectives of the {stage_title} stage around \"{title}\"",
                    node_ids=stage_node_ids,
                    estimated_minutes=90,
                )
            )

        term_source = (
            f"Placeholder blueprint planned from course metadata and {len(evidence)} pieces of evidence, "
            if evidence
            else "Placeholder blueprint planned from course metadata only, "
        )
        overview = (
            f"⚠️ This blueprint was written by an LLM and has not been verified against knowledge-base evidence\n\n"
            if mode is GenerationMode.loose
            else ""
        ) + (
            f"{term_source}covering {len(stages)} stages of \"{title}\" from beginner to practical use, "
            f"with {len(nodes)} {unit}s. Target audience: {series.audience or 'not specified'}; difficulty: {series.difficulty}."
        )
        glossary = self._placeholder_terms(
            series, evidence, [node.id for node in nodes]
        )
        warning = PLACEHOLDER_WARNING
        if mode is GenerationMode.loose:
            warning = f"{PLACEHOLDER_WARNING}; {LOOSE_WARNING}"
        return SeriesBlueprint(
            series_id=series.id,
            overview=overview,
            mode=mode.value,
            grounded=mode is GenerationMode.strict and bool(evidence),
            learning_path=stages,
            outline=nodes,
            glossary=glossary,
            provider=provider_name,
            warning=warning,
            updated_at=time.time(),
        )

    def _placeholder_terms(
        self, series: Series, evidence: Sequence[Evidence], node_ids: Sequence[str]
    ) -> list[GlossaryTerm]:
        counts: dict[str, int] = {}
        for item in evidence:
            text = item.citation.text or item.citation.snippet
            for term, count in _candidate_counts(text).items():
                counts[term] = counts.get(term, 0) + count
        selected = _select_terms(counts, 6)
        if len(selected) < 6:
            meta = " ".join([series.title, series.subtitle, series.audience])
            for term in _metadata_terms(meta):
                if term in selected:
                    continue
                selected.append(term)
                if len(selected) >= 6:
                    break
        for fallback in ("Core concept", "Workflow", "Common pitfalls", "Practical path"):
            if len(selected) >= 6:
                break
            if fallback not in selected:
                selected.append(fallback)

        terms: list[GlossaryTerm] = []
        for position, term in enumerate(selected[:6]):
            sources = sorted(
                {
                    item.citation.source_name
                    for item in evidence
                    if term in (item.citation.text or item.citation.snippet)
                }
            )
            definition = f"Placeholder definition: a key concept related to \"{series.title}\", to be finalized once more material is available."
            if sources:
                definition = f"{definition}Appears in: {', '.join(sources[:2])}."
            terms.append(
                GlossaryTerm(
                    term=term,
                    definition=definition,
                    aliases=[],
                    node_ids=[node_ids[position % len(node_ids)]] if node_ids else [],
                )
            )
        return terms


def _normalize_stage_links(blueprint: SeriesBlueprint) -> SeriesBlueprint:
    """Keep stage.node_ids and node.stage_id consistent after hand editing."""
    by_stage: dict[str, list[str]] = {stage.id: [] for stage in blueprint.learning_path}
    for node in blueprint.outline:
        if node.stage_id in by_stage:
            by_stage[node.stage_id].append(node.id)
    for stage in blueprint.learning_path:
        stage.node_ids = by_stage.get(stage.id, [])
    return blueprint


def _plan_token(plan: Mapping[str, Any]) -> str:
    material = {
        "series_id": plan.get("series_id"),
        "blueprint_version": plan.get("blueprint_version"),
        "created": [item.get("node_id") for item in plan.get("created") or []],
        "renamed": [
            [item.get("unit_id"), item.get("to")]
            for item in plan.get("renamed") or []
        ],
        "updated": [item.get("unit_id") for item in plan.get("updated") or []],
        "removed": [item.get("unit_id") for item in plan.get("removed") or []],
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _parse_stages(raw: Any) -> list[LearningStage]:
    if not isinstance(raw, list):
        return []
    stages: list[LearningStage] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        stage_id = _as_str(item.get("id")) or f"stage-{index}"
        stages.append(
            LearningStage(
                id=stage_id,
                title=_as_str(item.get("title")) or f"Stage {index}",
                goal=_as_str(item.get("goal")),
                node_ids=_as_str_list(item.get("node_ids")),
                estimated_minutes=_as_int(item.get("estimated_minutes")),
            )
        )
    return stages


def _parse_nodes(raw: Any) -> list[OutlineNode]:
    if not isinstance(raw, list):
        return []
    nodes: list[OutlineNode] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        node_id = _as_str(item.get("id")) or f"node-{index}"
        while node_id in seen:
            node_id = f"{node_id}-{index}"
        seen.add(node_id)
        title = _as_str(item.get("title"))
        if not title:
            continue
        nodes.append(
            OutlineNode(
                id=node_id,
                stage_id=_as_str(item.get("stage_id")),
                title=title,
                summary=_as_str(item.get("summary")),
                objectives=_as_str_list(item.get("objectives")),
                prerequisites=_as_str_list(item.get("prerequisites")),
                estimated_minutes=_as_int(item.get("estimated_minutes")),
                status=NODE_PLANNED,
            )
        )
    return nodes


def _parse_terms(raw: Any) -> list[GlossaryTerm]:
    if not isinstance(raw, list):
        return []
    terms: list[GlossaryTerm] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        term = _as_str(item.get("term"))
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(
            GlossaryTerm(
                term=term,
                definition=_as_str(item.get("definition")),
                aliases=_as_str_list(item.get("aliases")),
                node_ids=_as_str_list(item.get("node_ids")),
            )
        )
    return terms


def _assign_stages(stages: Sequence[LearningStage], nodes: Sequence[OutlineNode]) -> None:
    if not stages:
        return
    valid = {stage.id for stage in stages}
    for node in nodes:
        if node.stage_id and node.stage_id not in valid:
            node.stage_id = ""
    if any(not node.stage_id for node in nodes):
        per_stage = max(1, -(-len(nodes) // len(stages)))
        for position, node in enumerate(nodes):
            if node.stage_id:
                continue
            node.stage_id = stages[min(position // per_stage, len(stages) - 1)].id
    for stage in stages:
        if not stage.node_ids:
            stage.node_ids = [node.id for node in nodes if node.stage_id == stage.id]


def _extract_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        return None
    candidate = text[start : end + 1] if end > start else text[start:]
    for attempt in (candidate, _repair_json(candidate)):
        try:
            payload = json.loads(attempt)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _repair_json(text: str) -> str:
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    repaired = re.sub(r"[\x00-\x1f](?![\n\r\t])", " ", repaired)
    missing_brackets = repaired.count("[") - repaired.count("]")
    missing_braces = repaired.count("{") - repaired.count("}")
    repaired += "]" * max(0, missing_brackets)
    repaired += "}" * max(0, missing_braces)
    return repaired


def _candidate_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    source = text or ""
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", source):
        counts[word] = counts.get(word, 0) + 1
    for run in re.findall(r"[\u4e00-\u9fa5]+", source):
        for size in (2, 3, 4):
            for start in range(len(run) - size + 1):
                gram = run[start : start + size]
                if gram in _STOPWORDS:
                    continue
                counts[gram] = counts.get(gram, 0) + 1
    return counts


def _select_terms(counts: Mapping[str, int], limit: int) -> list[str]:
    scored: list[tuple[str, float]] = []
    for term, count in counts.items():
        if len(term) < 2:
            continue
        is_ascii = term.isascii()
        if count < 2 and not is_ascii:
            continue
        weight = 2.0 if is_ascii else float(min(len(term), 4))
        scored.append((term, count * weight))
    scored.sort(key=lambda item: (-item[1], -counts[item[0]], item[0]))
    selected: list[str] = []
    for term, _ in scored:
        if any(term in existing or existing in term for existing in selected):
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def _metadata_terms(text: str) -> list[str]:
    terms: list[str] = []
    for segment in re.split(r"[，,、。;；/\|·\s]+", text or ""):
        cleaned = segment.strip().lstrip("\u4e0e\u548c\u53ca\u6216\u7684")
        if 2 <= len(cleaned) <= 10:
            terms.append(cleaned)
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", text or ""):
        if word not in terms:
            terms.append(word)
    return terms


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_str(item) for item in value if _as_str(item)]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，;；\n]", value) if item.strip()]
    return []
