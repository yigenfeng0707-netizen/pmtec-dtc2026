"""
OpenWeather Data Adapter (P2-3).

Fetches real weather data from the Open-Meteo API (free, no API key).
Provides weather conditions at military base locations for the LVC Live
layer, affecting sensor performance and mission planning.

P7-v2: Config-driven API URL, timeout, and retry attempts with
       automatic fallback to simulation mode on failure.

API: https://api.open-meteo.com/v1/forecast
Rate limit: 10,000 requests/day (free, no key)

Weather data affects:
  - Sensor detection range (cloud cover, precipitation reduce radar range)
  - Aircraft operations (crosswind limits, visibility restrictions)
  - Missile trajectory (wind drift)
"""

import logging
import math
import os
import random
import sys
import time
from dataclasses import dataclass

logger = logging.getLogger("pmtec.live_data.weather")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from config import LIVE_DATA_OPENMETEO_URL as _API_URL
    from config import LIVE_DATA_RETRY_ATTEMPTS as _RETRIES
    from config import LIVE_DATA_TIMEOUT_S as _TIMEOUT
except ImportError:
    _API_URL = "https://api.open-meteo.com/v1/forecast"
    _TIMEOUT = 10
    _RETRIES = 3

OPEN_METEO_API = _API_URL


@dataclass
class WeatherReport:
    """Normalized weather report for a location."""

    location_id: str
    location_name: str
    lat: float
    lon: float
    temperature_c: float
    wind_speed_kmh: float
    wind_dir_deg: float
    cloud_cover_pct: float
    precipitation_mm: float
    visibility_km: float
    weather_code: int  # WMO weather code
    timestamp: int


