from __future__ import annotations

import math
from typing import Sequence

from app.services.textproc import coverage

COVERAGE_FLOOR = 0.15
LIKE_MATCH_SCORE = 0.75
DISTINCTIVE_MIN_LEN = 4


def absolute_score(raw_rank: float, term_coverage: float) -> float:
    if raw_rank <= 0 or term_coverage <= 0:
        return 0.0
    gate = (term_coverage - COVERAGE_FLOOR) / (1.0 - COVERAGE_FLOOR)
    if gate <= 0:
        return 0.0
    return min(1.0, gate) * (0.6 + 0.4 * (raw_rank / (1.0 + raw_rank)))


def name_boost(terms: Sequence[str], source_name: str) -> float:
    if not terms or not source_name:
        return 1.0
    hit = sum(1 for term in terms if term and term in source_name)
    if not hit:
        return 1.0
    ratio = hit / max(1, len(terms))
    return 1.0 + 0.45 * min(1.0, ratio * 2)


def distinctive_factor(terms: Sequence[str], text: str) -> float:
    distinctive = [
        term for term in terms if len(term) >= DISTINCTIVE_MIN_LEN or term.isascii()
    ]
    if not distinctive:
        return 1.0
    lowered = (text or "").lower()
    matched = sum(1 for term in distinctive if term in lowered)
    if matched == 0:
        return 0.3
    if matched < len(distinctive):
        return 0.7
    return 1.0


def length_penalty(text: str) -> float:
    size = len(text or "")
    if size < 80:
        return 0.8
    if size > 4000:
        return 0.95
    return 1.0


def matched_terms(terms: Sequence[str], text: str) -> int:
    if not terms:
        return 0
    lowered = (text or "").lower()
    return sum(1 for term in terms if term and term in lowered)


def term_score(
    terms: Sequence[str],
    text: str,
    source_name: str,
    raw_rank: float,
) -> float:
    base = absolute_score(raw_rank, coverage(terms, text))
    if base <= 0.0:
        return 0.0
    boosted = (
        base
        * name_boost(terms, source_name)
        * length_penalty(text)
        * distinctive_factor(terms, text)
    )
    return min(1.0, boosted)


def clip01(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    return {key: min(1.0, max(0.0, value)) for key, value in scores.items()}


def blend(
    keyword_scores: dict[str, float],
    vector_scores: dict[str, float],
    keyword_weight: float,
) -> dict[str, float]:
    weight = keyword_weight
    merged: dict[str, float] = {}
    for chunk_id in set(keyword_scores) | set(vector_scores):
        merged[chunk_id] = weight * keyword_scores.get(chunk_id, 0.0) + (
            1.0 - weight
        ) * vector_scores.get(chunk_id, 0.0)
    return merged


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def select_top(
    ranked: Sequence[tuple[str, float]],
    covs: dict[str, float],
    top_k: int,
    min_relative_score: float,
    min_relative_coverage: float,
) -> list[tuple[str, float]]:
    if not ranked or top_k <= 0:
        return []
    best_score = ranked[0][1]
    best_cov = max(covs.values()) if covs else 0.0
    kept: list[tuple[str, float]] = [ranked[0]]
    for chunk_id, score in ranked[1:]:
        if len(kept) >= top_k:
            break
        if best_score > 0 and score < best_score * min_relative_score:
            continue
        if best_cov > 0 and covs.get(chunk_id, 0.0) < best_cov * min_relative_coverage:
            continue
        kept.append((chunk_id, score))
    return kept


def rank_with_coverage(
    scores: dict[str, float],
    texts: dict[str, str],
    terms: Sequence[str],
) -> tuple[list[tuple[str, float]], dict[str, float]]:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    covs = {chunk_id: coverage(terms, texts.get(chunk_id, "")) for chunk_id, _ in ranked}
    return ranked, covs
