"""
Military Base Model - represents a single installation in the INDOPACOM network.
Maps to DTB Model: Battle Network node + Application Store host.
"""

import json
import math
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MilitaryBase:
    id: str
    name: str
    name_cn: str
    country: str
    region: str
    lat: float
    lon: float
    branch: str
    unit: str = ""
    aircraft: str = ""
    runway_m: int = 0
    personnel: int = 0
    facility_code: str = ""
    ace_hub: bool = False
    scars: bool = False
    lvc_layer: str = ""
    role: str = ""
    vs26_role: str = ""
    dtb_mapping: str = ""
    asda_mapping: str = ""
    # P10: 政治准入（v2 数据字段；旧数据缺省不受约束）
    access_uncertainty: str = None
    # Computed/derived
    parking_capacity: int = 0
    has_shelters: bool = False
    defense_level: int = 1  # 1=basic, 2=enhanced, 3=IAMD
    current_aircraft: list = field(default_factory=list)
    # P10: 政治准入约束（由 ASDAEngine 注入 PoliticalConstraint）
    political: object = None

    @property
    def access_state(self) -> str:
        if self.political is None:
            return "full"
        return self.political.state(self.id)

    @property
    def politically_accessible(self) -> bool:
        """P10: DENIED 基地不可用于分散/疏散目的地。"""
        return self.access_state != "denied"

    def __post_init__(self):
        if self.parking_capacity == 0:
            if self.runway_m > 2400:
                self.parking_capacity = 40
            elif self.runway_m > 1800:
                self.parking_capacity = 25
            elif self.runway_m > 1200:
                self.parking_capacity = 12
            else:
                self.parking_capacity = 8
        if self.defense_level == 1 and self.ace_hub:
            self.defense_level = 2
        if "IAMD" in self.role or "GDS" in self.role or "defense" in self.role.lower():
            self.defense_level = 3

    @property
    def available_parking(self) -> int:
        used = sum(1 for _ in self.current_aircraft)
        # P10: 政治准入折减容量（restricted 减半，denied 归零）
        cap = self.parking_capacity
        if self.political is not None:
            cap = int(cap * self.political.capacity_factor(self.id))
        return max(0, cap - used)

    @property
    def utilization(self) -> float:
        if self.parking_capacity == 0:
            return 0.0
        return len(self.current_aircraft) / self.parking_capacity

    @property
    def vulnerability_index(self) -> float:
        """Higher = more vulnerable. Combines aircraft count, defense level, shelter status."""
        ac_count = len(self.current_aircraft)
        if ac_count == 0:
            return 0.0
        defense_factor = 1.0 / self.defense_level
        shelter_factor = 0.3 if self.has_shelters else 1.0
        concentration_factor = min(1.0, ac_count / 20.0)
        return (
            ac_count
            * defense_factor
            * shelter_factor
            * (0.5 + 0.5 * concentration_factor)
        )

    @property
    def strike_capability(self) -> float:
        """Aggregate strike power of based aircraft (P10: denied sites contribute 0)."""
        if not self.politically_accessible:
            return 0.0
        from .aircraft import Aircraft

        total = 0.0
        for ac in self.current_aircraft:
            if hasattr(ac, "ac_type"):
                from config import AIRCRAFT_VALUE, COMBAT_RADIUS_KM

                total += AIRCRAFT_VALUE.get(ac.ac_type, 0) * (
                    COMBAT_RADIUS_KM.get(ac.ac_type, 0) / 1000.0
                )
        return total

    def distance_to(self, other: "MilitaryBase") -> float:
        """Great-circle distance in km using Haversine formula."""
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        from config import EARTH_RADIUS_KM

        return EARTH_RADIUS_KM * c

    def bearing_to(self, other: "MilitaryBase") -> float:
        """Initial bearing in degrees."""
        lat1, lon1 = math.radians(self.lat), math.radians(self.lon)
        lat2, lon2 = math.radians(other.lat), math.radians(other.lon)
        dlon = lon2 - lon1
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(
            lat2
        ) * math.cos(dlon)
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360

    def can_accept(self, ac_type: str, count: int = 1) -> bool:
        from config import PARKING_SPOTS

        needed = PARKING_SPOTS.get(ac_type, 1) * count
        return self.available_parking >= needed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "name_cn": self.name_cn,
            "lat": self.lat,
            "lon": self.lon,
            "region": self.region,
            "branch": self.branch,
            "ace_hub": self.ace_hub,
            "parking_capacity": self.parking_capacity,
            "current_count": len(self.current_aircraft),
            "available_parking": self.available_parking,
            "utilization": round(self.utilization, 3),
            "vulnerability_index": round(self.vulnerability_index, 2),
            "defense_level": self.defense_level,
            "dtb_mapping": self.dtb_mapping,
            "asda_mapping": self.asda_mapping,
        }


