"""
Battlefield Entities - aircraft, missiles, sensors for PMTEC simulation.
DTB Model: Plug-and-Play components (each entity is a composable capability module).
"""

import math
import random
import uuid
from dataclasses import dataclass, field
from typing import Optional
from config import (
    AIRCRAFT_SPEED_KMH,
    COMBAT_RADIUS_KM,
    AIRCRAFT_VALUE,
    THREAT_SPEED_KMH,
    THREAT_CEP_M,
    THREAT_WARHEAD_KG,
    EARTH_RADIUS_KM,
    EW_JAMMER_POWER_KW,
    EW_JAM_RANGE_KM,
    EW_BANDS,
    CYBER_ATTACK_TYPES,
)


@dataclass
class BattlefieldEntity:
    id: str
    entity_type: str  # aircraft, missile, sensor, base
    subtype: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0
    heading_deg: float = 0.0
    speed_kmh: float = 0.0
    affiliation: str = "friendly"  # friendly, hostile, neutral
    base_id: str = ""
    status: str = "active"  # active, destroyed, transferring, landed
    fuel_pct: float = 1.0
    ammo_count: int = 0
    timestamp: float = 0.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def move(self, dt_seconds: float):
        """Move entity based on heading and speed."""
        if self.status != "active" or self.speed_kmh <= 0:
            return
        # Convert to meters
        distance_m = (self.speed_kmh * 1000 / 3600) * dt_seconds
        # Great circle movement
        lat_rad = math.radians(self.lat)
        lon_rad = math.radians(self.lon)
        bearing = math.radians(self.heading_deg)
        # Angular distance
        delta = distance_m / (EARTH_RADIUS_KM * 1000)
        new_lat = math.asin(
            math.sin(lat_rad) * math.cos(delta)
            + math.cos(lat_rad) * math.sin(delta) * math.cos(bearing)
        )
        new_lon = lon_rad + math.atan2(
            math.sin(bearing) * math.sin(delta) * math.cos(lat_rad),
            math.cos(delta) - math.sin(lat_rad) * math.sin(new_lat),
        )
        self.lat = math.degrees(new_lat)
        self.lon = math.degrees(new_lon)
        self.timestamp += dt_seconds

    def set_heading_toward(self, target_lat: float, target_lon: float):
        """Set heading to point toward target coordinates."""
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(target_lat), math.radians(target_lon)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)
        bearing = math.degrees(math.atan2(y, x))
        self.heading_deg = (bearing + 360) % 360

    def distance_to(self, lat: float, lon: float) -> float:
        """Distance in km to a point."""
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(lat), math.radians(lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "uid": self.uid,
            "type": self.entity_type,
            "subtype": self.subtype,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "alt_m": round(self.alt_m, 0),
            "heading": round(self.heading_deg, 1),
            "speed_kmh": round(self.speed_kmh, 0),
            "affiliation": self.affiliation,
            "base_id": self.base_id,
            "status": self.status,
            "fuel_pct": round(self.fuel_pct, 2),
            "ammo": self.ammo_count,
        }


class AircraftEntity(BattlefieldEntity):
    """A simulated aircraft entity in the Virtual layer."""

    def __init__(
        self,
        ac_type: str,
        base_id: str,
        lat: float,
        lon: float,
        callsign: str = "",
        affiliation: str = "friendly",
    ):
        super().__init__(
            id=callsign or f"AC-{uuid.uuid4().hex[:6]}",
            entity_type="aircraft",
            subtype=ac_type,
            lat=lat,
            lon=lon,
            alt_m=10000,
            speed_kmh=AIRCRAFT_SPEED_KMH.get(ac_type, 1000) * 0.7,
            affiliation=affiliation,
            base_id=base_id,
            ammo_count=6 if ac_type.startswith("F-") else 0,
        )
        self.ac_type = ac_type
        self.combat_radius = COMBAT_RADIUS_KM.get(ac_type, 800)
        self.value = AIRCRAFT_VALUE.get(ac_type, 50)
        self.mission: str = "patrol"
        self.target_lat: float = 0.0
        self.target_lon: float = 0.0

    def assign_mission(
        self, mission: str, target_lat: float = 0, target_lon: float = 0
    ):
        self.mission = mission
        self.target_lat = target_lat
        self.target_lon = target_lon
        if mission in ("transfer", "strike"):
            self.set_heading_toward(target_lat, target_lon)
            self.status = "active"
        elif mission == "patrol":
            self.status = "active"

    def update(self, dt_seconds: float):
        """Update aircraft state."""
        if self.status != "active":
            return
        self.move(dt_seconds)
        # Consume fuel
        self.fuel_pct = max(0, self.fuel_pct - 0.001 * dt_seconds)
        # Check mission completion
        if self.mission in ("transfer", "strike") and self.target_lat:
            dist = self.distance_to(self.target_lat, self.target_lon)
            if dist < 5.0:  # within 5km = arrived
                if self.mission == "transfer":
                    self.status = "landed"
                    self.speed_kmh = 0
                elif self.mission == "strike":
                    self.status = "rtb"  # return to base
                    self.mission = "transfer"
                    self.target_lat, self.target_lon = 0, 0  # will be set by command


