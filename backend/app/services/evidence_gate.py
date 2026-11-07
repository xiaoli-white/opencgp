from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.config import EvidenceGateConfig, get_settings
from app.models.citation import Citation
from app.models.mode import GenerationMode
from app.services.topical_coverage import (
    TopicProfile,
    build_topic_profile,
    match_passage,
)

CODE_PASSED = "evidence_gate_passed"
CODE_INSUFFICIENT = "insufficient_evidence"
CODE_OVERRIDDEN = "evidence_gate_overridden"
CODE_OPTED_OUT = "evidence_gate_opted_out"
CODE_DISABLED = "evidence_gate_disabled"

NEXT_STEP = (
    "Open the knowledge base and add material for this topic, then generate again."
)

REFUSAL_TEMPLATE = (
    "Generation refused: insufficient evidence for \"{topic}\". "
    "Searched {searched} chunks; the best relevance score {best:.3f} is below the "
    "required {threshold:.3f}. Usable passages: {usable} (at least {required} required). "
    "{next_step}"
)

OFF_TOPIC_TEMPLATE = (
    "Generation refused: material was found but it is about a different subject. "
    "Searched {searched} chunks; {off_topic} passage(s) passed the relevance threshold "
    "{threshold:.3f} but none contains the topic's distinctive terms ({terms}). "
    "Offending sources: {sources}. Usable passages: 0 (at least {required} required). "
    "{next_step}"
)

COVERAGE_MARKERS = (
    "does not contain material on",
    "does not contain material about",
    "does not contain any material",
    "contains no material on",
    "cannot describe actual course content",
    "no relevant material",
    "not about the course topic",
    "different subject",
    "无法描述实际课程内容",
    "没有与该主题相关的材料",
    "不包含与该主题相关的材料",
    "材料与该主题无关",
    "证据与课程主题无关",
    "无法覆盖课程主题",
)


def text_admits_missing_coverage(text: str) -> bool:
    lowered = (text or "").casefold()
    if not lowered.strip():
        return False
    return any(marker.casefold() in lowered for marker in COVERAGE_MARKERS)


def passage_relevance(citation: Citation) -> float:
    keyword = citation.keyword_score
    if keyword is not None and float(keyword) > 0.0:
        return float(keyword)
    vector = citation.vector_score
    if vector is not None:
        return max(0.0, float(vector))
    return max(0.0, float(citation.score or 0.0))


def markers_of(citations: Sequence[Citation]) -> list[str]:
    return [citation.marker for citation in citations if citation.marker]


def text_cites_markers(text: str, markers: Sequence[str]) -> bool:
    body = text or ""
    if not markers:
        return False
    return any(f"[{marker}]" in body for marker in markers if marker)


