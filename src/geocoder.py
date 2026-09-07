"""
geocoder.py
===========
Cached reverse geocoding for the Smart Road Monitoring System.

Converts ``(latitude, longitude)`` into a human-readable location made up of
road name, city and state using geopy's Nominatim backend.

Two-tier caching keeps the system fast and polite:
    * An in-memory dict for the current process.
    * A JSON file on disk (``data/geocode_cache.json``) that survives restarts.

Cache keys are the coordinates rounded to ``config.GEOCODER.cache_precision``
decimal places, which collapses nearby points onto a single lookup. Requests
are rate-limited to satisfy Nominatim's usage policy, and every failure mode
degrades gracefully to a coordinate-based label rather than raising.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import config
from src.utils import get_logger

_LOGGER = get_logger(__name__)

_CACHE_FILE: Path = config.DATA_DIR / "geocode_cache.json"


@dataclass
class LocationInfo:
    """Structured reverse-geocoding result."""

    road: str = "Unknown Road"
    city: str = "Unknown City"
    state: str = "Unknown State"
    display_name: str = ""

    def summary(self) -> str:
        """Return a compact, human-friendly one-line location string."""
        parts = [p for p in (self.road, self.city, self.state) if p and "Unknown" not in p]
        if parts:
            return ", ".join(parts)
        return self.display_name or "Unknown Location"


class ReverseGeocoder:
    """Reverse-geocode coordinates with rate limiting and persistent caching."""

    def __init__(self) -> None:
        self._precision = config.GEOCODER.cache_precision
        self._lock = threading.Lock()
        self._memory_cache: Dict[str, Dict[str, str]] = {}
        self._load_disk_cache()
        self._geocode_fn = self._build_geocoder()

    # ------------------------------------------------------------------
    # Backend setup
    # ------------------------------------------------------------------
    def _build_geocoder(self):
        """Construct a rate-limited geopy reverse function, or ``None``.

        Import is done lazily so the rest of the system works even if geopy
        is unavailable at runtime.
        """
        try:
            from geopy.extra.rate_limiter import RateLimiter
            from geopy.geocoders import Nominatim

            nominatim = Nominatim(
                user_agent=config.GEOCODER.user_agent,
                timeout=config.GEOCODER.timeout,
            )
            return RateLimiter(
                nominatim.reverse,
                min_delay_seconds=config.GEOCODER.min_delay_seconds,
                max_retries=2,
                error_wait_seconds=2.0,
                swallow_exceptions=True,
            )
        except Exception as exc:  # pragma: no cover - optional dependency path
            _LOGGER.warning("Geocoder backend unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------
    def _cache_key(self, lat: float, lon: float) -> str:
        return f"{round(lat, self._precision)},{round(lon, self._precision)}"

    def _load_disk_cache(self) -> None:
        if _CACHE_FILE.exists():
            try:
                self._memory_cache = json.loads(
                    _CACHE_FILE.read_text(encoding="utf-8")
                )
                _LOGGER.info(
                    "Loaded %d cached geocodes", len(self._memory_cache)
                )
            except (OSError, json.JSONDecodeError) as exc:
                _LOGGER.warning("Could not read geocode cache: %s", exc)
                self._memory_cache = {}

    def _save_disk_cache(self) -> None:
        try:
            _CACHE_FILE.write_text(
                json.dumps(self._memory_cache, indent=2), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover
            _LOGGER.warning("Could not write geocode cache: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reverse(self, lat: float, lon: float) -> LocationInfo:
        """Return a :class:`LocationInfo` for the given coordinates.

        Uses the cache first; on a miss, queries the backend (if available),
        stores the result, and returns it. Always returns a usable object.
        """
        key = self._cache_key(lat, lon)

        with self._lock:
            if key in self._memory_cache:
                return LocationInfo(**self._memory_cache[key])

        info = self._query_backend(lat, lon)

        with self._lock:
            self._memory_cache[key] = asdict(info)
            self._save_disk_cache()

        return info

    def reverse_summary(self, lat: float, lon: float) -> str:
        """Convenience: return only the one-line summary string."""
        return self.reverse(lat, lon).summary()

    # ------------------------------------------------------------------
    # Internal query
    # ------------------------------------------------------------------
    def _query_backend(self, lat: float, lon: float) -> LocationInfo:
        fallback = LocationInfo(
            road="Unknown Road",
            city="Unknown City",
            state="Unknown State",
            display_name=f"{round(lat, 5)}, {round(lon, 5)}",
        )

        if self._geocode_fn is None:
            return fallback

        try:
            location = self._geocode_fn(
                (lat, lon),
                language=config.GEOCODER.language,
                addressdetails=True,
            )
            if location is None or not getattr(location, "raw", None):
                return fallback

            address: Dict[str, str] = location.raw.get("address", {})
            road = (
                address.get("road")
                or address.get("pedestrian")
                or address.get("footway")
                or address.get("neighbourhood")
                or "Unknown Road"
            )
            city = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("suburb")
                or address.get("county")
                or "Unknown City"
            )
            state = address.get("state") or address.get("region") or "Unknown State"

            return LocationInfo(
                road=road,
                city=city,
                state=state,
                display_name=getattr(location, "address", "") or "",
            )
        except Exception as exc:  # pragma: no cover - network/backends vary
            _LOGGER.warning("Reverse geocode failed for (%s, %s): %s", lat, lon, exc)
            return fallback


# Module-level singleton.
geocoder = ReverseGeocoder()


def reverse_geocode(lat: float, lon: float) -> LocationInfo:
    """Module-level convenience wrapper around the singleton geocoder."""
    return geocoder.reverse(lat, lon)


__all__ = ["LocationInfo", "ReverseGeocoder", "geocoder", "reverse_geocode"]
