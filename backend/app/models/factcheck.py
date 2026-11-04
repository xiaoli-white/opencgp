from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.citation import Citation

VERDICT_SUPPORTED = "supported"
VERDICT_UNSURE = "unsure"
VERDICT_UNSUPPORTED = "unsupported"
VERDICTS = (VERDICT_SUPPORTED, VERDICT_UNSURE, VERDICT_UNSUPPORTED)

SUPPORTED_THRESHOLD = 0.5
UNSURE_THRESHOLD = 0.2

VERDICT_LABELS = {
    VERDICT_SUPPORTED: "有证据支撑",
    VERDICT_UNSURE: "证据不足需核实",
    VERDICT_UNSUPPORTED: "无证据支撑",
}


class CheckResult(BaseModel):
    claim: str
    verdict: str = VERDICT_UNSUPPORTED
    evidence: list[Citation] = Field(default_factory=list)
    score: float = 0.0
    source: str = "retrieval"


class FactCheckReport(BaseModel):
    lesson_id: str = ""
    count: int = 0
    supported: int = 0
    unsure: int = 0
    unsupported: int = 0
    results: list[CheckResult] = Field(default_factory=list)

    @classmethod
    def build(cls, results: list[CheckResult], lesson_id: str = "") -> "FactCheckReport":
        supported = sum(1 for item in results if item.verdict == VERDICT_SUPPORTED)
        unsure = sum(1 for item in results if item.verdict == VERDICT_UNSURE)
        unsupported = sum(1 for item in results if item.verdict == VERDICT_UNSUPPORTED)
        return cls(
            lesson_id=lesson_id,
            count=len(results),
            supported=supported,
            unsure=unsure,
            unsupported=unsupported,
            results=results,
        )