@dataclass
class EvidenceGateResult:
    allowed: bool
    code: str
    message: str
    query: str
    topic: str
    chunks_searched: int
    best_score: float
    threshold: float
    min_passages: int
    usable_passages: int
    mode: str
    citation_policy: str
    grounded: bool
    opted_out: bool = False
    opt_out_reason: str = ""
    overridden: bool = False
    usable_markers: list[str] = field(default_factory=list)
    usable_citations: list[Citation] = field(default_factory=list)
    local_passages: int = 0
    web_passages: int = 0
    evidence_origin: str = "none"
    web_fallback: dict[str, Any] = field(default_factory=dict)
    profile_opted_out_web: bool = False
    warnings: list[str] = field(default_factory=list)
    topical_coverage_required: bool = False
    coverage_language: str = "unknown"
    topic_terms: list[str] = field(default_factory=list)
    topic_min_matches: int = 1
    threshold_passages: int = 0
    best_usable_score: float = 0.0
    off_topic_passages: int = 0
    off_topic_sources: list[str] = field(default_factory=list)
    off_topic_local_sources: list[str] = field(default_factory=list)
    off_topic_web_sources: list[str] = field(default_factory=list)

    def payload(self) -> dict[str, Any]:
        coverage = {
            "required": bool(self.topical_coverage_required),
            "language": self.coverage_language,
            "terms": list(self.topic_terms),
            "min_matches": int(self.topic_min_matches),
            "threshold_passages": int(self.threshold_passages),
            "usable_passages": int(self.usable_passages),
            "off_topic_passages": int(self.off_topic_passages),
            "off_topic_sources": list(self.off_topic_sources),
            "off_topic_local_sources": list(self.off_topic_local_sources),
            "off_topic_web_sources": list(self.off_topic_web_sources),
        }
        return {
            "code": self.code,
            "message": self.message,
            "query": self.query,
            "topic": self.topic,
            "chunks_searched": self.chunks_searched,
            "best_score": round(self.best_score, 6),
            "best_usable_score": round(self.best_usable_score, 6),
            "threshold": round(self.threshold, 6),
            "min_passages": self.min_passages,
            "usable_passages": self.usable_passages,
            "mode": self.mode,
            "citation_policy": self.citation_policy,
            "grounded": self.grounded,
            "opted_out": self.opted_out,
            "opt_out_reason": self.opt_out_reason,
            "overridden": self.overridden,
            "usable_markers": list(self.usable_markers),
            "local_passages": int(self.local_passages),
            "web_passages": int(self.web_passages),
            "evidence_origin": self.evidence_origin,
            "profile_opted_out_web": bool(self.profile_opted_out_web),
            "web_fallback": dict(self.web_fallback),
            "next_step": NEXT_STEP,
            "warnings": list(self.warnings),
            "topical_coverage_required": bool(self.topical_coverage_required),
            "coverage_language": self.coverage_language,
            "topic_terms": list(self.topic_terms),
            "topic_min_matches": int(self.topic_min_matches),
            "threshold_passages": int(self.threshold_passages),
            "off_topic_passages": int(self.off_topic_passages),
            "off_topic_sources": list(self.off_topic_sources),
            "off_topic_local_sources": list(self.off_topic_local_sources),
            "off_topic_web_sources": list(self.off_topic_web_sources),
            "topical_coverage": coverage,
        }

    def attach_web(
        self,
        *,
        local_passages: int,
        web_passages: int,
        status: Any = None,
        profile_opted_out: bool = False,
        note: str = "",
    ) -> None:
        self.local_passages = max(0, int(local_passages))
        self.web_passages = max(0, int(web_passages))
        self.profile_opted_out_web = bool(profile_opted_out)
        if status is not None:
            self.web_fallback = (
                status.payload() if hasattr(status, "payload") else dict(status or {})
            )
        elif note:
            self.web_fallback = {"enabled": False, "attempted": False, "error": note}
        if self.local_passages and self.web_passages:
            self.evidence_origin = "mixed"
        elif self.web_passages:
            self.evidence_origin = "web"
        elif self.local_passages:
            self.evidence_origin = "local"
        else:
            self.evidence_origin = "none"

    def summary(self) -> dict[str, Any]:
        data = self.payload()
        data.pop("warnings", None)
        return data

    def mark_evidence_unused(self) -> None:
        self.grounded = False
        self.code = "evidence_not_cited"
        self.message = (
            "Evidence was retrieved, but the generated text contains no citation "
            "marker for it; this result is not marked as grounded."
        )
        if self.message not in self.warnings:
            self.warnings.append(self.message)

    def mark_coverage_admission(self, detail: str = "") -> None:
        self.grounded = False
        self.code = "evidence_coverage_admitted"
        self.message = (
            "The generated text itself reports that the evidence does not cover the "
            "course topic, so this result is not marked as grounded."
        )
        if detail:
            self.message = f"{self.message} {detail}".strip()
        if self.message not in self.warnings:
            self.warnings.append(self.message)


