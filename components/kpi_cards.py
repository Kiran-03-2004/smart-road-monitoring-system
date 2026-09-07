"""
components/kpi_cards.py
=======================
KPI card row for the dashboard. Renders six premium metric cards, each with
an icon, an animated counter, a colored accent bar, and a trend indicator
(direction + percentage change).

Cards: Total Potholes, Road Health Score, Critical Alerts, Pending Repairs,
Resolved Cases, Average Severity.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import List, Optional

import streamlit as st

from src.utils import get_logger

_LOGGER = get_logger(__name__)


def render_kpi_card(
    title: str,
    value: str,
    icon: str,
    accent_color: str,
    trend: Optional[float] = None,
    suffix: str = "",
    trend_up_is_good: bool = True,
) -> None:
    """Render a single KPI card directly to the page.

    A thin, explicit wrapper around the card builder for callers that want to
    place one card at a time. Renders clean HTML via ``unsafe_allow_html``.

    Args:
        title: Card label (e.g. "Total Potholes").
        value: Primary display value.
        icon: Emoji/icon shown in the corner.
        accent_color: Hex accent colour for the bar and icon.
        trend: Optional signed percentage change.
        suffix: Optional value suffix (e.g. "/100").
        trend_up_is_good: Whether an increasing trend is positive.
    """
    kpi = KPI(
        label=title,
        value=value,
        icon=icon,
        accent=accent_color,
        trend=trend,
        trend_up_is_good=trend_up_is_good,
        suffix=suffix,
    )
    html_str = " ".join(_card_html(kpi, 0).split())
    st.markdown(html_str, unsafe_allow_html=True)


@dataclass
class KPI:
    """A single KPI card definition."""

    label: str
    value: str
    icon: str
    accent: str
    trend: Optional[float] = None      # signed percentage change
    trend_up_is_good: bool = True
    suffix: str = ""


def _trend_html(trend: Optional[float], up_is_good: bool) -> str:
    """Render the trend chip (direction + percentage)."""
    if trend is None:
        return '<span class="kpi-trend flat">—</span>'
    if abs(trend) < 0.05:
        return '<span class="kpi-trend flat">▬ 0%</span>'

    going_up = trend > 0
    good = going_up if up_is_good else not going_up
    cls = "up" if good else "down"
    arrow = "▲" if going_up else "▼"
    return f'<span class="kpi-trend {cls}">{arrow} {abs(trend):.1f}%</span>'


def _card_html(kpi: KPI, index: int) -> str:
    trend = _trend_html(kpi.trend, kpi.trend_up_is_good)
    delay = f"{index * 0.06:.2f}s"
    value = f"{html.escape(str(kpi.value))}{html.escape(kpi.suffix)}"
    # Emit as a single, unindented line. Leading whitespace makes Streamlit's
    # markdown parser treat the HTML as an indented code block (printing it
    # verbatim) instead of rendering it.
    return (
        f'<div class="kpi-card" style="--accent: {kpi.accent}; '
        f'animation-delay: {delay};">'
        f'<div class="kpi-top"><div class="kpi-icon">{kpi.icon}</div>{trend}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-label">{html.escape(kpi.label)}</div>'
        f"</div>"
    )


def render_kpis(summary: dict, previous: Optional[dict] = None) -> None:
    """Render the six-card KPI row from a summary payload.

    Args:
        summary: Output of :func:`utils.data_loader.kpi_summary`.
        previous: Optional earlier summary used to compute trend deltas.
    """
    def pct(curr: float, key: str) -> Optional[float]:
        if not previous or key not in previous:
            return None
        prev = previous.get(key) or 0
        if prev == 0:
            return None
        return (curr - prev) / prev * 100.0

    kpis: List[KPI] = [
        KPI(
            label="Total Potholes",
            value=f"{summary['total']:,}",
            icon="🕳️",
            accent="#3B82F6",
            trend=pct(summary["total"], "total"),
            trend_up_is_good=False,
        ),
        KPI(
            label="Road Health Score",
            value=f"{summary['health_score']:.0f}",
            suffix="/100",
            icon="💚",
            accent=summary["health_color"],
            trend=pct(summary["health_score"], "health_score"),
            trend_up_is_good=True,
        ),
        KPI(
            label="Critical Alerts",
            value=f"{summary['critical']:,}",
            icon="🚨",
            accent="#EF4444",
            trend=pct(summary["critical"], "critical"),
            trend_up_is_good=False,
        ),
        KPI(
            label="Pending Repairs",
            value=f"{summary['pending']:,}",
            icon="🛠️",
            accent="#F97316",
            trend=pct(summary["pending"], "pending"),
            trend_up_is_good=False,
        ),
        KPI(
            label="Resolved Cases",
            value=f"{summary['resolved']:,}",
            icon="✅",
            accent="#22C55E",
            trend=pct(summary["resolved"], "resolved"),
            trend_up_is_good=True,
        ),
        KPI(
            label="Average Severity",
            value=summary["avg_severity_label"],
            icon="📊",
            accent="#EAB308",
        ),
    ]

    _render_grid(kpis)


def _render_grid(kpis: List[KPI]) -> None:
    """Render the KPI grid with a native-widget fallback on failure.

    The assembled HTML is collapsed to a single line with no leading
    whitespace or newlines, which guarantees Streamlit's markdown renderer
    treats it as HTML (via ``unsafe_allow_html``) rather than as an indented
    code block.
    """
    try:
        cards = "".join(_card_html(k, i) for i, k in enumerate(kpis))
        grid = f'<div class="kpi-grid">{cards}</div>'
        # Defensive: strip any stray newlines/indentation that could trip the
        # markdown code-block heuristic.
        grid = " ".join(grid.split())
        st.markdown(grid, unsafe_allow_html=True)
    except Exception as exc:  # pragma: no cover - defensive fallback
        _LOGGER.exception("KPI HTML render failed; using native fallback")
        _render_fallback(kpis)


def _render_fallback(kpis: List[KPI]) -> None:
    """Fallback KPI row using native Streamlit metrics (always renders)."""
    columns = st.columns(len(kpis))
    for col, kpi in zip(columns, kpis):
        delta = None
        if kpi.trend is not None and abs(kpi.trend) >= 0.05:
            delta = f"{kpi.trend:+.1f}%"
        col.metric(
            label=f"{kpi.icon} {kpi.label}",
            value=f"{kpi.value}{kpi.suffix}",
            delta=delta,
        )


__all__ = ["KPI", "render_kpis", "render_kpi_card"]
