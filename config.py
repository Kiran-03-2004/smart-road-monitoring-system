"""
config.py
=========
Central configuration for the AI-Powered Smart Road Infrastructure
Monitoring and Pothole Severity Analysis System.

All tunable parameters, filesystem paths, thresholds, weights and
presentation settings live here so the rest of the codebase reads from a
single, well-documented source of truth.

The module is import-safe: importing it creates every required directory
on disk, so downstream modules never have to worry about missing folders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple

from dotenv import load_dotenv

# Load environment variables from a local .env file if present.
load_dotenv()


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent

MODEL_DIR: Path = BASE_DIR / "model"
DATABASE_DIR: Path = BASE_DIR / "database"
DATA_DIR: Path = BASE_DIR / "data"
REPORTS_DIR: Path = BASE_DIR / "reports"
MAPS_DIR: Path = BASE_DIR / "maps"
CAPTURES_DIR: Path = BASE_DIR / "captures"
POTHOLE_CAPTURES_DIR: Path = CAPTURES_DIR / "potholes"
LOGS_DIR: Path = BASE_DIR / "logs"

MODEL_PATH: Path = MODEL_DIR / "final_pothole_detector.pt"
DATABASE_PATH: Path = DATABASE_DIR / "potholes.db"
DETECTIONS_CSV: Path = DATA_DIR / "detections.csv"

# Directories that must exist for the system to operate.
_REQUIRED_DIRS = (
    MODEL_DIR,
    DATABASE_DIR,
    DATA_DIR,
    REPORTS_DIR,
    MAPS_DIR,
    CAPTURES_DIR,
    POTHOLE_CAPTURES_DIR,
    LOGS_DIR,
)


def ensure_directories() -> None:
    """Create every required directory if it does not already exist."""
    for directory in _REQUIRED_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# Create directories eagerly on import.
ensure_directories()


# ----------------------------------------------------------------------
# Model / Detection
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class DetectionConfig:
    """Inference-time configuration for the YOLOv8 detector."""

    model_path: str = str(MODEL_PATH)
    confidence_threshold: float = float(os.getenv("CONF_THRESHOLD", "0.35"))
    iou_threshold: float = float(os.getenv("IOU_THRESHOLD", "0.45"))
    image_size: int = int(os.getenv("IMG_SIZE", "640"))
    device: str = os.getenv("DEVICE", "cpu")  # "cpu", "0", "cuda:0", ...
    class_name: str = "pothole"


DETECTION = DetectionConfig()


# ----------------------------------------------------------------------
# Severity classification (based on bounding-box pixel area)
# ----------------------------------------------------------------------
# Thresholds are upper-exclusive bounds interpreted as:
#   area < 3000            -> Low
#   3000 <= area < 8000    -> Medium
#   8000 <= area < 15000   -> High
#   area >= 15000          -> Critical
SEVERITY_THRESHOLDS: Dict[str, int] = {
    "low": 3000,
    "medium": 8000,
    "high": 15000,
}

SEVERITY_LEVELS: Tuple[str, ...] = ("Low", "Medium", "High", "Critical")

# Weight applied per detected pothole when computing the road-health score.
SEVERITY_SCORE_WEIGHTS: Dict[str, int] = {
    "Low": 1,
    "Medium": 3,
    "High": 6,
    "Critical": 8,
}

# Presentation colors.
# BGR is used by OpenCV overlays; HEX is used by folium/plotly/reports.
SEVERITY_COLORS_BGR: Dict[str, Tuple[int, int, int]] = {
    "Low": (0, 200, 0),        # green
    "Medium": (0, 220, 220),   # yellow
    "High": (0, 140, 255),     # orange
    "Critical": (0, 0, 255),   # red
}

SEVERITY_COLORS_HEX: Dict[str, str] = {
    "Low": "#00C800",
    "Medium": "#E6C200",
    "High": "#FF8C00",
    "Critical": "#FF0000",
}

# folium marker color names (folium only accepts a fixed palette).
SEVERITY_FOLIUM_COLORS: Dict[str, str] = {
    "Low": "green",
    "Medium": "beige",
    "High": "orange",
    "Critical": "red",
}


# ----------------------------------------------------------------------
# Road health scoring
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class RoadHealthConfig:
    """Thresholds used to classify a numeric road-health score."""

    max_score: int = 100
    min_score: int = 0
    excellent: int = 90
    good: int = 70
    moderate: int = 50


ROAD_HEALTH = RoadHealthConfig()


# ----------------------------------------------------------------------
# GPS simulation
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class GPSConfig:
    """Configuration for the (replaceable) simulated GPS source."""

    # Default anchor point (Bengaluru, India) used as the trip origin.
    start_lat: float = float(os.getenv("GPS_START_LAT", "12.9716"))
    start_lon: float = float(os.getenv("GPS_START_LON", "77.5946"))
    # Approximate metres of drift applied per step to emulate a moving vehicle.
    step_metres: float = float(os.getenv("GPS_STEP_METRES", "15.0"))


GPS = GPSConfig()


# ----------------------------------------------------------------------
# Reverse geocoding
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class GeocoderConfig:
    """Configuration for reverse geocoding via geopy/Nominatim."""

    user_agent: str = os.getenv("GEOCODER_AGENT", "smart_road_monitor")
    timeout: int = int(os.getenv("GEOCODER_TIMEOUT", "10"))
    # Nominatim usage policy requires >= 1s between requests.
    min_delay_seconds: float = float(os.getenv("GEOCODER_MIN_DELAY", "1.1"))
    # Round coordinates to this many decimals for cache keys (~11m at 4dp).
    cache_precision: int = 4
    language: str = "en"


GEOCODER = GeocoderConfig()


# ----------------------------------------------------------------------
# Tracking / de-duplication
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class TrackerConfig:
    """Configuration for the lightweight IoU-based object tracker."""

    iou_match_threshold: float = 0.3
    max_missed_frames: int = 30      # frames a track survives without a match
    min_hits_to_count: int = 3       # confirmed detections before counting

    # Two detections within this pixel distance AND with a similar box are
    # treated as the same physical pothole (secondary de-duplication guard).
    dedup_distance_px: float = 60.0


TRACKER = TrackerConfig()


# ----------------------------------------------------------------------
# Application metadata
# ----------------------------------------------------------------------
APP_NAME: str = "AI-Powered Smart Road Infrastructure Monitoring System"
APP_SHORT_NAME: str = "Smart Road Monitor"
APP_VERSION: str = "1.0.0"
ORGANIZATION: str = os.getenv("ORGANIZATION", "Municipal Corporation")

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: Path = LOGS_DIR / "app.log"


__all__ = [
    "BASE_DIR",
    "MODEL_DIR",
    "DATABASE_DIR",
    "DATA_DIR",
    "REPORTS_DIR",
    "MAPS_DIR",
    "CAPTURES_DIR",
    "POTHOLE_CAPTURES_DIR",
    "LOGS_DIR",
    "MODEL_PATH",
    "DATABASE_PATH",
    "DETECTIONS_CSV",
    "ensure_directories",
    "DETECTION",
    "SEVERITY_THRESHOLDS",
    "SEVERITY_LEVELS",
    "SEVERITY_SCORE_WEIGHTS",
    "SEVERITY_COLORS_BGR",
    "SEVERITY_COLORS_HEX",
    "SEVERITY_FOLIUM_COLORS",
    "ROAD_HEALTH",
    "GPS",
    "GEOCODER",
    "TRACKER",
    "APP_NAME",
    "APP_SHORT_NAME",
    "APP_VERSION",
    "ORGANIZATION",
    "LOG_LEVEL",
    "LOG_FILE",
]