class MissileEntity(BattlefieldEntity):
    """A simulated missile entity (threat) in the Virtual layer."""

    def __init__(
        self,
        missile_type: str,
        launch_lat: float,
        launch_lon: float,
        target_lat: float,
        target_lon: float,
    ):
        super().__init__(
            id=f"MSL-{uuid.uuid4().hex[:6]}",
            entity_type="missile",
            subtype=missile_type,
            lat=launch_lat,
            lon=launch_lon,
            alt_m=50000,
            speed_kmh=THREAT_SPEED_KMH.get(missile_type, 3000),
            affiliation="hostile",
            status="active",
        )
        self.target_lat = target_lat
        self.target_lon = target_lon
        self.cep = THREAT_CEP_M.get(missile_type, 100)
        self.warhead_kg = THREAT_WARHEAD_KG.get(missile_type, 500)
        self.impact_time: float = 0.0
        self.set_heading_toward(target_lat, target_lon)

    def update(self, dt_seconds: float):
        """Update missile trajectory."""
        if self.status != "active":
            return
        self.move(dt_seconds)
        self.alt_m = max(0, self.alt_m - 100 * dt_seconds)  # descending
        # Check impact
        dist = self.distance_to(self.target_lat, self.target_lon)
        if dist < 2.0:  # impact
            self.status = "destroyed"
            self.lat = self.target_lat
            self.lon = self.target_lon
            self.alt_m = 0
            self.impact_time = self.timestamp  # record actual impact time


class SensorEntity(BattlefieldEntity):
    """A sensor entity (radar/satellite) in the Live layer."""

    def __init__(
        self,
        sensor_type: str,
        lat: float,
        lon: float,
        base_id: str = "",
        detection_range_km: float = 400,
    ):
        super().__init__(
            id=f"SEN-{uuid.uuid4().hex[:6]}",
            entity_type="sensor",
            subtype=sensor_type,
            lat=lat,
            lon=lon,
            alt_m=0,
            speed_kmh=0,
            affiliation="friendly",
            base_id=base_id,
            status="active",
        )
        self.detection_range_km = detection_range_km
        self.detection_confidence = 0.8
        self.range_factor = 1.0  # P3-1: dynamic range multiplier (weather, EW, etc.)

    def set_range_factor(self, factor: float):
        """P3-1: Set dynamic detection range factor (weather/EW impact)."""
        self.range_factor = max(0.1, min(1.5, factor))

    def scan(self, entities: list) -> list:
        """Detect entities within range. Returns list of detected tracks."""
        effective_range = self.detection_range_km * self.range_factor
        tracks = []
        for e in entities:
            if e.affiliation == "friendly":
                continue
            dist = self.distance_to(e.lat, e.lon)
            if dist <= effective_range and e.status == "active":
                # Confidence decreases with distance
                conf = self.detection_confidence * (1 - dist / effective_range * 0.5)
                tracks.append(
                    {
                        "lat": e.lat + random.gauss(0, 0.01),  # measurement noise
                        "lon": e.lon + random.gauss(0, 0.01),
                        "alt_m": e.alt_m,
                        "heading_deg": e.heading_deg,
                        "speed_kmh": e.speed_kmh,
                        "confidence": max(0.1, conf),
                        "classification": e.entity_type,
                        "source": self.id,
                    }
                )
        return tracks

    def update(self, dt_seconds: float):
        pass  # sensors don't move


