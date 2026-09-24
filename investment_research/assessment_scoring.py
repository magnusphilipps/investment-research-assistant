from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable


def safe_numeric(value: Any) -> float | None:
    """Return a finite float when possible, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"n/a", "nan", "inf", "-inf", "none", "null"}:
            return None
        try:
            value = float(cleaned)
        except ValueError:
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def valid_metric_values(values: Any, *, metric_name: str | None = None) -> list[float]:
    """Return usable numeric values from a collection while skipping invalid entries."""
    if values is None:
        return []
    if isinstance(values, dict):
        items = list(values.values())
    elif isinstance(values, (list, tuple, set)):
        items = list(values)
    else:
        items = [values]

    usable: list[float] = []
    for value in items:
        numeric = safe_numeric(value)
        if numeric is None:
            continue
        if metric_name is not None:
            key = metric_name.lower().replace(" ", "")
            if any(token in key for token in ("pe", "ebitda")) and numeric <= 0:
                continue
            if "peg" in key and numeric <= 0:
                continue
        usable.append(float(numeric))
    return usable


def metric_median(values: Iterable[float] | None) -> float | None:
    """Calculate the median only when enough values are available."""
    cleaned = [float(v) for v in (values or []) if safe_numeric(v) is not None]
    if not cleaned:
        return None
    return float(median(cleaned))


def weighted_average(scores: list[float], weights: list[float]) -> float:
    """Weighted average with zero-safe handling."""
    if not scores:
        return 0.0
    total_weight = sum(weights[:len(scores)])
    if total_weight <= 0:
        return 0.0
    return sum(score * weight for score, weight in zip(scores, weights[:len(scores)])) / total_weight


def build_driver(label: str, positive: bool, *, detail: str | None = None) -> str:
    """Create a compact, deterministic driver string."""
    details = detail.strip() if detail else "the metric remains supportive"
    if positive:
        return f"{label}: {details}."
    return f"{label}: {details}."


def unavailable_indicator(reason: str = "Insufficient data to calculate this indicator.") -> dict[str, Any]:
    """Return the standard unavailable indicator object."""
    return {
        "label": "N/A",
        "score": None,
        "drivers": [reason],
        "components": {},
        "evidence": {"reason": reason},
    }


def score_to_label(value: float | None, *, positive_label: str, neutral_label: str, negative_label: str, positive_cutoff: float, negative_cutoff: float) -> str:
    """Map a numeric score to a dashboard label."""
    if value is None:
        return "N/A"
    if value >= positive_cutoff:
        return positive_label
    if value <= negative_cutoff:
        return negative_label
    return neutral_label


def normalize_key(value: Any) -> str:
    """Create a stable, comparable key for dict lookups."""
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "").replace("/", "").replace(" ", "")


def deep_find_value(container: Any, candidates: Iterable[str]) -> Any:
    """Recursively search a nested structure for a likely key match."""
    candidate_list = [str(item) for item in candidates]
    if isinstance(container, dict):
        normalized = {normalize_key(k): v for k, v in container.items()}
        for item in candidate_list:
            if normalize_key(item) in normalized:
                return normalized[normalize_key(item)]
        for value in container.values():
            found = deep_find_value(value, candidate_list)
            if found is not None:
                return found
    elif isinstance(container, (list, tuple, set)):
        for item in container:
            found = deep_find_value(item, candidate_list)
            if found is not None:
                return found
    return None


def safe_ratio(numerator: Any, denominator: Any) -> float | None:
    """Safely divide two values while rejecting missing or zero denominators."""
    num = safe_numeric(numerator)
    den = safe_numeric(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def percent_from_value(value: Any, base: Any) -> float | None:
    """Return a percentage number as a float (not fraction)."""
    ratio = safe_ratio(value, base)
    if ratio is None:
        return None
    return ratio * 100.0


def array_first(values: Any) -> Any:
    """Fetch the latest/first numeric item from a list-like structure when present."""
    if values is None:
        return None
    if isinstance(values, (list, tuple)):
        for item in values:
            if safe_numeric(item) is not None:
                return item
        return None
    return values


def compare_to_peer(company_value: Any, peer_median: Any) -> float | None:
    """Return the premium/discount score relative to a peer median."""
    company = safe_numeric(company_value)
    peer = safe_numeric(peer_median)
    if company is None or peer is None or peer <= 0 or company <= 0:
        return None
    delta = company / peer - 1.0
    if delta >= 0.25:
        return -2.0
    if delta >= 0.10:
        return -1.0
    if delta <= -0.10:
        return 1.0
    if delta <= -0.25:
        return 2.0
    return 0.0


def peer_metric_values(peer_data: Any, aliases: Iterable[str]) -> list[float]:
    """Extract valid peer metric values for a metric across the peer dataset."""
    aliases = [str(item) for item in aliases]
    if peer_data is None:
        return []
    values: list[float] = []

    # Common structured format from this project.
    if isinstance(peer_data, dict):
        if isinstance(peer_data.get("df"), object):
            try:
                import pandas as pd
                df = peer_data["df"]
                if isinstance(df, pd.DataFrame):
                    for alias in aliases:
                        match = None
                        for label in list(df.index):
                            if normalize_key(label) == normalize_key(alias):
                                match = label
                                break
                        if match is None:
                            continue
                        for value in df.loc[match].tolist():
                            numeric = safe_numeric(value)
                            if numeric is None:
                                continue
                            if alias.lower().find("pe") >= 0 or alias.lower().find("ebitda") >= 0:
                                if numeric <= 0:
                                    continue
                            values.append(float(numeric))
                    return values
            except Exception:
                pass

        if "peer_medians" in peer_data and isinstance(peer_data["peer_medians"], dict):
            for alias in aliases:
                for key, value in peer_data["peer_medians"].items():
                    if normalize_key(key) == normalize_key(alias):
                        numeric = safe_numeric(value)
                        if numeric is not None:
                            values.append(float(numeric))
            return values

        for alias in aliases:
            hidden = deep_find_value(peer_data, [alias])
            if isinstance(hidden, (list, tuple, set)):
                for item in hidden:
                    numeric = safe_numeric(item)
                    if numeric is not None:
                        values.append(float(numeric))
            elif hidden is not None:
                numeric = safe_numeric(hidden)
                if numeric is not None:
                    values.append(float(numeric))
        return values

    if isinstance(peer_data, (list, tuple, set)):
        for entry in peer_data:
            if isinstance(entry, dict):
                for alias in aliases:
                    value = deep_find_value(entry, [alias])
                    numeric = safe_numeric(value)
                    if numeric is not None:
                        values.append(float(numeric))
    return values


def peer_coverage_label(valid_count: int) -> str:
    """Translate the number of usable peer values into a coverage label."""
    if valid_count >= 3:
        return "strong"
    if valid_count == 2:
        return "acceptable"
    if valid_count == 1:
        return "insufficient"
    return "none"


def bucket_score(raw: Any) -> int:
    """Return a 0/1/2 score from a qualitative value bucket."""
    numeric = safe_numeric(raw)
    if numeric is None:
        return 0
    if numeric < 0:
        return 0
    if numeric < 1:
        return 0
    return int(numeric)
