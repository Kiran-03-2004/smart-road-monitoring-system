"""
heatmap_generator.py
====================
Weighted pothole-density heatmap using folium's HeatMap plugin.

Each detection contributes an intensity proportional to its severity weight
(from :data:`config.SEVERITY_SCORE_WEIGHTS`), so clusters of critical
potholes glow far more intensely than clusters of minor ones. This gives
municipal planners an at-a-glance view of the highest-risk corridors.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import folium
from folium.plugins import HeatMap

import config
from src.utils import get_logger, timestamp_slug

_LOGGER = get_logger(__name__)

_DEFAULT_CENTER: Tuple[float, float] = (config.GPS.start_lat, config.GPS.start_lon)

# Gradient tuned so high-weight clusters trend toward red.
_GRADIENT: Dict[float, str] = {
    0.2: "#00C800",  # green
    0.4: "#E6C200",  # yellow
    0.6: "#FF8C00",  # orange
    0.8: "#FF4500",  # orange-red
    1.0: "#FF0000",  # red
}


class HeatmapGenerator:
    """Generate weighted folium heatmaps from detection records."""

    def __init__(self, zoom_start: int = 14) -> None:
        self.zoom_start = zoom_start
        self._max_weight = max(config.SEVERITY_SCORE_WEIGHTS.values())

    def _weighted_points(
        self, detections: Sequence[Dict[str, object]]
    ) -> List[List[float]]:
        """Return ``[lat, lon, normalised_weight]`` triples for the heatmap."""
        points: List[List[float]] = []
        for det in detections:
            lat = det.get("latitude")
            lon = det.get("longitude")
            if lat is None or lon is None:
                continue
            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (TypeError, ValueError):
                continue
            severity = str(det.get("severity", "Low"))
            weight = config.SEVERITY_SCORE_WEIGHTS.get(severity, 1)
            normalised = weight / self._max_weight
            points.append([lat_f, lon_f, normalised])
        return points

    @staticmethod
    def _center(points: Sequence[Sequence[float]]) -> Tuple[float, float]:
        if not points:
            return _DEFAULT_CENTER
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        return (sum(lats) / len(lats), sum(lons) / len(lons))

    def build_heatmap(
        self, detections: Sequence[Dict[str, object]]
    ) -> folium.Map:
        """Build and return a weighted folium heatmap."""
        points = self._weighted_points(detections)
        center = self._center(points)

        fmap = folium.Map(
            location=list(center),
            zoom_start=self.zoom_start,
            control_scale=True,
            tiles="OpenStreetMap",
        )

        if points:
            HeatMap(
                points,
                min_opacity=0.35,
                radius=22,
                blur=18,
                max_zoom=17,
                gradient=_GRADIENT,
            ).add_to(fmap)
        else:
            _LOGGER.info("No geolocated detections; heatmap is empty.")

        return fmap

    def save_heatmap(
        self,
        detections: Sequence[Dict[str, object]],
        filename: Optional[str] = None,
    ) -> str:
        """Build and save a heatmap to ``maps/``, returning the path."""
        fmap = self.build_heatmap(detections)
        name = filename or f"heatmap_{timestamp_slug()}.html"
        path = config.MAPS_DIR / name
        fmap.save(str(path))
        _LOGGER.info("Saved heatmap to %s", path)
        return str(path)


# Module-level singleton and convenience wrappers.
heatmap_generator = HeatmapGenerator()


def build_heatmap(detections: Sequence[Dict[str, object]]) -> folium.Map:
    """Convenience wrapper returning a folium heatmap object."""
    return heatmap_generator.build_heatmap(detections)


def save_heatmap(
    detections: Sequence[Dict[str, object]], filename: Optional[str] = None
) -> str:
    """Convenience wrapper saving a heatmap and returning its path."""
    return heatmap_generator.save_heatmap(detections, filename=filename)


__all__ = [
    "HeatmapGenerator",
    "heatmap_generator",
    "build_heatmap",
    "save_heatmap",
]
