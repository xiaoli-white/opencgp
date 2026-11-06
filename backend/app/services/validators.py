from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.validation import (
    LEVEL_ERROR,
    LEVEL_WARNING,
    ValidationIssue,
    ValidationReport,
    ValidationResult,
    ValidationSummary,
)
from app.models.work_profile import ProfileSpec

CITATION_PARAGRAPH_MIN = 30
CITATION_WARN_RATIO = 0.6
CITATION_ERROR_RATIO = 0.3
LENGTH_LOW_FACTOR = 0.5
LENGTH_HIGH_FACTOR = 2.0
MARKER_PATTERN = re.compile(r"\[E\d+\]")
HEADING2_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
CJK_RUN = re.compile(r"[\u4e00-\u9fa5]{2,4}")
BOOK_TITLE = re.compile(r"《([^》]{1,24})》")
SENTENCE_SPLIT = re.compile(r"[。！？；\n]")
CONTINUITY_STOPWORDS = {
    "\u4e00\u4e2a", "\u6211\u4eec", "\u4f60\u4eec", "\u4ed6\u4eec", "\u81ea\u5df1", "\u8fd9\u4e2a", "\u90a3\u4e2a", "\u4ec0\u4e48", "\u56e0\u4e3a", "\u6240\u4ee5",
    "\u4f46\u662f", "\u800c\u4e14", "\u5982\u679c", "\u5c31\u662f", "\u4e0d\u662f", "\u6ca1\u6709", "\u53ef\u4ee5", "\u9700\u8981", "\u5df2\u7ecf", "\u8fd8\u662f",
    "\u77e5\u9053", "\u89c9\u5f97", "\u65f6\u5019", "\u73b0\u5728", "\u7136\u540e", "\u4e8e\u662f", "\u8fd9\u6837", "\u90a3\u6837", "\u4e00\u6837", "\u8d77\u6765",
    "\u51fa\u6765", "\u4e0b\u6765", "\u8fc7\u53bb", "\u56de\u6765", "\u4e1c\u897f", "\u4e8b\u60c5", "\u5730\u65b9", "\u95ee\u9898", "\u6837\u5b50", "\u5fc3\u91cc",
}


@dataclass
class ValidationContext:
    spec: ProfileSpec
    content: str
    extra: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Validator(Protocol):
    name: str

    async def validate(self, ctx: ValidationContext) -> ValidationResult: ...


def text_length(content: str) -> int:
    return len(re.sub(r"\s+", "", content or ""))


def paragraphs(content: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", content or "")
    result: list[str] = []
    for block in blocks:
        text = block.strip()
        if not text:
            continue
        if text.startswith("#"):
            continue
        if text.startswith(">"):
            text = "\n".join(
                line.lstrip("> ").strip() for line in text.splitlines()
            ).strip()
        if text:
            result.append(text)
    return result


class CitationValidator:
    name = "citation"

    async def validate(self, ctx: ValidationContext) -> ValidationResult:
        policy = (ctx.spec.grounding.citation_policy or "").strip()
        if policy != "required":
            return ValidationResult(name=self.name, passed=True, score=1.0, issues=[])
        blocks = paragraphs(ctx.content)
        considered = [item for item in blocks if text_length(item) >= CITATION_PARAGRAPH_MIN]
        if not considered:
            return ValidationResult(name=self.name, passed=True, score=1.0, issues=[])
        cited = sum(1 for item in considered if MARKER_PATTERN.search(item))
        ratio = cited / len(considered)
        issues: list[ValidationIssue] = []
        level = ""
        if ratio < CITATION_ERROR_RATIO:
            level = LEVEL_ERROR
        elif ratio < CITATION_WARN_RATIO:
            level = LEVEL_WARNING
        if level:
            issues.append(
                ValidationIssue(
                    level=level,
                    message=(
                        f"Share of paragraphs with evidence markers: {ratio:.0%} "
                        f"({cited}/{len(considered)}), below the recommended threshold of {CITATION_WARN_RATIO:.0%}"
                    ),
                    where="content",
                )
            )
        return ValidationResult(
            name=self.name,
            passed=level != LEVEL_ERROR,
            score=round(ratio, 4),
            issues=issues,
        )


class LengthValidator:
    name = "length"

    async def validate(self, ctx: ValidationContext) -> ValidationResult:
        words = max(1, int(ctx.spec.unit.default_words or 900))
        low = int(words * LENGTH_LOW_FACTOR)
        high = int(words * LENGTH_HIGH_FACTOR)
        actual = text_length(ctx.content)
        issues: list[ValidationIssue] = []
        if actual < low or actual > high:
            issues.append(
                ValidationIssue(
                    level=LEVEL_WARNING,
                    message=(
                        f"Body length is {actual} characters, outside the configured range of {low}-{high} characters "
                        f"(configured target: {words} characters)"
                    ),
                    where="content",
                )
            )
        score = 1.0
        if words and actual:
            score = round(min(1.0, actual / float(words)), 4)
        return ValidationResult(
            name=self.name,
            passed=not issues,
            score=score,
            issues=issues,
        )


class StructureValidator:
    name = "structure"

    async def validate(self, ctx: ValidationContext) -> ValidationResult:
        bounds = list(ctx.spec.structure.sections_per_unit or [2, 5])
        low = bounds[0] if bounds else 2
        headings = HEADING2_PATTERN.findall(ctx.content or "")
        count = len(headings)
        issues: list[ValidationIssue] = []
        if count < low:
            issues.append(
                ValidationIssue(
                    level=LEVEL_WARNING,
                    message=f"Level-2 heading count is {count}, below the configured minimum of {low}",
                    where="content",
                )
            )
        score = round(min(1.0, count / float(low)), 4) if low else 1.0
        return ValidationResult(
            name=self.name,
            passed=not issues,
            score=score,
            issues=issues,
        )


def _known_names(extra: dict[str, Any]) -> set[str]:
    raw = extra.get("setting_book") or extra.get("known_names") or []
    names: set[str] = set()
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, dict):
        raw = list(raw.keys())
    for item in raw if isinstance(raw, (list, tuple, set)) else []:
        text = str(item).strip()
        if text:
            names.add(text)
    return names


