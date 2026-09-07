"""
app.py
======
Smart Road Monitor - Enterprise Dashboard (entry point).

A production-grade Smart City road-monitoring platform built on Streamlit.
This module is the application shell: it injects the custom theme, renders the
professional sidebar navigation, wires the reusable components together, and
routes between pages. Heavy CV dependencies (YOLO, OpenCV) are imported lazily
so the dashboard stays fast and degrades gracefully.

Pages: Dashboard · Live Monitoring · Road Analytics · Map View · Reports ·
       Alerts · Settings.

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

import config
from components import alerts as alerts_ui
from components import charts as charts_ui
from components import kpi_cards as kpi_ui
from components import map_view as map_ui
from components import reports as reports_ui
from components.header import render_header
from utils import data_loader as data
from utils.scoring import compute_health

# ----------------------------------------------------------------------
# Page config MUST be the first Streamlit call.
# ----------------------------------------------------------------------
st.set_page_config(
    page_title=f"{config.APP_SHORT_NAME} · Dashboard",
    page_icon="🛣️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_ASSETS = config.BASE_DIR / "assets" / "styles.css"

# Optional dependencies (degrade gracefully).
try:
    from streamlit_folium import st_folium
    _HAS_FOLIUM = True
except Exception:  # pragma: no cover
    _HAS_FOLIUM = False

try:
    from streamlit_autorefresh import st_autorefresh
    _HAS_AUTOREFRESH = True
except Exception:  # pragma: no cover
    _HAS_AUTOREFRESH = False


# ----------------------------------------------------------------------
# Theme + helpers
# ----------------------------------------------------------------------
def inject_css() -> None:
    """Inject the custom stylesheet once per run."""
    try:
        css = _ASSETS.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except OSError:
        st.warning("Theme stylesheet not found; using default styling.")


def section_title(text: str) -> None:
    """Render a styled section header."""
    st.markdown(
        f'<div class="section-title"><span class="accent-bar"></span>{text}</div>',
        unsafe_allow_html=True,
    )


def _tick_last_updated() -> int:
    """Track seconds since the last data refresh via session state."""
    now = time.time()
    last = st.session_state.get("_last_update_ts", now)
    st.session_state["_last_update_ts"] = now
    return max(0, int(now - last))


def _remember_summary(summary: dict) -> Optional[dict]:
    """Store the previous KPI summary so trend deltas can be computed."""
    prev = st.session_state.get("_prev_summary")
    st.session_state["_prev_summary"] = summary
    return prev


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
def page_dashboard(df: pd.DataFrame) -> None:
    summary = data.kpi_summary(df)
    prev = _remember_summary(summary)
    kpi_ui.render_kpis(summary, previous=prev)

    counts = data.severity_counts(df)

    # Charts row 1: distribution + share.
    c1, c2 = st.columns([1.4, 1])
    with c1:
        section_title("Severity Distribution")
        st.plotly_chart(charts_ui.severity_bar(counts), use_container_width=True)
    with c2:
        section_title("Severity Share")
        st.plotly_chart(charts_ui.severity_donut(counts), use_container_width=True)

    # Charts row 2: health trend + detection timeline.
    c3, c4 = st.columns(2)
    with c3:
        section_title("Road Health Trend")
        st.plotly_chart(
            charts_ui.health_area(data.health_trend(df)), use_container_width=True
        )
    with c4:
        section_title("Detection Timeline")
        st.plotly_chart(
            charts_ui.detection_timeline(data.timeline_series(df)),
            use_container_width=True,
        )

    # AI insights + recent alerts.
    c5, c6 = st.columns([1.3, 1])
    with c5:
        section_title("AI Insights")
        alerts_ui.render_ai_insights(data.ai_insights(df))
    with c6:
        section_title("Recent Alerts")
        alerts_ui.render_alerts(data.build_alerts(df, limit=4))


def page_live(df: pd.DataFrame) -> None:
    section_title("Live Monitoring")
    st.caption(
        "Run detection on an uploaded image/video or the local webcam. "
        "Confirmed potholes are de-duplicated via tracking and stored with "
        "GPS + reverse-geocoded location."
    )

    mode = st.radio(
        "Input source",
        ["Image upload", "Video upload", "Webcam (local run only)"],
        horizontal=True,
    )
    col_a, col_b = st.columns(2)
    with col_a:
        source = st.text_input("Source label", value="Field Survey")
    with col_b:
        destination = st.text_input("Destination label", value="City Depot")

    try:
        detector = _get_detector()
    except Exception as exc:  # pragma: no cover
        st.error(f"Could not load the detection model: {exc}")
        return

    if mode == "Image upload":
        _live_image(detector, source, destination)
    elif mode == "Video upload":
        _live_video(detector, source, destination)
    else:
        _live_webcam(detector, source, destination)


def page_analytics(df: pd.DataFrame) -> None:
    counts = data.severity_counts(df)
    health = compute_health(counts)

    c1, c2 = st.columns([1, 1.4])
    with c1:
        section_title("Road Health Score")
        st.plotly_chart(
            charts_ui.health_gauge(health.score, health.color),
            use_container_width=True,
        )
        st.markdown(
            f'<div class="glass-card" style="text-align:center;">'
            f'<div style="font-size:22px;font-weight:800;color:{health.color};">'
            f"{health.rating}</div>"
            f'<div style="color:#94A3B8;font-size:13px;margin-top:4px;">'
            f"Priority: {health.priority} · Risk: {health.risk}</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        section_title("Monthly Trends")
        st.plotly_chart(
            charts_ui.monthly_trends(data.monthly_trend(df)),
            use_container_width=True,
        )

    c3, c4 = st.columns(2)
    with c3:
        section_title("Severity Distribution")
        st.plotly_chart(charts_ui.severity_bar(counts), use_container_width=True)
    with c4:
        section_title("Detection Timeline")
        st.plotly_chart(
            charts_ui.detection_timeline(data.timeline_series(df)),
            use_container_width=True,
        )


def page_map(df: pd.DataFrame) -> None:
    section_title("Map View")
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        show_markers = st.toggle("Markers", value=True)
    with ctrl2:
        show_heatmap = st.toggle("Heatmap", value=True)
    with ctrl3:
        show_route = st.toggle("Route line", value=False)

    map_col, panel_col = st.columns([2.4, 1])
    with map_col:
        if not _HAS_FOLIUM:
            st.warning("Install streamlit-folium to view the interactive map.")
        else:
            fmap = map_ui.build_map(
                df,
                show_markers=show_markers,
                show_heatmap=show_heatmap,
                show_route=show_route,
            )
            st_folium(fmap, width=None, height=560, returned_objects=[])
    with panel_col:
        section_title("Detected Locations")
        loc_df = data.location_summary(df, top=10)
        st.markdown(map_ui.location_panel_html(loc_df), unsafe_allow_html=True)


def page_reports(df: pd.DataFrame) -> None:
    section_title("Detection Management")
    reports_ui.render_detection_table(df, page_size=10)

    st.divider()
    section_title("Municipal Reporting")
    c1, c2 = st.columns(2)
    with c1:
        source = st.text_input("Source", value="Field Survey", key="rep_src")
    with c2:
        destination = st.text_input("Destination", value="City Depot", key="rep_dst")

    detections = data.get_db().get_detections()
    reports_ui.render_report_tools(detections, source, destination, trip_id=None)


def page_alerts(df: pd.DataFrame) -> None:
    counts = data.severity_counts(df)
    c1, c2 = st.columns([1.4, 1])
    with c1:
        section_title("Alert Center")
        alerts_ui.render_alerts(data.build_alerts(df, limit=12))
    with c2:
        section_title("AI Recommendations")
        alerts_ui.render_ai_insights(data.ai_insights(df))
        section_title("High Priority Roads")
        alerts_ui.render_priority_list(data.location_summary(df, top=6))


def page_settings(df: pd.DataFrame) -> None:
    section_title("Settings & System")
    # Build the whole card as one HTML string so the wrapper div actually
    # contains its content (separate st.write calls would render outside it).
    model_ok = "✅" if config.MODEL_PATH.exists() else "❌"
    st.markdown(
        '<div class="glass-card">'
        f"<b>Application:</b> {config.APP_NAME}<br>"
        f"<b>Version:</b> {config.APP_VERSION}<br>"
        f"<b>Organization:</b> {config.ORGANIZATION}<br>"
        f"<b>Model present:</b> {model_ok}<br>"
        f"<b>Model path:</b> <code>{config.DETECTION.model_path}</code><br>"
        f"<b>Device:</b> {config.DETECTION.device}"
        "</div>",
        unsafe_allow_html=True,
    )

    section_title("Scoring Model")
    from utils.scoring import SCORE_WEIGHTS

    st.json(SCORE_WEIGHTS)
    st.caption(
        "Bands: 90-100 Excellent · 75-89 Good · 60-74 Moderate · "
        "40-59 Poor · 0-39 Critical"
    )

    section_title("Data")
    st.write(f"Detections: **{len(df)}**")
    st.write(f"Trips: **{len(data.load_trips())}**")
    st.caption(f"Database: `{config.DATABASE_PATH}`")


# ----------------------------------------------------------------------
# Live monitoring helpers (lazy CV imports)
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading detection model...")
def _get_detector():
    from src.detector import PotholeDetector

    return PotholeDetector()


def _live_image(detector, source, destination) -> None:
    import cv2
    import numpy as np

    uploaded = st.file_uploader("Upload a road image", type=["jpg", "jpeg", "png"])
    if uploaded is None:
        return

    file_bytes = np.frombuffer(uploaded.read(), dtype=np.uint8)
    frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if frame is None:
        st.error("Could not read the uploaded image.")
        return

    with st.spinner("Detecting..."):
        detections = detector.detect(frame)
        annotated = detector.annotate(frame, detections)

    st.image(
        cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
        caption=f"{len(detections)} detection(s)",
        use_container_width=True,
    )

    if detections and st.button("💾 Save detections to database"):
        db = data.get_db()
        from src.geocoder import reverse_geocode
        from src.gps_tracker import create_gps_tracker

        trip_id = db.create_trip(source=source, destination=destination)
        gps = create_gps_tracker()
        for det in detections:
            lat, lon = gps.get_current_location()
            location = reverse_geocode(lat, lon).summary()
            db.insert_detection(
                trip_id=trip_id, track_id=None, latitude=lat, longitude=lon,
                location=location, severity=det.severity,
                confidence=det.confidence, bbox_area=det.area,
            )
        health = compute_health(db.get_severity_counts(trip_id))
        db.finalize_trip(trip_id, health.total, health.score, destination)
        st.cache_data.clear()
        st.success(f"Saved {len(detections)} detection(s) to trip #{trip_id}.")


def _live_video(detector, source, destination) -> None:
    import tempfile

    import cv2

    uploaded = st.file_uploader("Upload a road video", type=["mp4", "avi", "mov", "mkv"])
    max_frames = st.slider("Max frames to process", 30, 900, 300, step=30)
    if uploaded is None or not st.button("▶️ Run detection"):
        return

    from src.gps_tracker import create_gps_tracker
    from src.tracker import ObjectTracker

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    db = data.get_db()
    trip_id = db.create_trip(source=source, destination=destination)
    gps = create_gps_tracker()
    tracker = ObjectTracker()

    capture = cv2.VideoCapture(tmp_path)
    frame_slot = st.empty()
    metric_slot = st.empty()
    progress = st.progress(0.0)

    frames = 0
    total_new = 0
    try:
        while frames < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            result = detector.process_frame(
                frame, tracker=tracker, database=db, gps=gps, trip_id=trip_id
            )
            frames += 1
            total_new += result.new_potholes
            if frames % 3 == 0:
                frame_slot.image(
                    cv2.cvtColor(result.frame, cv2.COLOR_BGR2RGB),
                    use_container_width=True,
                )
                metric_slot.metric("Potholes counted", total_new)
            progress.progress(min(1.0, frames / max_frames))
    finally:
        capture.release()

    health = compute_health(db.get_severity_counts(trip_id))
    db.finalize_trip(trip_id, health.total, health.score, destination)
    st.cache_data.clear()
    st.success(
        f"Processed {frames} frames · counted {total_new} unique pothole(s) · "
        f"road health {health.score:.0f} ({health.rating})."
    )


def _live_webcam(detector, source, destination) -> None:
    st.info(
        "Webcam capture requires running the app locally (browsers block "
        "camera access in hosted sandboxes)."
    )
    max_frames = st.slider("Frames to capture", 30, 600, 150, step=30)
    cam_index = st.number_input("Webcam index", min_value=0, value=0, step=1)
    if not st.button("🎥 Start webcam detection"):
        return

    import cv2

    from src.gps_tracker import create_gps_tracker
    from src.tracker import ObjectTracker

    db = data.get_db()
    trip_id = db.create_trip(source=source, destination=destination)
    gps = create_gps_tracker()
    tracker = ObjectTracker()

    capture = cv2.VideoCapture(int(cam_index))
    if not capture.isOpened():
        st.error("Could not open webcam. Check the device index/permissions.")
        return

    frame_slot = st.empty()
    metric_slot = st.empty()
    progress = st.progress(0.0)
    frames = 0
    total_new = 0
    try:
        while frames < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            result = detector.process_frame(
                frame, tracker=tracker, database=db, gps=gps, trip_id=trip_id
            )
            frames += 1
            total_new += result.new_potholes
            frame_slot.image(
                cv2.cvtColor(result.frame, cv2.COLOR_BGR2RGB),
                use_container_width=True,
            )
            metric_slot.metric("Potholes counted", total_new)
            progress.progress(min(1.0, frames / max_frames))
            time.sleep(0.01)
    finally:
        capture.release()

    health = compute_health(db.get_severity_counts(trip_id))
    db.finalize_trip(trip_id, health.total, health.score, destination)
    st.cache_data.clear()
    st.success(
        f"Captured {frames} frames · counted {total_new} unique pothole(s) · "
        f"road health {health.score:.0f} ({health.rating})."
    )


# ----------------------------------------------------------------------
# Sidebar + routing
# ----------------------------------------------------------------------
_PAGES = {
    "Dashboard": ("📊", page_dashboard),
    "Live Monitoring": ("🎥", page_live),
    "Road Analytics": ("📈", page_analytics),
    "Map View": ("🗺️", page_map),
    "Reports": ("📄", page_reports),
    "Alerts": ("🚨", page_alerts),
    "Settings": ("⚙️", page_settings),
}


def render_sidebar() -> str:
    """Render the branded sidebar and return the selected page name."""
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand">'
            '<div class="logo">🛣️</div>'
            '<div class="brand-text">'
            f'<div class="brand-title">{config.APP_SHORT_NAME}</div>'
            '<div class="brand-sub">Smart City Platform</div>'
            "</div></div>",
            unsafe_allow_html=True,
        )

        selection = st.radio(
            "Navigation",
            list(_PAGES.keys()),
            format_func=lambda name: f"{_PAGES[name][0]}  {name}",
            label_visibility="collapsed",
        )

        st.divider()
        auto = st.toggle("🔄 Auto-refresh (5s)", value=False)
        if auto and _HAS_AUTOREFRESH:
            st_autorefresh(interval=5000, key="auto_refresh")
        elif auto and not _HAS_AUTOREFRESH:
            st.caption("Install streamlit-autorefresh for live updates.")

        if not config.MODEL_PATH.exists():
            st.error("Model weights not found in model/.")
        st.caption(f"v{config.APP_VERSION}")
    return selection


def main() -> None:
    inject_css()
    selection = render_sidebar()

    try:
        df = data.load_detections()
        summary = data.kpi_summary(df)
        render_header(
            critical_alerts=summary["critical"],
            notifications=summary["pending"],
            last_updated_seconds=_tick_last_updated(),
            subtitle=f"Live Monitoring Dashboard · {selection}",
        )
        _PAGES[selection][1](df)
    except Exception as exc:  # pragma: no cover - surfaced to the user
        st.error(f"Something went wrong while rendering **{selection}**:\n\n{exc}")
        with st.expander("Technical details"):
            import traceback

            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
