"""Display-safe helpers for the Streamlit stock assessment dashboard."""

from typing import Any


ASSESSMENT_INDICATORS = (
    ("valuation", "Valuation"),
    ("financial_quality", "Financial Quality"),
    ("growth", "Growth"),
    ("risk", "Risk"),
    ("volatility", "Volatility"),
    ("market_environment", "Market Environment"),
    ("competitive_position", "Competitive Position"),
    ("expectations", "Expectations"),
)

_POSITIVE_LABELS = {"positive", "strong", "favourable", "favorable", "cheap", "low"}
_NEUTRAL_LABELS = {"neutral", "moderate", "fair", "medium"}
_CAUTION_LABELS = {
    "negative",
    "weak",
    "unfavourable",
    "unfavorable",
    "expensive",
    "high",
}


def get_label_style(label: str) -> str:
    """Map an assessment label to a non-recommendation visual state."""
    normalized = label.strip().casefold()
    if normalized == "n/a":
        return "muted"
    if normalized in _POSITIVE_LABELS:
        return "positive"
    if normalized in _CAUTION_LABELS:
        return "caution"
    if normalized in _NEUTRAL_LABELS:
        return "neutral"
    return "neutral"


def get_indicator_display(
    report: Any,
    indicator_key: str,
    indicator_name: str,
) -> dict[str, str]:
    """Extract only an indicator's name, label, first driver, and visual state."""
    assessment = report.get("assessment") if isinstance(report, dict) else None
    indicators = assessment.get("indicators") if isinstance(assessment, dict) else None
    indicator = indicators.get(indicator_key) if isinstance(indicators, dict) else None
    if not isinstance(indicator, dict):
        indicator = {}

    raw_label = indicator.get("label")
    label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "N/A"

    raw_drivers = indicator.get("drivers")
    drivers = raw_drivers if isinstance(raw_drivers, list) else []
    driver = next(
        (value.strip() for value in drivers if isinstance(value, str) and value.strip()),
        "",
    )

    return {
        "name": indicator_name,
        "label": label,
        "driver": driver,
        "style": get_label_style(label),
    }


def get_assessment_display(report: Any) -> list[dict[str, str]]:
    """Return the eight dashboard indicators without assessment internals."""
    return [
        get_indicator_display(report, key, name)
        for key, name in ASSESSMENT_INDICATORS
    ]
