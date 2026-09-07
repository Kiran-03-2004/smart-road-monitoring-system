"""
utils.py
========
Shared helper utilities used across the Smart Road Monitoring System.

Provides:
    * A configured, reusable logger factory (console + rotating file).
    * Geometry helpers (IoU, area, centre) for the tracker/detector.
    * Haversine great-circle distance for GPS calculations.
    * Timestamp helpers.
    * Safe CSV append helper for the detections log.
"""

from __future__ import annotations

import csv
import logging
import math
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple, Union

import config

# Type alias for a bounding box in (x1, y1, x2, y2) pixel coordinates.
BBox = Sequence[float]

# Track loggers we have already configured so handlers are not duplicated.
_CONFIGURED_LOGGERS: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger writing to both console and a rotating file.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    if name in _CONFIGURED_LOGGERS:
        return logger

    level = getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler.
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Rotating file handler (best-effort; never crash logging setup).
    try:
        config.ensure_directories()
        file_handler = RotatingFileHandler(
            filename=str(config.LOG_FILE),
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:  # pragma: no cover - filesystem edge cases
        logger.warning("Could not attach file log handler; console only.")

    _CONFIGURED_LOGGERS.add(name)
    return logger


_LOGGER = get_logger(__name__)


# ----------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------
def box_area(box: BBox) -> float:
    """Return the pixel area of an (x1, y1, x2, y2) bounding box."""
    x1, y1, x2, y2 = box
    width = max(0.0, float(x2) - float(x1))
    height = max(0.0, float(y2) - float(y1))
    return width * height


def box_center(box: BBox) -> Tuple[float, float]:
    """Return the (cx, cy) centre point of a bounding box."""
    x1, y1, x2, y2 = box
    return ((float(x1) + float(x2)) / 2.0, (float(y1) + float(y2)) / 2.0)


def iou(box_a: BBox, box_b: BBox) -> float:
    """Compute Intersection-over-Union between two bounding boxes.

    Args:
        box_a: First box as (x1, y1, x2, y2).
        box_b: Second box as (x1, y1, x2, y2).

    Returns:
        IoU in the range [0.0, 1.0].
    """
    ax1, ay1, ax2, ay2 = map(float, box_a)
    bx1, by1, bx2, by2 = map(float, box_b)

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0
    return intersection / union


def euclidean_distance(
    point_a: Tuple[float, float], point_b: Tuple[float, float]
) -> float:
    """Return the Euclidean pixel distance between two 2D points."""
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


# ----------------------------------------------------------------------
# GPS helpers
# ----------------------------------------------------------------------
def haversine_metres(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in metres between two lat/lon points.

    Uses the haversine formula on a spherical earth (radius 6,371,000 m).
    """
    earth_radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_m * c


# ----------------------------------------------------------------------
# Time helpers
# ----------------------------------------------------------------------
def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def local_now_iso() -> str:
    """Return the current local time as an ISO-8601 string."""
    return datetime.now().replace(microsecond=0).isoformat()


def timestamp_slug() -> str:
    """Return a filesystem-safe timestamp slug, e.g. ``20260905_142530``."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ----------------------------------------------------------------------
# CSV helper
# ----------------------------------------------------------------------
def append_csv_row(
    path: Union[str, Path],
    row: Dict[str, object],
    fieldnames: Iterable[str],
) -> None:
    """Append a single dict row to a CSV file, writing a header if new.

    Args:
        path: Destination CSV path.
        row: Mapping of column name to value.
        fieldnames: Ordered iterable of column names.
    """
    path = Path(path)
    field_list = list(fieldnames)
    write_header = not path.exists() or path.stat().st_size == 0

    try:
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=field_list)
            if write_header:
                writer.writeheader()
            writer.writerow({key: row.get(key, "") for key in field_list})
    except OSError as exc:  # pragma: no cover - filesystem edge cases
        _LOGGER.error("Failed to append CSV row to %s: %s", path, exc)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp ``value`` into the inclusive range [minimum, maximum]."""
    return max(minimum, min(maximum, value))


__all__ = [
    "get_logger",
    "box_area",
    "box_center",
    "iou",
    "euclidean_distance",
    "haversine_metres",
    "utc_now_iso",
    "local_now_iso",
    "timestamp_slug",
    "append_csv_row",
    "clamp",
]