class BaseNetwork:
    """Network of military bases forming the ACE Hub-Spoke architecture."""

    def __init__(self):
        self.bases: dict[str, MilitaryBase] = {}
        self._adjacency: dict[str, dict[str, float]] = {}

    @classmethod
    def from_geojson(cls, geojson_path: str) -> "BaseNetwork":
        net = cls()
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        props_list = []
        for feat in data["features"]:
            p = feat["properties"]
            props_list.append(p)
            lon, lat = feat["geometry"]["coordinates"]
            base = MilitaryBase(
                id=p["id"],
                name=p["name"],
                name_cn=p["name_cn"],
                country=p["country"],
                region=p["region"],
                lat=lat,
                lon=lon,
                branch=p["branch"],
                unit=p.get("unit", ""),
                aircraft=p.get("aircraft", ""),
                runway_m=p.get("runway_m", 0),
                personnel=p.get("personnel", 0),
                facility_code=p.get("facility_code", ""),
                ace_hub=p.get("ace_hub", False),
                scars=p.get("scars", False),
                lvc_layer=p.get("lvc_layer", ""),
                role=p.get("role", ""),
                vs26_role=p.get("vs26_role", ""),
                dtb_mapping=p.get("dtb_mapping", ""),
                asda_mapping=p.get("asda_mapping", ""),
                access_uncertainty=p.get("access_uncertainty"),
            )
            net.bases[base.id] = base
        # P10: 附加政治准入约束（演化场景；无盟友站点时为空约束，行为不变）
        from .political import PoliticalConstraint

        net.political = PoliticalConstraint.from_geojson_props(props_list)
        for base in net.bases.values():
            base.political = net.political
        net._build_adjacency()
        return net

    def _build_adjacency(self):
        for id1, b1 in self.bases.items():
            self._adjacency[id1] = {}
            for id2, b2 in self.bases.items():
                if id1 != id2:
                    self._adjacency[id1][id2] = b1.distance_to(b2)

    def get(self, base_id: str) -> Optional[MilitaryBase]:
        return self.bases.get(base_id)

    def hubs(self) -> list[MilitaryBase]:
        return [b for b in self.bases.values() if b.ace_hub]

    def spokes(self) -> list[MilitaryBase]:
        return [b for b in self.bases.values() if not b.ace_hub]

    def nearby_bases(self, base_id: str, max_distance_km: float = 2000) -> list[tuple]:
        """Return [(base, distance)] sorted by distance."""
        base = self.bases[base_id]
        result = []
        for other_id, dist in self._adjacency.get(base_id, {}).items():
            if dist <= max_distance_km:
                result.append((self.bases[other_id], dist))
        result.sort(key=lambda x: x[1])
        return result

    def neighbors_in_range(self, base_id: str, ac_type: str) -> list[tuple]:
        """Return bases within aircraft's combat radius."""
        from config import COMBAT_RADIUS_KM

        max_range = COMBAT_RADIUS_KM.get(ac_type, 1000)
        return self.nearby_bases(base_id, max_range)

    @property
    def total_aircraft(self) -> int:
        return sum(len(b.current_aircraft) for b in self.bases.values())

    @property
    def network_vulnerability(self) -> float:
        return sum(b.vulnerability_index for b in self.bases.values())

    @property
    def network_strike_capability(self) -> float:
        return sum(b.strike_capability for b in self.bases.values())

    def status_report(self) -> dict:
        return {
            "total_bases": len(self.bases),
            "total_hubs": len(self.hubs()),
            "total_spokes": len(self.spokes()),
            "total_aircraft": self.total_aircraft,
            "network_vulnerability": round(self.network_vulnerability, 2),
            "network_strike_capability": round(self.network_strike_capability, 2),
            "bases": {bid: b.to_dict() for bid, b in self.bases.items()},
        }
