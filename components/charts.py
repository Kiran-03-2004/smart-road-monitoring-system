"""
components/charts.py
====================
Plotly visualizations for the dashboard, all sharing a consistent dark theme:

    * severity_bar        - severity distribution (bar)
    * severity_donut      - severity share (donut)
    * monthly_trends      - stacked monthly trend line
    * health_area         - road-health score over time (area)
    * detection_timeline  - live detection count over time (line)
    * health_gauge        - color-coded road-health gauge

Each function returns a ``plotly.graph_objects.Figure`` so pages can place
them with ``st.plotly_chart(fig, use_container_width=True)``.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from utils.scoring import SEVERITY_COLORS

# Shared theme tokens.
_PAPER = "rgba(0,0,0,0)"
_PLOT = "rgba(0,0,0,0)"
_GRID = "rgba(148,163,184,0.12)"
_TEXT = "#94A3B8"
_FONT = "Inter, Segoe UI, sans-serif"
_SEV_ORDER = ["Critical", "High", "Medium", "Low"]


def _base_layout(fig: go.Figure, height: int = 320, showlegend: bool = False) -> go.Figure:
    """Apply the shared dark theme to a figure."""
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        paper_bgcolor=_PAPER,
        plot_bgcolor=_PLOT,
        font=dict(family=_FONT, color=_TEXT, size=12),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18),
        hoverlabel=dict(bgcolor="#1E293B", font_size=12, font_family=_FONT),
    )
    fig.update_xaxes(gridcolor=_GRID, zeroline=False, linecolor=_GRID)
    fig.update_yaxes(gridcolor=_GRID, zeroline=False, linecolor=_GRID)
    return fig


def severity_bar(counts: dict) -> go.Figure:
    """Severity distribution as a bar chart."""
    levels = _SEV_ORDER
    values = [counts.get(l, 0) for l in levels]
    fig = go.Figure(
        go.Bar(
            x=levels,
            y=values,
            marker=dict(
                color=[SEVERITY_COLORS[l] for l in levels],
                line=dict(width=0),
            ),
            text=values,
            textposition="outside",
            hovertemplate="%{x}: %{y}<extra></extra>",
        )
    )
    return _base_layout(fig, height=320)


def severity_donut(counts: dict) -> go.Figure:
    """Severity share as a modern donut chart."""
    levels = [l for l in _SEV_ORDER if counts.get(l, 0) > 0] or _SEV_ORDER
    values = [counts.get(l, 0) for l in levels]
    fig = go.Figure(
        go.Pie(
            labels=levels,
            values=values,
            hole=0.62,
            marker=dict(colors=[SEVERITY_COLORS[l] for l in levels]),
            textinfo="percent",
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )
    )
    total = sum(values)
    fig.add_annotation(
        text=f"<b>{total}</b><br><span style='font-size:11px'>Total</span>",
        showarrow=False,
        font=dict(size=22, color="#FFFFFF"),
    )
    return _base_layout(fig, height=320, showlegend=True)


def monthly_trends(df: pd.DataFrame) -> go.Figure:
    """Monthly detection trends per severity as a multi-line chart."""
    fig = go.Figure()
    if df is not None and not df.empty:
        for level in _SEV_ORDER:
            sub = df[df["severity"] == level]
            if sub.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sub["month"],
                    y=sub["count"],
                    mode="lines+markers",
                    name=level,
                    line=dict(color=SEVERITY_COLORS[level], width=2.5, shape="spline"),
                    marker=dict(size=6),
                    hovertemplate=f"{level}: %{{y}}<extra></extra>",
                )
            )
    return _base_layout(fig, height=340, showlegend=True)


def health_area(df: pd.DataFrame) -> go.Figure:
    """Road-health score over time as a filled area chart."""
    fig = go.Figure()
    if df is not None and not df.empty:
        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["score"],
                mode="lines",
                line=dict(color="#3B82F6", width=2.5, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(59,130,246,0.18)",
                hovertemplate="Score: %{y:.0f}<extra></extra>",
            )
        )
    fig.update_yaxes(range=[0, 100])
    return _base_layout(fig, height=320)


def detection_timeline(df: pd.DataFrame) -> go.Figure:
    """Live detection count over time as a line chart."""
    fig = go.Figure()
    if df is not None and not df.empty:
        fig.add_trace(
            go.Scatter(
                x=df["time"],
                y=df["count"],
                mode="lines",
                line=dict(color="#22C55E", width=2.5, shape="spline"),
                fill="tozeroy",
                fillcolor="rgba(34,197,94,0.14)",
                hovertemplate="%{y} detections<extra></extra>",
            )
        )
    return _base_layout(fig, height=300)


def health_gauge(score: float, color: str) -> go.Figure:
    """Color-coded road-health gauge."""
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number=dict(font=dict(size=34, color="#FFFFFF"), suffix=" / 100"),
            gauge=dict(
                axis=dict(range=[0, 100], tickcolor=_TEXT, tickfont=dict(size=10)),
                bar=dict(color=color, thickness=0.28),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                steps=[
                    dict(range=[0, 40], color="rgba(239,68,68,0.22)"),
                    dict(range=[40, 60], color="rgba(249,115,22,0.20)"),
                    dict(range=[60, 75], color="rgba(234,179,8,0.20)"),
                    dict(range=[75, 90], color="rgba(132,204,22,0.20)"),
                    dict(range=[90, 100], color="rgba(34,197,94,0.22)"),
                ],
            ),
        )
    )
    return _base_layout(fig, height=280)


__all__ = [
    "severity_bar",
    "severity_donut",
    "monthly_trends",
    "health_area",
    "detection_timeline",
    "health_gauge",
]
