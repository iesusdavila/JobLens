LOW_CONFIDENCE_THRESHOLD = 0.5

RECOMMENDATION_STYLES = {
    "apply": ("green", "Apply"),
    "apply_after_tailoring": ("orange", "Apply after tailoring"),
    "skip": ("red", "Skip"),
}

VERDICT_STYLES = {"met": "green", "partial": "orange", "missing": "red"}

def confidence_badge(confidence: float) -> str:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return f":orange-badge[Low confidence {confidence:.0%}]"
    return f":gray-badge[Confidence {confidence:.0%}]"

def recommendation_badge(recommendation: str) -> str:
    color, label = RECOMMENDATION_STYLES.get(recommendation, ("gray", recommendation))
    return f":{color}-badge[{label}]"

def verdict_badge(verdict: str) -> str:
    return f":{VERDICT_STYLES.get(verdict, 'gray')}-badge[{verdict}]"

def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"
