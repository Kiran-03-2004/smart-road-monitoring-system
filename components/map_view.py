"""
components/map_view.py
======================
Interactive map dashboard using folium.

Features:
    * Color-coded severity markers.
    * Marker clustering (MarkerCluster) for dense areas.
    * Optional severity-weighted heatmap layer.
    * Layer control to toggle markers / heatmap.
    * A "current detected locations" side panel (HTML) summarising hotspots.

Colors follow the platform palette:
    Critical=red, High=orange, Medium=yellow, Low=green.
"""

from __future__ import annotations

import html
from typing import Dict, Optional

import folium
import pandas as pd
from folium.plugins import HeatMap, MarkerCluster

import config

# folium's icon palette is limited; map severity to closest named colors.
_FOLIUM_COLOR = {
    "Critical": "red",
    "High": "orange",
    "Medium": "beige",
    "Low": "green",
}
_HEX = {
    "Critical": "#EF4444",
    "High": "#F97316",
    "Medium": "#EAB308",
    "Low": "#22C55E",
}
_WEIGHT = {"Critical": 1.0, "High": 0.7, "Medium": 0.45, "Low": 0.25}
_DEFAULT_CENTER = (config.GPS.start_lat, config.GPS.start_lon)


def _geo_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return only rows with valid coordinates."""
    if df is None or df.empty:
        return pd.DataFrame()
    sub = df.dropna(subset=["latitude", "longitude"]).copy()
    sub = sub[(sub["latitude"] != 0) | (sub["longitude"] != 0)]
    return sub


def build_map(
    df: pd.DataFrame,
    show_markers: bool = True,
    show_heatmap: bool = True,
    show_route: bool = False,
) -> folium.Map:
    """Build a folium map with clustered markers and an optional heatmap.

    Args:
        df: Enriched detections DataFrame.
        show_markers: Toggle the clustered severity markers layer.
        show_heatmap: Toggle the severity-weighted heatmap layer.
        show_route: Draw a polyline through detections in order.
    """
    geo = _geo_df(df)
    if geo.empty:
        center = _DEFAULT_CENTER
    else:
        center = (geo["latitude"].mean(), geo["longitude"].mean())

    # A dark base map that matches the dashboard theme and requires no API
    # key (some CartoDB tile endpoints now require one, so we add them
    # explicitly with attribution and fall back to OpenStreetMap).
    fmap = folium.Map(
        location=list(center),
        zoom_start=14,
        control_scale=True,
        tiles=None,
    )
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap contributors &copy; CARTO",
        name="Dark",
        control=True,
    ).add_to(fmap)
    folium.TileLayer("OpenStreetMap", name="Street", control=True).add_to(fmap)

    if geo.empty:
        return fmap

    # Route polyline (optional).
    if show_route and len(geo) >= 2:
        folium.PolyLine(
            geo[["latitude", "longitude"]].values.tolist(),
            color="#3B82F6",
            weight=3,
            opacity=0.6,
        ).add_to(fmap)

    # Clustered markers.
    if show_markers:
        cluster = MarkerCluster(name="Detections").add_to(fmap)
        for row in geo.itertuples():
            severity = getattr(row, "severity", "Low")
            popup = folium.Popup(
                f"<b>{html.escape(str(getattr(row, 'location', 'Unknown')))}</b><br>"
                f"Severity: {severity}<br>"
                f"Depth: {getattr(row, 'depth_cm', 0):.1f} cm<br>"
                f"Confidence: {getattr(row, 'confidence', 0) * 100:.0f}%<br>"
                f"Time: {getattr(row, 'timestamp', '')}",
                max_width=260,
            )
            folium.CircleMarker(
                location=[row.latitude, row.longitude],
                radius=7,
                color=_HEX.get(severity, "#3B82F6"),
                fill=True,
                fill_color=_HEX.get(severity, "#3B82F6"),
                fill_opacity=0.85,
                popup=popup,
                tooltip=f"{severity} · {getattr(row, 'location', '')}",
            ).add_to(cluster)

    # Weighted heatmap.
    if show_heatmap:
        points = [
            [r.latitude, r.longitude, _WEIGHT.get(getattr(r, "severity", "Low"), 0.25)]
            for r in geo.itertuples()
        ]
        HeatMap(
            points,
            name="Heatmap",
            min_opacity=0.35,
            radius=24,
            blur=18,
            gradient={0.2: "#22C55E", 0.4: "#EAB308", 0.6: "#F97316", 1.0: "#EF4444"},
        ).add_to(fmap)

    folium.LayerControl(collapsed=True).add_to(fmap)
    return fmap


def location_panel_html(loc_df: pd.DataFrame) -> str:
    """Render the 'current detected locations' side panel as HTML."""
    if loc_df is None or loc_df.empty:
        return (
            '<div class="loc-item"><span class="loc-name">No locations yet</span>'
            '</div>'
        )
    items = []
    for row in loc_df.itertuples():
        worst = getattr(row, "worst", "Low")
        pill_cls = str(worst).lower()
        items.append(
            f'<div class="loc-item">'
            f'<div><div class="loc-name">📍 {html.escape(str(row.location))}</div>'
            f'<div class="loc-sub">{int(row.count)} detection(s)</div></div>'
            f'<span class="pill {pill_cls}">{html.escape(str(worst))}</span>'
            f"</div>"
        )
    return "".join(items)


__all__ = ["build_map", "location_panel_html"]
