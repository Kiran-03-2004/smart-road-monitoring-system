"""
road_health.py
==============
Road-health scoring for the Smart Road Monitoring System.

Score formula (penalties per detected pothole)::

    score = 100
            - (critical * 8)
            - (high     * 6)
            - (medium   * 3)
            - (low      * 1)

The score is clamped to a minimum of 0 and classified as:

    >= 90  -> Excellent
    >= 70  -> Good
    >= 50  -> Moderate
    <  50  -> Poor
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import config
from src.utils import clamp, get_logger

_LOGGER = get_logger(__name__)


@dataclass
class RoadHealthResult:
    """Structured road-health assessment."""

    score: float
    rating: str
    total_potholes: int
    severity_counts: Dict[str, int] = field(default_factory=dict)
    maintenance_priority: str = ""
    recommendation: str = ""


class RoadHealthCalculator:
    """Compute and classify a road-health score from severity counts."""

    def compute(self, severity_counts: Dict[str, int]) -> RoadHealthResult:
        """Compute a :class:`RoadHealthResult` from severity counts.

        Args:
            severity_counts: Mapping of severity level -> count. Missing
                levels are treated as zero.
        """
        low = int(severity_counts.get("Low", 0))
        medium = int(severity_counts.get("Medium", 0))
        high = int(severity_counts.get("High", 0))
        critical = int(severity_counts.get("Critical", 0))

        raw_score = (
            config.ROAD_HEALTH.max_score
            - critical * config.SEVERITY_SCORE_WEIGHTS["Critical"]
            - high * config.SEVERITY_SCORE_WEIGHTS["High"]
            - medium * config.SEVERITY_SCORE_WEIGHTS["Medium"]
            - low * config.SEVERITY_SCORE_WEIGHTS["Low"]
        )
        score = clamp(
            float(raw_score),
            float(config.ROAD_HEALTH.min_score),
            float(config.ROAD_HEALTH.max_score),
        )

        rating = self.classify(score)
        total = low + medium + high + critical

        result = RoadHealthResult(
            score=round(score, 1),
            rating=rating,
            total_potholes=total,
            severity_counts={
                "Low": low,
                "Medium": medium,
                "High": high,
                "Critical": critical,
            },
            maintenance_priority=self._priority(rating, critical, high),
            recommendation=self._recommendation(rating, critical, high),
        )
        _LOGGER.debug("Road health computed: %.1f (%s)", result.score, result.rating)
        return result

    @staticmethod
    def classify(score: float) -> str:
        """Classify a numeric score into a rating label."""
        if score >= config.ROAD_HEALTH.excellent:
            return "Excellent"
        if score >= config.ROAD_HEALTH.good:
            return "Good"
        if score >= config.ROAD_HEALTH.moderate:
            return "Moderate"
        return "Poor"

    @staticmethod
    def _priority(rating: str, critical: int, high: int) -> str:
        """Derive a municipal maintenance-priority band."""
        if critical > 0 or rating == "Poor":
            return "URGENT (P1)"
        if high > 0 or rating == "Moderate":
            return "HIGH (P2)"
        if rating == "Good":
            return "MEDIUM (P3)"
        return "LOW (P4)"

    @staticmethod
    def _recommendation(rating: str, critical: int, high: int) -> str:
        """Produce a short, actionable maintenance recommendation."""
        if critical > 0:
            return (
                f"Immediate intervention required: {critical} critical "
                "pothole(s) pose a safety hazard. Dispatch a repair crew "
                "within 24-48 hours."
            )
        if rating == "Poor":
            return (
                "Road surface is severely degraded. Schedule comprehensive "
                "resurfacing and prioritise in the next maintenance cycle."
            )
        if high > 0 or rating == "Moderate":
            return (
                f"Plan targeted repairs for {high} high-severity pothole(s). "
                "Address within the current maintenance window."
            )
        if rating == "Good":
            return (
                "Road condition is acceptable. Continue routine monitoring "
                "and patch minor defects opportunistically."
            )
        return "Road is in excellent condition. Maintain standard inspection cadence."


# Module-level singleton and convenience wrapper.
calculator = RoadHealthCalculator()


def compute_road_health(severity_counts: Dict[str, int]) -> RoadHealthResult:
    """Convenience wrapper around the singleton calculator."""
    return calculator.compute(severity_counts)


__all__ = [
    "RoadHealthResult",
    "RoadHealthCalculator",
    "calculator",
    "compute_road_health",
]
