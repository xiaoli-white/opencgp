"""Web evidence fallback for generation.

The knowledge base stays the first and preferred evidence source. This module is
only consulted after the evidence gate has rejected the local evidence (or found
too little of it). Web results are converted into the same ``Citation`` objects
that the retrieval layer produces, so writer prompts, citation references and
the reader's citation panel need no parallel format.

Rules enforced here:

* the query is built from the topic/title plus a few extracted keywords, never
  from the whole document;
* only text actually returned by the configured web-search adapter is cited;
* the archived passage (capped by configuration) is stored in ``Citation.text``
  together with ``meta.kind="web"``, ``meta.url`` and ``meta.retrieved_at``;
* identical queries are cached for a short, configured window;
* provider failures return no passages and an honest status; nothing is invented.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from app.config import WebFallbackConfig, get_settings
from app.models.citation import Citation
from app.models.mode import GenerationMode
from app.ports.web_search import WebSearchPort
from app.services.evidence_gate import EvidenceGate, EvidenceGateResult, passage_relevance

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+#.\-]{1,23}|[\u4e00-\u9fff]{2,8}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "about",
    "your",
    "you",
    "are",
    "was",
    "were",
    "will",
    "what",
    "when",
    "where",
    "how",
    "why",
    "not",
    "but",
    "all",
    "any",
    "can",
    "has",
    "have",
    "its",
    "our",
    "their",
    "they",
    "them",
    "then",
    "than",
    "also",
    "such",
    "very",
    "more",
    "most",
    "some",
    "one",
    "two",
    "use",
    "using",
    "used",
    "the",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "is",
    "it",
    "as",
    "an",
    "or",
    "if",
    "be",
    "do",
    "does",
    "we",
    "i",
}


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    """Extract a few distinctive terms; Latin tokens first, then CJK runs."""

    latin: list[str] = []
    cjk: list[str] = []
    seen: set[str] = set()
    for match in TOKEN_RE.finditer(text or ""):
        token = match.group(0).strip()
        if not token:
            continue
        lowered = token.lower()
        if lowered in STOPWORDS or lowered in seen:
            continue
        if len(token) < 3 and not re.search(r"[\u4e00-\u9fff]", token):
            continue
        seen.add(lowered)
        if re.match(r"^[A-Za-z]", token):
            latin.append(token)
        else:
            cjk.append(token)
    return (latin + cjk)[: max(1, int(limit or 1))]


def build_web_query(
    topic: str,
    title: str = "",
    extra: str = "",
    *,
    max_keywords: int = 8,
    max_length: int = 240,
) -> str:
    """Compose a compact search query from topic + title + a few keywords."""

    parts: list[str] = []
    for value in (topic, title):
        text = " ".join((value or "").split())
        if text and text not in parts:
            parts.append(text[:120])
    keywords = extract_keywords(extra, limit=max_keywords)
    for keyword in keywords:
        if keyword not in parts:
            parts.append(keyword)
    query = " ".join(parts).strip()
    return query[:max_length].strip()


def _text_of(result_text: str, max_chars: int) -> str:
    normalized = (result_text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    cleaned: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if cleaned and not blank:
                cleaned.append("")
            blank = True
            continue
        cleaned.append(line)
        blank = False
    return "\n".join(cleaned).strip()[: max(1, int(max_chars))]


def _rerank_score(sources: Sequence[str]) -> float:
    for item in sources:
        text = str(item or "")
        if text.startswith("rerank="):
            try:
                return float(text[7:])
            except ValueError:
                return 0.0
    return 0.0


def relevance_score(query: str, title: str, text: str, sources: Sequence[str]) -> float:
    """Blend lexical overlap with the provider's own rerank signal (0..1)."""

    keywords = extract_keywords(query, limit=12)
    haystack = f"{title}\n{text}".lower()
    latin = [item for item in keywords if re.match(r"^[A-Za-z]", item)]
    checks = latin or keywords
    if checks:
        hits = sum(1 for item in checks if item.lower() in haystack)
        coverage = hits / len(checks)
    else:
        coverage = 0.0
    rerank = _rerank_score(sources)
    rerank_norm = min(1.0, max(0.0, rerank / 3.0))
    return max(0.0, min(1.0, 0.6 * coverage + 0.4 * rerank_norm))


