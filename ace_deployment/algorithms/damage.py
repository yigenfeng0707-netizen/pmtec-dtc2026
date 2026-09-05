"""
Damage Assessment Module - Monte Carlo simulation of strike outcomes.
Maps to DTB Model: War Engine (simulation state update)
Maps to ASDA: Sense (damage assessment) + Adapt (strategy adjustment based on results)
"""

import math
import random
from dataclasses import dataclass, field
from models.base import BaseNetwork, MilitaryBase
from models.aircraft import Aircraft, AircraftFleet
from models.threat import Threat
from config import (
    SHELTER_SURVIVAL_PROB,
    OPEN_SURVIVAL_PROB,
    RUNWAY_CRATER_RADIUS_PER_500KG,
    BLAST_RADIUS_500KG_M,
)


@dataclass
class BaseDamageResult:
    base_id: str
    base_name: str
    runway_destroyed: bool = False
    runway_repair_hours: float = 0.0
    parking_destroyed: int = 0
    aircraft_destroyed: int = 0
    aircraft_damaged: int = 0
    aircraft_sheltered_survived: int = 0
    infrastructure_destroyed_pct: float = 0.0
    crater_count: int = 0
    sim_iterations: int = 0

    def to_dict(self) -> dict:
        return {
            "base_id": self.base_id,
            "base_name": self.base_name,
            "runway_destroyed": self.runway_destroyed,
            "runway_repair_hours": round(self.runway_repair_hours, 1),
            "parking_destroyed": self.parking_destroyed,
            "aircraft_destroyed": self.aircraft_destroyed,
            "aircraft_damaged": self.aircraft_damaged,
            "aircraft_sheltered_survived": self.aircraft_sheltered_survived,
            "infrastructure_destroyed_pct": round(self.infrastructure_destroyed_pct, 1),
            "crater_count": self.crater_count,
            "sim_iterations": self.sim_iterations,
        }


@dataclass
class DamageReport:
    scenario_name: str = ""
    total_threats: int = 0
    total_warheads: int = 0
    bases_hit: list[BaseDamageResult] = field(default_factory=list)
    total_aircraft_lost: int = 0
    total_value_lost: int = 0
    runways_disabled: int = 0
    estimated_recovery_hours: float = 0.0
    monte_carlo_runs: int = 100

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "total_threats": self.total_threats,
            "total_warheads": self.total_warheads,
            "bases_hit": [b.to_dict() for b in self.bases_hit],
            "total_aircraft_lost": self.total_aircraft_lost,
            "total_value_lost": self.total_value_lost,
            "runways_disabled": self.runways_disabled,
            "estimated_recovery_hours": round(self.estimated_recovery_hours, 1),
            "monte_carlo_runs": self.monte_carlo_runs,
        }


