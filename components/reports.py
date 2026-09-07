"""
components/reports.py
=====================
Detection management table and report/export tools.

    * render_detection_table - searchable, filterable, sortable, paginated
      table of detections with a CSV export button.
    * render_report_tools     - generate + download a municipal PDF report and
      show report history.

The table presents the derived, presentation-ready columns produced by
:func:`utils.data_loader.enrich_detections`.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st

from utils.data_loader import get_db

# Columns shown in the management table (order matters).
_TABLE_COLUMNS = [
    "id", "location", "severity", "width_cm", "depth_cm",
    "area_px", "detection_time", "status", "priority", "confidence",
]
_COLUMN_LABELS = {
    "id": "ID",
    "location": "Location",
    "severity": "Severity",
    "width_cm": "Width (cm)",
    "depth_cm": "Depth (cm)",
    "area_px": "Area (px)",
    "detection_time": "Detection Time",
    "status": "Status",
    "priority": "Priority",
    "confidence": "Confidence",
}


def render_detection_table(df: pd.DataFrame, page_size: int = 10) -> None:
    """Render the interactive detection management table.

    Args:
        df: Enriched detections DataFrame.
        page_size: Default rows per page.
    """
    if df is None or df.empty:
        st.info("No detections recorded yet.")
        return

    # ---- Filter / search controls ----
    c1, c2, c3, c4 = st.columns([2.4, 1.4, 1.4, 1])
    with c1:
        search = st.text_input("🔍 Search location", key="tbl_search", placeholder="e.g. MG Road")
    with c2:
        sev_filter = st.multiselect(
            "Severity",
            ["Critical", "High", "Medium", "Low"],
            default=[],
            key="tbl_sev",
        )
    with c3:
        sort_col = st.selectbox(
            "Sort by",
            ["detection_time", "severity", "depth_cm", "area_px", "confidence"],
            key="tbl_sort",
        )
    with c4:
        ascending = st.toggle("Asc", value=False, key="tbl_asc")

    view = df.copy()
    if search:
        view = view[view["location"].astype(str).str.contains(search, case=False, na=False)]
    if sev_filter:
        view = view[view["severity"].isin(sev_filter)]

    # Sort (severity uses a logical rank, not alphabetical).
    if sort_col == "severity":
        rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        view = view.assign(_r=view["severity"].map(rank)).sort_values(
            "_r", ascending=ascending
        ).drop(columns="_r")
    else:
        view = view.sort_values(sort_col, ascending=ascending, na_position="last")

    total_rows = len(view)
    if total_rows == 0:
        st.warning("No detections match the current filters.")
        return

    # ---- Pagination ----
    total_pages = max(1, -(-total_rows // page_size))  # ceil div
    pcol1, pcol2 = st.columns([1, 3])
    with pcol1:
        page = st.number_input(
            "Page", min_value=1, max_value=total_pages, value=1, step=1, key="tbl_page"
        )
    with pcol2:
        st.caption(
            f"Showing page {page} of {total_pages} · {total_rows} record(s)"
        )
    start = (int(page) - 1) * page_size
    page_df = view.iloc[start : start + page_size]

    # ---- Display ----
    display_cols = [c for c in _TABLE_COLUMNS if c in page_df.columns]
    show = page_df[display_cols].rename(columns=_COLUMN_LABELS)
    st.dataframe(
        show,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0.0, max_value=1.0, format="%.0f%%"
            ),
        },
    )

    # ---- Export (full filtered set, not just the page) ----
    export_cols = [c for c in _TABLE_COLUMNS if c in view.columns]
    csv = view[export_cols].rename(columns=_COLUMN_LABELS).to_csv(index=False)
    st.download_button(
        "⬇️ Export CSV",
        data=csv,
        file_name="pothole_detections.csv",
        mime="text/csv",
        key="tbl_export",
    )


def render_report_tools(
    detections: List[dict],
    source: str,
    destination: str,
    trip_id: Optional[int],
) -> None:
    """Generate a municipal PDF report and show report history."""
    if st.button("📄 Generate Municipal PDF Report", key="gen_pdf"):
        try:
            from src.report_generator import generate_report

            path = generate_report(
                detections,
                source=source,
                destination=destination,
                trip_id=trip_id,
                database=get_db(),
            )
            st.success("Report generated successfully.")
            with open(path, "rb") as handle:
                st.download_button(
                    "⬇️ Download PDF",
                    data=handle.read(),
                    file_name=path.split("\\")[-1].split("/")[-1],
                    mime="application/pdf",
                    key="dl_pdf",
                )
        except Exception as exc:  # pragma: no cover
            st.error(f"Could not generate report: {exc}")

    st.markdown('<div class="section-title"><span class="accent-bar"></span>'
                'Report History</div>', unsafe_allow_html=True)
    reports = get_db().reports_dataframe()
    if reports.empty:
        st.info("No reports generated yet.")
    else:
        st.dataframe(reports, use_container_width=True, hide_index=True)


__all__ = ["render_detection_table", "render_report_tools"]
