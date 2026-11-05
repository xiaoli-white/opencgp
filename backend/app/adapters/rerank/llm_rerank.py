from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Sequence

from app.ports.llm import LLMProvider


_SYSTEM = (
    "你是一个检索结果重排器。根据用户问题，为每条候选文档的相关性打分。"
    "分数范围 0 到 10，可保留一位小数，越相关分越高。"
    '只输出严格 JSON，格式为 {"scores":[{"i":1,"s":8.5}]}，不要输出解释或代码块。'
)


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
        scores = [0.0] * len(items)
        limit = len(items) if top_n is None or top_n <= 0 else min(len(items), int(top_n))
        index = 0
        while index < limit:
            batch = items[index : index + self.batch_size]
            batch_scores = await self._score_batch(query, batch)
            if batch_scores is None:
                return []
            for offset, value in enumerate(batch_scores):
                scores[index + offset] = value
            index += len(batch)
        return scores

    async def _score_batch(self, query: str, batch: Sequence[str]) -> list[float] | None:
        lines = []
        for position, text in enumerate(batch, start=1):
            body = text.strip().replace("\n", " ")[: self.max_doc_chars]
            lines.append(f"[{position}] {body}")
        prompt = (
            f"{_SYSTEM}\n\n问题：{query}\n\n候选文档：\n"
            + "\n".join(lines)
            + f'\n\n请只输出 {{"scores":[{{"i":1,"s":0.0}}]}} 形式的 JSON，覆盖 1 到 {len(batch)}。'
        )
        try:
            raw = await asyncio.wait_for(
                self.llm.complete(prompt, temperature=0, max_tokens=512),
                timeout=self.timeout,
            )
        except Exception as exc:
            print(f"[rerank] llm 打分失败，跳过重排: {exc!r}")
            return None
        parsed = _parse_scores(raw, len(batch))
        if parsed is None:
            return None
        return parsed

    def healthcheck(self) -> bool:
        try:
            return bool(self.llm.healthcheck())
        except Exception:
            return False


def _parse_scores(raw: Any, expected: int) -> list[float] | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return None
    rows = data.get("scores") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    scores = [0.0] * expected
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("i"))
            value = float(row.get("s"))
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= expected:
            scores[idx - 1] = min(1.0, max(0.0, value / 10.0))
    return scores
