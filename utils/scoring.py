"""
utils/scoring.py
================
Enhanced road-health scoring model for the enterprise dashboard.

Score model (penalties per detected pothole)::

    score = 100
            - (critical * 10)
            - (high     *  5)
            - (medium   *  2)
            - (low      *  1)

Clamped to [0, 100] and classified into five bands:

    90 - 100  -> Excellent
    75 -  89  -> Good
    60 -  74  -> Moderate
    40 -  59  -> Poor
     0 -  39  -> Critical
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

# Penalty weight per severity level.
SCORE_WEIGHTS: Dict[str, int] = {
    "Critical": 10,
    "High": 5,
    "Medium": 2,
    "Low": 1,
}

# Classification bands: (inclusive_lower_bound, label, hex_color).
_BANDS: Tuple[Tuple[int, str, str], ...] = (
    (90, "Excellent", "#22C55E"),
    (75, "Good", "#84CC16"),
    (60, "Moderate", "#EAB308"),
    (40, "Poor", "#F97316"),
    (0, "Critical", "#EF4444"),
)

SEVERITY_COLORS: Dict[str, str] = {
    "Critical": "#EF4444",
    "High": "#F97316",
    "Medium": "#EAB308",
    "Low": "#22C55E",
}


@dataclass
class HealthScore:
    """Structured road-health result for the dashboard."""

    score: float
    rating: str
    color: str
    total: int
    severity_counts: Dict[str, int] = field(default_factory=dict)
    priority: str = ""
    risk: str = ""


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value into the inclusive range [low, high]."""
    return max(low, min(high, value))


def classify(score: float) -> Tuple[str, str]:
    """Return ``(rating_label, hex_color)`` for a numeric score."""
    for lower, label, color in _BANDS:
        if score >= lower:
            return label, color
    return "Critical", "#EF4444"


def compute_health(severity_counts: Dict[str, int]) -> HealthScore:
    """Compute a :class:`HealthScore` from a severity-count mapping.

    Args:
        severity_counts: Mapping of severity level -> count. Missing levels
            are treated as zero.
    """
    low = int(severity_counts.get("Low", 0))
    medium = int(severity_counts.get("Medium", 0))
    high = int(severity_counts.get("High", 0))
    critical = int(severity_counts.get("Critical", 0))

    raw = (
        100
        - critical * SCORE_WEIGHTS["Critical"]
        - high * SCORE_WEIGHTS["High"]
        - medium * SCORE_WEIGHTS["Medium"]
        - low * SCORE_WEIGHTS["Low"]
    )
    score = clamp(float(raw))
    rating, color = classify(score)
    total = low + medium + high + critical

    return HealthScore(
        score=round(score, 1),
        rating=rating,
        color=color,
        total=total,
        severity_counts={
            "Critical": critical,
            "High": high,
            "Medium": medium,
            "Low": low,
        },
        priority=_priority(rating, critical, high),
        risk=_risk(rating, critical),
    )


def average_severity(severity_counts: Dict[str, int]) -> Tuple[float, str]:
    """Return the mean severity as ``(numeric_1to4, label)``.

    Low=1, Medium=2, High=3, Critical=4.
    """
    weights = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}
    total = sum(severity_counts.get(k, 0) for k in weights)
    if total == 0:
        return 0.0, "N/A"
    score = sum(weights[k] * severity_counts.get(k, 0) for k in weights) / total
    label = {1: "Low", 2: "Medium", 3: "High", 4: "Critical"}[round(score)]
    return round(score, 2), label


def _priority(rating: str, critical: int, high: int) -> str:
    if critical > 0 or rating == "Critical":
        return "P1 - URGENT"
    if high > 0 or rating == "Poor":
        return "P2 - HIGH"
    if rating == "Moderate":
        return "P3 - MEDIUM"
    return "P4 - LOW"


def _risk(rating: str, critical: int) -> str:
    if critical >= 3 or rating == "Critical":
        return "Severe safety hazard"
    if rating in ("Poor", "Moderate"):
        return "Elevated risk"
    return "Within tolerance"


__all__ = [
    "SCORE_WEIGHTS",
    "SEVERITY_COLORS",
    "HealthScore",
    "clamp",
    "classify",
    "compute_health",
    "average_severity",
]
