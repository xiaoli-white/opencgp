from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation

VERDICT_SUPPORTED = "supported"
VERDICT_UNSURE = "unsure"
VERDICT_UNSUPPORTED = "unsupported"
VERDICTS = (VERDICT_SUPPORTED, VERDICT_UNSURE, VERDICT_UNSUPPORTED)

SUPPORTED_THRESHOLD = 0.45
UNSURE_THRESHOLD = 0.15

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
    llm_verdict: str = ""
    llm_reason: str = ""


class FactCheckReport(BaseModel):
    unit_id: str = ""
    count: int = 0
    supported: int = 0
    unsure: int = 0
    unsupported: int = 0
    results: list[CheckResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    retrieval: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(
        cls,
        results: list[CheckResult],
        unit_id: str = "",
        retrieval: dict[str, Any] | None = None,
    ) -> "FactCheckReport":
        supported = sum(1 for item in results if item.verdict == VERDICT_SUPPORTED)
        unsure = sum(1 for item in results if item.verdict == VERDICT_UNSURE)
        unsupported = sum(1 for item in results if item.verdict == VERDICT_UNSUPPORTED)
        payload = dict(retrieval or {})
        return cls(
            unit_id=unit_id,
            count=len(results),
            supported=supported,
            unsure=unsure,
            unsupported=unsupported,
            results=results,
            warnings=list(payload.get("warnings") or []),
            retrieval=payload,
        )
