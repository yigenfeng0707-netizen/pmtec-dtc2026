"""
AIS Maritime Vessel Tracking Adapter (P2-3).

Provides maritime vessel position data from AIS (Automatic Identification
System) feeds. Uses simulated data with realistic vessel patterns for the
IndoPACOM area of responsibility, with optional real API integration.

Real API integration options:
  - MarineTraffic API (requires API key)
  - VesselFinder API (requires API key)

In simulation mode, generates realistic vessel tracks including:
  - Military vessels (carrier strike groups, destroyers)
  - Commercial shipping (tankers, cargo, fishing)
  - Coast guard / patrol vessels

Normalized output: list of LiveSensorData dicts with lat/lon/speed/heading.
"""

import time
import logging
import random
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("pmtec.live_data.ais")


@dataclass
class AISVessel:
    """Normalized AIS vessel contact."""

    mmsi: str
    vessel_name: str
    vessel_type: str
    lat: float
    lon: float
    speed_kmh: float
    heading_deg: float
    nav_status: str  # underway, anchored, moored, etc.
    destination: str
    timestamp: int


class AISAdapter:
    """AIS maritime vessel data adapter.

    Generates realistic vessel tracks for the Western Pacific AOR.
    Can be extended to use real AIS API feeds.
    """

    # Common vessel types and their speed characteristics
    VESSEL_TYPES = {
        "carrier": {
            "speed_range": (20, 35),
            "prefix": "CVN",
            "affiliation": "friendly",
        },
        "destroyer": {
            "speed_range": (25, 45),
            "prefix": "DDG",
            "affiliation": "friendly",
        },
        "cruiser": {"speed_range": (25, 40), "prefix": "CG", "affiliation": "friendly"},
        "tanker": {"speed_range": (20, 28), "prefix": "M/T", "affiliation": "neutral"},
        "cargo": {"speed_range": (18, 25), "prefix": "M/V", "affiliation": "neutral"},
        "fishing": {"speed_range": (8, 15), "prefix": "F/V", "affiliation": "neutral"},
        "patrol": {"speed_range": (25, 35), "prefix": "WPC", "affiliation": "friendly"},
        "recon": {"speed_range": (15, 30), "prefix": "AGI", "affiliation": "hostile"},
    }

    def __init__(
        self,
        bbox: tuple = None,
        sim_vessel_count: int = 20,
    ):
        self.bbox = bbox or (10.0, 45.0, 120.0, 160.0)
        self.sim_vessel_count = sim_vessel_count
        self._vessels: list[AISVessel] = []
        self._last_fetch: float = 0
        self._fetch_interval: int = 30  # AIS updates less frequently
        self._total_fetches: int = 0

    def fetch(self) -> list[AISVessel]:
        """Fetch current vessel contacts."""
        now = time.time()
        if now - self._last_fetch < self._fetch_interval and self._vessels:
            return self._vessels

        self._last_fetch = now
        self._total_fetches += 1

        # Generate/update vessel positions
        if not self._vessels:
            self._vessels = self._generate_vessels()
        else:
            self._update_vessels()

        return self._vessels

    def _generate_vessels(self) -> list[AISVessel]:
        """Generate realistic initial vessel distribution."""
        min_lat, max_lat, min_lon, max_lon = self.bbox
        vessels = []
        nav_statuses = ["underway", "anchored", "moored"]

        for i in range(self.sim_vessel_count):
            vtype = random.choices(
                list(self.VESSEL_TYPES.keys()),
                weights=[1, 2, 1, 4, 4, 3, 2, 1],  # more commercial than military
                k=1,
            )[0]
            spec = self.VESSEL_TYPES[vtype]
            lat = random.uniform(min_lat, max_lat)
            lon = random.uniform(min_lon, max_lon)
            nav_status = random.choice(nav_statuses)
            speed = (
                0 if nav_status != "underway" else random.uniform(*spec["speed_range"])
            )
            heading = random.uniform(0, 360) if speed > 0 else 0

            vessels.append(
                AISVessel(
                    mmsi=f"{random.randint(300000000, 799999999)}",
                    vessel_name=f"{spec['prefix']}-{i + 1:03d}",
                    vessel_type=vtype,
                    lat=lat,
                    lon=lon,
                    speed_kmh=speed,
                    heading_deg=heading,
                    nav_status=nav_status,
                    destination=random.choice(
                        [
                            "Yokosuka",
                            "Pearl Harbor",
                            "Guam",
                            "Singapore",
                            "Busan",
                            "Manila",
                            " Sydney",
                            "Unknown",
                        ]
                    ),
                    timestamp=int(time.time()),
                )
            )
        return vessels

    def _update_vessels(self):
        """Update vessel positions (simulate movement)."""
        for v in self._vessels:
            if v.nav_status != "underway" or v.speed_kmh == 0:
                continue
            # Simple kinematic update
            dt = self._fetch_interval
            dist_km = v.speed_kmh * (dt / 3600.0)
            # Convert heading to radians
            rad = math.radians(v.heading_deg)
            # Approximate lat/lon update (small distances)
            dlat = (dist_km / 111.0) * math.cos(rad)
            dlon = (dist_km / (111.0 * math.cos(math.radians(v.lat)))) * math.sin(rad)
            v.lat += dlat
            v.lon += dlon
            v.timestamp = int(time.time())

            # Keep within bbox
            min_lat, max_lat, min_lon, max_lon = self.bbox
            if v.lat < min_lat or v.lat > max_lat:
                v.heading_deg = (180 - v.heading_deg) % 360
            if v.lon < min_lon or v.lon > max_lon:
                v.heading_deg = (360 - v.heading_deg) % 360

    def normalize(self, vessels: list[AISVessel] = None) -> list[dict]:
        """Convert AISVessel list to LiveSensorData dicts."""
        vessels = vessels or self._vessels
        result = []
        for v in vessels:
            spec = self.VESSEL_TYPES.get(v.vessel_type, {})
            affiliation = spec.get("affiliation", "neutral")

            result.append(
                {
                    "sensor_id": f"AIS-{v.mmsi}",
                    "sensor_type": "AIS",
                    "lat": v.lat,
                    "lon": v.lon,
                    "alt_m": 0.0,  # vessels are at sea level
                    "heading_deg": v.heading_deg,
                    "speed_kmh": v.speed_kmh,
                    "callsign": v.vessel_name,
                    "affiliation": affiliation,
                    "confidence": 0.90,
                    "timestamp": v.timestamp,
                    "raw_data": {
                        "mmsi": v.mmsi,
                        "vessel_type": v.vessel_type,
                        "nav_status": v.nav_status,
                        "destination": v.destination,
                    },
                }
            )
        return result

    @property
    def stats(self) -> dict:
        return {
            "total_fetches": self._total_fetches,
            "current_vessels": len(self._vessels),
            "underway": sum(1 for v in self._vessels if v.nav_status == "underway"),
        }
