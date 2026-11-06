from __future__ import annotations

import asyncio
from typing import Any, Sequence

import httpx


_BACKOFFS = (0.3, 0.9)


class HTTPReranker:
    name = "http"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 20.0,
        retries: int = 2,
    ) -> None:
        self.base_url = (base_url or "").strip()
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = float(timeout or 20)
        self.retries = max(0, int(retries if retries is not None else 2))

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
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.05, self.timeout)
        attempts = self.retries + 1
        for attempt in range(attempts):
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                async with httpx.AsyncClient(timeout=remaining) as client:
                    response = await asyncio.wait_for(
                        client.post(self.base_url, headers=headers, json=payload),
                        timeout=remaining,
                    )
                    response.raise_for_status()
                    data = response.json()
                scores = _parse_response(data, len(items))
                if scores is not None:
                    return scores
                print("[rerank] incompatible http response format, skipping rerank")
            except Exception as exc:
                print(f"[rerank] http scoring failed (attempt {attempt + 1}): {exc!r}")
            if attempt >= attempts - 1:
                break
            wait = _BACKOFFS[min(attempt, len(_BACKOFFS) - 1)]
            if loop.time() + wait >= deadline:
                break
            await asyncio.sleep(wait)
        return []

    async def probe(self) -> dict[str, Any]:
        scores = await self.rerank("ping", ["ping"], 1)
        return {"ok": bool(scores), "model": self.model}

    def healthcheck(self) -> bool:
        return bool(self.base_url)


def _parse_response(data: Any, expected: int) -> list[float] | None:
    if not isinstance(data, dict) or expected <= 0:
        return None
    rows = data.get("results")
    if not isinstance(rows, list):
        rows = data.get("data")
    values: list[float] | None = None
    if isinstance(rows, list) and rows:
        collected: dict[int, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                index = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            if not 0 <= index < expected:
                continue
            value = row.get("relevance_score")
            if value is None:
                value = row.get("score")
            try:
                collected[index] = float(value)
            except (TypeError, ValueError):
                continue
        if not collected:
            return None
        if len(collected) == expected:
            values = [collected[index] for index in range(expected)]
        else:
            middle = _median(list(collected.values()))
            values = [collected.get(index, middle) for index in range(expected)]
    else:
        direct = data.get("scores")
        if not isinstance(direct, list) or not direct:
            return None
        parsed: list[float] = []
        for item in direct:
            try:
                parsed.append(float(item))
            except (TypeError, ValueError):
                return None
        if len(parsed) < expected:
            middle = _median(parsed)
            parsed.extend([middle] * (expected - len(parsed)))
        values = parsed[:expected]
    peak = max(abs(value) for value in values)
    if peak > 1.0:
        values = [value / 10.0 for value in values]
    return [min(1.0, max(0.0, value)) for value in values]


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
