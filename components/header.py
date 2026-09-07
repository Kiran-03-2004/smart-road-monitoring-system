"""
components/header.py
====================
Top application header: product title, live date/time, system-health status
indicator, notification bell with unread count, and a "last updated" chip.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

import streamlit as st

import config


def _health_status(critical: int) -> tuple[str, str]:
    """Map critical-alert count to a status ``(css_class, label)``."""
    if critical == 0:
        return "", "All Systems Operational"
    if critical < 3:
        return "warn", "Attention Required"
    return "crit", "Critical Alerts Active"


def render_header(
    critical_alerts: int = 0,
    notifications: int = 0,
    last_updated_seconds: Optional[int] = None,
    subtitle: str = "Live Monitoring Dashboard",
) -> None:
    """Render the top header bar.

    Args:
        critical_alerts: Number of active critical alerts (drives status dot).
        notifications: Unread notification count (drives the bell badge).
        last_updated_seconds: Seconds since last refresh, if known.
        subtitle: Secondary line under the product title.
    """
    now = datetime.now()
    date_str = now.strftime("%a, %d %b %Y")
    time_str = now.strftime("%H:%M:%S")
    status_cls, status_label = _health_status(critical_alerts)

    updated_txt = (
        f"{last_updated_seconds}s ago"
        if last_updated_seconds is not None
        else "just now"
    )

    badge_html = (
        f'<span class="badge">{notifications}</span>' if notifications > 0 else ""
    )

    # Built as unindented, concatenated HTML. Leading whitespace would make
    # Streamlit's markdown treat this as a code block and print it verbatim.
    header_html = (
        '<div class="app-header">'
        '<div class="title-block">'
        f"<h1>🛣️ {html.escape(config.APP_SHORT_NAME)}</h1>"
        f"<p>{html.escape(subtitle)} &bull; {html.escape(config.ORGANIZATION)}</p>"
        "</div>"
        '<div class="header-meta">'
        f'<div class="header-chip">📅 <b>{date_str}</b></div>'
        f'<div class="header-chip">🕒 <b>{time_str}</b></div>'
        '<div class="header-chip">'
        f'<span class="status-dot {status_cls}"></span>'
        f"<b>{html.escape(status_label)}</b></div>"
        f'<div class="header-chip">Last Updated: <b>{updated_txt}</b></div>'
        f'<div class="notif-bell">🔔{badge_html}</div>'
        "</div>"
        "</div>"
    )
    st.markdown(" ".join(header_html.split()), unsafe_allow_html=True)


__all__ = ["render_header"]