@dataclass
class WebEvidenceStatus:
    enabled: bool = True
    attempted: bool = False
    provider: str = ""
    provider_available: bool = False
    query: str = ""
    result_count: int = 0
    passage_count: int = 0
    cache_hit: bool = False
    cache_ttl_seconds: float = 0.0
    max_results: int = 0
    max_chars: int = 0
    retrieved_at: str = ""
    error: str = ""
    opted_out: bool = False
    opt_out_reason: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "attempted": self.attempted,
            "provider": self.provider,
            "provider_available": self.provider_available,
            "query": self.query,
            "result_count": self.result_count,
            "passage_count": self.passage_count,
            "cache_hit": self.cache_hit,
            "cache_ttl_seconds": round(float(self.cache_ttl_seconds), 3),
            "max_results": self.max_results,
            "max_chars": self.max_chars,
            "retrieved_at": self.retrieved_at,
            "error": self.error,
            "opted_out": self.opted_out,
            "opt_out_reason": self.opt_out_reason,
        }


@dataclass
class _CacheEntry:
    created: float
    citations: list[dict[str, Any]] = field(default_factory=list)
    status: dict[str, Any] = field(default_factory=dict)


class WebEvidenceService:
    """Turn web-search results into citation-shaped evidence passages."""

    def __init__(
        self,
        web_search: WebSearchPort | None = None,
        config: WebFallbackConfig | None = None,
    ) -> None:
        self.web_search = web_search
        self.config = config or get_settings().web_fallback
        self._cache: dict[str, _CacheEntry] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    @property
    def provider_name(self) -> str:
        return str(getattr(self.web_search, "name", "") or "")

    def available(self) -> bool:
        if not self.enabled or self.web_search is None:
            return False
        try:
            return bool(self.web_search.healthcheck())
        except Exception:  # noqa: BLE001 - a broken adapter is simply unavailable
            return False

    def build_query(self, topic: str, title: str = "", extra: str = "") -> str:
        return build_web_query(
            topic,
            title,
            extra,
            max_keywords=self.config.max_keywords,
        )

    def status_unavailable(self, query: str = "", reason: str = "") -> WebEvidenceStatus:
        return WebEvidenceStatus(
            enabled=self.enabled,
            attempted=False,
            provider=self.provider_name,
            provider_available=False,
            query=query,
            cache_ttl_seconds=self.config.cache_ttl,
            max_results=self.config.max_results,
            max_chars=self.config.max_chars,
            error=reason or "provider_unavailable",
        )

    def status_opted_out(self, query: str = "", reason: str = "profile_local_only") -> WebEvidenceStatus:
        return WebEvidenceStatus(
            enabled=self.enabled,
            attempted=False,
            provider=self.provider_name,
            provider_available=self.available(),
            query=query,
            cache_ttl_seconds=self.config.cache_ttl,
            max_results=self.config.max_results,
            max_chars=self.config.max_chars,
            opted_out=True,
            opt_out_reason=reason,
        )

    def _cache_key(self, query: str) -> str:
        raw = f"{self.provider_name}|{self.config.max_results}|{self.config.max_chars}|{query.lower()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _cache_get(self, query: str) -> _CacheEntry | None:
        key = self._cache_key(query)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if self.config.cache_ttl <= 0 or time.monotonic() - entry.created >= self.config.cache_ttl:
            self._cache.pop(key, None)
            return None
        return entry

    def _cache_put(self, query: str, citations: Sequence[Citation], status: WebEvidenceStatus) -> None:
        if self.config.cache_ttl <= 0:
            return
        # Keep only one short window of entries; this is a retry cache, not a store.
        cutoff = time.monotonic() - self.config.cache_ttl
        for key, entry in list(self._cache.items()):
            if entry.created < cutoff:
                self._cache.pop(key, None)
        self._cache[self._cache_key(query)] = _CacheEntry(
            created=time.monotonic(),
            citations=[citation.model_dump() for citation in citations],
            status=status.payload(),
        )

    async def search(
        self,
        query: str,
        *,
        topic: str = "",
        title: str = "",
    ) -> tuple[list[Citation], WebEvidenceStatus]:
        """Search the web and return archived-passage citations.

        An empty list always means "no retrievable evidence". The status carries
        the honest reason (disabled/unavailable/error/zero results).
        """

        resolved_query = (query or "").strip()
        status = WebEvidenceStatus(
            enabled=self.enabled,
            attempted=False,
            provider=self.provider_name,
            provider_available=self.available(),
            query=resolved_query,
            cache_ttl_seconds=self.config.cache_ttl,
            max_results=self.config.max_results,
            max_chars=self.config.max_chars,
        )
        if not self.enabled:
            status.error = "web_fallback_disabled"
            return [], status
        if self.web_search is None or not status.provider_available:
            status.error = "provider_unavailable"
            return [], status
        if not resolved_query:
            status.error = "empty_query"
            return [], status

        cached = self._cache_get(resolved_query)
        if cached is not None:
            status.attempted = True
            status.cache_hit = True
            status.result_count = int(cached.status.get("result_count", 0))
            status.passage_count = int(cached.status.get("passage_count", 0))
            status.retrieved_at = str(cached.status.get("retrieved_at") or "")
            citations = [Citation.model_validate(item) for item in cached.citations]
            print(
                f"[web-evidence] cache hit provider={self.provider_name} "
                f"passages={status.passage_count} query={resolved_query[:120]!r}",
                flush=True,
            )
            return citations, status

        status.attempted = True
        print(
            f"[web-evidence] search provider={self.provider_name} "
            f"limit={self.config.max_results} query={resolved_query[:120]!r}",
            flush=True,
        )
        try:
            results = await self.web_search.search(
                resolved_query, limit=self.config.max_results
            )
        except Exception as exc:  # noqa: BLE001 - degrade honestly
            status.error = f"{type(exc).__name__}: {exc}"[:200]
            return [], status
        if not results:
            status.error = "no_results"
            self._cache_put(resolved_query, [], status)
            return [], status

        retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        citations: list[Citation] = []
        for rank, result in enumerate(results[: self.config.max_results], start=1):
            url = str(getattr(result, "url", "") or "").strip()
            body = _text_of(str(getattr(result, "snippet", "") or ""), self.config.max_chars)
            if not url or not body:
                # Never cite what the adapter did not retrieve.
                continue
            if not re.match(r"^https?://", url, re.IGNORECASE):
                continue
            result_title = str(getattr(result, "title", "") or "").strip()[:200]
            sources = [str(item) for item in (getattr(result, "sources", None) or [])]
            score = relevance_score(resolved_query, result_title, body, sources)
            digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
            citations.append(
                Citation(
                    source_id=url,
                    source_name=result_title or url,
                    chunk_id=f"web-{digest}",
                    chunk_index=rank - 1,
                    text=body,
                    snippet=body[:400],
                    score=round(score, 6),
                    keyword_score=round(score, 6),
                    start=0,
                    end=len(body),
                    sources=[*sources, "web"],
                    meta={
                        "kind": "web",
                        "origin": "web",
                        "url": url,
                        "retrieved_at": retrieved_at,
                        "retrieved_ts": time.time(),
                        "provider": self.provider_name,
                        "rank": rank,
                        "archive_chars": len(body),
                        "max_chars": self.config.max_chars,
                    },
                )
            )
        status.result_count = len(results)
        status.passage_count = len(citations)
        status.retrieved_at = retrieved_at
        if not citations:
            status.error = "no_citable_results"
        self._cache_put(resolved_query, citations, status)
        return citations, status


