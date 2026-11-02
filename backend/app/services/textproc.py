from __future__ import annotations

import re
from typing import Sequence

_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")

_TERM_SCAN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]+|[A-Za-z0-9_]+"
)

_PUNCT = re.compile(r"[\s\u3000]+")


def cjk_bigrams(run: str) -> list[str]:
    return [run[i : i + 2] for i in range(len(run) - 1)]


def index_tokens(text: str) -> str:
    tokens: list[str] = []
    for run in _CJK_RUN.findall(text):
        tokens.extend(cjk_bigrams(run))
    for word in _ASCII_WORD.findall(text):
        if len(word) > 1:
            tokens.append(word.lower())
    return " ".join(tokens)


def query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for run in _TERM_SCAN.findall(query or ""):
        if _CJK_RUN.fullmatch(run):
            terms.extend(cjk_bigrams(run))
        else:
            terms.append(run.lower())
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_PUNCT.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def coverage(terms: Sequence[str], text: str) -> float:
    if not terms:
        return 0.0
    lowered = text.lower()
    hits = sum(1 for term in terms if term in lowered)
    return hits / len(terms)


def make_snippet(text: str, terms: Sequence[str], width: int = 80) -> str:
    lowered = text.lower()
    positions = [lowered.find(term.lower()) for term in terms]
    positions = [pos for pos in positions if pos >= 0]
    if not positions:
        head = text.strip()
        return head if len(head) <= width * 2 else head[: width * 2] + "…"
    anchor = min(positions)
    start = max(0, anchor - width // 2)
    end = min(len(text), anchor + width + width // 2)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet
