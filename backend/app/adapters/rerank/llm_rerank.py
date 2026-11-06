from __future__ import annotations

import asyncio
import json
import re
import statistics
from typing import Any, Sequence

from app.ports.llm import LLMProvider


_SYSTEM = (
    "You are a retrieval-result reranker. Given the user's question, score the relevance of each candidate document. "
    "Scores range from 0 to 10, may keep one decimal place, and higher means more relevant. "
    'Output only strict JSON in the form {"scores":[{"i":1,"s":8.5}]}; do not output explanations or code blocks.'
)

_PAIR_A = re.compile(r'"i"\s*:\s*(\d+)\s*,\s*"s"\s*:\s*(-?\d+(?:\.\d+)?)')
_PAIR_B = re.compile(r'"s"\s*:\s*(-?\d+(?:\.\d+)?)\s*,\s*"i"\s*:\s*(\d+)')


class LLMReranker:
    name = "llm"

    def __init__(
        self,
        llm: LLMProvider,
        timeout: float = 20.0,
        batch_size: int = 12,
        max_doc_chars: int = 600,
    ) -> None:
        self.llm = llm
        self.timeout = float(timeout or 20)
        self.batch_size = max(1, int(batch_size or 12))
        self.max_doc_chars = max(80, int(max_doc_chars or 600))

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int
    ) -> list[float]:
        items = [str(doc or "") for doc in docs]
        if not items:
            return []
        scores = await self._score_all(query, items)
        if scores is None:
            return []
        return scores

    async def _score_all(
        self, query: str, items: Sequence[str]
    ) -> list[float] | None:
        lines = []
        for position, text in enumerate(items, start=1):
            body = text.strip().replace("\n", " ")[: self.max_doc_chars]
            lines.append(f"[{position}] {body}")
        prompt = (
            f"{_SYSTEM}\n\nQuestion: {query}\n\nCandidate documents:\n"
            + "\n".join(lines)
            + f'\n\nOutput only JSON of the form {{"scores":[{{"i":1,"s":0.0}}]}}, covering 1 through {len(items)}.'
        )
        max_tokens = 12 * len(items) + 64
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(prompt, temperature=0, max_tokens=max_tokens),
                timeout=self.timeout,
            )
        except Exception as exc:
            print(f"[rerank] llm scoring failed, skipping rerank: {exc!r}")
            return None
        return _parse_scores(raw, len(items))

    def healthcheck(self) -> bool:
        try:
            return bool(self.llm.healthcheck())
        except Exception:
            return False


def _extract_rows(text: str) -> list[tuple[int, float]]:
    rows: list[tuple[int, float]] = []
    data: Any = None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
        except (TypeError, ValueError):
            data = None
    payload = data.get("scores") if isinstance(data, dict) else None
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            try:
                idx = int(row.get("i"))
                value = float(row.get("s"))
            except (TypeError, ValueError):
                continue
            rows.append((idx, value))
    if not rows:
        for match in _PAIR_A.finditer(text):
            try:
                rows.append((int(match.group(1)), float(match.group(2))))
            except (TypeError, ValueError):
                continue
        if not rows:
            for match in _PAIR_B.finditer(text):
                try:
                    rows.append((int(match.group(2)), float(match.group(1))))
                except (TypeError, ValueError):
                    continue
    return rows


def _parse_scores(raw: Any, expected: int) -> list[float] | None:
    if not isinstance(raw, str) or not raw.strip() or expected <= 0:
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    rows = _extract_rows(text)
    collected: dict[int, float] = {}
    for idx, value in rows:
        if 1 <= idx <= expected:
            collected[idx] = value
    if not collected:
        return None
    if len(collected) / expected < 0.6:
        return None
    normalized = [min(1.0, max(0.0, value / 10.0)) for value in collected.values()]
    middle = float(statistics.median(normalized))
    scores = [middle] * expected
    for idx, value in collected.items():
        scores[idx - 1] = min(1.0, max(0.0, value / 10.0))
    return scores
