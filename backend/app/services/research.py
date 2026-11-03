from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.research import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    ResearchBrief,
    ResearchContradiction,
    ResearchFinding,
    ResearchRun,
)
from app.ports.llm import LLMProvider
from app.ports.research_repository import ResearchRepository
from app.ports.vectorstore import VectorStore
from app.ports.web_search import WebSearchPort
from app.services.errors import ResearchParseError

QUESTION_PATTERNS = (
    "{topic} 的定义与边界",
    "{topic} 的关键要素",
    "{topic} 的常见误区",
    "{topic} 的典型应用场景",
    "{topic} 的实施步骤",
    "{topic} 的评估指标",
    "{topic} 的常见问题与排查",
    "{topic} 的进阶要点",
    "{topic} 的替代方案与取舍",
)

PLACEHOLDER_WARNING = "未配置 LLM key，本研究为基于检索证据的占位综合"
NO_EVIDENCE_WARNING = "知识库与联网检索均无命中，本研究由大模型基于自身知识生成，未经证据核实"
WEB_DISABLED_WARNING = "联网检索未启用，仅使用知识库证据"
MAX_SECTION_CHARS = 400


class ResearchService:
    def __init__(
        self,
        repository: ResearchRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        web_search: WebSearchPort | None = None,
        default_top_k: int = 6,
        max_evidence: int = 16,
        web_limit: int = 3,
        evidence_char_limit: int = MAX_SECTION_CHARS,
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.web_search = web_search
        self.default_top_k = default_top_k
        self.max_evidence = max_evidence
        self.web_limit = web_limit
        self.evidence_char_limit = evidence_char_limit

    async def run(
        self,
        topic: str,
        depth: int = 2,
        top_k: int | None = None,
        source_ids: Sequence[str] | None = None,
        tenant_id: str = "",
        user_id: str = "",
        llm: LLMProvider | None = None,
    ) -> ResearchRun:
        resolved_topic = (topic or "").strip()
        if not resolved_topic:
            raise ValueError("研究主题不能为空")
        resolved_depth = max(1, min(int(depth or 1), 3))
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        provider = llm or self.llm
        run = ResearchRun(
            id=f"research_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id or "",
            user_id=user_id or "",
            topic=resolved_topic,
            depth=resolved_depth,
            status=STATUS_COMPLETED,
            created_at=time.time(),
            updated_at=time.time(),
            provider=type(provider).__name__,
        )
        try:
            questions = await self._plan(provider, resolved_topic, resolved_depth)
            run.questions = questions
            citations, web_used, web_available = await self._gather(
                questions, resolved_top_k, source_ids, tenant_id
            )
            run.citations = citations
            run.web_used = web_used
            brief, warning = await self._synthesize(
                provider, resolved_topic, questions, citations, resolved_depth
            )
            run.brief = brief
            run.warning = self._warning(provider, citations, web_available, warning)
        except ResearchParseError:
            run.status = STATUS_FAILED
            run.warning = "研究综合失败：模型输出无法解析为结构化 JSON"
            raise
        finally:
            run.updated_at = time.time()
            self.repository.save(run)
        return run

    def get(self, run_id: str, tenant_id: str | None = None) -> ResearchRun | None:
        return self.repository.get(run_id, tenant_id)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[ResearchRun]:
        return self.repository.list(tenant_id, limit)

    def delete(self, run_id: str, tenant_id: str | None = None) -> bool:
        return self.repository.delete(run_id, tenant_id)

    async def _plan(
        self, provider: LLMProvider, topic: str, depth: int
    ) -> list[str]:
        count = max(1, depth) * 3
        if getattr(provider, "is_placeholder", False):
            return self._template_questions(topic, count)
        prompt = self._plan_prompt(topic, count)
        try:
            text = await provider.complete(prompt)
        except Exception:
            return self._template_questions(topic, count)
        questions = _parse_questions(text)
        if not questions:
            return self._template_questions(topic, count)
        return questions[:count]

    async def _gather(
        self,
        questions: Sequence[str],
        top_k: int,
        source_ids: Sequence[str] | None,
        tenant_id: str,
    ) -> tuple[list[Citation], int, bool]:
        citations: list[Citation] = []
        seen: set[str] = set()
        web_used = 0
        web_search = self.web_search
        web_available = bool(web_search is not None and web_search.healthcheck())
        for question in questions:
            found = await self.vectorstore.search(
                question,
                top_k=top_k,
                source_ids=source_ids,
                tenant_id=tenant_id,
            )
            for citation in found:
                key = f"kb:{citation.source_id}:{citation.chunk_index}"
                if key in seen:
                    continue
                seen.add(key)
                citations.append(citation)
            if web_available and web_search is not None:
                results = await web_search.search(question, limit=self.web_limit)
                web_used += len(results)
                for index, result in enumerate(results):
                    key = f"web:{result.url}"
                    if key in seen:
                        continue
                    seen.add(key)
                    citations.append(
                        Citation(
                            source_id=result.url or f"web-{index}",
                            source_name=result.title or result.url,
                            chunk_id=f"web-{index}",
                            chunk_index=index,
                            text=result.snippet,
                            snippet=result.snippet,
                            score=0.0,
                            start=0,
                            end=0,
                            meta={"kind": "web", "url": result.url},
                        )
                    )
        return citations[: self.max_evidence], web_used, web_available

    async def _synthesize(
        self,
        provider: LLMProvider,
        topic: str,
        questions: Sequence[str],
        citations: Sequence[Citation],
        depth: int,
    ) -> tuple[ResearchBrief, str]:
        if getattr(provider, "is_placeholder", False):
            return self._placeholder_brief(topic, questions, citations), PLACEHOLDER_WARNING
        prompt = self._synthesize_prompt(topic, questions, citations, depth)
        text = await provider.complete(prompt)
        payload = _extract_json(text)
        if payload is None:
            retry_prompt = f"{prompt}\n\n只输出合法 JSON，不要任何解释与 Markdown 代码块。"
            text = await provider.complete(retry_prompt)
            payload = _extract_json(text)
        if payload is None:
            raise ResearchParseError("模型输出无法解析为结构化 JSON")
        return _brief_from_payload(payload), ""

    def _warning(
        self,
        provider: LLMProvider,
        citations: Sequence[Citation],
        web_available: bool,
        extra: str,
    ) -> str:
        parts: list[str] = []
        if extra:
            parts.append(extra)
        if getattr(provider, "is_placeholder", False):
            parts.append(PLACEHOLDER_WARNING)
        if not citations:
            parts.append(NO_EVIDENCE_WARNING)
        elif not web_available:
            parts.append(WEB_DISABLED_WARNING)
        return "；".join(dict.fromkeys(parts))

    @staticmethod
    def _template_questions(topic: str, count: int) -> list[str]:
        questions: list[str] = []
        for index in range(count):
            pattern = QUESTION_PATTERNS[index % len(QUESTION_PATTERNS)]
            questions.append(pattern.format(topic=topic))
        return questions

    def _plan_prompt(self, topic: str, count: int) -> str:
        return "\n".join(
            [
                "你是资深研究规划员，需要把一个研究主题拆解成可检索、可回答的子问题。",
                f"- 研究主题：{topic}",
                f"- 子问题数量：恰好 {count} 个",
                "- 子问题必须互补，覆盖定义、关键要素、误区、方法与评估。",
                "只输出 JSON 字符串数组，例如 [\"第一个子问题\", \"第二个子问题\"]，不要输出任何解释。",
            ]
        )

    def _synthesize_prompt(
        self,
        topic: str,
        questions: Sequence[str],
        citations: Sequence[Citation],
        depth: int,
    ) -> str:
        lines = [
            "你是严谨的研究员，请只基于给定的检索证据综合出一份研究简报。",
            "",
            f"## 研究主题\n{topic}",
            "",
            "## 子问题",
        ]
        lines.extend(f"- {question}" for question in questions)
        lines.extend(
            [
                "",
                "## 证据",
            ]
        )
        for index, citation in enumerate(citations, start=1):
            snippet = (citation.snippet or citation.text or "")[: self.evidence_char_limit]
            lines.append(f"[E{index}] {citation.source_name}：{snippet}")
        if not citations:
            lines.append("（无检索证据，需在 gaps 中显式说明资料不足）")
        lines.extend(
            [
                "",
                "## 输出要求",
                "只输出一个 JSON 对象，不要 Markdown 代码块与任何解释，字段如下：",
                '{"summary": "3-6 句研究综述",',
                ' "findings": [{"title": "发现标题", "detail": "具体说明", "evidence": ["E1"]}],',
                ' "contradictions": [{"claim": "存在冲突的结论", "evidence": ["E1","E2"]}],',
                ' "gaps": ["资料不足之处"],',
                ' "next_steps": ["下一步建议"]}',
                f"- findings 数量 {max(3, depth * 2)}-{max(6, depth * 3)} 条，每条必须引用证据标记。",
                "- 不得引入证据之外的事实、数据或结论；证据不足时写入 gaps，不要编造。",
            ]
        )
        return "\n".join(lines)

    def _placeholder_brief(
        self,
        topic: str,
        questions: Sequence[str],
        citations: Sequence[Citation],
    ) -> ResearchBrief:
        findings: list[ResearchFinding] = []
        for index, citation in enumerate(citations, start=1):
            snippet = (citation.snippet or citation.text or "").strip()
            findings.append(
                ResearchFinding(
                    title=f"{citation.source_name} 的相关要点",
                    detail=snippet[: self.evidence_char_limit] or "证据片段为空",
                    evidence=[f"E{index}"],
                )
            )
        if not findings:
            findings.append(
                ResearchFinding(
                    title=f"{topic} 尚无可用证据",
                    detail="知识库与联网检索均未命中，需要补充资料后再做综合。",
                    evidence=[],
                )
            )
        gaps = list(questions[:3]) if citations else [f"{topic} 缺少可溯源资料"]
        contradictions: list[ResearchContradiction] = []
        if len(citations) >= 3:
            contradictions.append(
                ResearchContradiction(
                    claim="占位综合：多份证据侧重点不同，需人工确认是否存在口径差异",
                    evidence=["E1", "E3"],
                )
            )
        summary = (
            f"围绕「{topic}」检索到 {len(citations)} 条证据，覆盖子问题："
            + "、".join(questions)
            + "。以下结论按证据逐条整理，未做超出证据的推断。"
        )
        return ResearchBrief(
            summary=summary,
            findings=findings,
            contradictions=contradictions,
            gaps=gaps,
            next_steps=[
                "补齐资料不足的子问题后重新执行研究",
                "将确认后的结论转为课程蓝图或长篇初稿",
            ],
        )


def _parse_questions(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    candidate = text[start : end + 1] if start != -1 and end > start else text
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        return [
            line.strip(" -*\t0123456789.")
            for line in text.splitlines()
            if line.strip(" -*\t0123456789.")
        ][:9]
    if not isinstance(payload, list):
        return []
    questions: list[str] = []
    for item in payload:
        if isinstance(item, str) and item.strip():
            questions.append(item.strip())
        elif isinstance(item, Mapping):
            value = item.get("question") or item.get("title")
            if isinstance(value, str) and value.strip():
                questions.append(value.strip())
    return questions


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
    repaired += "]" * max(0, repaired.count("[") - repaired.count("]"))
    repaired += "}" * max(0, repaired.count("{") - repaired.count("}"))
    return repaired


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _brief_from_payload(payload: Mapping[str, Any]) -> ResearchBrief:
    findings: list[ResearchFinding] = []
    raw_findings = payload.get("findings")
    if isinstance(raw_findings, list):
        for item in raw_findings:
            if not isinstance(item, Mapping):
                continue
            title = _as_str(item.get("title"))
            detail = _as_str(item.get("detail"))
            if not title and not detail:
                continue
            findings.append(
                ResearchFinding(
                    title=title or detail[:30],
                    detail=detail,
                    evidence=_as_str_list(item.get("evidence")),
                )
            )
    contradictions: list[ResearchContradiction] = []
    raw_contradictions = payload.get("contradictions")
    if isinstance(raw_contradictions, list):
        for item in raw_contradictions:
            if not isinstance(item, Mapping):
                continue
            claim = _as_str(item.get("claim"))
            if not claim:
                continue
            contradictions.append(
                ResearchContradiction(
                    claim=claim,
                    evidence=_as_str_list(item.get("evidence")),
                )
            )
    return ResearchBrief(
        summary=_as_str(payload.get("summary")),
        findings=findings,
        contradictions=contradictions,
        gaps=_as_str_list(payload.get("gaps")),
        next_steps=_as_str_list(payload.get("next_steps")),
    )
