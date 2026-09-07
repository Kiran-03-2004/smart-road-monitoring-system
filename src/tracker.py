"""
tracker.py
==========
Lightweight multi-object tracker for pothole de-duplication.

Implements a SORT-style tracker: detections in each frame are matched to
existing tracks by Intersection-over-Union using the Hungarian assignment
algorithm. Each track carries a stable integer id, so a single physical
pothole seen across many frames is counted only once.

A track is *confirmed* after it accumulates ``min_hits_to_count`` matched
detections. The frame on which a track first becomes confirmed is reported
via :attr:`Track.just_confirmed`, which is the precise signal the detection
loop uses to persist exactly one database row per pothole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

import numpy as np
from scipy.optimize import linear_sum_assignment

import config
from src.utils import box_center, get_logger, iou

_LOGGER = get_logger(__name__)

BBox = Tuple[float, float, float, float]


@dataclass
class Track:
    """State for a single tracked object."""

    track_id: int
    box: BBox
    confidence: float
    hits: int = 1               # total matched detections
    age: int = 0                # frames since creation
    time_since_update: int = 0  # frames since last match
    confirmed: bool = False
    counted: bool = False       # has the caller already persisted this track?
    just_confirmed: bool = False  # became confirmed on the current frame

    @property
    def center(self) -> Tuple[float, float]:
        """Centre point of the current bounding box."""
        return box_center(self.box)


class ObjectTracker:
    """IoU + Hungarian-assignment multi-object tracker."""

    def __init__(
        self,
        iou_threshold: float | None = None,
        max_missed_frames: int | None = None,
        min_hits_to_count: int | None = None,
    ) -> None:
        self._iou_threshold = (
            iou_threshold if iou_threshold is not None
            else config.TRACKER.iou_match_threshold
        )
        self._max_missed = (
            max_missed_frames if max_missed_frames is not None
            else config.TRACKER.max_missed_frames
        )
        self._min_hits = (
            min_hits_to_count if min_hits_to_count is not None
            else config.TRACKER.min_hits_to_count
        )
        self._tracks: Dict[int, Track] = {}
        self._next_id: int = 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update(
        self,
        detections: Sequence[Tuple[BBox, float]],
    ) -> List[Track]:
        """Advance the tracker by one frame.

        Args:
            detections: Sequence of ``(box, confidence)`` where ``box`` is
                ``(x1, y1, x2, y2)``.

        Returns:
            The list of currently *live* tracks after this update.
        """
        # Age all tracks and reset the per-frame "just confirmed" flag.
        for track in self._tracks.values():
            track.age += 1
            track.time_since_update += 1
            track.just_confirmed = False

        track_ids = list(self._tracks.keys())
        matches, unmatched_dets = self._associate(track_ids, detections)

        # Update matched tracks.
        for track_id, det_idx in matches:
            box, conf = detections[det_idx]
            track = self._tracks[track_id]
            track.box = box
            track.confidence = float(conf)
            track.hits += 1
            track.time_since_update = 0
            if not track.confirmed and track.hits >= self._min_hits:
                track.confirmed = True
                track.just_confirmed = True

        # Create new tracks for unmatched detections.
        for det_idx in unmatched_dets:
            box, conf = detections[det_idx]
            self._create_track(box, float(conf))

        # Remove stale tracks.
        self._prune()

        return list(self._tracks.values())

    def confirmed_tracks(self) -> List[Track]:
        """Return all currently confirmed live tracks."""
        return [t for t in self._tracks.values() if t.confirmed]

    def reset(self) -> None:
        """Clear all tracks and reset id allocation."""
        self._tracks.clear()
        self._next_id = 1

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _create_track(self, box: BBox, confidence: float) -> Track:
        track = Track(track_id=self._next_id, box=box, confidence=confidence)
        # A track can be confirmed immediately if the threshold is 1.
        if track.hits >= self._min_hits:
            track.confirmed = True
            track.just_confirmed = True
        self._tracks[self._next_id] = track
        self._next_id += 1
        return track

    def _prune(self) -> None:
        stale = [
            tid
            for tid, t in self._tracks.items()
            if t.time_since_update > self._max_missed
        ]
        for tid in stale:
            del self._tracks[tid]

    def _associate(
        self,
        track_ids: List[int],
        detections: Sequence[Tuple[BBox, float]],
    ) -> Tuple[List[Tuple[int, int]], List[int]]:
        """Match tracks to detections by IoU using Hungarian assignment.

        Returns:
            ``(matches, unmatched_detection_indices)`` where ``matches`` is a
            list of ``(track_id, detection_index)`` pairs.
        """
        if not track_ids or not detections:
            return [], list(range(len(detections)))

        # Build an IoU cost matrix (rows: tracks, cols: detections).
        iou_matrix = np.zeros((len(track_ids), len(detections)), dtype=np.float32)
        for i, tid in enumerate(track_ids):
            track_box = self._tracks[tid].box
            for j, (det_box, _conf) in enumerate(detections):
                iou_matrix[i, j] = iou(track_box, det_box)

        # Hungarian algorithm maximises IoU by minimising its negative.
        row_idx, col_idx = linear_sum_assignment(-iou_matrix)

        matches: List[Tuple[int, int]] = []
        matched_dets: set[int] = set()
        for r, c in zip(row_idx, col_idx):
            if iou_matrix[r, c] >= self._iou_threshold:
                matches.append((track_ids[r], int(c)))
                matched_dets.add(int(c))

        unmatched_dets = [
            j for j in range(len(detections)) if j not in matched_dets
        ]
        return matches, unmatched_dets


__all__ = ["Track", "ObjectTracker", "BBox"]
