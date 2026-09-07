"""
utils/data_loader.py
====================
Cached data-access and enrichment layer for the enterprise dashboard.

Responsibilities:
    * Load detections/trips/reports from the existing SQLite database.
    * Enrich raw detections with derived, presentation-friendly fields
      (estimated width/depth in cm, area, status, priority).
    * Aggregate timelines and monthly trends for the charts.
    * Build the alert feed and AI insight recommendations.

All read paths are cached with a short TTL so the auto-refreshing dashboard
stays responsive without hammering SQLite.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

import config
from src.database import Database
from utils.scoring import (
    HealthScore,
    average_severity,
    compute_health,
)

SEVERITY_ORDER = ["Critical", "High", "Medium", "Low"]


# ----------------------------------------------------------------------
# Cached resources / reads
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_db() -> Database:
    """Return a process-wide Database instance."""
    return Database()


@st.cache_data(ttl=4, show_spinner=False)
def load_detections(trip_id: Optional[int] = None) -> pd.DataFrame:
    """Load enriched detections as a DataFrame (cached, short TTL)."""
    db = get_db()
    df = db.detections_dataframe(trip_id)
    return enrich_detections(df)


@st.cache_data(ttl=10, show_spinner=False)
def load_trips() -> pd.DataFrame:
    """Load all trips (cached)."""
    return get_db().trips_dataframe()


@st.cache_data(ttl=10, show_spinner=False)
def load_reports() -> pd.DataFrame:
    """Load report history (cached)."""
    return get_db().reports_dataframe()


# ----------------------------------------------------------------------
# Enrichment
# ----------------------------------------------------------------------
def enrich_detections(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived presentation fields to a detections DataFrame.

    Derived columns:
        width_cm, depth_cm  - estimated physical dimensions from bbox area.
        area_px             - alias of bbox_area (kept explicit for the table).
        status              - workflow state derived from severity.
        priority            - maintenance priority derived from severity.
        detection_time      - parsed timestamp.
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "id", "trip_id", "track_id", "timestamp", "latitude",
                "longitude", "location", "severity", "confidence",
                "bbox_area", "image_path", "width_cm", "depth_cm",
                "area_px", "status", "priority", "detection_time",
            ]
        )

    df = df.copy()
    df["bbox_area"] = pd.to_numeric(df.get("bbox_area", 0), errors="coerce").fillna(0.0)
    df["area_px"] = df["bbox_area"].round(0).astype(int)

    # Estimate physical dimensions. Bounding-box area (px) is mapped to an
    # approximate real-world footprint; depth scales with the square root of
    # area. These are heuristic estimates for reporting, not survey-grade.
    side = np.sqrt(df["bbox_area"].clip(lower=1.0))
    df["width_cm"] = (side * 0.18).round(1)          # px side -> ~cm width
    df["depth_cm"] = (np.sqrt(side) * 1.35).round(1)  # sub-linear depth proxy

    df["status"] = df["severity"].map(_status_for_severity).fillna("Detected")
    df["priority"] = df["severity"].map(_priority_for_severity).fillna("P4 - Low")

    df["detection_time"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["location"] = df["location"].fillna("Unknown Location")
    df["confidence"] = pd.to_numeric(df.get("confidence", 0), errors="coerce").fillna(0.0)

    return df


def _status_for_severity(severity: str) -> str:
    return {
        "Critical": "Repair Required",
        "High": "Pending Repair",
        "Medium": "Under Review",
        "Low": "Monitoring",
    }.get(severity, "Detected")


def _priority_for_severity(severity: str) -> str:
    return {
        "Critical": "P1 - Urgent",
        "High": "P2 - High",
        "Medium": "P3 - Medium",
        "Low": "P4 - Low",
    }.get(severity, "P4 - Low")


# ----------------------------------------------------------------------
# Aggregations
# ----------------------------------------------------------------------
def severity_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Return counts per severity level, guaranteeing all four keys."""
    counts = {level: 0 for level in SEVERITY_ORDER}
    if df is None or df.empty:
        return counts
    for level, n in df["severity"].value_counts().items():
        if level in counts:
            counts[level] = int(n)
    return counts


def health_from_df(df: pd.DataFrame) -> HealthScore:
    """Compute a :class:`HealthScore` from a detections DataFrame."""
    return compute_health(severity_counts(df))


def kpi_summary(df: pd.DataFrame) -> Dict[str, object]:
    """Build the six-KPI summary payload used by the KPI card row."""
    counts = severity_counts(df)
    health = compute_health(counts)
    avg_num, avg_label = average_severity(counts)

    total = int(len(df)) if df is not None else 0
    critical = counts["Critical"]
    # Pending repairs = Critical + High (need action); Resolved = Low.
    pending = counts["Critical"] + counts["High"]
    resolved = counts["Low"]

    return {
        "total": total,
        "health_score": health.score,
        "health_rating": health.rating,
        "health_color": health.color,
        "critical": critical,
        "pending": pending,
        "resolved": resolved,
        "avg_severity_num": avg_num,
        "avg_severity_label": avg_label,
    }


