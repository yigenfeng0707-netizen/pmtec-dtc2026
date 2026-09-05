"""
Threat Model - represents incoming threats (ballistic missiles, cruise missiles, air raids).
Maps to DTB Model: Battle Network sensor feed; ASDA: Sense trigger.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional
from config import (
    THREAT_SPEED_KMH,
    THREAT_CEP_M,
    THREAT_WARHEAD_KG,
    THREAT_RANGE_KM,
    ALERT_TO_IMPACT_MINUTES,
    BLAST_RADIUS_500KG_M,
    SHELTER_SURVIVAL_PROB,
    OPEN_SURVIVAL_PROB,
    RUNWAY_CRATER_RADIUS_PER_500KG,
)


@dataclass
class Threat:
    threat_type: str  # DF-21D, DF-26, KH-101, etc.
    target_base_id: str
    launch_lat: float = 0.0
    launch_lon: float = 0.0
    launch_time: float = 0.0  # T=0 reference
    quantity: int = 1
    uid: str = field(default_factory=lambda: f"THREAT-{random.randint(1000, 9999)}")

    @property
    def speed_kmh(self) -> float:
        return THREAT_SPEED_KMH.get(self.threat_type, 3000)

    @property
    def cep_m(self) -> float:
        return THREAT_CEP_M.get(self.threat_type, 100)

    @property
    def warhead_kg(self) -> float:
        return THREAT_WARHEAD_KG.get(self.threat_type, 500)

    @property
    def range_km(self) -> float:
        return THREAT_RANGE_KM.get(self.threat_type, 2000)

    @property
    def alert_to_impact_min(self) -> float:
        return ALERT_TO_IMPACT_MINUTES.get(self.threat_type, 30)

    @property
    def blast_radius_m(self) -> float:
        """Effective blast radius scaled by warhead size."""
        return BLAST_RADIUS_500KG_M * (self.warhead_kg / 500.0) ** 0.33

    @property
    def crater_radius_m(self) -> float:
        return RUNWAY_CRATER_RADIUS_PER_500KG * (self.warhead_kg / 500.0) ** 0.33

    def flight_time_hours(self, distance_km: float) -> float:
        return distance_km / self.speed_kmh

    def time_to_impact_min(self, distance_km: float) -> float:
        """Minutes from launch to impact."""
        return self.flight_time_hours(distance_km) * 60

    def available_response_time_min(self) -> float:
        """Minutes available for response (alert to impact)."""
        return self.alert_to_impact_min

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "type": self.threat_type,
            "target": self.target_base_id,
            "quantity": self.quantity,
            "warhead_kg": self.warhead_kg,
            "cep_m": self.cep_m,
            "blast_radius_m": round(self.blast_radius_m, 1),
            "crater_radius_m": round(self.crater_radius_m, 1),
            "alert_to_impact_min": self.alert_to_impact_min,
        }


@dataclass
class ThreatPackage:
    """A coordinated multi-base threat scenario."""

    threats: list[Threat] = field(default_factory=list)
    scenario_name: str = ""
    description: str = ""

    def add_threat(self, threat: Threat):
        self.threats.append(threat)

    @property
    def total_warheads(self) -> int:
        return sum(t.quantity for t in self.threats)

    @property
    def targeted_bases(self) -> list[str]:
        return list(set(t.target_base_id for t in self.threats))

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "description": self.description,
            "total_threats": len(self.threats),
            "total_warheads": self.total_warheads,
            "targeted_bases": self.targeted_bases,
            "threats": [t.to_dict() for t in self.threats],
        }

    @classmethod
    def scenario_china_salvo(cls, network) -> "ThreatPackage":
        """Scenario: Coordinated Chinese missile salvo against key INDOPACOM bases."""
        pkg = cls(
            scenario_name="PLA Missile Salvo",
            description="Coordinated DF-26 IRBM + DF-17 HGV + CJ-10 LACM strike "
            "against Andersen AFB, Kadena AB, Yokota AB, and K-2",
        )
        # DF-26 against Andersen AFB (Guam)
        pkg.add_threat(
            Threat(
                threat_type="DF-26",
                target_base_id="GU-ANDERSEN",
                launch_lat=25.0,
                launch_lon=118.0,
                quantity=6,
            )
        )
        # DF-26 against Kadena AB (Okinawa)
        pkg.add_threat(
            Threat(
                threat_type="DF-26",
                target_base_id="JP-KADENA",
                launch_lat=26.0,
                launch_lon=120.0,
                quantity=4,
            )
        )
        # DF-17 HGV against Yokota AB (Japan)
        pkg.add_threat(
            Threat(
                threat_type="DF-17",
                target_base_id="JP-YOKOTA",
                launch_lat=32.0,
                launch_lon=125.0,
                quantity=3,
            )
        )
        # CJ-10 LACM against Kunsan AB (Korea)
        pkg.add_threat(
            Threat(
                threat_type="CJ-10",
                target_base_id="KR-KUNSAN",
                launch_lat=36.0,
                launch_lon=123.0,
                quantity=8,
            )
        )
        return pkg

    @classmethod
    def scenario_single_strike(
        cls, base_id: str, threat_type: str = "DF-26"
    ) -> "ThreatPackage":
        """Single-base strike scenario."""
        pkg = cls(
            scenario_name=f"Single Strike: {threat_type} -> {base_id}",
            description=f"{threat_type} strike against {base_id}",
        )
        pkg.add_threat(
            Threat(
                threat_type=threat_type,
                target_base_id=base_id,
                quantity=4,
            )
        )
        return pkg
