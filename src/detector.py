"""
detector.py
===========
YOLOv8 pothole detection engine for the Smart Road Monitoring System.

Responsibilities:
    * Load the trained ``final_pothole_detector.pt`` model once.
    * Run inference on a frame and return structured detections.
    * Classify each detection's severity from bounding-box area.
    * Draw annotated overlays (box + confidence + severity).
    * Orchestrate the full pipeline for a live stream:
        detect -> track -> (on newly-confirmed track) GPS + geocode + persist.

The class is deliberately framework-agnostic about *where* frames come from:
callers pass NumPy BGR frames, so the same engine drives webcam, video file
and single-image workflows, as well as the Streamlit dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

import config
from src.database import Database
from src.geocoder import reverse_geocode
from src.gps_tracker import BaseGPSTracker, create_gps_tracker
from src.severity import classifier
from src.tracker import ObjectTracker, Track
from src.utils import get_logger, timestamp_slug

_LOGGER = get_logger(__name__)

BBox = Tuple[float, float, float, float]


@dataclass
class Detection:
    """A single raw detection from one frame."""

    box: BBox
    confidence: float
    severity: str
    area: float


@dataclass
class FrameResult:
    """Everything produced for one processed frame."""

    frame: np.ndarray                       # annotated BGR image
    detections: List[Detection] = field(default_factory=list)
    tracks: List[Track] = field(default_factory=list)
    new_potholes: int = 0                   # newly counted this frame


class PotholeDetector:
    """High-level detection engine wrapping a YOLOv8 model."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
    ) -> None:
        self.model_path = model_path or config.DETECTION.model_path
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else config.DETECTION.confidence_threshold
        )
        self.iou_threshold = (
            iou_threshold
            if iou_threshold is not None
            else config.DETECTION.iou_threshold
        )
        self._model = self._load_model()

    # ------------------------------------------------------------------
    # Model loading / inference
    # ------------------------------------------------------------------
    def _load_model(self):
        """Load the YOLO model, raising a clear error if unavailable."""
        model_file = Path(self.model_path)
        if not model_file.exists():
            raise FileNotFoundError(
                f"Model weights not found at '{model_file}'. "
                "Place final_pothole_detector.pt under the model/ directory."
            )
        try:
            from ultralytics import YOLO

            model = YOLO(str(model_file))
            _LOGGER.info("Loaded YOLO model from %s", model_file)
            return model
        except Exception as exc:  # pragma: no cover - depends on environment
            _LOGGER.error("Failed to load YOLO model: %s", exc)
            raise

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run inference on a single BGR frame.

        Args:
            frame: Image as a NumPy BGR array (OpenCV convention).

        Returns:
            A list of :class:`Detection` objects above the confidence
            threshold.
        """
        results = self._model.predict(
            source=frame,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            imgsz=config.DETECTION.image_size,
            device=config.DETECTION.device,
            verbose=False,
        )

        detections: List[Detection] = []
        if not results:
            return detections

        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xyxy is None:
            return detections

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()

        for (x1, y1, x2, y2), conf in zip(xyxy, confs):
            box: BBox = (float(x1), float(y1), float(x2), float(y2))
            severity, area = classifier.classify_box(box)
            detections.append(
                Detection(
                    box=box,
                    confidence=float(conf),
                    severity=severity,
                    area=area,
                )
            )
        return detections

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    @staticmethod
    def annotate(
        frame: np.ndarray,
        detections: Sequence[Detection],
    ) -> np.ndarray:
        """Draw bounding boxes, confidence and severity onto a copy of ``frame``."""
        annotated = frame.copy()
        for det in detections:
            x1, y1, x2, y2 = (int(v) for v in det.box)
            color = classifier.color_bgr(det.severity)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

            label = f"{det.severity} {det.confidence * 100:.0f}%"
            (tw, th), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
            )
            top = max(0, y1 - th - baseline - 4)
            cv2.rectangle(
                annotated,
                (x1, top),
                (x1 + tw + 4, y1),
                color,
                thickness=-1,
            )
            cv2.putText(
                annotated,
                label,
                (x1 + 2, y1 - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
        return annotated

    # ------------------------------------------------------------------
    # Single frame with tracking + persistence
    # ------------------------------------------------------------------
    def process_frame(
        self,
        frame: np.ndarray,
        tracker: ObjectTracker,
        database: Optional[Database] = None,
        gps: Optional[BaseGPSTracker] = None,
        trip_id: Optional[int] = None,
        save_captures: bool = True,
    ) -> FrameResult:
        """Detect, track and (for newly confirmed potholes) persist one frame.

        Args:
            frame: BGR frame.
            tracker: A persistent :class:`ObjectTracker` for the stream.
            database: Optional DB to persist new potholes into.
            gps: Optional GPS source; stamps coordinates on new potholes.
            trip_id: Trip to associate detections with.
            save_captures: Whether to write an annotated crop per new pothole.

        Returns:
            A :class:`FrameResult` with the annotated frame and metadata.
        """
        detections = self.detect(frame)
        annotated = self.annotate(frame, detections)

        tracker_input = [(det.box, det.confidence) for det in detections]
        tracks = tracker.update(tracker_input)

        new_count = 0
        newly_confirmed = [t for t in tracks if t.just_confirmed and not t.counted]

        for track in newly_confirmed:
            severity, area = classifier.classify_box(track.box)
            lat, lon, location = self._resolve_location(gps)
            image_path = ""
            if save_captures:
                image_path = self._save_capture(annotated, track, severity)

            if database is not None:
                try:
                    database.insert_detection(
                        trip_id=trip_id,
                        track_id=track.track_id,
                        latitude=lat,
                        longitude=lon,
                        location=location,
                        severity=severity,
                        confidence=track.confidence,
                        bbox_area=area,
                        image_path=image_path,
                    )
                except Exception as exc:  # pragma: no cover
                    _LOGGER.error("Failed to persist detection: %s", exc)

            track.counted = True
            new_count += 1

        return FrameResult(
            frame=annotated,
            detections=detections,
            tracks=tracks,
            new_potholes=new_count,
        )

    # ------------------------------------------------------------------
    # Stream processing (webcam / video file)
    # ------------------------------------------------------------------
    def process_stream(
        self,
        source: object = 0,
        trip_id: Optional[int] = None,
        database: Optional[Database] = None,
        gps: Optional[BaseGPSTracker] = None,
        max_frames: Optional[int] = None,
        on_frame: Optional[Callable[[FrameResult], bool]] = None,
    ) -> Dict[str, int]:
        """Process a full video stream (webcam index or file path).

        Args:
            source: OpenCV video source (``0`` for default webcam, or a path).
            trip_id: Trip to associate detections with.
            database: Optional persistence target.
            gps: Optional GPS source (a fresh simulated one is created if None).
            max_frames: Optional cap on frames processed.
            on_frame: Optional callback invoked per frame with the
                :class:`FrameResult`. Return ``False`` to stop early.

        Returns:
            A summary dict including ``frames`` and ``new_potholes``.
        """
        tracker = ObjectTracker()
        gps = gps or create_gps_tracker()
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video source: {source!r}")

        frames = 0
        total_new = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                result = self.process_frame(
                    frame,
                    tracker=tracker,
                    database=database,
                    gps=gps,
                    trip_id=trip_id,
                )
                frames += 1
                total_new += result.new_potholes

                if on_frame is not None and on_frame(result) is False:
                    break
                if max_frames is not None and frames >= max_frames:
                    break
        finally:
            capture.release()

        _LOGGER.info(
            "Stream complete: %d frames, %d new potholes", frames, total_new
        )
        return {"frames": frames, "new_potholes": total_new}

    # ------------------------------------------------------------------
    # Headless single-image API (used by tests / batch tools)
    # ------------------------------------------------------------------
    def detect_image(self, image_path: str) -> List[Detection]:
        """Detect potholes in an image file and return raw detections."""
        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")
        return self.detect(frame)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_location(
        gps: Optional[BaseGPSTracker],
    ) -> Tuple[Optional[float], Optional[float], str]:
        """Read GPS and reverse-geocode it, degrading gracefully."""
        if gps is None:
            return None, None, "Unknown Location"
        try:
            lat, lon = gps.get_current_location()
            location = reverse_geocode(lat, lon).summary()
            return lat, lon, location
        except Exception as exc:  # pragma: no cover
            _LOGGER.warning("Location resolution failed: %s", exc)
            return None, None, "Unknown Location"

    @staticmethod
    def _save_capture(frame: np.ndarray, track: Track, severity: str) -> str:
        """Save an annotated capture for a newly confirmed pothole."""
        try:
            filename = f"pothole_{severity.lower()}_{track.track_id}_{timestamp_slug()}.jpg"
            path = config.POTHOLE_CAPTURES_DIR / filename
            cv2.imwrite(str(path), frame)
            return str(path)
        except Exception as exc:  # pragma: no cover
            _LOGGER.warning("Failed to save capture: %s", exc)
            return ""


__all__ = ["Detection", "FrameResult", "PotholeDetector", "BBox"]
