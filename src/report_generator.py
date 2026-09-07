"""
report_generator.py
===================
Municipal PDF report generation using reportlab.

Produces a professional, self-contained PDF summarising a monitoring trip:

    * Title, organisation and generation metadata.
    * Trip context: source, destination, date.
    * Headline metrics: total potholes and road-health score.
    * Severity distribution table.
    * Road-health rating and maintenance recommendations.
    * Municipal maintenance priority band.

The generated report is optionally recorded in the ``reports`` table so the
dashboard can list and re-download historical reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config
from src.database import Database
from src.road_health import RoadHealthResult, compute_road_health
from src.utils import get_logger, local_now_iso, timestamp_slug

_LOGGER = get_logger(__name__)


class ReportGenerator:
    """Build municipal PDF reports from detection data."""

    def __init__(self) -> None:
        self._styles = self._build_styles()

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    def _build_styles(self):
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="ReportTitle",
                parent=styles["Title"],
                fontSize=18,
                textColor=colors.HexColor("#1a3d5c"),
                alignment=TA_CENTER,
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="Subtitle",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.HexColor("#555555"),
                alignment=TA_CENTER,
                spaceAfter=12,
            )
        )
        styles.add(
            ParagraphStyle(
                name="SectionHeader",
                parent=styles["Heading2"],
                fontSize=13,
                textColor=colors.HexColor("#1a3d5c"),
                spaceBefore=12,
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="Body",
                parent=styles["Normal"],
                fontSize=10,
                leading=15,
            )
        )
        return styles

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(
        self,
        detections: Sequence[Dict[str, object]],
        source: str = "N/A",
        destination: str = "N/A",
        trip_id: Optional[int] = None,
        database: Optional[Database] = None,
        filename: Optional[str] = None,
        road_health: Optional[RoadHealthResult] = None,
    ) -> str:
        """Generate a PDF report and return its file path.

        Args:
            detections: Sequence of detection dicts (see database layer).
            source: Trip origin label.
            destination: Trip destination label.
            trip_id: Optional trip id to associate the report record with.
            database: Optional DB used to record the generated report.
            filename: Optional output filename (defaults to a timestamped name).
            road_health: Optional precomputed road-health result; computed
                from the detections if not supplied.
        """
        severity_counts = self._count_severities(detections)
        health = road_health or compute_road_health(severity_counts)

        name = filename or f"road_report_{timestamp_slug()}.pdf"
        path = config.REPORTS_DIR / name

        doc = SimpleDocTemplate(
            str(path),
            pagesize=A4,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            title="Road Infrastructure Report",
        )

        story: List[object] = []
        story.extend(self._header())
        story.extend(self._metadata_section(source, destination))
        story.extend(self._summary_section(health))
        story.extend(self._severity_table(severity_counts))
        story.extend(self._health_section(health))
        story.extend(self._recommendations_section(health))

        doc.build(story)
        _LOGGER.info("Generated PDF report at %s", path)

        if database is not None:
            try:
                database.insert_report(
                    trip_id=trip_id,
                    file_path=str(path),
                    total_potholes=health.total_potholes,
                    road_health=health.score,
                )
            except Exception as exc:  # pragma: no cover
                _LOGGER.error("Failed to record report in DB: %s", exc)

        return str(path)

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------
    def _header(self) -> List[object]:
        return [
            Paragraph(config.APP_NAME, self._styles["ReportTitle"]),
            Paragraph(
                f"{config.ORGANIZATION} &bull; Municipal Maintenance Report",
                self._styles["Subtitle"],
            ),
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a3d5c")),
            Spacer(1, 8),
        ]

    def _metadata_section(self, source: str, destination: str) -> List[object]:
        data = [
            ["Source", source or "N/A", "Destination", destination or "N/A"],
            ["Generated", local_now_iso(), "Version", config.APP_VERSION],
        ]
        table = Table(data, colWidths=[28 * mm, 60 * mm, 30 * mm, 56 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a3d5c")),
                    ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#1a3d5c")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
                ]
            )
        )
        return [table, Spacer(1, 10)]

    def _summary_section(self, health: RoadHealthResult) -> List[object]:
        data = [
            ["Total Potholes Detected", str(health.total_potholes)],
            ["Road Health Score", f"{health.score:.1f} / 100"],
            ["Road Condition Rating", health.rating],
            ["Maintenance Priority", health.maintenance_priority],
        ]
        table = Table(data, colWidths=[90 * mm, 84 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f7")),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ]
            )
        )
        return [
            Paragraph("Executive Summary", self._styles["SectionHeader"]),
            table,
            Spacer(1, 6),
        ]

    def _severity_table(self, counts: Dict[str, int]) -> List[object]:
        header = ["Severity", "Count", "Penalty / Unit", "Total Penalty"]
        rows: List[List[str]] = [header]
        for level in config.SEVERITY_LEVELS:
            count = counts.get(level, 0)
            weight = config.SEVERITY_SCORE_WEIGHTS[level]
            rows.append([level, str(count), str(weight), str(count * weight)])

        table = Table(rows, colWidths=[44 * mm, 40 * mm, 45 * mm, 45 * mm])

        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d5c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]
        # Colour the severity cell to match the project palette.
        for idx, level in enumerate(config.SEVERITY_LEVELS, start=1):
            style.append(
                (
                    "TEXTCOLOR",
                    (0, idx),
                    (0, idx),
                    colors.HexColor(config.SEVERITY_COLORS_HEX[level]),
                )
            )
            style.append(("FONTNAME", (0, idx), (0, idx), "Helvetica-Bold"))
        table.setStyle(TableStyle(style))

        return [
            Paragraph("Severity Distribution", self._styles["SectionHeader"]),
            table,
            Spacer(1, 6),
        ]

    def _health_section(self, health: RoadHealthResult) -> List[object]:
        text = (
            f"The computed road-health score is "
            f"<b>{health.score:.1f}/100</b>, classified as "
            f"<b>{health.rating}</b>. The score reflects the weighted impact "
            f"of {health.total_potholes} de-duplicated pothole(s) detected "
            f"along the surveyed route."
        )
        return [
            Paragraph("Road Health Assessment", self._styles["SectionHeader"]),
            Paragraph(text, self._styles["Body"]),
            Spacer(1, 6),
        ]

    def _recommendations_section(self, health: RoadHealthResult) -> List[object]:
        return [
            Paragraph("Recommendations", self._styles["SectionHeader"]),
            Paragraph(health.recommendation, self._styles["Body"]),
            Spacer(1, 8),
            Paragraph(
                f"<b>Municipal Maintenance Priority:</b> {health.maintenance_priority}",
                self._styles["Body"],
            ),
            Spacer(1, 12),
            HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")),
            Paragraph(
                "This report was generated automatically by the "
                f"{config.APP_SHORT_NAME}. Figures are derived from computer-vision "
                "detections and GPS positioning along the surveyed route.",
                self._styles["Subtitle"],
            ),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _count_severities(
        detections: Sequence[Dict[str, object]]
    ) -> Dict[str, int]:
        counts: Dict[str, int] = {level: 0 for level in config.SEVERITY_LEVELS}
        for det in detections:
            severity = str(det.get("severity", ""))
            if severity in counts:
                counts[severity] += 1
        return counts


# Module-level singleton and convenience wrapper.
report_generator = ReportGenerator()


def generate_report(
    detections: Sequence[Dict[str, object]],
    source: str = "N/A",
    destination: str = "N/A",
    trip_id: Optional[int] = None,
    database: Optional[Database] = None,
) -> str:
    """Convenience wrapper around :meth:`ReportGenerator.generate`."""
    return report_generator.generate(
        detections,
        source=source,
        destination=destination,
        trip_id=trip_id,
        database=database,
    )


__all__ = ["ReportGenerator", "report_generator", "generate_report"]
