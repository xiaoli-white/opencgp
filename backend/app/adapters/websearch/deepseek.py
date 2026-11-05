from __future__ import annotations

import httpx

from app.models.web_search import WebResult
from app.ports.web_search import WebSearchPort


class DeepSeekWebSearch(WebSearchPort):
    name = "deepseek"

    def __init__(
        self,
        base_url: str = "https://api.deepseek.com",
        api_key: str = "",
        timeout: float = 20.0,
        need_content: bool = False,
    ) -> None:
        self.base_url = (base_url or "https://api.deepseek.com").rstrip("/")
        self.api_key = api_key
        self.timeout = float(timeout or 20)
        self.need_content = bool(need_content)
        self.last_error = ""

    def healthcheck(self) -> bool:
        return bool(self.api_key)

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
        return results
