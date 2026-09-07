"""
severity.py
===========
Pothole severity classification based on bounding-box pixel area.

Classification rules (upper bounds exclusive)::

    area < 3000            -> Low
    3000 <= area < 8000    -> Medium
    8000 <= area < 15000   -> High
    area >= 15000          -> Critical

Thresholds, level names, colours and score weights are all sourced from
:mod:`config`, so tuning happens in one place.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import config
from src.utils import box_area, get_logger

_LOGGER = get_logger(__name__)


class SeverityClassifier:
    """Classify potholes into discrete severity levels by bounding-box area."""

    def __init__(self) -> None:
        self._low = config.SEVERITY_THRESHOLDS["low"]
        self._medium = config.SEVERITY_THRESHOLDS["medium"]
        self._high = config.SEVERITY_THRESHOLDS["high"]

    def classify_area(self, area: float) -> str:
        """Return the severity level for a given bounding-box area.

        Args:
            area: Bounding-box area in pixels.

        Returns:
            One of ``"Low"``, ``"Medium"``, ``"High"``, ``"Critical"``.
        """
        if area < self._low:
            return "Low"
        if area < self._medium:
            return "Medium"
        if area < self._high:
            return "High"
        return "Critical"

    def classify_box(self, box: Sequence[float]) -> Tuple[str, float]:
        """Classify a bounding box, returning ``(severity, area)``.

        Args:
            box: Bounding box as (x1, y1, x2, y2) in pixels.
        """
        area = box_area(box)
        return self.classify_area(area), area

    @staticmethod
    def color_bgr(severity: str) -> Tuple[int, int, int]:
        """Return the OpenCV (BGR) overlay colour for a severity level."""
        return config.SEVERITY_COLORS_BGR.get(severity, (255, 255, 255))

    @staticmethod
    def color_hex(severity: str) -> str:
        """Return the HEX colour for a severity level (maps/reports)."""
        return config.SEVERITY_COLORS_HEX.get(severity, "#808080")

    @staticmethod
    def weight(severity: str) -> int:
        """Return the road-health penalty weight for a severity level."""
        return config.SEVERITY_SCORE_WEIGHTS.get(severity, 0)


# Module-level singleton for convenient reuse.
classifier = SeverityClassifier()


def classify(area: float) -> str:
    """Convenience wrapper around :meth:`SeverityClassifier.classify_area`."""
    return classifier.classify_area(area)


__all__ = ["SeverityClassifier", "classifier", "classify"]
