from pydantic import BaseModel, Field
from app.domain.enums import FitDimension, Recommendation, RequirementPriority, RequirementVerdict, RiskSide, SeniorityMatch

class NoulResult(BaseModel):
    probability: float
    confidence: float

class ChoiceResult(BaseModel):
    choice: str
    probabilities: dict[str, float]
    confidence: float

class ScoreResult(BaseModel):
    score: float
    normalized: float
    probabilities: dict[str, float]
    legend: dict[str, str]
    confidence: float

    @property
    def most_likely_level(self) -> str:
        if not self.probabilities:
            return ""
        best_key = max(self.probabilities, key=self.probabilities.__getitem__)
        return self.legend.get(best_key, best_key)

class JevEvaluation(BaseModel):
    nouls: dict[str, NoulResult] = Field(default_factory=dict)
    choices: dict[str, ChoiceResult] = Field(default_factory=dict)
    scores: dict[str, ScoreResult] = Field(default_factory=dict)

    def merge(self, other: "JevEvaluation") -> "JevEvaluation":
        return JevEvaluation(
            nouls={**self.nouls, **other.nouls},
            choices={**self.choices, **other.choices},
            scores={**self.scores, **other.scores},
        )

class RequirementAssessment(BaseModel):
    requirement_id: str
    text: str
    priority: RequirementPriority
    met_probability: float
    confidence: float
    verdict: RequirementVerdict
    low_confidence: bool

class DimensionAssessment(BaseModel):
    dimension: FitDimension
    score: float
    raw_score: float
    level_label: str
    confidence: float
    low_confidence: bool

class SeniorityAssessment(BaseModel):
    match: SeniorityMatch
    probabilities: dict[str, float]
    confidence: float
    years_required: float | None = None
    years_requirement_probability: float | None = None
    low_confidence: bool

class RedFlag(BaseModel):
    code: str
    side: RiskSide
    description: str
    probability: float
    severity: float
    triggered: bool

class AtsAlignment(BaseModel):
    score: float
    keyword_coverage: float
    terminology_mirroring: float
    priority_alignment: float
    confidence: float
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)

class FitValidationBundle(BaseModel):
    requirements: list[RequirementAssessment]
    dimensions: list[DimensionAssessment]
    seniority: SeniorityAssessment
    red_flags: list[RedFlag]
    ats_original: AtsAlignment

class FitAnalysis(BaseModel):
    overall_score: float
    recommendation: Recommendation
    recommendation_reasons: list[str]
    must_have_coverage: float | None
    nice_to_have_coverage: float | None
    component_scores: dict[str, float]
    requirements: list[RequirementAssessment]
    dimensions: list[DimensionAssessment]
    seniority: SeniorityAssessment
    red_flags: list[RedFlag]
    ats_original: AtsAlignment
    strengths: list[str]
    gaps: list[str]
    low_confidence_items: list[str]

    def missing_requirement_texts(self) -> list[str]:
        return [item.text for item in self.requirements if item.verdict == RequirementVerdict.MISSING]

class ClaimCheck(BaseModel):
    claim_id: str
    text: str
    section: str
    support_probability: float
    supported: bool

class QualityCheck(BaseModel):
    name: str
    passed: bool
    value: float
    detail: str

class CvQualityReport(BaseModel):
    checks: list[QualityCheck]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def failing_checks(self) -> list[QualityCheck]:
        return [check for check in self.checks if not check.passed]

class CvValidationReport(BaseModel):
    claim_checks: list[ClaimCheck]
    ats_original: AtsAlignment
    ats_tailored: AtsAlignment
    ats_improved: bool
    quality: CvQualityReport

    @property
    def unsupported_claims(self) -> list[ClaimCheck]:
        return [check for check in self.claim_checks if not check.supported]

    @property
    def faithfulness_passed(self) -> bool:
        return not self.unsupported_claims

    @property
    def ready_to_finalize(self) -> bool:
        return self.faithfulness_passed and self.ats_improved

    def unresolved_issues(self) -> list[str]:
        issues = [f"Unsupported claim: {check.text}" for check in self.unsupported_claims]
        if not self.ats_improved:
            issues.append(
                f"ATS alignment did not improve (original {self.ats_original.score:.2f}, tailored {self.ats_tailored.score:.2f})."
            )
        issues.extend(f"Quality check failed: {check.name} ({check.detail})" for check in self.quality.failing_checks())
        return issues