class EWThreatEntity(BattlefieldEntity):
    """Electronic Warfare threat entity - radar jamming and ELINT.

    Simulates hostile electronic attack on friendly sensors and comms.
    Affects sensor detection confidence and datalink reliability within jam range.
    LVC layer: Virtual (CGF emitter) / Live (effect on real sensors).
    """

    def __init__(
        self,
        ew_type: str,
        launch_lat: float,
        launch_lon: float,
        target_lat: float,
        target_lon: float,
        affiliation: str = "hostile",
    ):
        power_kw = EW_JAMMER_POWER_KW.get(ew_type, 100)
        jam_range = EW_JAM_RANGE_KM.get(ew_type, 200)
        speed = 800 if ew_type.startswith("IL") else 0  # airborne vs naval
        super().__init__(
            id=f"EW-{uuid.uuid4().hex[:6]}",
            entity_type="ew_threat",
            subtype=ew_type,
            lat=launch_lat,
            lon=launch_lon,
            alt_m=8000 if ew_type.startswith("IL") else 0,
            speed_kmh=speed,
            affiliation=affiliation,
            status="active",
        )
        self.target_lat = target_lat
        self.target_lon = target_lon
        self.power_kw = power_kw
        self.jam_range_km = jam_range
        self.jammed_bands = list(EW_BANDS)
        self.effectiveness = 0.0  # 0=ineffective, 1=full jam
        self.active_duration = 0.0
        self._move_to_target = speed > 0

    def update(self, dt_seconds: float):
        if self.status != "active":
            return
        self.active_duration += dt_seconds
        if self._move_to_target:
            self.move(dt_seconds)
            dist = self.distance_to(self.target_lat, self.target_lon)
            if dist < 10.0:
                self._move_to_target = False  # on station, start jamming
        # Calculate jamming effectiveness based on proximity to target
        dist_to_target = self.distance_to(self.target_lat, self.target_lon)
        if dist_to_target < self.jam_range_km:
            # Closer = stronger jamming, ramp up over time
            proximity_factor = 1.0 - (dist_to_target / self.jam_range_km)
            ramp = min(1.0, self.active_duration / 10.0)  # 10s ramp-up
            self.effectiveness = min(0.9, proximity_factor * ramp * 0.8)
        else:
            self.effectiveness = 0.0

    def get_jammed_sensors(self, sensors: list) -> list:
        """Return list of sensor IDs within jamming range."""
        if self.effectiveness < 0.1:
            return []
        jammed = []
        for s in sensors:
            if s.status != "active":
                continue
            dist = self.distance_to(s.lat, s.lon)
            if dist <= self.jam_range_km:
                jammed.append(s.id)
        return jammed

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["power_kw"] = round(self.power_kw, 0)
        d["jam_range_km"] = self.jam_range_km
        d["effectiveness"] = round(self.effectiveness, 2)
        d["active_duration"] = round(self.active_duration, 1)
        return d


class CyberThreatEntity(BattlefieldEntity):
    """Cyber attack threat entity - network intrusion, GPS spoofing, comms disruption.

    Non-kinetic threat targeting C2 networks, datalinks, navigation systems.
    Progresses through phases: infiltration -> persistence -> impact -> (detection) -> remediation.
    LVC layer: Constructive (affects command decisions) / Live (affects real comms).
    """

    def __init__(
        self,
        attack_type: str,
        target_base_id: str = "",
        affiliation: str = "hostile",
    ):
        params = CYBER_ATTACK_TYPES.get(attack_type, {})
        super().__init__(
            id=f"CYB-{uuid.uuid4().hex[:6]}",
            entity_type="cyber_threat",
            subtype=attack_type,
            lat=0.0,
            lon=0.0,
            alt_m=0,
            speed_kmh=0,
            affiliation=affiliation,
            status="active",
        )
        self.target_base_id = target_base_id
        self.target_system = params.get("target", "unknown")
        self.detection_difficulty = params.get("detection_difficulty", 0.7)
        self.impact_severity = params.get("impact_severity", 0.5)
        self.duration_s = params.get("duration_s", 60)
        self.elapsed_s = 0.0
        self.phase = (
            "infiltration"  # infiltration -> persistence -> impact -> remediated
        )
        self.detected = False
        self.effectiveness = 0.0
        self.impact_score = 0.0  # cumulative damage

    def update(self, dt_seconds: float):
        if self.status != "active":
            return
        self.elapsed_s += dt_seconds
        # Phase progression
        if self.elapsed_s < self.duration_s * 0.25:
            self.phase = "infiltration"
            self.effectiveness = self.elapsed_s / (self.duration_s * 0.25) * 0.3
        elif self.elapsed_s < self.duration_s * 0.5:
            self.phase = "persistence"
            self.effectiveness = (
                0.3
                + (self.elapsed_s - self.duration_s * 0.25)
                / (self.duration_s * 0.25)
                * 0.3
            )
        elif self.elapsed_s < self.duration_s:
            self.phase = "impact"
            self.effectiveness = (
                0.6
                + (self.elapsed_s - self.duration_s * 0.5)
                / (self.duration_s * 0.5)
                * 0.4
            )
            self.impact_score += self.impact_severity * dt_seconds / 10.0
        else:
            self.phase = "remediated"
            self.effectiveness = max(0, self.effectiveness - dt_seconds / 5.0)
            if self.effectiveness < 0.05:
                self.status = "neutralized"
        # Auto-detection check
        if not self.detected and self.elapsed_s > self.duration_s * 0.3:
            import random as _r

            if _r.random() < (1.0 - self.detection_difficulty) * 0.1:
                self.detected = True

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["target_system"] = self.target_system
        d["phase"] = self.phase
        d["detected"] = self.detected
        d["effectiveness"] = round(self.effectiveness, 2)
        d["impact_score"] = round(self.impact_score, 2)
        return d
