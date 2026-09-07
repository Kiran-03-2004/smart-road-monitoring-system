"""
components/alerts.py
====================
Alert center and AI insights panels.

    * render_alerts       - critical/high alert cards with location, depth,
                            and relative time.
    * render_ai_insights  - AI-style recommendation panel(s).
    * render_priority_list- ranked priority list of affected roads.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

_ACCENT = {
    "Critical": "#EF4444",
    "High": "#F97316",
    "Medium": "#EAB308",
    "Low": "#22C55E",
}
_TAG_STYLE = {
    "Critical": "background:rgba(239,68,68,0.2);color:#EF4444;",
    "High": "background:rgba(249,115,22,0.2);color:#F97316;",
    "Medium": "background:rgba(234,179,8,0.2);color:#EAB308;",
    "Low": "background:rgba(34,197,94,0.2);color:#22C55E;",
}
_ICON = {"Critical": "🚨", "High": "⚠️", "Medium": "🔶", "Low": "🟢"}


def _relative_time(ts: Optional[object]) -> str:
    """Return a compact relative time like '2 mins ago'."""
    if ts is None or pd.isna(ts):
        return "recently"
    try:
        dt = pd.to_datetime(ts)
    except Exception:
        return "recently"
    delta = datetime.now() - dt.to_pydatetime().replace(tzinfo=None)
    secs = int(delta.total_seconds())
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} hr ago"
    return f"{secs // 86400} d ago"


def render_alerts(alerts: List[Dict[str, object]]) -> None:
    """Render a stack of alert cards."""
    if not alerts:
        st.markdown(
            '<div class="alert-card" style="--accent:#22C55E;">'
            '<div class="alert-icon">✅</div>'
            '<div class="alert-body"><div class="alert-title">No active alerts</div>'
            '<div class="alert-meta">All monitored roads are within tolerance.</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    html_parts = []
    for a in alerts:
        sev = str(a.get("severity", "High"))
        accent = _ACCENT.get(sev, "#3B82F6")
        tag_style = _TAG_STYLE.get(sev, "")
        icon = _ICON.get(sev, "⚠️")
        loc = html.escape(str(a.get("location", "Unknown")))
        depth = a.get("depth", 0.0) or 0.0
        width = a.get("width", 0.0) or 0.0
        conf = (a.get("confidence", 0.0) or 0.0) * 100
        when = _relative_time(a.get("time"))

        html_parts.append(
            f'<div class="alert-card" style="--accent:{accent};">'
            f'<div class="alert-icon">{icon}</div>'
            f'<div class="alert-body">'
            f'<div class="alert-title">{loc} '
            f'<span class="alert-tag" style="{tag_style}">{sev}</span></div>'
            f'<div class="alert-meta">Depth: {depth:.1f} cm · Width: {width:.1f} cm '
            f'· Confidence: {conf:.0f}%</div>'
            f'<div class="alert-time">🕒 Detected {when}</div>'
            f"</div></div>"
        )
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_ai_insights(insights: List[Dict[str, str]]) -> None:
    """Render the AI insights panel(s)."""
    badge = {
        "priority": "Priority",
        "risk": "Risk Analysis",
        "action": "Action",
        "info": "Insight",
    }
    for ins in insights:
        kind = ins.get("type", "info")
        st.markdown(
            f'<div class="ai-panel">'
            f'<div class="ai-head">🤖 {html.escape(ins.get("title", "Insight"))} '
            f'<span class="ai-badge">{badge.get(kind, "Insight")}</span></div>'
            f'<div class="ai-body">{html.escape(ins.get("body", ""))}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def render_priority_list(loc_df: pd.DataFrame) -> None:
    """Render a ranked list of the most-affected roads."""
    if loc_df is None or loc_df.empty:
        st.info("No prioritized roads yet.")
        return
    rows = []
    for i, row in enumerate(loc_df.itertuples(), start=1):
        worst = str(getattr(row, "worst", "Low"))
        rows.append(
            f'<div class="loc-item">'
            f'<div class="loc-name">#{i} · {html.escape(str(row.location))}</div>'
            f'<span class="pill {worst.lower()}">{worst} · {int(row.count)}</span>'
            f"</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


__all__ = ["render_alerts", "render_ai_insights", "render_priority_list"]
