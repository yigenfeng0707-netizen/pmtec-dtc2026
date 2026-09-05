"""
Live Data Adapter Manager (P2-3).

Coordinates all real-world sensor data adapters (ADS-B, AIS, Weather)
and injects normalized data into the PMTEC LVC Live layer.

Provides:
  - Unified fetch/poll cycle for all data sources
  - Background polling threads (non-blocking)
  - LVC Live layer injection with entity tracking
  - Track fusion buffer integration
  - Sensor performance impact from weather
  - Statistics and health monitoring

Usage:
  from live_data import LiveAdapterManager
  manager = LiveAdapterManager()
  manager.start_all()  # start background polling
  manager.inject_into_lvc(engine.lvc)  # inject current data
  stats = manager.stats  # get all adapter stats
"""

import sys
import os
import time
import threading
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("pmtec.live_data")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# P7-v2: Read default use_real_api from config
try:
    from config import LIVE_DATA_USE_REAL_API as _DEFAULT_USE_REAL_API
except ImportError:
    _DEFAULT_USE_REAL_API = False

from .adsb_adapter import ADSBAdapter
from .ais_adapter import AISAdapter
from .weather_adapter import WeatherAdapter


class LiveDataAdapterBase:
    """Base class for all live data adapters."""

    def fetch(self):
        raise NotImplementedError

    def normalize(self, data=None) -> list[dict]:
        raise NotImplementedError

    @property
    def stats(self) -> dict:
        return {}


