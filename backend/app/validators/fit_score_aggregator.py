from app.config.settings import DimensionWeights, FitWeights, RecommendationThresholds
from app.domain.enums import FitDimension, Recommendation, RequirementPriority, RequirementVerdict, SeniorityMatch
from app.domain.validation_models import FitAnalysis, FitValidationBundle, RedFlag, RequirementAssessment, SeniorityAssessment
from app.validators.red_flag_validator import RedFlagValidator

class FitScoreAggregator:
    VERDICT_CREDIT = {RequirementVerdict.MET: 1.0, RequirementVerdict.PARTIAL: 0.5, RequirementVerdict.MISSING: 0.0}
    SENIORITY_CREDIT = {SeniorityMatch.BELOW.value: 0.3, SeniorityMatch.MATCHES.value: 1.0, SeniorityMatch.ABOVE.value: 0.75}
    YEARS_SHARE = 0.4
    STRONG_DIMENSION = 0.75
    WEAK_DIMENSION = 0.45

    def __init__(self, fit_weights: FitWeights, dimension_weights: DimensionWeights, thresholds: RecommendationThresholds) -> None:
        self._fit_weights = fit_weights
        self._dimension_weights = dimension_weights
        self._thresholds = thresholds

    def aggregate(self, bundle: FitValidationBundle) -> FitAnalysis:
        must_have = self._coverage(bundle.requirements, RequirementPriority.MUST_HAVE)
        nice_to_have = self._coverage(bundle.requirements, RequirementPriority.NICE_TO_HAVE)
        components = {
            "must_have_requirements": must_have,
            "nice_to_have_requirements": nice_to_have,
            "fit_dimensions": self._dimension_score(bundle),
            "seniority": self._seniority_score(bundle.seniority),
            "ats_alignment": bundle.ats_original.score,
        }
        base_score = self._weighted_average(components)
        penalty = self._red_flag_penalty(bundle.red_flags)
        overall = round(max(0.0, min(1.0, base_score - penalty)) * 100, 1)
        recommendation, reasons = self._recommend(overall, must_have, bundle)
        return FitAnalysis(
            overall_score=overall,
            recommendation=recommendation,
            recommendation_reasons=reasons,
            must_have_coverage=must_have,
            nice_to_have_coverage=nice_to_have,
            component_scores={key: round(value, 4) for key, value in components.items() if value is not None} | {"red_flag_penalty": round(penalty, 4)},
            requirements=bundle.requirements,
            dimensions=bundle.dimensions,
            seniority=bundle.seniority,
            red_flags=bundle.red_flags,
            ats_original=bundle.ats_original,
            strengths=self._strengths(bundle),
            gaps=self._gaps(bundle),
            low_confidence_items=self._low_confidence_items(bundle),
        )

    def _coverage(self, requirements: list[RequirementAssessment], priority: RequirementPriority) -> float | None:
        selected = [item for item in requirements if item.priority == priority]
        if not selected:
            return None
        return sum(self.VERDICT_CREDIT[item.verdict] for item in selected) / len(selected)

    def _dimension_score(self, bundle: FitValidationBundle) -> float | None:
        weights = self._dimension_weights.model_dump()
        weighted = [(weights[item.dimension.value], item.score) for item in bundle.dimensions]
        total_weight = sum(weight for weight, _ in weighted)
        if not total_weight:
            return None
        return sum(weight * score for weight, score in weighted) / total_weight

    def _seniority_score(self, seniority: SeniorityAssessment) -> float:
        level_score = sum(self.SENIORITY_CREDIT.get(level, 0.0) * probability for level, probability in seniority.probabilities.items())
        if seniority.years_requirement_probability is None:
            return level_score
        return (1 - self.YEARS_SHARE) * level_score + self.YEARS_SHARE * seniority.years_requirement_probability

    def _weighted_average(self, components: dict[str, float | None]) -> float:
        weights = self._fit_weights.model_dump()
        present = {key: value for key, value in components.items() if value is not None}
        total_weight = sum(weights[key] for key in present)
        if not total_weight:
            return 0.0
        return sum(weights[key] * value for key, value in present.items()) / total_weight

    def _red_flag_penalty(self, flags: list[RedFlag]) -> float:
        raw = sum(flag.severity * flag.probability for flag in flags if flag.triggered)
        return min(self._fit_weights.max_red_flag_penalty, raw * self._fit_weights.max_red_flag_penalty)

    def _recommend(self, overall: float, must_have: float | None, bundle: FitValidationBundle) -> tuple[Recommendation, list[str]]:
        coverage = 1.0 if must_have is None else must_have
        scam = next((flag for flag in bundle.red_flags if flag.code == RedFlagValidator.SCAM_CODE and flag.triggered), None)
        if scam:
            return Recommendation.SKIP, ["The posting shows scam-like signals; do not share personal data with it."]
        skip_reasons = self._skip_reasons(overall, coverage)
        if skip_reasons:
            return Recommendation.SKIP, skip_reasons
        if self._qualifies_for_direct_apply(overall, coverage, bundle.ats_original.score):
            return Recommendation.APPLY, [
                f"Overall fit is {overall:.0f}/100 with {coverage:.0%} of must-haves covered.",
                f"The current CV already mirrors the posting well (ATS alignment {bundle.ats_original.score:.0%}).",
            ]
        return Recommendation.APPLY_AFTER_TAILORING, self._tailoring_reasons(overall, coverage, bundle.ats_original.score)

    def _skip_reasons(self, overall: float, coverage: float) -> list[str]:
        reasons = []
        if coverage < self._thresholds.skip_max_must_have_coverage:
            reasons.append(f"Only {coverage:.0%} of must-have requirements are covered by your documents.")
        if overall < self._thresholds.skip_score:
            reasons.append(f"Overall fit is {overall:.0f}/100, below the {self._thresholds.skip_score:.0f} threshold.")
        return reasons

    def _qualifies_for_direct_apply(self, overall: float, coverage: float, ats_score: float) -> bool:
        return (
            overall >= self._thresholds.apply_score
            and coverage >= self._thresholds.apply_min_must_have_coverage
            and ats_score >= self._thresholds.apply_min_ats
        )

    def _tailoring_reasons(self, overall: float, coverage: float, ats_score: float) -> list[str]:
        reasons = [f"Overall fit is {overall:.0f}/100 with {coverage:.0%} of must-haves covered."]
        if ats_score < self._thresholds.apply_min_ats:
            reasons.append(f"Your current CV hides relevant evidence (ATS alignment {ats_score:.0%}); the tailored CV surfaces it.")
        if coverage < self._thresholds.apply_min_must_have_coverage:
            reasons.append("Some must-haves are only partially evidenced; address them in the cover letter or interview.")
        return reasons

    def _strengths(self, bundle: FitValidationBundle) -> list[str]:
        strengths = [
            f"Meets requirement: {item.text}"
            for item in bundle.requirements
            if item.verdict == RequirementVerdict.MET and item.priority == RequirementPriority.MUST_HAVE
        ]
        strengths += [
            f"Strong {self._dimension_label(item.dimension)} fit ({item.level_label})"
            for item in bundle.dimensions
            if item.score >= self.STRONG_DIMENSION
        ]
        if bundle.seniority.match == SeniorityMatch.MATCHES and not bundle.seniority.low_confidence:
            strengths.append("Seniority matches the role.")
        return strengths

    def _gaps(self, bundle: FitValidationBundle) -> list[str]:
        gaps = [
            f"{'Missing' if item.verdict == RequirementVerdict.MISSING else 'Partially evidenced'} "
            f"{'must-have' if item.priority == RequirementPriority.MUST_HAVE else 'nice-to-have'}: {item.text}"
            for item in bundle.requirements
            if item.verdict != RequirementVerdict.MET
        ]
        gaps += [
            f"Weak {self._dimension_label(item.dimension)} fit ({item.level_label})"
            for item in bundle.dimensions
            if item.score < self.WEAK_DIMENSION
        ]
        if bundle.seniority.match == SeniorityMatch.BELOW:
            gaps.append("Experience level appears below what the role asks for.")
        return gaps

    def _low_confidence_items(self, bundle: FitValidationBundle) -> list[str]:
        items = [f"Requirement: {item.text}" for item in bundle.requirements if item.low_confidence]
        items += [f"Dimension: {self._dimension_label(item.dimension)}" for item in bundle.dimensions if item.low_confidence]
        if bundle.seniority.low_confidence:
            items.append("Seniority match")
        return items

    @staticmethod
    def _dimension_label(dimension: FitDimension) -> str:
        return dimension.value.replace("_", " ")