def _proper_names(content: str) -> list[str]:
    names = [item.strip() for item in BOOK_TITLE.findall(content or "")]
    counter: Counter[str] = Counter()
    for sentence in SENTENCE_SPLIT.split(content or ""):
        for run in CJK_RUN.findall(sentence):
            if run in CONTINUITY_STOPWORDS:
                continue
            counter[run] += 1
    repeated = [name for name, count in counter.items() if count >= 2]
    return sorted({item for item in names if item} | set(repeated))


class ContinuityValidator:
    name = "continuity"

    async def validate(self, ctx: ValidationContext) -> ValidationResult:
        issues: list[ValidationIssue] = []
        known = _known_names(ctx.extra)
        titles = [item.strip() for item in BOOK_TITLE.findall(ctx.content or "") if item.strip()]
        if known:
            unknown = sorted({item for item in titles if item not in known})
            if unknown:
                issues.append(
                    ValidationIssue(
                        level=LEVEL_WARNING,
                        message="Proper names appear that are not registered in the setting book: " + ", ".join(unknown[:6]),
                        where="content",
                    )
                )
        else:
            names = _proper_names(ctx.content)
            conflicts: list[str] = []
            for left in names:
                for right in names:
                    if left == right or len(left) >= len(right):
                        continue
                    if right.startswith(left) and len(right) - len(left) <= 1:
                        conflicts.append(f"{left} / {right}")
            if conflicts:
                issues.append(
                    ValidationIssue(
                        level=LEVEL_WARNING,
                        message="Inconsistent proper-name variants detected: " + ", ".join(conflicts[:6]),
                        where="content",
                    )
                )
        return ValidationResult(
            name=self.name,
            passed=not issues,
            score=1.0 if not issues else 0.7,
            issues=issues,
        )


DEFAULT_VALIDATORS: tuple[Validator, ...] = (
    CitationValidator(),
    LengthValidator(),
    StructureValidator(),
    ContinuityValidator(),
)


class ValidatorRunner:
    def __init__(self, validators: Sequence[Validator] | None = None) -> None:
        source = list(validators or DEFAULT_VALIDATORS)
        self.registry: dict[str, Validator] = {
            str(item.name).strip().lower(): item for item in source
        }

    async def run(
        self,
        spec: ProfileSpec,
        content: str,
        extra: dict[str, Any] | None = None,
    ) -> ValidationReport:
        names = list((spec.validation.validators if spec else []) or [])
        context = ValidationContext(spec=spec, content=content or "", extra=dict(extra or {}))
        results: list[ValidationResult] = []
        for raw in names:
            key = str(raw or "").strip().lower()
            if not key:
                continue
            validator = self.registry.get(key)
            if validator is None:
                results.append(
                    ValidationResult(
                        name=key,
                        passed=True,
                        score=1.0,
                        issues=[
                            ValidationIssue(
                                level=LEVEL_WARNING,
                                message=f"unknown validator {key}; ignored",
                                where="validation.validators",
                            )
                        ],
                    )
                )
                continue
            try:
                results.append(await validator.validate(context))
            except Exception as exc:
                results.append(
                    ValidationResult(
                        name=key,
                        passed=False,
                        score=0.0,
                        issues=[
                            ValidationIssue(
                                level=LEVEL_ERROR,
                                message=f"validator execution failed: {str(exc)[:160]}",
                                where="validation",
                            )
                        ],
                    )
                )
        warnings = sum(
            1
            for item in results
            for issue in item.issues
            if issue.level == LEVEL_WARNING
        )
        errors = sum(
            1 for item in results for issue in item.issues if issue.level == LEVEL_ERROR
        )
        passed = sum(1 for item in results if item.passed and not item.issues)
        return ValidationReport(
            results=results,
            summary=ValidationSummary(passed=passed, warnings=warnings, errors=errors),
        )
