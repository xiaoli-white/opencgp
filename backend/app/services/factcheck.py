from __future__ import annotations

import json
import re
from typing import Any, Sequence

from app.models.citation import Citation
from app.models.factcheck import (
    SUPPORTED_THRESHOLD,
    UNSURE_THRESHOLD,
    VERDICT_SUPPORTED,
    VERDICT_UNSUPPORTED,
    VERDICT_UNSURE,
    VERDICTS,
    CheckResult,
)
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore

CLAIM_PATTERN = re.compile(r"\d+\s*%?|最好|最强|一定|必然|绝对|所有|从不|唯一|最新|最高|最低")
HEADING_PATTERN = re.compile(r"^(#{1,6}\s|>|\||```|~~~)")
LIST_PATTERN = re.compile(r"^([-*+]\s+|\d+[.)]\s+)")
MAX_CLAIMS = 12
MIN_CLAIM_CHARS = 6
MAX_CLAIM_CHARS = 240
EVIDENCE_LIMIT = 3
LLM_REVIEW_LIMIT = 6


SENTENCE_ENDINGS = "。！？!?；;"


def _split_sentences(block: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    for char in block:
        buffer.append(char)
        if char in SENTENCE_ENDINGS:
            parts.append("".join(buffer).strip())
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        parts.append(tail)
    return [part for part in parts if part]


class FactCheckService:
    def __init__(
        self,
        vectorstore: VectorStore,
        llm: LLMProvider | None = None,
        repository: Any = None,
        default_top_k: int = 3,
        use_llm: bool = True,
    ) -> None:
        self.vectorstore = vectorstore
        self.llm = llm
        self.repository = repository
        self.default_top_k = max(1, int(default_top_k or 1))
        self.use_llm = use_llm

    def extract_claims(self, content: str, limit: int = MAX_CLAIMS) -> list[str]:
        claims: list[str] = []
        seen: set[str] = set()
        for block in _prose_blocks(content or ""):
            for sentence in _split_sentences(block):
                plain = sentence.strip()
                if len(plain) < MIN_CLAIM_CHARS:
                    continue
                if not CLAIM_PATTERN.search(plain):
                    continue
                claim = plain[:MAX_CLAIM_CHARS]
                key = claim.lower()
                if key in seen:
                    continue
                seen.add(key)
                claims.append(claim)
                if len(claims) >= limit:
                    break
            if len(claims) >= limit:
                break
        return claims

    async def check(
        self,
        claims: Sequence[str],
        top_k: int | None = None,
        tenant_id: str = "",
        llm: LLMProvider | None = None,
    ) -> list[CheckResult]:
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 10))
        results: list[CheckResult] = []
        for claim in claims:
            text = (claim or "").strip()
            if not text:
                continue
            try:
                found = await self.vectorstore.search(
                    text, top_k=resolved_top_k, tenant_id=tenant_id
                )
            except Exception:
                found = []
            best = max((float(item.score or 0.0) for item in found), default=0.0)
            results.append(
                CheckResult(
                    claim=text,
                    verdict=_verdict_for(best),
                    evidence=list(found[:EVIDENCE_LIMIT]),
                    score=round(best, 6),
                )
            )
        provider = llm or self.llm
        if self.use_llm and provider is not None and not getattr(provider, "is_placeholder", False):
            results = await self._review_with_llm(provider, results, tenant_id)
        return results

    async def _review_with_llm(
        self,
        provider: LLMProvider,
        results: list[CheckResult],
        tenant_id: str,
    ) -> list[CheckResult]:
        targets = results[:LLM_REVIEW_LIMIT]
        if not targets:
            return results
        lines = ["你是事实核查助手。请判断下列陈述是否有充分依据，只能输出 JSON 数组。"]
        for index, item in enumerate(targets, start=1):
            evidence = " ".join(
                (citation.snippet or citation.text or "")[:120] for citation in item.evidence
            )
            lines.append(
                f'{index}. 陈述：{item.claim[:200]}\n   证据：{evidence or "（无检索证据）"}'
            )
        lines.append(
            '输出格式：[{"index": 1, "verdict": "supported|unsure|unsupported"}]，不要输出其它内容。'
        )
        try:
            raw = await provider.complete("\n".join(lines))
        except Exception:
            return results
        verdicts = _parse_verdicts(raw)
        if not verdicts:
            return results
        for index, item in enumerate(targets, start=1):
            verdict = verdicts.get(index)
            if verdict and verdict != item.verdict:
                item.llm_verdict = verdict
                item.llm_reason = "模型复核与检索判定不一致"
                item.source = "retrieval+llm"
        return results

    def summarize(self, results: Sequence[CheckResult]) -> str:
        supported = sum(1 for item in results if item.verdict == VERDICT_SUPPORTED)
        unsure = sum(1 for item in results if item.verdict == VERDICT_UNSURE)
        unsupported = sum(1 for item in results if item.verdict == VERDICT_UNSUPPORTED)
        return f"{supported}supported,{unsure}unsure,{unsupported}unsupported"


def _verdict_for(score: float) -> str:
    if score >= SUPPORTED_THRESHOLD:
        return VERDICT_SUPPORTED
    if score >= UNSURE_THRESHOLD:
        return VERDICT_UNSURE
    return VERDICT_UNSUPPORTED


def _prose_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            joined = " ".join(part for part in buffer if part).strip()
            if joined:
                blocks.append(joined)
            buffer.clear()

    in_fence = False
    for raw in (content or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence or not line:
            flush()
            continue
        if HEADING_PATTERN.match(line):
            flush()
            continue
        if LIST_PATTERN.match(line):
            flush()
            buffer.append(LIST_PATTERN.sub("", line).strip())
            flush()
            continue
        buffer.append(line)
    flush()
    return blocks


def _parse_verdicts(raw: str) -> dict[int, str]:
    text = (raw or "").strip()
    if not text:
        return {}
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, list):
        return {}
    out: dict[int, str] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        verdict = str(item.get("verdict") or "").strip().lower()
        if verdict in VERDICTS:
            out[index] = verdict
    return out


def citations_of(results: Sequence[CheckResult]) -> list[Citation]:
    seen: set[str] = set()
    out: list[Citation] = []
    for item in results:
        for citation in item.evidence:
            if citation.chunk_id in seen:
                continue
            seen.add(citation.chunk_id)
            out.append(citation)
    return out
