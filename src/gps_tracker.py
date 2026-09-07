"""
gps_tracker.py
==============
GPS location source for the Smart Road Monitoring System.

For local development this module simulates a vehicle moving along a road
so that consecutive pothole detections receive slightly different, realistic
coordinates. The public interface is intentionally small and abstract so the
simulated source can be swapped for a real mobile/serial/NMEA GPS feed later
without touching any caller.

Replace-later strategy:
    Subclass :class:`BaseGPSTracker` and override :meth:`get_current_location`
    (and optionally :meth:`reset`) to read from a real device. Then update the
    factory :func:`create_gps_tracker` to return your implementation.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from typing import Tuple

import config
from src.utils import get_logger

_LOGGER = get_logger(__name__)

# One degree of latitude is ~111,320 metres everywhere on earth.
_METRES_PER_DEG_LAT = 111_320.0

Coordinate = Tuple[float, float]  # (latitude, longitude)


class BaseGPSTracker(ABC):
    """Abstract GPS source. Real implementations override the hooks below."""

    @abstractmethod
    def get_current_location(self) -> Coordinate:
        """Return the current ``(latitude, longitude)``."""
        raise NotImplementedError

    def reset(self) -> None:  # pragma: no cover - optional hook
        """Reset any internal state (no-op by default)."""
        return None


class SimulatedGPSTracker(BaseGPSTracker):
    """Simulate a vehicle drifting along a pseudo-random road path.

    Each call to :meth:`get_current_location` advances the position by a
    configurable number of metres in a gently changing heading, producing a
    plausible route rather than a random scatter of points.
    """

    def __init__(
        self,
        start_lat: float | None = None,
        start_lon: float | None = None,
        step_metres: float | None = None,
        seed: int | None = None,
    ) -> None:
        """Initialise the simulator.

        Args:
            start_lat: Origin latitude (defaults to config).
            start_lon: Origin longitude (defaults to config).
            step_metres: Approx. distance advanced per reading (defaults to
                config).
            seed: Optional RNG seed for reproducible routes.
        """
        self._start_lat = start_lat if start_lat is not None else config.GPS.start_lat
        self._start_lon = start_lon if start_lon is not None else config.GPS.start_lon
        self._step_metres = (
            step_metres if step_metres is not None else config.GPS.step_metres
        )
        self._rng = random.Random(seed)

        self._lat = self._start_lat
        self._lon = self._start_lon
        # Initial heading in radians (0 = north, pi/2 = east).
        self._heading = self._rng.uniform(0.0, 2.0 * math.pi)
        _LOGGER.info(
            "SimulatedGPSTracker initialised at (%.5f, %.5f)",
            self._lat,
            self._lon,
        )

    def _metres_per_deg_lon(self, latitude: float) -> float:
        """Metres per degree of longitude at the given latitude."""
        return _METRES_PER_DEG_LAT * math.cos(math.radians(latitude))

    def get_current_location(self) -> Coordinate:
        """Advance the simulated position and return ``(lat, lon)``."""
        # Nudge the heading slightly so the path curves like a real road.
        self._heading += self._rng.uniform(-0.20, 0.20)

        # Add small variability to the step so points are not perfectly even.
        step = self._step_metres * self._rng.uniform(0.7, 1.3)

        north_m = step * math.cos(self._heading)
        east_m = step * math.sin(self._heading)

        self._lat += north_m / _METRES_PER_DEG_LAT
        self._lon += east_m / self._metres_per_deg_lon(self._lat)

        return (round(self._lat, 6), round(self._lon, 6))

    def peek(self) -> Coordinate:
        """Return the current position without advancing it."""
        return (round(self._lat, 6), round(self._lon, 6))

    def reset(self) -> None:
        """Return the simulator to its origin and a fresh heading."""
        self._lat = self._start_lat
        self._lon = self._start_lon
        self._heading = self._rng.uniform(0.0, 2.0 * math.pi)


def create_gps_tracker(seed: int | None = None) -> BaseGPSTracker:
    """Factory returning the active GPS implementation.

    Swap the returned class here when integrating a real GPS device.
    """
    return SimulatedGPSTracker(seed=seed)


# Module-level default instance and convenience function.
_default_tracker: BaseGPSTracker = create_gps_tracker()


def get_current_location() -> Coordinate:
    """Return the current ``(latitude, longitude)`` from the default tracker.

    This module-level function preserves the simple call site requested by
    the specification while still delegating to a replaceable implementation.
    """
    return _default_tracker.get_current_location()


__all__ = [
    "BaseGPSTracker",
    "SimulatedGPSTracker",
    "create_gps_tracker",
    "get_current_location",
    "Coordinate",
]
