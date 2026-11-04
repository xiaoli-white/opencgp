from __future__ import annotations

from pydantic import BaseModel, Field

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

VERDICT_PASS = "pass"
VERDICT_WARN = "warn"
VERDICT_FAIL = "fail"


class ValidationIssue(BaseModel):
    level: str = LEVEL_WARNING
    message: str = ""
    where: str = ""


class ValidationResult(BaseModel):
    name: str = ""
    passed: bool = True
    score: float = 1.0
    issues: list[ValidationIssue] = Field(default_factory=list)

    def verdict(self) -> str:
        if not self.passed:
            return VERDICT_FAIL
        if any(issue.level == LEVEL_WARNING for issue in self.issues):
            return VERDICT_WARN
        return VERDICT_PASS


class ValidationSummary(BaseModel):
    passed: int = 0
    warnings: int = 0
    errors: int = 0


class ValidationReport(BaseModel):
    results: list[ValidationResult] = Field(default_factory=list)
    summary: ValidationSummary = Field(default_factory=ValidationSummary)

    def note_fragment(self) -> str:
        parts = [f"{item.name}={item.verdict()}" for item in self.results if item.name]
        return ",".join(parts)
