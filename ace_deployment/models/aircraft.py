"""
Aircraft Model - represents military aircraft assigned to bases.
Maps to DTB Model: Plug-and-Play component (each aircraft is a deployable capability module).
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional
from config import AIRCRAFT_SPEED_KMH, COMBAT_RADIUS_KM, AIRCRAFT_VALUE, PARKING_SPOTS


@dataclass
class Aircraft:
    ac_type: str
    base_id: str
    callsign: str = ""
    status: str = "grounded"  # grounded, transferring, airborne, destroyed
    sheltered: bool = False
    mission_ready: bool = True
    fuel_pct: float = 1.0
    uid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def speed_kmh(self) -> float:
        return AIRCRAFT_SPEED_KMH.get(self.ac_type, 1000)

    @property
    def combat_radius_km(self) -> float:
        return COMBAT_RADIUS_KM.get(self.ac_type, 800)

    @property
    def value(self) -> int:
        return AIRCRAFT_VALUE.get(self.ac_type, 50)

    @property
    def parking_spots(self) -> int:
        return PARKING_SPOTS.get(self.ac_type, 1)

    @property
    def is_high_value(self) -> bool:
        return self.value >= 80

    @property
    def is_fighter(self) -> bool:
        return self.ac_type in ("F-35A", "F-22A", "F-15C", "F-15E", "F-16C")

    def transfer_time_hours(self, distance_km: float) -> float:
        """Time to transfer distance_km at cruise speed."""
        cruise_speed = self.speed_kmh * 0.7  # cruise at ~70% max
        if cruise_speed <= 0:
            return 999.0
        return distance_km / cruise_speed

    def can_reach(self, distance_km: float) -> bool:
        """Check if aircraft can fly distance_km unrefueled."""
        return distance_km <= self.combat_radius_km * 0.8  # 80% safety margin

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "type": self.ac_type,
            "base_id": self.base_id,
            "callsign": self.callsign,
            "status": self.status,
            "sheltered": self.sheltered,
            "mission_ready": self.mission_ready,
            "value": self.value,
            "fuel_pct": round(self.fuel_pct, 2),
        }


class AircraftFleet:
    """Manages a collection of aircraft across the base network."""

    def __init__(self):
        self.aircraft: list[Aircraft] = []

    def add(self, ac: Aircraft):
        self.aircraft.append(ac)

    def add_squadron(self, ac_type: str, base_id: str, count: int):
        for i in range(count):
            ac = Aircraft(
                ac_type=ac_type,
                base_id=base_id,
                callsign=f"{ac_type[:3]}-{i + 1:02d}",
                sheltered=False,
            )
            self.add(ac)

    @property
    def total(self) -> int:
        return len(self.aircraft)

    @property
    def active(self) -> int:
        return sum(1 for a in self.aircraft if a.status == "grounded")

    @property
    def destroyed(self) -> int:
        return sum(1 for a in self.aircraft if a.status == "destroyed")

    def at_base(self, base_id: str) -> list[Aircraft]:
        return [
            a for a in self.aircraft if a.base_id == base_id and a.status == "grounded"
        ]

    def by_type(self, ac_type: str) -> list[Aircraft]:
        return [a for a in self.aircraft if a.ac_type == ac_type]

    def high_value(self) -> list[Aircraft]:
        return [a for a in self.aircraft if a.is_high_value and a.status == "grounded"]

    def sort_by_priority(self, reverse=True) -> list[Aircraft]:
        """Sort by evacuation priority (high value first)."""
        return sorted(self.aircraft, key=lambda a: a.value, reverse=reverse)

    def summary(self) -> dict:
        type_counts = {}
        for ac in self.aircraft:
            type_counts[ac.ac_type] = type_counts.get(ac.ac_type, 0) + 1
        return {
            "total": self.total,
            "active": self.active,
            "destroyed": self.destroyed,
            "by_type": type_counts,
            "total_value": sum(
                a.value for a in self.aircraft if a.status != "destroyed"
            ),
        }

    def assign_to_bases(self, network):
        """Link aircraft to their base objects."""
        for ac in self.aircraft:
            base = network.get(ac.base_id)
            if base and ac.status == "grounded":
                if ac not in base.current_aircraft:
                    base.current_aircraft.append(ac)

    def remove_from_base(self, ac: Aircraft, network):
        base = network.get(ac.base_id)
        if base and ac in base.current_aircraft:
            base.current_aircraft.remove(ac)

    def add_to_base(self, ac: Aircraft, new_base_id: str, network):
        ac.base_id = new_base_id
        base = network.get(new_base_id)
        if base and ac not in base.current_aircraft:
            base.current_aircraft.append(ac)
