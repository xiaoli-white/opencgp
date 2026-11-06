"""Single-chapter generation service: strict (grounded) and loose writing modes.

Flow: retrieve -> assemble evidence -> mode-specific prompt -> LLM writing -> persist version.

``strict`` (default) keeps grounded writing, with hard constraints enforced by both
prompt and structure:

- Writing may only use retrieved evidence, and every paragraph must carry an ``[En]`` source marker.
- When no evidence is retrieved, the LLM is not called; the service returns
  "insufficient material" instead of letting the model improvise.
- When no real LLM key is configured (placeholder provider), the body is assembled
  directly from the evidence as a placeholder draft, while the citation chain stays
  complete and verifiable.

``loose`` lets the model write freely from its own general knowledge, with evidence as
optional reference only:

- Retrieval results are still returned, but missing evidence does not block generation
  and per-paragraph citations are not required.
- The first line of the body must contain the notice "This article was written by an
  LLM and has not been verified against knowledge-base evidence", injected by the
  server before persisting rather than relying on the model's compliance.
"""

from __future__ import annotations

from typing import Sequence

from app.models.citation import Citation
from app.models.series import Series, Unit
from app.models.factcheck import CheckResult
from app.models.generation import Evidence, GenerationResult
from app.models.mode import GenerationMode, with_loose_notice
from app.models.validation import ValidationReport
from app.models.work_profile import ProfileSpec
from app.ports.series_repository import SeriesRepository
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore
from app.models.auth import AuthContext
from app.services.assets import PLACEHOLDER, AssetMaterializer
from app.services.errors import UnitNotFoundError, VersionConflictError
from app.services.factcheck import FactCheckService
from app.services.retrieval_providers import RetrievalContext
from app.services.prompting import (
    DEFAULT_LOOSE_WORDS,
    DEFAULT_STRICT_WORDS,
    extra_requirement,
    glossary_lines,
    policy_of,
    prompt_values,
    system_prefix,
    unit_name,
    voice_lines,
    word_range,
)
from app.services.validators import ValidatorRunner