class EvidenceGate:
    def __init__(self, config: EvidenceGateConfig | None = None) -> None:
        self.config = config or get_settings().evidence_gate

    def profile_for(
        self,
        topic_texts: Sequence[str] | None,
        fallback: str = "",
    ) -> TopicProfile | None:
        if not self.config.require_topical_coverage:
            return None
        texts = [str(text).strip() for text in (topic_texts or []) if str(text).strip()]
        if not texts:
            texts = [str(fallback or "").strip()]
        return build_topic_profile(
            texts,
            alias_map=self.config.topic_aliases,
            max_terms=self.config.topic_max_terms,
            primary_count=2,
        )

    def citation_is_topical(
        self,
        citation: Citation,
        topic_texts: Sequence[str] | None,
        fallback: str = "",
    ) -> bool:
        profile = self.profile_for(topic_texts, fallback)
        if profile is None or not profile.available:
            return True
        body = citation.text or citation.snippet or ""
        return match_passage(
            body,
            profile,
            min_matches=self.config.topic_min_matches,
        ).matched

    async def check(
        self,
        *,
        store: Any,
        query: str,
        citations: Sequence[Citation],
        tenant_id: str = "",
        source_ids: Sequence[str] | None = None,
        mode: str | GenerationMode = GenerationMode.strict,
        citation_policy: str = "required",
        allow_without_evidence: bool = False,
        topic: str = "",
        topic_texts: Sequence[str] | None = None,
    ) -> EvidenceGateResult:
        resolved_mode = GenerationMode.normalize(
            mode.value if isinstance(mode, GenerationMode) else mode
        ).value
        policy = (citation_policy or "required").strip().lower()
        threshold = max(0.0, float(self.config.min_score))
        required = max(1, int(self.config.min_passages))
        resolved_topic = (topic or query or "").strip()
        scored = [(citation, passage_relevance(citation)) for citation in citations]
        threshold_hits = [
            (citation, score)
            for citation, score in scored
            if score + 1e-9 >= threshold
        ]
        profile = self.profile_for(topic_texts, resolved_topic or query)
        coverage_active = bool(
            self.config.enabled and profile is not None and profile.available
        )
        usable = list(threshold_hits)
        off_topic: list[tuple[Citation, float]] = []
        if coverage_active:
            usable = []
            for citation, score in threshold_hits:
                body = citation.text or citation.snippet or ""
                matched = match_passage(
                    body,
                    profile,
                    min_matches=self.config.topic_min_matches,
                )
                if matched.matched:
                    usable.append((citation, score))
                else:
                    off_topic.append((citation, score))
        best_score = max((score for _, score in scored), default=0.0)
        best_usable_score = max((score for _, score in usable), default=0.0)
        searched = await self._chunks_searched(store, tenant_id, source_ids)
        off_topic_local = self._sources_of(
            [citation for citation, _ in off_topic], origin="local"
        )
        off_topic_web = self._sources_of(
            [citation for citation, _ in off_topic], origin="web"
        )
        off_topic_sources = self._sources_of([citation for citation, _ in off_topic])
        result = EvidenceGateResult(
            allowed=True,
            code=CODE_PASSED,
            message="",
            query=query,
            topic=resolved_topic,
            chunks_searched=searched,
            best_score=best_score,
            best_usable_score=best_usable_score,
            threshold=threshold,
            min_passages=required,
            usable_passages=len(usable),
            mode=resolved_mode,
            citation_policy=policy,
            grounded=False,
            usable_markers=[citation.marker for citation, _ in usable if citation.marker],
            usable_citations=[citation for citation, _ in usable],
            topical_coverage_required=coverage_active,
            coverage_language=profile.language if profile is not None else "unknown",
            topic_terms=profile.term_texts if profile is not None else [],
            topic_min_matches=max(1, int(self.config.topic_min_matches)),
            threshold_passages=len(threshold_hits),
            off_topic_passages=len(off_topic),
            off_topic_sources=off_topic_sources,
            off_topic_local_sources=off_topic_local,
            off_topic_web_sources=off_topic_web,
        )
        if self.config.enabled and self.config.require_topical_coverage:
            if profile is None or not profile.available:
                result.warnings.append(
                    "Topical coverage could not be evaluated because no distinctive "
                    "topic terms were extracted; the score threshold was the only rule."
                )

        if not self.config.enabled:
            result.code = CODE_DISABLED
            result.grounded = (
                resolved_mode == GenerationMode.strict.value and len(usable) > 0
            )
            result.message = (
                "Evidence gate is disabled by configuration; generation ran without "
                "an evidence requirement."
            )
            if not result.grounded:
                result.warnings.append(
                    "Evidence gate disabled and no usable evidence was found; this result is not grounded."
                )
            return result

        if policy == "forbidden":
            result.code = CODE_OPTED_OUT
            result.opted_out = True
            result.opt_out_reason = "citation_policy_forbidden"
            result.grounded = False
            result.message = (
                "The active profile forbids citations, so the evidence gate was "
                "explicitly opted out; this result is not grounded in knowledge-base evidence."
            )
            result.warnings.append(result.message)
            return result

        if resolved_mode == GenerationMode.loose.value:
            result.code = CODE_OPTED_OUT
            result.opted_out = True
            result.opt_out_reason = "loose_mode"
            result.grounded = False
            result.message = (
                "Loose mode generation is allowed without requiring evidence; this "
                "result is not grounded in knowledge-base evidence."
            )
            result.warnings.append(result.message)
            return result

        if len(usable) >= required:
            result.grounded = True
            coverage_note = (
                f"; topical coverage matched {profile.term_texts}."
                if coverage_active and profile is not None
                else "."
            )
            result.message = (
                f"Evidence gate passed with {len(usable)} usable passage(s); "
                f"best usable relevance score {best_usable_score:.3f} >= {threshold:.3f}"
                f"{coverage_note}"
            )
            return result

        if allow_without_evidence and self.config.allow_override:
            result.code = CODE_OVERRIDDEN
            result.overridden = True
            result.grounded = False
            result.message = (
                "The operator explicitly allowed generation without usable evidence; "
                "this result is not grounded in knowledge-base evidence."
            )
            result.warnings.append(result.message)
            return result

        result.allowed = False
        result.code = CODE_INSUFFICIENT
        result.grounded = False
        if off_topic:
            sources = off_topic_local or off_topic_sources
            result.message = OFF_TOPIC_TEMPLATE.format(
                searched=searched,
                off_topic=len(off_topic),
                threshold=threshold,
                terms=", ".join(profile.term_texts) if profile is not None else "(none)",
                sources=", ".join(sources[:8]) or "(unknown)",
                required=required,
                next_step=NEXT_STEP,
            )
            if off_topic_local:
                result.warnings.append(
                    "Local material was found but is about a different subject: "
                    + ", ".join(off_topic_local[:8])
                    + "; it was treated as no evidence."
                )
            if off_topic_web:
                result.warnings.append(
                    "Web material was found but is about a different subject: "
                    + ", ".join(off_topic_web[:8])
                    + "; it was treated as no evidence."
                )
        else:
            result.message = REFUSAL_TEMPLATE.format(
                topic=resolved_topic or "(untitled)",
                searched=searched,
                best=best_score,
                threshold=threshold,
                usable=len(usable),
                required=required,
                next_step=NEXT_STEP,
            )
        return result

    @staticmethod
    def _sources_of(
        citations: Sequence[Citation], origin: str = ""
    ) -> list[str]:
        names: list[str] = []
        for citation in citations:
            kind = str((citation.meta or {}).get("kind") or "kb").lower()
            if origin == "web" and kind != "web":
                continue
            if origin == "local" and kind == "web":
                continue
            name = citation.source_name or citation.source_id or "(unknown)"
            if name not in names:
                names.append(name)
        return names

    async def _chunks_searched(
        self,
        store: Any,
        tenant_id: str,
        source_ids: Sequence[str] | None,
    ) -> int:
        counter = getattr(store, "count_chunks", None)
        if callable(counter):
            try:
                return int(
                    await counter(
                        tenant_id=tenant_id, source_ids=list(source_ids or [])
                    )
                )
            except Exception:
                pass
        lister = getattr(store, "list_chunks", None)
        if callable(lister):
            try:
                return len(await lister(tenant_id=tenant_id))
            except Exception:
                pass
        return 0


def build_evidence_gate() -> EvidenceGate:
    return EvidenceGate()
