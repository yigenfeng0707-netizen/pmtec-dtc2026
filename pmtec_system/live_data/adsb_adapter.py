"""
ADS-B Aircraft Tracking Adapter (P2-3).

Connects to the OpenSky Network public API to fetch real-time aircraft
position data (ADS-B transponder squawks). No API key required for
basic anonymous access.

P7-v2: Config-driven API URL, timeout, and retry attempts with
       automatic fallback to simulation mode on failure.

API: https://opensky-network.org/api/states/all
Rate limit: ~10 requests/min (anonymous), 400/day

Each state vector contains:
  [icao24, callsign, origin_country, time_position, last_contact,
   longitude, latitude, baro_altitude, on_ground, velocity, true_track,
   vertical_rate, sensors, geo_altitude, squawk, spi, position_source]

Normalized output: list of LiveSensorData dicts with lat/lon/alt/heading/speed.
"""

import logging
import os
import random
import sys
import time
from dataclasses import dataclass

logger = logging.getLogger("pmtec.live_data.adsb")

# P7-v2: Config-driven settings (with safe defaults)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from config import LIVE_DATA_OPENSKY_URL as _API_URL
    from config import LIVE_DATA_RETRY_ATTEMPTS as _RETRIES
    from config import LIVE_DATA_TIMEOUT_S as _TIMEOUT
except ImportError:
    _API_URL = "https://opensky-network.org/api/states/all"
    _TIMEOUT = 10
    _RETRIES = 3

# OpenSky API endpoint (config-driven)
OPENSKY_API = _API_URL


@dataclass
class ADSBContact:
    """Normalized ADS-B contact from OpenSky Network."""

    icao24: str
    callsign: str
    origin_country: str
    lat: float
    lon: float
    alt_m: float
    heading_deg: float
    speed_kmh: float
    on_ground: bool
    squawk: str
    timestamp: int


