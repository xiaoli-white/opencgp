from __future__ import annotations

from pydantic import BaseModel, Field

LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

VERDICT_PASS = "pass"
VERDICT_WARN = "warn"
VERDICT_FAIL = "fail"

CITATION_GAP_REPORT = "report"
CITATION_GAP_ATTACH = "attach"
CITATION_GAP_OFF = "off"
CITATION_GAP_ACTIONS = (
    CITATION_GAP_REPORT,
    CITATION_GAP_ATTACH,
    CITATION_GAP_OFF,
)


class CitationGap(BaseModel):
    paragraph: str = ""
    start: int = 0
    end: int = 0
    signals: list[str] = Field(default_factory=list)
    suggested_marker: str = ""
    reason: str = ""


class CitationCoverage(BaseModel):
    paragraphs_total: int = 0
    required_paragraphs: int = 0
    cited_paragraphs: int = 0
    coverage: float = 1.0
    missing: list[CitationGap] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    level: str = LEVEL_WARNING
    message: str = ""
    where: str = ""


class ValidationResult(BaseModel):
    name: str = ""
    passed: bool = True
    score: float = 1.0
    issues: list[ValidationIssue] = Field(default_factory=list)
    coverage: CitationCoverage | None = None
    revised_content: str | None = None

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
    citation_coverage: CitationCoverage | None = None
    revised_content: str | None = None

    def note_fragment(self) -> str:
        parts = [f"{item.name}={item.verdict()}" for item in self.results if item.name]
        return ",".join(parts)
