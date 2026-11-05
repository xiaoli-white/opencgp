from __future__ import annotations

from typing import Any, Sequence

import httpx


class HTTPReranker:
    name = "http"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 20.0,
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = float(timeout or 20)

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int
    ) -> list[float]:
        items = [str(doc or "") for doc in docs]
        if not items or not self.base_url:
            return []
        payload: dict[str, Any] = {
            "query": query,
            "documents": items,
            "top_n": int(top_n or len(items)),
        }
        if self.model:
            payload["model"] = self.model
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            print(f"[rerank] http 打分失败，跳过重排: {exc!r}")
            return []
        rows = data.get("results") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        scores = [0.0] * len(items)
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                index = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            if not 0 <= index < len(items):
                continue
            value = row.get("relevance_score", row.get("score", 0.0))
            try:
                score = float(value)
            except (TypeError, ValueError):
                score = 0.0
            scores[index] = min(1.0, max(0.0, score))
        return scores

    def healthcheck(self) -> bool:
        return bool(self.base_url)