def timeline_series(df: pd.DataFrame, freq: str = "h") -> pd.DataFrame:
    """Aggregate detections into a time series (count per bucket)."""
    if df is None or df.empty or df["detection_time"].isna().all():
        return pd.DataFrame({"time": [], "count": []})
    series = (
        df.dropna(subset=["detection_time"])
        .set_index("detection_time")
        .resample(freq)
        .size()
        .reset_index(name="count")
        .rename(columns={"detection_time": "time"})
    )
    return series


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate detections per month per severity for the trends chart."""
    if df is None or df.empty or df["detection_time"].isna().all():
        return pd.DataFrame({"month": [], "severity": [], "count": []})
    tmp = df.dropna(subset=["detection_time"]).copy()
    tmp["month"] = tmp["detection_time"].dt.to_period("M").dt.to_timestamp()
    grouped = (
        tmp.groupby(["month", "severity"]).size().reset_index(name="count")
    )
    return grouped


def health_trend(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Compute a running road-health score over time for the area chart."""
    if df is None or df.empty or df["detection_time"].isna().all():
        return pd.DataFrame({"time": [], "score": []})

    tmp = df.dropna(subset=["detection_time"]).sort_values("detection_time")
    tmp = tmp.set_index("detection_time")
    rows = []
    for ts, bucket in tmp.resample(freq):
        if bucket.empty:
            continue
        score = compute_health(severity_counts(bucket)).score
        rows.append({"time": ts, "score": score})
    return pd.DataFrame(rows) if rows else pd.DataFrame({"time": [], "score": []})


def location_summary(df: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    """Summarise the most-affected locations for the map side panel."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["location", "count", "worst"])
    worst_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    grp = df.groupby("location")
    out = grp.agg(count=("id", "size")).reset_index()
    worst = grp["severity"].agg(
        lambda s: max(s, key=lambda x: worst_rank.get(x, 0))
    )
    out["worst"] = out["location"].map(worst)
    out = out.sort_values("count", ascending=False).head(top)
    return out


# ----------------------------------------------------------------------
# Alerts + AI insights
# ----------------------------------------------------------------------
def build_alerts(df: pd.DataFrame, limit: int = 8) -> List[Dict[str, object]]:
    """Build a list of alert payloads (most severe + most recent first)."""
    if df is None or df.empty:
        return []
    rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
    tmp = df.copy()
    tmp["rank"] = tmp["severity"].map(rank).fillna(0)
    tmp = tmp.sort_values(["rank", "detection_time"], ascending=[False, False])
    tmp = tmp[tmp["severity"].isin(["Critical", "High"])].head(limit)

    alerts: List[Dict[str, object]] = []
    for row in tmp.itertuples():
        alerts.append(
            {
                "severity": row.severity,
                "location": getattr(row, "location", "Unknown"),
                "depth": getattr(row, "depth_cm", 0.0),
                "width": getattr(row, "width_cm", 0.0),
                "time": getattr(row, "detection_time", None),
                "confidence": getattr(row, "confidence", 0.0),
            }
        )
    return alerts


def ai_insights(df: pd.DataFrame) -> List[Dict[str, str]]:
    """Generate human-readable AI-style insights and recommendations."""
    counts = severity_counts(df)
    health = compute_health(counts)
    total = sum(counts.values())
    insights: List[Dict[str, str]] = []

    if total == 0:
        return [
            {
                "type": "info",
                "title": "No detections yet",
                "body": "Run a monitoring session to populate analytics and "
                "generate maintenance recommendations.",
            }
        ]

    # Hotspot analysis.
    locs = location_summary(df, top=3)
    if not locs.empty:
        names = ", ".join(locs["location"].astype(str).tolist())
        insights.append(
            {
                "type": "priority",
                "title": "Maintenance hotspots identified",
                "body": f"Road health is most impacted around {names}. "
                "Prioritise inspection and repair crews for these corridors.",
            }
        )

    # Critical trend.
    if counts["Critical"] > 0:
        insights.append(
            {
                "type": "risk",
                "title": "Critical defects present",
                "body": f"{counts['Critical']} critical pothole(s) detected, "
                f"driving the road-health score down to {health.score:.0f} "
                f"({health.rating}). Immediate intervention is recommended "
                "within 24-48 hours to mitigate safety risk.",
            }
        )
    elif counts["High"] > 0:
        insights.append(
            {
                "type": "action",
                "title": "High-severity defects accumulating",
                "body": f"{counts['High']} high-severity pothole(s) require "
                "scheduled repair within the current maintenance window to "
                "prevent escalation to critical.",
            }
        )
    else:
        insights.append(
            {
                "type": "info",
                "title": "Conditions stable",
                "body": f"No critical defects detected. Road-health score is "
                f"{health.score:.0f} ({health.rating}). Continue routine "
                "monitoring.",
            }
        )

    return insights


__all__ = [
    "SEVERITY_ORDER",
    "get_db",
    "load_detections",
    "load_trips",
    "load_reports",
    "enrich_detections",
    "severity_counts",
    "health_from_df",
    "kpi_summary",
    "timeline_series",
    "monthly_trend",
    "health_trend",
    "location_summary",
    "build_alerts",
    "ai_insights",
]