NO_EVIDENCE_NOTICE = (
    "Insufficient material: no evidence related to this section's topic was found in the knowledge base, so no body text will be generated.\n\n"
    "Upload relevant material to the knowledge base first, or adjust this section's topic and try again; "
    "if you want the model to write freely from its own knowledge, switch to loose mode."
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
        repository: SeriesRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 5,
        evidence_char_limit: int = 600,
        max_evidence: int = 8,
        default_mode: str = "strict",
        min_score: float = 0.15,
        factcheck: FactCheckService | None = None,
        validators: ValidatorRunner | None = None,
        asset_max_images: int = 3,
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
        self.validators = validators
        self.asset_max_images = max(0, int(asset_max_images or 0))

    async def generate_unit(
        self,
        unit_id: str,
        topic: str | None = None,
        top_k: int | None = None,
        note: str = "",
        source_ids: Sequence[str] | None = None,
        mode: str | None = None,
        expected_version: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
        spec: ProfileSpec | None = None,
        retrieval: RetrievalContext | None = None,
        ctx: AuthContext | None = None,
        assets: AssetMaterializer | None = None,
    ) -> GenerationResult:
        unit = self.repository.get_unit(unit_id)
        if unit is None:
            raise UnitNotFoundError(unit_id)
        if expected_version is not None and int(expected_version) != unit.current_version:
            raise VersionConflictError(int(expected_version), unit.current_version)
        series = self.repository.get_series(unit.series_id)
        resolved_mode = GenerationMode.normalize(mode or self.default_mode)
        policy = policy_of(spec, resolved_mode.value)

        resolved_topic = (topic or unit.title).strip()
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        min_score = (
            self.min_score
            if (policy == "required" and resolved_mode is GenerationMode.strict)
            else None
        )
        if policy == "forbidden":
            citations: list[Citation] = []
        elif retrieval is not None:
            citations, _ = await retrieval.search(
                self.vectorstore,
                self._build_query(resolved_topic, unit),
                top_k=resolved_top_k,
                source_ids=source_ids,
                tenant_id=tenant_id,
                min_score=min_score,
            )
            citations = _diversify(citations, self.max_evidence, per_source=3)
        else:
            citations = await self.vectorstore.search(
                self._build_query(resolved_topic, unit),
                top_k=resolved_top_k,
                source_ids=source_ids,
                tenant_id=tenant_id,
                min_score=min_score,
            )
            citations = _diversify(citations, self.max_evidence, per_source=3)
        evidence = [
            Evidence(marker=f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]

        provider = llm or self.llm
        if resolved_mode is GenerationMode.loose and policy != "forbidden":
            content, prompt, provider_name, grounded = await self._write_loose(
                series, unit, resolved_topic, evidence, provider, spec
            )
        elif policy == "required":
            content, prompt, provider_name, grounded = await self._write_strict(
                series, unit, resolved_topic, evidence, provider, spec
            )
        elif policy == "optional" and evidence:
            content, prompt, provider_name, grounded = await self._write_strict(
                series, unit, resolved_topic, evidence, provider, spec
            )
        else:
            content, prompt, provider_name, grounded = await self._write_free(
                series, unit, resolved_topic, evidence, provider, spec, resolved_mode
            )

        checks = await self._run_factcheck(
            content,
            tenant_id,
            provider,
            resolved_mode is GenerationMode.strict and policy != "forbidden",
            retrieval,
        )
        report = await self._run_validators(spec, content, unit)
        note_value = note or self._default_note(resolved_mode, evidence)
        if checks:
            note_value = f"{note_value};factcheck:{self.factcheck.summarize(checks)}"
        if report is not None and report.results:
            note_value = f"{note_value};validators:{report.note_fragment()}"

        usable = (
            resolved_mode is GenerationMode.loose
            or bool(evidence)
            or policy != "required"
        )
        asset_ids: list[str] = []
        if assets is None or ctx is None:
            content = PLACEHOLDER.sub("", content).strip()
        elif assets.has_placeholders(content):
            content, asset_ids, asset_errors = await assets.materialize(ctx, content)
            if asset_errors:
                note_value = f"{note_value};assets:error={';'.join(asset_errors)[:200]}"
            elif asset_ids:
                note_value = f"{note_value};assets:{len(asset_ids)}"

        applied = self.repository.append_version(
            unit_id,
            content=content,
            citations=citations,
            note=note_value,
            status="generated" if usable else unit.status,
            mode=resolved_mode.value,
        )
        assert applied is not None
        updated, version = applied

        return GenerationResult(
            unit_id=unit_id,
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
            validation=report,
            warnings=list(retrieval.warnings) if retrieval is not None else [],
            retrieval=retrieval.summary() if retrieval is not None else {},
        )

    async def _run_validators(
        self, spec: ProfileSpec | None, content: str, unit: Unit
    ) -> ValidationReport | None:
        if self.validators is None or spec is None or not content:
            return None
        try:
            return await self.validators.run(
                spec,
                content,
                {
                    "unit_id": unit.id,
                    "series_id": unit.series_id,
                    "title": unit.title,
                    "setting_book": (spec.assets.setting_book),
                },
            )
        except Exception:
            return None

    async def _run_factcheck(
        self,
        content: str,
        tenant_id: str,
        provider: LLMProvider,
        is_strict: bool,
        retrieval: RetrievalContext | None = None,
    ) -> list[CheckResult]:
        if not is_strict or self.factcheck is None or not content:
            return []
        claims = self.factcheck.extract_claims(content)
        if not claims:
            return []
        try:
            return await self.factcheck.check(
                claims, tenant_id=tenant_id, retrieval=retrieval
            )
        except Exception:
            return []

    async def _write_strict(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        llm: LLMProvider,
        spec: ProfileSpec | None = None,
    ) -> tuple[str, str, str, bool]:
        if not evidence:
            return NO_EVIDENCE_NOTICE, "", "", False
        prompt = self._build_strict_prompt(series, unit, topic, evidence, spec)
        provider_name = type(llm).__name__
        if getattr(llm, "is_placeholder", False):
            content = self._strict_placeholder_draft(unit, topic, evidence, spec)
        else:
            content = await llm.complete(prompt)
        return content, prompt, provider_name, bool(content)

    async def _write_loose(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        llm: LLMProvider,
        spec: ProfileSpec | None = None,
    ) -> tuple[str, str, str, bool]:
        prompt = self._build_loose_prompt(series, unit, topic, evidence, spec)
        provider_name = type(llm).__name__
        if getattr(llm, "is_placeholder", False):
            content = self._loose_placeholder_draft(unit, topic, evidence, spec)
        else:
            content = await llm.complete(prompt)
        return with_loose_notice(content), prompt, provider_name, False

    async def _write_free(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        llm: LLMProvider,
        spec: ProfileSpec | None,
        mode: GenerationMode,
    ) -> tuple[str, str, str, bool]:
        prompt = self._build_free_prompt(series, unit, topic, evidence, spec, mode)
        provider_name = type(llm).__name__
        if getattr(llm, "is_placeholder", False):
            content = self._free_placeholder_draft(unit, topic, evidence, spec)
        else:
            content = await llm.complete(prompt)
        if mode is GenerationMode.loose:
            content = with_loose_notice(content)
        return content, prompt, provider_name, False

    @staticmethod
    def _default_note(mode: GenerationMode, evidence: Sequence[Evidence]) -> str:
        if mode is GenerationMode.loose:
            return "generate:loose"
        return "generate" if evidence else "generate:no-evidence"

    def _build_query(self, topic: str, unit: Unit) -> str:
        parts = [topic]
        if unit.learning_objectives:
            parts.append(" ".join(unit.learning_objectives))
        return " ".join(part for part in parts if part).strip()

    def _prompt_values(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None,
    ) -> dict[str, object]:
        return prompt_values(
            spec,
            title=(series.title if series else unit.title) or unit.title,
            unit=unit_name(spec),
            unit_index=unit.order_index,
            audience=(series.audience if series else "") or "",
            evidence_count=len(evidence),
        )

    def _build_strict_prompt(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        unit_label = unit_name(spec)
        low, high = word_range(spec, DEFAULT_STRICT_WORDS)
        values = self._prompt_values(series, unit, topic, evidence, spec)
        lines: list[str] = []
        prefix = system_prefix(spec, values)
        if prefix:
            lines.extend([prefix, ""])
        lines.extend(
            [
                f"You are a rigorous author responsible for writing the body of one {unit_label} of a series.",
                "",
                "## Series information",
                f"- Series: {series.title if series else 'Untitled series'}",
                f"- {unit_label} #{unit.order_index} · {unit.title}",
                f"- Topic of this {unit_label}: {topic}",
            ]
        )
        lines.extend(self._unit_context(unit, spec))

        lines.extend(
            [
                "",
                "## Hard writing constraints",
                "1. Only use content explicitly stated in the \"Evidence\" section; do not introduce facts, data, cases, people, or conclusions beyond the evidence.",
                "2. Every paragraph must carry at least one source marker in the form [E1]; when one paragraph cites multiple items, write [E1][E3].",
                "3. For subsections the evidence cannot support, explicitly write \"Insufficient material: <gap description>\"; never fill gaps with common knowledge or speculation.",
                f"4. Output Markdown: organize subsections with level-2 headings, keep the body between {low} and {high} characters, and briefly explain terms on first use.",
                "4.1 Tone: address the reader directly, like a teacher explaining. Do not repeatedly use reporting phrases such as \"evidence shows\", \"this indicates\", or \"it can be seen\"; state facts directly and keep the source marker at the end of the sentence.",
                f"5. End with a \"## Further questions\" section listing 2-3 questions that need additional material to answer.",
            ]
        )
        lines.extend(voice_lines(spec))
        lines.extend(glossary_lines(spec, unit))
        extra = extra_requirement(spec, "unit", values)
        if extra:
            lines.extend(["", extra])
        lines.extend(["", "## Evidence"])
        lines.extend(self._evidence_block(evidence))
        lines.append("## Output")
        lines.append("Output only the body Markdown; do not output explanations, prefaces, or commentary about the writing process.")
        lines.extend(self._asset_lines())
        return "\n".join(lines)

    def _build_loose_prompt(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        unit_label = unit_name(spec)
        low, high = word_range(spec, DEFAULT_LOOSE_WORDS)
        values = self._prompt_values(series, unit, topic, evidence, spec)
        lines: list[str] = []
        prefix = system_prefix(spec, values)
        if prefix:
            lines.extend([prefix, ""])
        lines.extend(
            [
                f"You are an experienced author responsible for writing the body of one {unit_label} of a series.",
                f"This {unit_label} uses \"free writing\" mode: you may expand from your own general knowledge, "
                "and per-paragraph citations of knowledge-base evidence are not required.",
                "",
                "## Series information",
                f"- Series: {series.title if series else 'Untitled series'}",
                f"- {unit_label} #{unit.order_index} · {unit.title}",
                f"- Topic of this {unit_label}: {topic}",
            ]
        )
        lines.extend(self._unit_context(unit, spec))

        lines.extend(
            [
                "",
                "## Writing requirements",
                "1. You may freely organize content from your own general knowledge, common practice, and teaching experience; you are not limited to the \"reference evidence\".",
                "2. The first line of the body must contain the notice: \"> ⚠️ This article was written by an LLM and has not been verified against knowledge-base evidence\".",
                "3. Per-paragraph source markers are not required; if you cite a specific claim from the reference evidence, you may optionally mark it [E1].",
                f"4. Output Markdown: organize subsections with level-2 headings, keep the body between {low} and {high} characters, and briefly explain terms on first use.",
                "5. For uncertain or time-sensitive conclusions, advise readers to verify them (e.g. \"recommend verifying\"); do not present them as verified facts.",
                "6. End with a \"## Further reading\" section listing 2-3 directions for further verification.",
            ]
        )
        lines.extend(voice_lines(spec))
        lines.extend(glossary_lines(spec, unit))
        extra = extra_requirement(spec, "unit", values)
        if extra:
            lines.extend(["", extra])
        lines.extend(["", "## Reference evidence (optional; ignore when absent)"])
        if evidence:
            lines.extend(self._evidence_block(evidence))
        else:
            lines.extend(["(No relevant knowledge-base evidence was retrieved this time; you may write entirely from the model's own knowledge)", ""])
        lines.append("## Output")
        lines.append("Output only the body Markdown; do not output explanations, prefaces, or commentary about the writing process.")
        lines.extend(self._asset_lines())
        return "\n".join(lines)

    def _build_free_prompt(
        self,
        series: Series | None,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None,
        mode: GenerationMode,
    ) -> str:
        unit_label = unit_name(spec)
        low, high = word_range(spec, DEFAULT_LOOSE_WORDS)
        values = self._prompt_values(series, unit, topic, evidence, spec)
        lines: list[str] = []
        prefix = system_prefix(spec, values)
        if prefix:
            lines.extend([prefix, ""])
        lines.extend(
            [
                f"You are an experienced author responsible for writing the body of one {unit_label} of a series.",
                "",
                "## Series information",
                f"- Series: {series.title if series else 'Untitled series'}",
                f"- {unit_label} #{unit.order_index} · {unit.title}",
                f"- Topic of this {unit_label}: {topic}",
            ]
        )
        lines.extend(self._unit_context(unit, spec))
        lines.extend(
            [
                "",
                "## Writing requirements",
                "1. Organize the content from your own knowledge, common practice, and teaching experience; no knowledge-base citations are needed.",
                "2. Never output source markers such as [E1], and do not fabricate source names.",
                f"3. Output Markdown: organize subsections with level-2 headings, keep the body between {low} and {high} characters, and briefly explain terms on first use.",
                "4. For uncertain or time-sensitive conclusions, advise readers to verify them (e.g. \"recommend verifying\"); do not present them as verified facts.",
            ]
        )
        if mode is GenerationMode.loose:
            lines.append("5. The first line of the body must contain the notice: \"> ⚠️ This article was written by an LLM and has not been verified against knowledge-base evidence\".")
        lines.extend(voice_lines(spec))
        lines.extend(glossary_lines(spec, unit))
        extra = extra_requirement(spec, "unit", values)
        if extra:
            lines.extend(["", extra])
        if evidence:
            lines.extend(["", "## Reference background (do not output source markers)"])
            for item in evidence[:3]:
                snippet = (item.citation.text or item.citation.snippet).strip()
                lines.append(snippet[:300])
                lines.append("")
        lines.append("## Output")
        lines.append("Output only the body Markdown; do not output explanations, prefaces, or commentary about the writing process.")
        lines.extend(self._asset_lines())
        return "\n".join(lines)


    def _asset_lines(self) -> list[str]:
        """Ask the model to mark spots where an illustration would help.

        The markers are resolved to real images after generation, so the body
        text keeps its own order; the article is still the primary artifact.
        """
        if not self.asset_max_images:
            return []
        return [
            "",
            "## Illustration markers (optional)",
            f"You may add at most {self.asset_max_images} illustration marker(s) in the whole body.",
            "A marker is a line that contains exactly: [[image: a short, concrete scene description]]",
            "Put it directly below the paragraph it illustrates, and only where an image genuinely helps understanding.",
            "Do not mention the marker in the prose, do not number them, and do not output anything when no image is needed.",
        ]

    @staticmethod
    def _unit_context(unit: Unit, spec: ProfileSpec | None = None) -> list[str]:
        lines: list[str] = []
        if unit.learning_objectives:
            lines.append("- Learning objectives: " + "; ".join(unit.learning_objectives))
        if unit.prerequisites:
            lines.append("- Prerequisites: " + "; ".join(unit.prerequisites))
        return lines

    def _evidence_block(self, evidence: Sequence[Evidence]) -> list[str]:
        lines: list[str] = []
        for item in evidence:
            citation = item.citation
            snippet = citation.text or citation.snippet
            if len(snippet) > self.evidence_char_limit:
                snippet = snippet[: self.evidence_char_limit] + "…"
            lines.append(f"[{item.marker}] Source: {citation.source_name} | chunk #{citation.chunk_index}")
            lines.append(snippet)
            lines.append("")
        return lines

    def _strict_placeholder_draft(
        self,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        unit_label = unit_name(spec)
        lines: list[str] = [
            f"# {unit.title}",
            "",
            "> Placeholder draft (no LLM API key configured, strict mode): the body is assembled directly from retrieved evidence to verify the citation-carrying writing pipeline.",
            "",
            f"## Topic of this {unit_label}",
            topic,
            "",
        ]
        if unit.learning_objectives:
            lines.append("## Learning objectives")
            lines.extend(f"- {item}" for item in unit.learning_objectives)
            lines.append("")

        lines.append("## Evidence highlights")
        lines.append("")
        for item in evidence:
            snippet = (item.citation.text or item.citation.snippet).strip()
            if len(snippet) > self.evidence_char_limit:
                snippet = snippet[: self.evidence_char_limit] + "…"
            lines.append(f"### Point {item.marker[1:]}")
            lines.append(f"{snippet} [{item.marker}]")
            lines.append(f"Source: {item.citation.source_name} | chunk #{item.citation.chunk_index}")
            lines.append("")

        lines.append("## Insufficient-material notes")
        lines.append(
            f"This {unit_label} only covers the {len(evidence)} pieces of evidence retrieved and does not yet develop the topic fully; "
            "once a real model is configured, a coherent body will be generated from the same evidence."
        )
        lines.append("")
        lines.append("## Further questions")
        lines.append("- Do these pieces of evidence contradict each other or differ in applicable conditions?")
        lines.append("- Which scenarios relevant to this topic are still not covered by the evidence?")
        if spec is not None and spec.assets.glossary:
            lines.extend(self._placeholder_glossary(evidence, spec))
        return "\n".join(lines)

    def _loose_placeholder_draft(
        self,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        unit_label = unit_name(spec)
        lines: list[str] = [
            f"# {unit.title}",
            "",
            "> Placeholder draft (no LLM API key configured, non-strict mode): this section allows the model to write freely from its own knowledge, "
            "so per-paragraph citations are not promised; once a real model is configured, it will generate the full body.",
            "",
            f"## Topic of this {unit_label}",
            topic,
            "",
            "## Writing outline (placeholder)",
            f"- Around \"{topic}\", give a concept definition, typical use cases, and common pitfalls.",
            "- Develop it step by step in a teaching style, adding examples and comparisons where necessary.",
            "- Mark time-sensitive or disputed conclusions as \"recommend verifying\".",
            "",
        ]
        if unit.learning_objectives:
            lines.append("## Learning objectives")
            lines.extend(f"- {item}" for item in unit.learning_objectives)
            lines.append("")
        if unit.prerequisites:
            lines.append("## Prerequisites")
            lines.extend(f"- {item}" for item in unit.prerequisites)
            lines.append("")

        lines.append("## Optional reference evidence")
        if evidence:
            for item in evidence[:3]:
                snippet = (item.citation.text or item.citation.snippet).strip()
                lines.append(
                    f"- {item.citation.source_name} | chunk #{item.citation.chunk_index}: "
                    f"{snippet[:200]}…"
                )
        else:
            lines.append("- No evidence was retrieved this time; this section relies entirely on the model's own knowledge.")
        lines.append("")
        lines.append("## Further reading")
        lines.append("- Consult the official documentation and specification for this topic.")
        lines.append("- Compare the trade-offs and applicable boundaries of different implementation approaches.")
        if spec is not None and spec.assets.glossary:
            lines.extend(self._placeholder_glossary(evidence, spec))
        return "\n".join(lines)

    def _free_placeholder_draft(
        self,
        unit: Unit,
        topic: str,
        evidence: Sequence[Evidence],
        spec: ProfileSpec | None = None,
    ) -> str:
        unit_label = unit_name(spec)
        profile_name = (spec.meta.name if spec is not None else "") or "Free writing"
        lines: list[str] = [
            f"# {unit.title}",
            "",
            f"> Placeholder draft (no LLM API key configured): free writing according to the creation profile \"{profile_name}\", "
            "without citing knowledge-base evidence or outputting source markers.",
            "",
            f"## Topic of this {unit_label}",
            topic,
            "",
            f"## Content outline (placeholder)",
            f"- Start from the core question of \"{topic}\" and explain the pain point it solves and its applicable boundaries.",
            "- Break down key concepts and common practices, and give criteria you can compare against.",
            "- Close with actionable steps and flag factual details that need verification.",
            "",
        ]
        if unit.learning_objectives:
            lines.append("## Learning objectives")
            lines.extend(f"- {item}" for item in unit.learning_objectives)
            lines.append("")
        if unit.prerequisites:
            lines.append("## Prerequisites")
            lines.extend(f"- {item}" for item in unit.prerequisites)
            lines.append("")
        lines.append("## Further reading")
        lines.append("- Consult the official documentation and specification for this topic.")
        lines.append("- Compare the trade-offs and applicable boundaries of different implementation approaches.")
        if spec is not None and spec.assets.glossary:
            lines.extend(self._placeholder_glossary(evidence, spec))
        return "\n".join(lines)

    def _placeholder_glossary(
        self, evidence: Sequence[Evidence], spec: ProfileSpec | None
    ) -> list[str]:
        lines: list[str] = ["", "## Glossary"]
        candidates: list[str] = []
        for item in evidence:
            text = (item.citation.text or item.citation.snippet or "").strip()
            for token in text.replace("，", " ").replace("。", " ").split():
                cleaned = token.strip("，。、；：（）()[]《》")
                if 2 <= len(cleaned) <= 8 and cleaned not in candidates:
                    candidates.append(cleaned)
                if len(candidates) >= 5:
                    break
            if len(candidates) >= 5:
                break
        if not candidates:
            candidates = ["Core concept", "Workflow", "Common pitfalls"]
        for term in candidates[:5]:
            lines.append(f"- {term}: placeholder definition, to be finalized once more material is available.")
        return lines