class DamageAssessor:
    """
    Monte Carlo damage assessment for strike scenarios.

    Models:
    - Ballistic/cruise missile impact point (CEP-based normal distribution)
    - Blast radius damage to aircraft (sheltered vs open)
    - Runway cratering and repair time
    - Infrastructure damage percentage
    """

    def __init__(
        self, network: BaseNetwork, fleet: AircraftFleet, n_simulations: int = 100
    ):
        self.network = network
        self.fleet = fleet
        self.n_simulations = n_simulations

    def assess_threat(self, threat: Threat) -> BaseDamageResult:
        """Assess damage from a single threat against its target base."""
        target = self.network.get(threat.target_base_id)
        if not target:
            return BaseDamageResult(base_id=threat.target_base_id, base_name="Unknown")

        # Aggregate results over Monte Carlo runs
        total_runway_destroyed = 0
        total_parking_destroyed = 0
        total_aircraft_destroyed = 0
        total_aircraft_sheltered_survived = 0
        total_craters = 0
        total_infra_damage = 0.0
        total_repair_hours = 0.0

        base_aircraft = self.fleet.at_base(threat.target_base_id)

        for _ in range(self.n_simulations):
            runway_hit = False
            craters = 0
            aircraft_killed = 0
            aircraft_saved_shelter = 0
            parking_spots_destroyed = 0

            for _ in range(threat.quantity):
                # Generate impact point using CEP (2D normal distribution)
                # CEP = radius containing 50% of impacts
                # sigma = CEP / 1.1774 (2D normal)
                sigma = threat.cep_m / 1.1774
                impact_offset_n = random.gauss(0, sigma)
                impact_offset_e = random.gauss(0, sigma)

                # Check runway damage
                if target.runway_m > 0:
                    # Runway is a long strip; check if impact is on runway
                    # Simplified: if impact within runway width + blast radius
                    runway_width = 60  # meters, typical
                    runway_half_length = target.runway_m / 2
                    if abs(impact_offset_n) < runway_width / 2 + threat.crater_radius_m:
                        if abs(impact_offset_e) < runway_half_length:
                            runway_hit = True
                            craters += 1

                # Check aircraft damage (within blast radius)
                blast_r = threat.blast_radius_m
                # Simulate aircraft positions around parking area
                # Assume parking area is within 500m of base center
                for ac in base_aircraft:
                    # Random position within parking area
                    ac_offset = random.uniform(0, 300)  # meters from center
                    ac_angle = random.uniform(0, 2 * math.pi)
                    ac_n = ac_offset * math.cos(ac_angle)
                    ac_e = ac_offset * math.sin(ac_angle)
                    dist_to_impact = math.sqrt(
                        (ac_n - impact_offset_n) ** 2 + (ac_e - impact_offset_e) ** 2
                    )
                    if dist_to_impact < blast_r:
                        if ac.sheltered:
                            if random.random() > SHELTER_SURVIVAL_PROB:
                                aircraft_killed += 1
                            else:
                                aircraft_saved_shelter += 1
                        else:
                            if random.random() > OPEN_SURVIVAL_PROB:
                                aircraft_killed += 1

                # Count parking spots destroyed
                if blast_r > 100:
                    parking_spots_destroyed += int(blast_r / 50)

            total_runway_destroyed += int(runway_hit)
            total_parking_destroyed += min(
                parking_spots_destroyed, target.parking_capacity
            )
            total_aircraft_destroyed += min(aircraft_killed, len(base_aircraft))
            total_aircraft_sheltered_survived += aircraft_saved_shelter
            total_craters += craters

        n = self.n_simulations
        result = BaseDamageResult(
            base_id=target.id,
            base_name=target.name,
            runway_destroyed=total_runway_destroyed / n > 0.5,
            runway_repair_hours=self._estimate_runway_repair(total_craters / n)
            if total_runway_destroyed / n > 0.5
            else 0,
            parking_destroyed=int(total_parking_destroyed / n),
            aircraft_destroyed=int(total_aircraft_destroyed / n),
            aircraft_sheltered_survived=int(total_aircraft_sheltered_survived / n),
            infrastructure_destroyed_pct=min(
                100,
                (total_parking_destroyed / n / max(1, target.parking_capacity)) * 100,
            ),
            crater_count=int(total_craters / n),
            sim_iterations=self.n_simulations,
        )
        return result

    def assess_scenario(self, threat_package) -> DamageReport:
        """Assess damage from a multi-threat scenario."""
        report = DamageReport(
            scenario_name=threat_package.scenario_name,
            total_threats=len(threat_package.threats),
            total_warheads=threat_package.total_warheads,
            monte_carlo_runs=self.n_simulations,
        )

        for threat in threat_package.threats:
            result = self.assess_threat(threat)
            report.bases_hit.append(result)
            report.total_aircraft_lost += result.aircraft_destroyed
            if result.runway_destroyed:
                report.runways_disabled += 1
            report.estimated_recovery_hours = max(
                report.estimated_recovery_hours, result.runway_repair_hours
            )

        # Calculate total value lost
        for result in report.bases_hit:
            base = self.network.get(result.base_id)
            if base:
                for ac in base.current_aircraft[: result.aircraft_destroyed]:
                    report.total_value_lost += ac.value

        return report

    def _estimate_runway_repair(self, crater_count: float) -> float:
        """Estimate runway repair time based on crater count."""
        if crater_count <= 0:
            return 0.0
        # Each crater takes ~4-8 hours to repair (unrealistic but simplified)
        # More craters = diminishing returns (parallel repair teams)
        base_time_per_crater = 6.0
        parallel_factor = max(0.3, 1.0 / math.sqrt(max(1, crater_count)))
        return crater_count * base_time_per_crater * parallel_factor
