"""
map_generator.py
================
Interactive route-map generation using folium.

Plots de-duplicated pothole detections as colour-coded markers on an OSM
base map, connects them with a route polyline in detection order, and adds a
severity legend. Colour coding follows the project convention:

    Low = green, Medium = yellow, High = orange, Critical = red.

The map object is returned for direct embedding in Streamlit and can also be
saved to ``maps/`` as a standalone HTML file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import folium

import config
from src.utils import get_logger, timestamp_slug

_LOGGER = get_logger(__name__)

# Default map centre (config GPS origin) when no detections are available.
_DEFAULT_CENTER: Tuple[float, float] = (config.GPS.start_lat, config.GPS.start_lon)


class MapGenerator:
    """Generate folium route maps from pothole detection records."""

    def __init__(self, zoom_start: int = 15) -> None:
        self.zoom_start = zoom_start

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _valid_points(
        detections: Sequence[Dict[str, object]],
    ) -> List[Dict[str, object]]:
        """Filter detections to those with usable coordinates."""
        points: List[Dict[str, object]] = []
        for det in detections:
            lat = det.get("latitude")
            lon = det.get("longitude")
            if lat is None or lon is None:
                continue
            try:
                float(lat)
                float(lon)
            except (TypeError, ValueError):
                continue
            points.append(det)
        return points

    @staticmethod
    def _center(points: Sequence[Dict[str, object]]) -> Tuple[float, float]:
        """Compute a sensible map centre from the available points."""
        if not points:
            return _DEFAULT_CENTER
        lats = [float(p["latitude"]) for p in points]
        lons = [float(p["longitude"]) for p in points]
        return (sum(lats) / len(lats), sum(lons) / len(lons))

    @staticmethod
    def _legend_html() -> str:
        """Return an HTML snippet for a fixed-position severity legend."""
        rows = "".join(
            f'<div style="margin:2px 0;">'
            f'<span style="display:inline-block;width:12px;height:12px;'
            f'background:{color};margin-right:6px;border:1px solid #333;">'
            f"</span>{level}</div>"
            for level, color in config.SEVERITY_COLORS_HEX.items()
        )
        return f"""
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                    background: white; padding: 10px 14px; border:1px solid #999;
                    border-radius: 6px; font-size: 13px; box-shadow: 0 1px 4px rgba(0,0,0,0.3);">
            <b>Severity</b>
            {rows}
        </div>
        """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_map(
        self,
        detections: Sequence[Dict[str, object]],
        draw_route: bool = True,
    ) -> folium.Map:
        """Build and return a folium map for the given detections.

        Args:
            detections: Detection dicts with at least ``latitude``,
                ``longitude``, ``severity``, ``confidence``, ``location``,
                ``timestamp``.
            draw_route: Whether to connect points with a route polyline.
        """
        points = self._valid_points(detections)
        center = self._center(points)

        fmap = folium.Map(
            location=list(center),
            zoom_start=self.zoom_start,
            control_scale=True,
            tiles="OpenStreetMap",
        )

        # Route polyline (in detection order).
        if draw_route and len(points) >= 2:
            route = [
                (float(p["latitude"]), float(p["longitude"])) for p in points
            ]
            folium.PolyLine(
                route, color="#3366cc", weight=3, opacity=0.7
            ).add_to(fmap)

        # Markers.
        for idx, det in enumerate(points, start=1):
            severity = str(det.get("severity", "Low"))
            marker_color = config.SEVERITY_FOLIUM_COLORS.get(severity, "gray")
            confidence = det.get("confidence", 0.0)
            try:
                conf_pct = f"{float(confidence) * 100:.0f}%"
            except (TypeError, ValueError):
                conf_pct = "n/a"

            popup_html = (
                f"<b>Pothole #{idx}</b><br>"
                f"Severity: {severity}<br>"
                f"Confidence: {conf_pct}<br>"
                f"Location: {det.get('location', 'Unknown')}<br>"
                f"Time: {det.get('timestamp', '')}"
            )
            folium.Marker(
                location=[float(det["latitude"]), float(det["longitude"])],
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=f"{severity} pothole",
                icon=folium.Icon(color=marker_color, icon="exclamation-triangle", prefix="fa"),
            ).add_to(fmap)

        # Start/end markers for orientation.
        if points:
            start = points[0]
            folium.Marker(
                location=[float(start["latitude"]), float(start["longitude"])],
                tooltip="Start",
                icon=folium.Icon(color="blue", icon="play", prefix="fa"),
            ).add_to(fmap)
            end = points[-1]
            folium.Marker(
                location=[float(end["latitude"]), float(end["longitude"])],
                tooltip="End",
                icon=folium.Icon(color="cadetblue", icon="flag-checkered", prefix="fa"),
            ).add_to(fmap)

        fmap.get_root().html.add_child(folium.Element(self._legend_html()))
        return fmap

    def save_map(
        self,
        detections: Sequence[Dict[str, object]],
        filename: Optional[str] = None,
        draw_route: bool = True,
    ) -> str:
        """Build a map and save it to ``maps/`` as HTML, returning the path."""
        fmap = self.build_map(detections, draw_route=draw_route)
        name = filename or f"route_map_{timestamp_slug()}.html"
        path = config.MAPS_DIR / name
        fmap.save(str(path))
        _LOGGER.info("Saved route map to %s", path)
        return str(path)


# Module-level singleton and convenience wrappers.
map_generator = MapGenerator()


def build_route_map(detections: Sequence[Dict[str, object]]) -> folium.Map:
    """Convenience wrapper returning a folium map object."""
    return map_generator.build_map(detections)


def save_route_map(
    detections: Sequence[Dict[str, object]], filename: Optional[str] = None
) -> str:
    """Convenience wrapper saving a map and returning its path."""
    return map_generator.save_map(detections, filename=filename)


__all__ = [
    "MapGenerator",
    "map_generator",
    "build_route_map",
    "save_route_map",
]