def build_web_evidence_service(
    web_search: WebSearchPort | None = None,
    config: WebFallbackConfig | None = None,
) -> WebEvidenceService:
    return WebEvidenceService(web_search=web_search, config=config)


def _tag_local(citations: Sequence[Citation]) -> None:
    for citation in citations:
        meta = citation.meta if isinstance(citation.meta, dict) else {}
        meta.setdefault("kind", "kb")
        meta.setdefault("origin", "knowledge_base")
        citation.meta = meta


def _assign_markers(citations: Sequence[Citation]) -> None:
    for index, citation in enumerate(citations, start=1):
        citation.marker = f"E{index}"


def counts_by_origin(citations: Sequence[Citation]) -> tuple[int, int]:
    local = 0
    web = 0
    for citation in citations:
        kind = str((citation.meta or {}).get("kind") or "").lower()
        if kind == "web":
            web += 1
        else:
            local += 1
    return local, web


async def resolve_evidence(
    *,
    gate: EvidenceGate,
    store: Any,
    local_query: str,
    citations: Sequence[Citation],
    topic: str,
    tenant_id: str = "",
    source_ids: Sequence[str] | None = None,
    mode: str | GenerationMode = GenerationMode.strict,
    citation_policy: str = "required",
    allow_without_evidence: bool = False,
    web_service: WebEvidenceService | None = None,
    web_topic: str = "",
    web_title: str = "",
    web_extra: str = "",
    local_only: bool = False,
    local_only_reason: str = "profile_local_only",
    topic_texts: Sequence[str] | None = None,
) -> tuple[EvidenceGateResult, list[Citation], WebEvidenceStatus | None]:
    """Evaluate local evidence first, then optionally fall back to the web.

    The local gate is authoritative: a passing local result never triggers a web
    request. Only an insufficient local result may blend in web passages.
    """

    local_citations = list(citations)
    _tag_local(local_citations)
    _assign_markers(local_citations)

    local_gate = await gate.check(
        store=store,
        query=local_query,
        citations=local_citations,
        tenant_id=tenant_id,
        source_ids=source_ids,
        mode=mode,
        citation_policy=citation_policy,
        allow_without_evidence=allow_without_evidence,
        topic=topic,
        topic_texts=topic_texts,
    )
    local_used, _ = counts_by_origin(local_gate.usable_citations)
    if local_gate.allowed:
        opt_query = ""
        opt_status = None
        if local_only and web_service is not None:
            opt_query = web_service.build_query(
                web_topic or topic, web_title, web_extra
            )
            opt_status = web_service.status_opted_out(
                opt_query, local_only_reason
            )
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=opt_status,
            profile_opted_out=bool(opt_status is not None),
        )
        return local_gate, local_citations, opt_status

    # From here on the local gate refused. Decide whether the web may help.
    web_query = ""
    if web_service is not None:
        web_query = web_service.build_query(web_topic or topic, web_title, web_extra)

    if web_service is None:
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=None,
            note="web_fallback_not_configured",
        )
        return local_gate, local_citations, None

    if local_only:
        status = web_service.status_opted_out(web_query, local_only_reason)
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=status,
            profile_opted_out=True,
        )
        return local_gate, local_citations, status

    if not web_service.enabled:
        status = web_service.status_unavailable(web_query, "web_fallback_disabled")
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=status,
        )
        return local_gate, local_citations, status

    if not web_service.available():
        status = web_service.status_unavailable(web_query, "provider_unavailable")
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=status,
        )
        return local_gate, local_citations, status

    web_citations, status = await web_service.search(
        web_query, topic=web_topic or topic, title=web_title
    )
    if not web_citations:
        local_gate.attach_web(
            local_passages=local_used,
            web_passages=0,
            status=status,
        )
        return local_gate, local_citations, status

    combined = [*local_citations, *web_citations]
    _assign_markers(combined)
    combined_gate = await gate.check(
        store=store,
        query=local_query,
        citations=combined,
        tenant_id=tenant_id,
        source_ids=source_ids,
        mode=mode,
        citation_policy=citation_policy,
        allow_without_evidence=allow_without_evidence,
        topic=topic,
        topic_texts=topic_texts,
    )
    usable_local, usable_web = counts_by_origin(combined_gate.usable_citations)
    if combined_gate.allowed:
        # A weak local hit is still useful context for the writer. Keep hits
        # above a conservative floor alongside the usable web passages instead
        # of silently discarding the user's material.
        threshold = max(0.0, float(combined_gate.threshold))
        weak_floor = threshold * 0.4
        weak_local = [
            citation
            for citation in local_citations
            if (citation.keyword_score is not None and float(citation.keyword_score) > 0.0)
            and weak_floor <= passage_relevance(citation) < threshold
            and gate.citation_is_topical(citation, topic_texts, topic)
        ]
        blended = [*weak_local, *combined_gate.usable_citations]
        seen_ids: set[str] = set()
        ordered: list[Citation] = []
        for citation in blended:
            key = f"{citation.source_id}:{citation.chunk_id}"
            if key in seen_ids:
                continue
            seen_ids.add(key)
            ordered.append(citation)
        _assign_markers(ordered)
        combined_gate.usable_citations = ordered
        usable_local, usable_web = counts_by_origin(ordered)
    combined_gate.attach_web(
        local_passages=usable_local,
        web_passages=usable_web,
        status=status,
    )
    if not combined_gate.allowed:
        combined_gate.warnings.append(
            "Web fallback ran but still did not produce enough usable evidence; "
            "generation was refused rather than inventing passages."
        )
    return combined_gate, combined, status
