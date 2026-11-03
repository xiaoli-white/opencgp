from __future__ import annotations

from typing import Any

import httpx

from app.models.web_search import WebResult
from app.ports.web_search import WebSearchPort

TITLE_KEYS = ("title", "name", "heading")
URL_KEYS = ("url", "link", "href")
SNIPPET_KEYS = ("snippet", "description", "summary", "content", "text")


class HttpJsonWebSearch(WebSearchPort):
    name = "http_json"

    def __init__(
        self,
        url: str,
        api_key: str = "",
        result_path: str = "results",
        method: str = "POST",
        timeout: float = 10.0,
    ) -> None:
        self.url = url
        self.api_key = api_key
        self.result_path = (result_path or "results").strip()
        self.method = (method or "POST").strip().upper()
        self.timeout = float(timeout)

    def healthcheck(self) -> bool:
        return bool(self.url)

    async def search(self, query: str, limit: int = 5) -> list[WebResult]:
        if not self.url or not (query or "").strip():
            return []
        payload = {"query": query.strip(), "limit": int(limit)}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if self.method == "GET":
                    response = await client.get(
                        self.url,
                        params=payload,
                        headers=headers,
                    )
                else:
                    response = await client.post(
                        self.url,
                        json=payload,
                        headers=headers,
                    )
                response.raise_for_status()
                body = response.json()
        except Exception:
            return []
        items = self._extract(body)
        results: list[WebResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = self._first(item, URL_KEYS)
            title = self._first(item, TITLE_KEYS)
            snippet = self._first(item, SNIPPET_KEYS)
            if not (url or title):
                continue
            results.append(
                WebResult(
                    title=title or url,
                    url=url,
                    snippet=snippet,
                    sources=["web"],
                )
            )
            if len(results) >= max(1, int(limit)):
                break
        return results

    def _extract(self, body: Any) -> list[Any]:
        node: Any = body
        for part in [segment for segment in self.result_path.split(".") if segment]:
            if isinstance(node, dict):
                node = node.get(part)
            elif isinstance(node, list) and part.isdigit():
                index = int(part)
                node = node[index] if index < len(node) else None
            else:
                return []
            if node is None:
                return []
        if isinstance(node, dict):
            nested = node.get("items") or node.get("list") or node.get("data")
            if isinstance(nested, list):
                return nested
            return [node]
        if isinstance(node, list):
            return node
        return []

    @staticmethod
    def _first(item: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
