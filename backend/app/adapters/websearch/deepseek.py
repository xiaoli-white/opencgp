from __future__ import annotations

import asyncio
import re
import time

import httpx

from app.models.web_search import WebResult
from app.ports.web_search import WebSearchPort

_FETCH_CACHE_TTL = 300.0
_FETCH_CACHE_MAX = 500


class DeepSeekWebSearch(WebSearchPort):
    name = "deepseek"

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com",
        api_key: str = "",
        timeout: float = 20.0,
        need_content: bool = False,
        fetch_enabled: bool = True,
        fetch_top: int = 2,
        fetch_chars: int = 4000,
        fetch_timeout: float = 8.0,
    ) -> None:
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.api_key = api_key
        self.timeout = float(timeout or 20)
        self.need_content = bool(need_content)
        self.fetch_enabled = bool(fetch_enabled)
        self.fetch_top = max(0, int(fetch_top or 0))
        self.fetch_chars = max(200, int(fetch_chars or 4000))
        self.fetch_timeout = float(fetch_timeout or 8)
        self.last_error = ""
        self._fetch_cache: dict[str, tuple[float, tuple[str, str] | None]] = {}
        self._fetch_lock: asyncio.Lock | None = None

    def healthcheck(self) -> bool:
        return bool(self.api_key)

    def _lock(self) -> asyncio.Lock:
        if self._fetch_lock is None:
            self._fetch_lock = asyncio.Lock()
        return self._fetch_lock

    def _cache_get(self, url: str) -> tuple[bool, tuple[str, str] | None]:
        item = self._fetch_cache.get(url)
        if item is None:
            return False, None
        ts, value = item
        if time.monotonic() - ts >= _FETCH_CACHE_TTL:
            self._fetch_cache.pop(url, None)
            return False, None
        return True, value

    def _cache_put(self, url: str, value: tuple[str, str] | None) -> None:
        self._fetch_cache[url] = (time.monotonic(), value)
        if len(self._fetch_cache) > _FETCH_CACHE_MAX:
            cutoff = time.monotonic() - _FETCH_CACHE_TTL
            for key, (ts, _) in list(self._fetch_cache.items()):
                if ts < cutoff:
                    self._fetch_cache.pop(key, None)
            while len(self._fetch_cache) > _FETCH_CACHE_MAX:
                self._fetch_cache.pop(next(iter(self._fetch_cache)))

    async def fetch_page(self, url: str) -> tuple[str, str] | None:
        target = (url or "").strip()
        if not target or not self.api_key:
            return None
        if not re.match(r"^https?://", target, re.IGNORECASE):
            return None
        async with self._lock():
            hit, cached = self._cache_get(target)
        if hit:
            return cached
        value: tuple[str, str] | None = None
        try:
            async with httpx.AsyncClient(timeout=self.fetch_timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/tools/fetch",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"url": target},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = str(data.get("content") or "").strip()
                    title = str(data.get("title") or "").strip()[:200]
                    if content:
                        value = (title, content)
                else:
                    self.last_error = f"fetch {resp.status_code}"
        except Exception as exc:
            self.last_error = str(exc)[:200]
            value = None
        async with self._lock():
            self._cache_put(target, value)
        return value

    @staticmethod
    def _rerank_score(result: WebResult) -> float:
        for item in result.sources:
            text = str(item or "")
            if text.startswith("rerank="):
                try:
                    return float(text[7:])
                except ValueError:
                    return 0.0
        return 0.0

    @staticmethod
    def _clean(text: str, limit: int) -> str:
        normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
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
        return "\n".join(cleaned).strip()[:limit]

    async def search(self, query: str, limit: int = 5) -> list[WebResult]:
        text = (query or "").strip()
        if not text or not self.api_key:
            return []
        count = max(1, min(int(limit or 5), 50))
        payload = {
            "query": text[:128],
            "count": count,
            "need_content": self.need_content,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/tools/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            self.last_error = str(exc)[:200]
            return []
        results: list[WebResult] = []
        for item in data.get("results") or []:
            summary = str(item.get("summary") or item.get("snippet") or "").strip()
            content = str(item.get("content") or "").strip()
            body = summary or content
            if content and len(content) > len(body):
                body = content
            results.append(
                WebResult(
                    title=str(item.get("title") or "")[:200],
                    url=str(item.get("url") or ""),
                    snippet=body[:2000],
                    sources=[
                        str(item.get("site_name") or ""),
                        f"rerank={item.get('rerank_score')}",
                    ],
                )
            )
        if self.fetch_enabled and self.fetch_top > 0 and results:
            indexed = list(enumerate(results))
            strong = [pair for pair in indexed if self._rerank_score(pair[1]) >= 1.5]
            weak = [pair for pair in indexed if self._rerank_score(pair[1]) < 1.5]
            chosen = (strong + weak)[: self.fetch_top]
            tasks = [
                asyncio.create_task(self.fetch_page(result.url))
                for _, result in chosen
                if result.url
            ]
            selected = [pair for pair in chosen if pair[1].url]
            if tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=self.fetch_timeout,
                    )
                except Exception:
                    pass
                outcomes: list[tuple[str, str] | None] = []
                for task in tasks:
                    value: tuple[str, str] | None = None
                    if task.done() and not task.cancelled():
                        try:
                            raw = task.result()
                            if isinstance(raw, tuple) and len(raw) == 2:
                                value = raw
                        except Exception:
                            value = None
                    else:
                        task.cancel()
                    outcomes.append(value)
                if any(task.cancelled() for task in tasks):
                    await asyncio.gather(*tasks, return_exceptions=True)
                for (_, result), fetched in zip(selected, outcomes):
                    if not fetched:
                        continue
                    title, content = fetched
                    body = self._clean(content, self.fetch_chars)
                    if not body or len(body) <= len(result.snippet):
                        continue
                    result.snippet = body
                    if "fetched" not in result.sources:
                        result.sources.append("fetched")
                    if title and not result.title:
                        result.title = title
        return results
