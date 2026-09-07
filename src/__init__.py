"""
src package
===========
Core library for the AI-Powered Smart Road Infrastructure Monitoring and
Pothole Severity Analysis System.

Sub-modules:
    detector           - YOLOv8 inference engine
    tracker            - IoU-based multi-object tracker with de-duplication
    severity           - bounding-box-area severity classification
    gps_tracker        - simulated (replaceable) GPS source
    geocoder           - cached reverse geocoding
    road_health        - road-health scoring
    database           - SQLite persistence layer
    map_generator      - folium route maps
    heatmap_generator  - weighted folium heatmaps
    report_generator   - municipal PDF reports
    utils              - shared helpers and logging
"""

from __future__ import annotations

__version__ = "1.0.0"