class WeatherAdapter:
    """Open-Meteo weather data adapter.

    Fetches real weather data for military base locations.
    Falls back to simulated realistic weather when API unavailable.
    """

    # WMO weather code mapping
    WMO_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Rain showers",
        81: "Moderate showers",
        82: "Violent showers",
        95: "Thunderstorm",
        96: "Thunderstorm + hail",
        99: "Severe thunderstorm",
    }

    def __init__(self, locations: list = None, use_real_api: bool = True):
        """
        Args:
            locations: List of (location_id, name, lat, lon) tuples.
                        Default: major IndoPACOM bases.
            use_real_api: Attempt real API calls.
        """
        self.locations = locations or [
            ("PEARL", "Pearl Harbor", 21.36, -157.95),
            ("YOKO", "Yokosuka", 35.29, 139.67),
            ("GUAM", "Guam AFB", 13.58, 144.90),
            ("KADENA", "Kadena AB", 26.35, 127.76),
            ("OSAN", "Osan AB", 37.09, 127.03),
            ("SING", "Singapore", 1.35, 103.99),
            ("DARWIN", "Darwin", -12.42, 130.89),
            ("BUSAN", "Busan", 35.10, 129.04),
        ]
        self.use_real_api = use_real_api
        self._reports: list[WeatherReport] = []
        self._last_fetch: float = 0
        self._fetch_interval: int = 300  # 5 min (weather changes slowly)
        self._total_fetches: int = 0
        self._real_reports: int = 0
        self._sim_reports: int = 0

    def fetch(self) -> list[WeatherReport]:
        """Fetch current weather for all locations."""
        now = time.time()
        if now - self._last_fetch < self._fetch_interval and self._reports:
            return self._reports

        self._last_fetch = now
        self._total_fetches += 1

        if self.use_real_api:
            reports = self._fetch_real()
            if reports:
                self._reports = reports
                self._real_reports = len(reports)
                logger.info(
                    "Weather: fetched %d real reports from Open-Meteo",
                    len(reports),
                )
                return reports
            else:
                logger.warning("Weather: Open-Meteo unavailable, using simulation")

        # Fallback: simulate
        reports = self._simulate_weather()
        self._reports = reports
        self._sim_reports = len(reports)
        return reports

    def _fetch_real(self) -> list[WeatherReport]:
        """Fetch real weather from Open-Meteo API with retry logic.

        P7-v2: Uses config-driven timeout and retry attempts.
        Per-location retry: skips failed locations, aggregates successful ones.
        """
        import json
        import urllib.request

        reports = []
        for loc_id, name, lat, lon in self.locations:
            url = (
                f"{OPEN_METEO_API}"
                f"?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,wind_speed_10m,wind_direction_10m,"
                f"cloud_cover,precipitation,weather_code,visibility"
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "PMTEC-DTC2026/1.0"}
            )

            success = False
            for attempt in range(1, _RETRIES + 1):
                try:
                    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                        data = json.loads(resp.read().decode("utf-8"))

                    current = data.get("current", {})
                    ts = int(time.time())

                    reports.append(
                        WeatherReport(
                            location_id=loc_id,
                            location_name=name,
                            lat=lat,
                            lon=lon,
                            temperature_c=current.get("temperature_2m", 20.0),
                            wind_speed_kmh=current.get("wind_speed_10m", 0.0),
                            wind_dir_deg=current.get("wind_direction_10m", 0.0),
                            cloud_cover_pct=current.get("cloud_cover", 0.0),
                            precipitation_mm=current.get("precipitation", 0.0),
                            visibility_km=current.get("visibility", 10.0),
                            weather_code=current.get("weather_code", 0),
                            timestamp=ts,
                        )
                    )
                    success = True
                    break
                except Exception as e:
                    logger.debug(
                        "Weather API %s attempt %d/%d failed: %s",
                        loc_id,
                        attempt,
                        _RETRIES,
                        e,
                    )
                    if attempt < _RETRIES:
                        time.sleep(2 * attempt)

            if not success:
                logger.warning(
                    "Weather: %s (%s) API failed after %d attempts, skipping",
                    name,
                    loc_id,
                    _RETRIES,
                )

        if not reports:
            logger.warning("Weather: all locations failed, falling back to simulation")
        return reports

    def _simulate_weather(self) -> list[WeatherReport]:
        """Generate realistic weather for IndoPACOM bases."""
        reports = []
        ts = int(time.time())

        for loc_id, name, lat, lon in self.locations:
            # Seasonal temperature approximation
            base_temp = 20 + (10 * math.cos(math.radians(lat)))  # warmer near equator
            # Add randomness
            temp = base_temp + random.uniform(-5, 5)
            # Cloud cover: 0-100%
            cloud = random.choices(
                [0, 10, 25, 50, 75, 100], weights=[2, 3, 3, 2, 2, 1], k=1
            )[0]
            # Wind: 0-40 km/h
            wind = random.uniform(5, 30)
            wind_dir = random.uniform(0, 360)
            # Precipitation: 0-10mm
            precip = 0 if cloud < 50 else random.uniform(0, 5)
            # Visibility: reduced by rain/fog
            vis = 20.0 if precip < 1 else max(1.0, 20.0 - precip * 3)
            # Weather code
            if precip > 5:
                wcode = 65  # heavy rain
            elif precip > 0:
                wcode = 63  # moderate rain
            elif cloud >= 90:
                wcode = 3  # overcast
            elif cloud >= 50:
                wcode = 2  # partly cloudy
            else:
                wcode = 0  # clear

            reports.append(
                WeatherReport(
                    location_id=loc_id,
                    location_name=name,
                    lat=lat,
                    lon=lon,
                    temperature_c=round(temp, 1),
                    wind_speed_kmh=round(wind, 1),
                    wind_dir_deg=round(wind_dir, 0),
                    cloud_cover_pct=cloud,
                    precipitation_mm=round(precip, 1),
                    visibility_km=round(vis, 1),
                    weather_code=wcode,
                    timestamp=ts,
                )
            )
        return reports

    def normalize(self, reports: list[WeatherReport] = None) -> list[dict]:
        """Convert WeatherReport list to LiveSensorData dicts."""
        reports = reports or self._reports
        result = []
        for r in reports:
            result.append(
                {
                    "sensor_id": f"WX-{r.location_id}",
                    "sensor_type": "weather",
                    "lat": r.lat,
                    "lon": r.lon,
                    "alt_m": 0.0,
                    "heading_deg": r.wind_dir_deg,
                    "speed_kmh": r.wind_speed_kmh,
                    "callsign": r.location_name,
                    "affiliation": "friendly",
                    "confidence": 1.0,
                    "timestamp": r.timestamp,
                    "raw_data": {
                        "temperature_c": str(r.temperature_c),
                        "cloud_cover_pct": str(r.cloud_cover_pct),
                        "precipitation_mm": str(r.precipitation_mm),
                        "visibility_km": str(r.visibility_km),
                        "weather_code": str(r.weather_code),
                        "weather_desc": self.WMO_CODES.get(r.weather_code, "Unknown"),
                    },
                }
            )
        return result

    def get_sensor_impact(self, location_id: str = None) -> dict:
        """Calculate weather impact on sensor performance.

        Returns dict with:
          - detection_range_factor: 0.5-1.0 (rain/fog reduce radar range)
          - visibility_factor: 0.1-1.0 (reduced visual/EO/IR detection
          - crosswind_kt: crosswind component in knots
        """
        reports = (
            self._reports
            if not location_id
            else [r for r in self._reports if r.location_id == location_id]
        )
        if not reports:
            return {
                "detection_range_factor": 1.0,
                "visibility_factor": 1.0,
                "crosswind_kt": 0,
            }

        r = reports[0]
        # Rain attenuates radar: 1mm/hr ~ 10% range reduction
        rain_factor = max(0.5, 1.0 - r.precipitation_mm * 0.1)
        # Cloud cover slightly affects EO/IR
        cloud_factor = 1.0 - (r.cloud_cover_pct / 100.0) * 0.2
        # Fog reduces visibility sensors
        fog_factor = 1.0
        if r.weather_code in (45, 48):
            fog_factor = 0.3

        return {
            "detection_range_factor": round(rain_factor * cloud_factor, 2),
            "visibility_factor": round(
                min(r.visibility_km / 20.0, 1.0) * fog_factor, 2
            ),
            "crosswind_kt": round(r.wind_speed_kmh * 0.54, 0),  # km/h to knots
        }

    @property
    def stats(self) -> dict:
        return {
            "total_fetches": self._total_fetches,
            "real_reports": self._real_reports,
            "sim_reports": self._sim_reports,
            "locations": len(self.locations),
        }
