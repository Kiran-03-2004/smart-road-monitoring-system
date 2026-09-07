"""
database.py
===========
SQLite persistence layer for the Smart Road Monitoring System.

Defines three tables:

    TRIPS       - one row per monitoring session/journey.
    DETECTIONS  - one row per counted (de-duplicated) pothole.
    REPORTS     - one row per generated municipal PDF report.

The :class:`Database` class wraps all schema management and CRUD access
behind a small, typed API. Connections are created per-operation and
closed deterministically, which keeps the class safe to use from
Streamlit (multi-thread) and background detection loops alike.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

import pandas as pd

import config
from src.utils import get_logger, local_now_iso

_LOGGER = get_logger(__name__)


# ----------------------------------------------------------------------
# SQL schema
# ----------------------------------------------------------------------
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS trips (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at      TEXT NOT NULL,
        ended_at        TEXT,
        source          TEXT,
        destination     TEXT,
        start_lat       REAL,
        start_lon       REAL,
        end_lat         REAL,
        end_lon         REAL,
        total_potholes  INTEGER DEFAULT 0,
        road_health     REAL,
        notes           TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS detections (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id      INTEGER,
        track_id     INTEGER,
        timestamp    TEXT NOT NULL,
        latitude     REAL,
        longitude    REAL,
        location     TEXT,
        severity     TEXT,
        confidence   REAL,
        bbox_area    REAL,
        image_path   TEXT,
        FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_id        INTEGER,
        generated_at   TEXT NOT NULL,
        file_path      TEXT NOT NULL,
        total_potholes INTEGER,
        road_health    REAL,
        FOREIGN KEY (trip_id) REFERENCES trips (id) ON DELETE CASCADE
    )
    """,
)


class Database:
    """Thin, typed wrapper around the project's SQLite database."""

    def __init__(self, db_path: Union[str, Path, None] = None) -> None:
        """Initialise the database, creating the schema if needed.

        Args:
            db_path: Optional override for the SQLite file location.
        """
        self.db_path: Path = Path(db_path) if db_path else config.DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and guarantee it is closed."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            yield conn
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create all tables if they do not already exist."""
        try:
            with self._connect() as conn:
                for statement in _SCHEMA_STATEMENTS:
                    conn.execute(statement)
            _LOGGER.info("Database initialised at %s", self.db_path)
        except sqlite3.Error as exc:
            _LOGGER.error("Failed to initialise database: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Trips
    # ------------------------------------------------------------------
    def create_trip(
        self,
        source: str = "",
        destination: str = "",
        start_lat: Optional[float] = None,
        start_lon: Optional[float] = None,
        notes: str = "",
    ) -> int:
        """Insert a new trip and return its auto-generated id."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trips
                    (started_at, source, destination,
                     start_lat, start_lon, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    local_now_iso(),
                    source,
                    destination,
                    start_lat,
                    start_lon,
                    notes,
                ),
            )
            trip_id = int(cursor.lastrowid)
        _LOGGER.info("Created trip id=%s", trip_id)
        return trip_id

    def finalize_trip(
        self,
        trip_id: int,
        total_potholes: int,
        road_health: float,
        destination: str = "",
        end_lat: Optional[float] = None,
        end_lon: Optional[float] = None,
    ) -> None:
        """Update a trip with end-of-session summary values."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trips
                   SET ended_at = ?,
                       total_potholes = ?,
                       road_health = ?,
                       destination = COALESCE(NULLIF(?, ''), destination),
                       end_lat = ?,
                       end_lon = ?
                 WHERE id = ?
                """,
                (
                    local_now_iso(),
                    total_potholes,
                    road_health,
                    destination,
                    end_lat,
                    end_lon,
                    trip_id,
                ),
            )
        _LOGGER.info("Finalised trip id=%s (potholes=%s)", trip_id, total_potholes)

    # ------------------------------------------------------------------
    # Detections
    # ------------------------------------------------------------------
    def insert_detection(
        self,
        trip_id: Optional[int],
        track_id: Optional[int],
        latitude: Optional[float],
        longitude: Optional[float],
        location: str,
        severity: str,
        confidence: float,
        bbox_area: float,
        image_path: str = "",
        timestamp: Optional[str] = None,
    ) -> int:
        """Insert a single de-duplicated pothole detection."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO detections
                    (trip_id, track_id, timestamp, latitude, longitude,
                     location, severity, confidence, bbox_area, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    track_id,
                    timestamp or local_now_iso(),
                    latitude,
                    longitude,
                    location,
                    severity,
                    float(confidence),
                    float(bbox_area),
                    image_path,
                ),
            )
            detection_id = int(cursor.lastrowid)
        return detection_id

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    def insert_report(
        self,
        trip_id: Optional[int],
        file_path: str,
        total_potholes: int,
        road_health: float,
    ) -> int:
        """Record a generated PDF report."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports
                    (trip_id, generated_at, file_path,
                     total_potholes, road_health)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    trip_id,
                    local_now_iso(),
                    file_path,
                    total_potholes,
                    road_health,
                ),
            )
            report_id = int(cursor.lastrowid)
        _LOGGER.info("Recorded report id=%s -> %s", report_id, file_path)
        return report_id

    # ------------------------------------------------------------------
    # Queries (dict/list based)
    # ------------------------------------------------------------------
    def get_detections(
        self, trip_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return detections, optionally filtered to a single trip."""
        query = "SELECT * FROM detections"
        params: tuple = ()
        if trip_id is not None:
            query += " WHERE trip_id = ?"
            params = (trip_id,)
        query += " ORDER BY id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_trip(self, trip_id: int) -> Optional[Dict[str, Any]]:
        """Return a single trip as a dict, or ``None`` if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_severity_counts(
        self, trip_id: Optional[int] = None
    ) -> Dict[str, int]:
        """Return a mapping of severity level -> count.

        Ensures every configured severity level is present (default 0).
        """
        query = "SELECT severity, COUNT(*) AS n FROM detections"
        params: tuple = ()
        if trip_id is not None:
            query += " WHERE trip_id = ?"
            params = (trip_id,)
        query += " GROUP BY severity"

        counts: Dict[str, int] = {level: 0 for level in config.SEVERITY_LEVELS}
        with self._connect() as conn:
            for row in conn.execute(query, params).fetchall():
                severity = row["severity"]
                if severity in counts:
                    counts[severity] = int(row["n"])
        return counts

    # ------------------------------------------------------------------
    # Queries (pandas based - convenient for the dashboard)
    # ------------------------------------------------------------------
    def detections_dataframe(
        self, trip_id: Optional[int] = None
    ) -> pd.DataFrame:
        """Return detections as a pandas DataFrame."""
        query = "SELECT * FROM detections"
        params: tuple = ()
        if trip_id is not None:
            query += " WHERE trip_id = ?"
            params = (trip_id,)
        query += " ORDER BY id ASC"
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def trips_dataframe(self) -> pd.DataFrame:
        """Return all trips as a pandas DataFrame (most recent first)."""
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM trips ORDER BY id DESC", conn
            )

    def reports_dataframe(self) -> pd.DataFrame:
        """Return all reports as a pandas DataFrame (most recent first)."""
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM reports ORDER BY id DESC", conn
            )


__all__ = ["Database"]
