from __future__ import annotations

import asyncio
import math
import statistics
import time
from typing import Any, Sequence

import httpx


_BACKOFFS = (0.3, 0.9)
_NORMALIZE_MODES = ("auto", "sigmoid", "minmax", "none")


class RemoteRerank:
    name = "remote"

    def __init__(
        self,
        format: str = "cohere",
        base_url: str = "",
        model: str = "",
        api_key: str = "",
        timeout: float = 20.0,
        retries: int = 2,
        batch: int = 100,
        chars: int = 2000,
        normalize: str = "auto",
        raw_scores: bool = False,
    ) -> None:
        self.format = (format or "cohere").strip().lower()
        if self.format not in ("cohere", "tei", "generic", "dashscope"):
            self.format = "cohere"
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()
        self.api_key = api_key or ""
        self.timeout = max(0.1, float(timeout or 20))
        self.retries = max(0, int(retries if retries is not None else 2))
        self.batch = max(1, int(batch or 1))
        self.chars = max(1, int(chars or 2000))
        self.normalize = (normalize or "auto").strip().lower()
        if self.normalize not in _NORMALIZE_MODES:
            self.normalize = "auto"
        self.raw_scores = bool(raw_scores)
        self._health_at = 0.0
        self._health_ok = False

    def _documents(self, docs: Sequence[str]) -> list[str]:
        return [str(doc or "")[: self.chars] for doc in docs]

    def _payload(self, query: str, documents: Sequence[str]) -> dict[str, Any]:
        if self.format == "dashscope":
            return {
                "model": self.model,
                "input": {"query": query, "documents": list(documents)},
                "parameters": {"top_n": len(documents), "return_documents": False},
            }
        if self.format == "tei":
            return {
                "query": query,
                "texts": list(documents),
                "truncate": True,
                "raw_scores": self.raw_scores,
            }
        return {
            "model": self.model,
            "query": query,
            "documents": list(documents),
            "top_n": len(documents),
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int
    ) -> list[float]:
        items = self._documents(docs)
        total = len(items)
        if total == 0 or not self.base_url:
            return []
        size = max(1, min(self.batch, total))
        spans: list[tuple[int, list[str]]] = []
        for start in range(0, total, size):
            spans.append((start, items[start : start + size]))
        collected: dict[int, float] = {}
        successful: list[float] = []
        success_batches = 0
        normalize = self.normalize
        if self.format == "tei" and self.raw_scores and normalize == "auto":
            normalize = "sigmoid"
        for start, batch_docs in spans:
            parsed = await self._post_with_retry(query, batch_docs)
            if parsed is None:
                continue
            success_batches += 1
            filled = _fill_missing(parsed, len(batch_docs))
            values = _normalize_scores(filled, normalize)
            for offset, value in enumerate(values):
                collected[start + offset] = value
                successful.append(value)
        if success_batches == 0:
            return []
        middle = float(statistics.median(successful)) if successful else 0.0
        return [collected.get(index, middle) for index in range(total)]

    async def _post_with_retry(
        self,
        query: str,
        documents: Sequence[str],
        timeout: float | None = None,
        retries: int | None = None,
    ) -> dict[int, float] | None:
        payload = self._payload(query, documents)
        headers = self._headers()
        limit = max(0.1, float(timeout if timeout is not None else self.timeout))
        attempts = int(retries if retries is not None else self.retries) + 1
        attempts = max(1, attempts)
        for attempt in range(attempts):
            retryable = False
            try:
                async with httpx.AsyncClient(timeout=limit) as client:
                    response = await asyncio.wait_for(
                        client.post(self.base_url, headers=headers, json=payload),
                        timeout=limit,
                    )
                status = response.status_code
                if status == 429 or status >= 500:
                    retryable = True
                elif status >= 400:
                    return None
                else:
                    data = response.json()
                    return _parse_response(data, len(documents), self.format)
            except (asyncio.TimeoutError, httpx.TransportError) as exc:
                retryable = True
                print(f"[rerank] {self.format} 请求失败（第 {attempt + 1} 次）: {exc!r}")
            except Exception as exc:
                print(f"[rerank] {self.format} 响应解析失败: {exc!r}")
                return None
            if not retryable or attempt >= attempts - 1:
                return None
            await asyncio.sleep(_BACKOFFS[min(attempt, len(_BACKOFFS) - 1)])
        return None

    async def probe(self) -> dict[str, Any]:
        parsed = await self._post_with_retry("ping", ["ping"], timeout=3.0, retries=0)
        return {"ok": parsed is not None, "model": self.model}

    def healthcheck(self) -> bool:
        now = time.time()
        if now - self._health_at < 60.0:
            return self._health_ok
        ok = False
        if self.base_url:
            try:
                with httpx.Client(timeout=3.0) as client:
                    response = client.post(
                        self.base_url,
                        headers=self._headers(),
                        json=self._payload("ping", ["ping"]),
                    )
                if response.status_code < 400:
                    parsed = _parse_response(response.json(), 1, self.format)
                    ok = parsed is not None
            except Exception:
                ok = False
        self._health_at = now
        self._health_ok = ok
        return ok


def _parse_response(data: Any, expected: int, fmt: str) -> dict[int, float] | None:
    if expected <= 0:
        return None
    rows: Any = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if fmt == "dashscope":
            output = data.get("output")
            if isinstance(output, dict):
                rows = output.get("results")
        if not isinstance(rows, list):
            rows = data.get("results")
        if not isinstance(rows, list):
            rows = data.get("data")
        if not isinstance(rows, list) and isinstance(data.get("scores"), list):
            values = data.get("scores")
            parsed: dict[int, float] = {}
            for index, value in enumerate(values):
                if index >= expected:
                    break
                number = _number(value)
                if number is not None:
                    parsed[index] = number
            return parsed or None
    if not isinstance(rows, list) or not rows:
        return None
    parsed: dict[int, float] = {}
    for position, row in enumerate(rows):
        if isinstance(row, dict):
            raw_index = row.get("index", position)
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if not 0 <= index < expected:
                continue
            value = row.get("relevance_score")
            if value is None:
                value = row.get("score")
            number = _number(value)
            if number is not None:
                parsed[index] = number
        else:
            number = _number(row)
            if number is not None and position < expected:
                parsed[position] = number
    return parsed or None


def _fill_missing(parsed: dict[int, float], expected: int) -> list[float]:
    if len(parsed) >= expected:
        return [parsed[index] for index in range(expected)]
    middle = float(statistics.median(parsed.values())) if parsed else 0.0
    return [parsed.get(index, middle) for index in range(expected)]


def _normalize_scores(values: Sequence[float], mode: str) -> list[float]:
    numbers = [float(value) for value in values]
    if not numbers:
        return []
    chosen = (mode or "auto").strip().lower()
    if chosen == "sigmoid":
        return [_clip(_sigmoid(value)) for value in numbers]
    if chosen == "minmax":
        low = min(numbers)
        high = max(numbers)
        if high - low <= 1e-12:
            return [0.5 for _ in numbers]
        return [_clip((value - low) / (high - low)) for value in numbers]
    if chosen == "none":
        return [_clip(value) for value in numbers]
    if any(value < 0.0 for value in numbers) or max(numbers) > 1.0:
        return [_clip(_sigmoid(value)) for value in numbers]
    return [_clip(value) for value in numbers]


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -60.0))
    return z / (1.0 + z)


def _clip(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