class ADSBAdapter:
    """ADS-B real-time aircraft data adapter using OpenSky Network API.

    Falls back to realistic simulated data when network is unavailable
    or rate-limited.
    """

    def __init__(
        self,
        bbox: tuple = None,
        use_real_api: bool = True,
        sim_contact_count: int = 15,
    ):
        """
        Args:
            bbox: (min_lat, max_lat, min_lon, max_lon) bounding box for query.
                  Default: Western Pacific (IndoPACOM AOR).
            use_real_api: Attempt real API calls. Set False for pure simulation.
            sim_contact_count: Number of simulated contacts when offline.
        """
        self.bbox = bbox or (10.0, 45.0, 120.0, 160.0)
        self.use_real_api = use_real_api
        self.sim_contact_count = sim_contact_count
        self._contacts: list[ADSBContact] = []
        self._last_fetch: float = 0
        self._fetch_interval: int = 15  # seconds between fetches
        self._api_failures: int = 0
        self._total_fetches: int = 0
        self._real_contacts: int = 0
        self._sim_contacts: int = 0

    def fetch(self) -> list[ADSBContact]:
        """Fetch current aircraft contacts. Returns list of ADSBContact."""
        now = time.time()
        if now - self._last_fetch < self._fetch_interval and self._contacts:
            return self._contacts

        self._last_fetch = now
        self._total_fetches += 1

        if self.use_real_api:
            contacts = self._fetch_real()
            if contacts:
                self._contacts = contacts
                self._real_contacts = len(contacts)
                self._api_failures = 0
                logger.info(
                    "ADS-B: fetched %d real aircraft from OpenSky",
                    len(contacts),
                )
                return contacts
            else:
                self._api_failures += 1
                if self._api_failures <= 2:
                    logger.warning(
                        "ADS-B: OpenSky API unavailable (attempt %d), using simulation",
                        self._api_failures,
                    )

        # Fallback: simulate realistic contacts
        contacts = self._simulate_contacts()
        self._contacts = contacts
        self._sim_contacts = len(contacts)
        return contacts

    def _fetch_real(self) -> list[ADSBContact]:
        """Fetch real data from OpenSky Network API with retry logic.

        P7-v2: Uses config-driven timeout and retry attempts.
        Retries on failure, returns empty list if all attempts fail
        (triggering fallback to simulation).
        """
        import json
        import urllib.request

        min_lat, max_lat, min_lon, max_lon = self.bbox
        url = (
            f"{OPENSKY_API}"
            f"?lamin={min_lat}&lomin={min_lon}&lamax={max_lat}&lomax={max_lon}"
        )

        last_error = None
        for attempt in range(1, _RETRIES + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "PMTEC-DTC2026/1.0"}
                )
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                states = data.get("states") or []
                contacts = []
                for s in states:
                    if not s or len(s) < 9:
                        continue
                    icao24 = s[0] or ""
                    callsign = (s[1] or "").strip()
                    origin = s[2] or ""
                    lon = s[5]
                    lat = s[6]
                    alt_m = s[7] or 0.0
                    on_ground = s[8] or False
                    velocity_ms = s[9] or 0.0
                    heading = s[10] or 0.0
                    squawk = s[13] or ""

                    if lat is None or lon is None:
                        continue

                    contacts.append(
                        ADSBContact(
                            icao24=icao24,
                            callsign=callsign or icao24,
                            origin_country=origin,
                            lat=float(lat),
                            lon=float(lon),
                            alt_m=float(alt_m),
                            heading_deg=float(heading),
                            speed_kmh=float(velocity_ms) * 3.6,
                            on_ground=bool(on_ground),
                            squawk=squawk,
                            timestamp=int(time.time()),
                        )
                    )
                return contacts

            except Exception as e:
                last_error = e
                logger.debug(
                    "ADS-B API attempt %d/%d failed: %s",
                    attempt,
                    _RETRIES,
                    e,
                )
                if attempt < _RETRIES:
                    time.sleep(2 * attempt)  # simple linear backoff

        logger.warning(
            "ADS-B: all %d API attempts failed (last: %s), falling back to simulation",
            _RETRIES,
            last_error,
        )
        return []

    def _simulate_contacts(self) -> list[ADSBContact]:
        """Generate realistic simulated aircraft contacts."""
        min_lat, max_lat, min_lon, max_lon = self.bbox
        contacts = []
        # Common military callsigns in IndoPACOM
        callsigns = [
            "REACH",
            "EVAC",
            "SAM",
            "HUNT",
            "DUKE",
            "VIPER",
            "EAGLE",
            "RAPTOR",
            "HAVOC",
            "BOLT",
            "KNIFE",
            "STEEL",
            "NIGHT",
            "HOMER",
            "NOBLE",
        ]
        countries = ["USA", "Japan", "Australia", "Korea, Republic of", "Taiwan"]

        for i in range(self.sim_contact_count):
            lat = random.uniform(min_lat, max_lat)
            lon = random.uniform(min_lon, max_lon)
            # Vary altitude: military aircraft typically 3-12km
            alt = random.choice([0, 3000, 6000, 8000, 10000, 11000])
            on_ground = alt == 0
            speed = 0 if on_ground else random.uniform(400, 900)
            heading = random.uniform(0, 360)

            contacts.append(
                ADSBContact(
                    icao24=f"{random.randint(0, 0xFFFFFF):06x}",
                    callsign=f"{random.choice(callsigns)}{random.randint(1, 99):02d}",
                    origin_country=random.choice(countries),
                    lat=lat,
                    lon=lon,
                    alt_m=alt,
                    heading_deg=heading,
                    speed_kmh=speed,
                    on_ground=on_ground,
                    squawk=f"{random.randint(0, 7777):04d}",
                    timestamp=int(time.time()),
                )
            )
        return contacts

    def normalize(self, contacts: list[ADSBContact] = None) -> list[dict]:
        """Convert ADSBContact list to LiveSensorData dicts."""
        contacts = contacts or self._contacts
        result = []
        for c in contacts:
            # Determine affiliation: military callsigns = friendly, unknown = neutral
            mil_callsigns = [
                "REACH",
                "EVAC",
                "SAM",
                "HUNT",
                "DUKE",
                "VIPER",
                "EAGLE",
                "RAPTOR",
                "HAVOC",
                "BOLT",
                "KNIFE",
                "STEEL",
                "NIGHT",
                "HOMER",
                "NOBLE",
            ]
            cs_prefix = c.callsign.split()[0] if c.callsign else ""
            affiliation = "friendly" if cs_prefix in mil_callsigns else "neutral"

            result.append(
                {
                    "sensor_id": f"ADSB-{c.icao24}",
                    "sensor_type": "ADS-B",
                    "lat": c.lat,
                    "lon": c.lon,
                    "alt_m": c.alt_m,
                    "heading_deg": c.heading_deg,
                    "speed_kmh": c.speed_kmh,
                    "callsign": c.callsign,
                    "affiliation": affiliation,
                    "confidence": 0.95 if not c.on_ground else 0.85,
                    "timestamp": c.timestamp,
                    "raw_data": {
                        "icao24": c.icao24,
                        "origin_country": c.origin_country,
                        "on_ground": str(c.on_ground),
                        "squawk": c.squawk,
                    },
                }
            )
        return result

    @property
    def stats(self) -> dict:
        return {
            "total_fetches": self._total_fetches,
            "real_contacts": self._real_contacts,
            "sim_contacts": self._sim_contacts,
            "api_failures": self._api_failures,
            "current_contacts": len(self._contacts),
        }
