from app.config.settings import DimensionWeights, FitWeights, RecommendationThresholds
from app.domain.enums import FitDimension, Recommendation, RequirementPriority, RequirementVerdict, RiskSide, SeniorityMatch
from app.domain.validation_models import AtsAlignment, DimensionAssessment, FitValidationBundle, RedFlag, RequirementAssessment, SeniorityAssessment
from app.validators.fit_score_aggregator import FitScoreAggregator

def requirement(identifier: str, priority: RequirementPriority, verdict: RequirementVerdict) -> RequirementAssessment:
    probability = {RequirementVerdict.MET: 0.9, RequirementVerdict.PARTIAL: 0.5, RequirementVerdict.MISSING: 0.1}[verdict]
    return RequirementAssessment(requirement_id=identifier, text=f"Requirement {identifier}", priority=priority, met_probability=probability, confidence=0.8, verdict=verdict, low_confidence=False)

def bundle(verdicts: list[RequirementVerdict], dimension_score: float, ats: float, flags: list[RedFlag] | None = None) -> FitValidationBundle:
    requirements = [requirement(f"M{index}", RequirementPriority.MUST_HAVE, verdict) for index, verdict in enumerate(verdicts, start=1)]
    requirements.append(requirement("N1", RequirementPriority.NICE_TO_HAVE, RequirementVerdict.MET))
    dimensions = [DimensionAssessment(dimension=dimension, score=dimension_score, raw_score=dimension_score * 4, level_label="level", confidence=0.8, low_confidence=False) for dimension in FitDimension]
    seniority = SeniorityAssessment(match=SeniorityMatch.MATCHES, probabilities={"below": 0.0, "matches": 1.0, "above": 0.0}, confidence=0.9, low_confidence=False)
    alignment = AtsAlignment(score=ats, keyword_coverage=ats, terminology_mirroring=ats, priority_alignment=ats, confidence=0.8)
    return FitValidationBundle(requirements=requirements, dimensions=dimensions, seniority=seniority, red_flags=flags or [], ats_original=alignment)

def aggregator() -> FitScoreAggregator:
    return FitScoreAggregator(FitWeights(), DimensionWeights(), RecommendationThresholds())

def test_strong_candidate_with_aligned_cv_should_apply() -> None:
    analysis = aggregator().aggregate(bundle([RequirementVerdict.MET] * 4, 0.9, 0.8))
    assert analysis.recommendation == Recommendation.APPLY
    assert analysis.overall_score > 85
    assert analysis.must_have_coverage == 1.0
    assert not analysis.gaps

def test_strong_candidate_with_buried_evidence_should_tailor() -> None:
    analysis = aggregator().aggregate(bundle([RequirementVerdict.MET] * 4, 0.9, 0.3))
    assert analysis.recommendation == Recommendation.APPLY_AFTER_TAILORING
    assert any("ATS alignment" in reason for reason in analysis.recommendation_reasons)

def test_missing_must_haves_should_skip() -> None:
    analysis = aggregator().aggregate(bundle([RequirementVerdict.MISSING, RequirementVerdict.MISSING, RequirementVerdict.PARTIAL, RequirementVerdict.MET], 0.5, 0.5))
    assert analysis.recommendation == Recommendation.SKIP
    assert analysis.must_have_coverage == 0.375
    assert sum(1 for gap in analysis.gaps if gap.startswith("Missing must-have")) == 2

def test_scam_flag_forces_skip_and_penalizes_score() -> None:
    scam = RedFlag(code="suspicious_posting", side=RiskSide.JOB, description="scam", probability=0.95, severity=1.0, triggered=True)
    clean = aggregator().aggregate(bundle([RequirementVerdict.MET] * 4, 0.9, 0.8))
    flagged = aggregator().aggregate(bundle([RequirementVerdict.MET] * 4, 0.9, 0.8, [scam]))
    assert flagged.recommendation == Recommendation.SKIP
    assert flagged.overall_score < clean.overall_score
    assert flagged.component_scores["red_flag_penalty"] > 0

def test_must_have_weight_dominates_nice_to_have() -> None:
    weights = FitWeights(must_have_requirements=0.9, nice_to_have_requirements=0.02, fit_dimensions=0.02, seniority=0.02, ats_alignment=0.04)
    custom = FitScoreAggregator(weights, DimensionWeights(), RecommendationThresholds())
    analysis = custom.aggregate(bundle([RequirementVerdict.MISSING] * 4, 1.0, 1.0))
    assert analysis.overall_score < 15