class LiveAdapterManager:
    """Manages all live data adapters and LVC Live injection.

    Coordinates polling of ADS-B, AIS, and weather data sources,
    normalizes results, and injects into the LVC Live layer.

    Each adapter runs on its own polling interval:
      - ADS-B: 15s (aircraft move fast)
      - AIS: 30s (vessels move slow)
      - Weather: 300s (5 min, weather changes slowly)
    """

    def __init__(
        self,
        bbox: tuple = None,
        use_real_api: bool = None,
        adsb_count: int = 15,
        ais_count: int = 20,
        weather_locations: list = None,
    ):
        # P7-v2: Default to config value if not explicitly set
        if use_real_api is None:
            use_real_api = bool(_DEFAULT_USE_REAL_API)
        self.bbox = bbox or (10.0, 45.0, 120.0, 160.0)
        self.adsb = ADSBAdapter(
            bbox=self.bbox,
            use_real_api=use_real_api,
            sim_contact_count=adsb_count,
        )
        self.ais = AISAdapter(
            bbox=self.bbox,
            sim_vessel_count=ais_count,
        )
        self.weather = WeatherAdapter(
            locations=weather_locations,
            use_real_api=use_real_api,
        )

        self._threads: dict[str, threading.Thread] = {}
        self._stop_flag = threading.Event()
        self._started = False

        # Track injected entity IDs for cleanup
        self._injected_entity_ids: set[str] = set()
        self._total_injected: int = 0
        self._total_tracks: int = 0

    def fetch_all(self) -> dict:
        """Fetch from all adapters (synchronous). Returns dict of source -> normalized data."""
        results = {}
        try:
            adsb_contacts = self.adsb.fetch()
            results["adsb"] = self.adsb.normalize(adsb_contacts)
        except Exception as e:
            logger.warning("ADS-B fetch failed: %s", e)
            results["adsb"] = []

        try:
            ais_vessels = self.ais.fetch()
            results["ais"] = self.ais.normalize(ais_vessels)
        except Exception as e:
            logger.warning("AIS fetch failed: %s", e)
            results["ais"] = []

        try:
            wx_reports = self.weather.fetch()
            results["weather"] = self.weather.normalize(wx_reports)
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
            results["weather"] = []

        return results

    def inject_into_lvc(self, lvc) -> dict:
        """Inject live data into the LVC Live layer.

        Creates LiveEntity objects for each contact and adds them
        to the Live layer. Also injects tracks into the fusion buffer.

        Returns injection statistics.
        """
        data = self.fetch_all()

        # Remove previously injected entities
        for eid in list(self._injected_entity_ids):
            lvc.live.remove_entity(eid)
        self._injected_entity_ids.clear()

        injected = 0
        tracks = 0

        for source, contacts in data.items():
            for contact in contacts:
                entity = LiveEntity(
                    entity_id=contact["sensor_id"],
                    entity_type=contact["sensor_type"],
                    lat=contact["lat"],
                    lon=contact["lon"],
                    alt_m=contact.get("alt_m", 0.0),
                    heading_deg=contact.get("heading_deg", 0.0),
                    speed_kmh=contact.get("speed_kmh", 0.0),
                    callsign=contact.get("callsign", ""),
                    affiliation=contact.get("affiliation", "neutral"),
                    confidence=contact.get("confidence", 0.8),
                    source=source,
                    raw_data=contact.get("raw_data", {}),
                )
                lvc.live.add_entity(entity)
                self._injected_entity_ids.add(entity.id)
                injected += 1

                # Also inject as track for fusion
                if source in ("adsb", "ais"):
                    lvc.inject_track(
                        {
                            "lat": contact["lat"],
                            "lon": contact["lon"],
                            "alt_m": contact.get("alt_m", 0.0),
                            "heading": contact.get("heading_deg", 0.0),
                            "speed": contact.get("speed_kmh", 0.0),
                            "confidence": contact.get("confidence", 0.8),
                            "classification": "aircraft"
                            if source == "adsb"
                            else "vessel",
                            "source": source,
                        },
                        source_layer="Live",
                    )
                    tracks += 1

        self._total_injected += injected
        self._total_tracks += tracks

        # Update entity_count on the live layer
        lvc.live.entity_count = len(lvc.live.entities)

        return {
            "total_injected": injected,
            "tracks_injected": tracks,
            "adsb_contacts": len(data.get("adsb", [])),
            "ais_vessels": len(data.get("ais", [])),
            "weather_stations": len(data.get("weather", [])),
        }

    def start_all(self):
        """Start background polling threads for all adapters."""
        if self._started:
            return

        self._stop_flag.clear()

        self._threads["adsb"] = threading.Thread(
            target=self._poll_loop,
            args=("adsb", self.adsb, 15),
            daemon=True,
        )
        self._threads["ais"] = threading.Thread(
            target=self._poll_loop,
            args=("ais", self.ais, 30),
            daemon=True,
        )
        self._threads["weather"] = threading.Thread(
            target=self._poll_loop,
            args=("weather", self.weather, 300),
            daemon=True,
        )

        for name, t in self._threads.items():
            t.start()
            logger.info("Live data polling started: %s", name)

        self._started = True

    def stop_all(self):
        """Stop all background polling threads."""
        self._stop_flag.set()
        for t in self._threads.values():
            t.join(timeout=3)
        self._threads.clear()
        self._started = False
        logger.info("Live data polling stopped")

    def _poll_loop(self, name: str, adapter, interval: int):
        """Background polling loop for a single adapter."""
        while not self._stop_flag.is_set():
            try:
                adapter.fetch()
            except Exception as e:
                logger.warning("Poll %s error: %s", name, e)
            self._stop_flag.wait(interval)

    def get_weather_impact(self, location_id: str = None) -> dict:
        """Get weather impact on sensor performance."""
        return self.weather.get_sensor_impact(location_id)

    @property
    def stats(self) -> dict:
        return {
            "adsb": self.adsb.stats,
            "ais": self.ais.stats,
            "weather": self.weather.stats,
            "total_injected": self._total_injected,
            "total_tracks": self._total_tracks,
            "polling_active": self._started,
        }


@dataclass
class LiveEntity:
    """Lightweight entity for LVC Live layer (real-world contacts).

    Unlike full BattlefieldEntity, this represents actual sensor-derived
    contacts (aircraft, vessels, weather stations) that exist in the
    real world and are tracked via external data feeds.
    """

    entity_id: str
    entity_type: str
    lat: float
    lon: float
    alt_m: float = 0.0
    heading_deg: float = 0.0
    speed_kmh: float = 0.0
    callsign: str = ""
    affiliation: str = "neutral"
    confidence: float = 0.8
    source: str = ""
    raw_data: dict = field(default_factory=dict)
    status: str = "active"

    @property
    def id(self) -> str:
        return self.entity_id

    @property
    def entity_type_str(self) -> str:
        return self.entity_type

    def to_dict(self) -> dict:
        return {
            "id": self.entity_id,
            "type": self.entity_type,
            "subtype": self.callsign or self.entity_type,
            "lat": self.lat,
            "lon": self.lon,
            "alt_m": self.alt_m,
            "heading": self.heading_deg,
            "speed_kmh": self.speed_kmh,
            "affiliation": self.affiliation,
            "callsign": self.callsign,
            "confidence": self.confidence,
            "source": self.source,
            "status": self.status,
            "raw_data": self.raw_data,
        }
