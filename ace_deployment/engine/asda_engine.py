"""
ASDA Loop Engine - Orchestrates the Act-Sense-Decide-Adapt cycle.
DTB Model: War Engine (simulation driver) + Battle Network (state propagation)
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from models.base import BaseNetwork
from models.aircraft import Aircraft, AircraftFleet
from models.threat import Threat, ThreatPackage
from algorithms.deployment import DeploymentOptimizer
from algorithms.transfer import TransferPlanner
from algorithms.damage import DamageAssessor
from algorithms.optimization import MultiObjectiveOptimizer
from config import (
    BASES_GEOJSON,
    OUTPUT_DIR,
    DEFAULT_SQUADRON_F35,
    DEFAULT_SQUADRON_F22,
    DEFAULT_SQUADRON_F15,
    DEFAULT_SQUADRON_F16,
    DEFAULT_TANKER_SQUADRON,
    DEFAULT_AEW_SQUADRON,
    ASDA_CYCLE_SECONDS,
    DTB_MAPPING,
    ASDA_MAPPING,
)


@dataclass
class CycleResult:
    cycle_num: int
    phase: str  # act, sense, decide, adapt
    timestamp: str
    summary: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle_num,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "data": self.data,
        }


@dataclass
class SimulationReport:
    scenario_name: str = ""
    cycles: list[CycleResult] = field(default_factory=list)
    initial_state: dict = field(default_factory=dict)
    final_state: dict = field(default_factory=dict)
    deployment_plan: dict = field(default_factory=dict)
    transfer_plans: list[dict] = field(default_factory=list)
    damage_report: dict = field(default_factory=dict)
    optimization_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "total_cycles": len(self.cycles),
            "initial_state": self.initial_state,
            "final_state": self.final_state,
            "deployment_plan": self.deployment_plan,
            "transfer_plans": self.transfer_plans,
            "damage_report": self.damage_report,
            "optimization_results": self.optimization_results,
            "cycles": [c.to_dict() for c in self.cycles],
        }

    def to_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


class ASDAEngine:
    """
    ASDA Loop Orchestrator for ACE Deployment Simulation.

    Cycle: Act -> Sense -> Decide -> Adapt -> (repeat)

    - Act: Execute deployment/transfer orders
    - Sense: Detect threats, assess damage
    - Decide: Multi-objective optimization for next actions
    - Adapt: Adjust strategy based on outcomes
    """

    def __init__(self, geojson_path: str = BASES_GEOJSON, seed: int = 42):
        import random

        random.seed(seed)

        self.network = BaseNetwork.from_geojson(geojson_path)
        self.fleet = AircraftFleet()
        self.optimizer = MultiObjectiveOptimizer(self.network, self.fleet)
        self.deployer = DeploymentOptimizer(self.network, self.fleet)
        self.transfer_planner = TransferPlanner(self.network, self.fleet)
        self.damage_assessor = DamageAssessor(self.network, self.fleet)
        self.report = SimulationReport()
        self.cycle_count = 0

    def initialize_fleet(self, custom_config: Optional[dict] = None):
        """Place aircraft at their home bases."""
        config = custom_config or {
            "JP-KADENA": DEFAULT_SQUADRON_F35,
            "JP-YOKOTA": DEFAULT_SQUADRON_F15,
            "GU-ANDERSEN": DEFAULT_SQUADRON_F35,
            "KR-OSAN": DEFAULT_SQUADRON_F15,
            "KR-KUNSAN": DEFAULT_SQUADRON_F16,
            "JP-MISAWA": DEFAULT_SQUADRON_F16,
            "AK-EIELSON": DEFAULT_SQUADRON_F22,
            "HI-PHICKAM": {**DEFAULT_TANKER_SQUADRON, **DEFAULT_AEW_SQUADRON},
        }
        for base_id, squadron in config.items():
            for ac_type, count in squadron.items():
                self.fleet.add_squadron(ac_type, base_id, count)
        self.fleet.assign_to_bases(self.network)
        self.report.initial_state = self._snapshot()

    def run_full_simulation(self, threat_package: ThreatPackage) -> SimulationReport:
        """Execute complete ASDA cycle: deploy -> threat -> evacuate -> assess -> adapt."""
        self.report.scenario_name = threat_package.scenario_name

        # === PHASE 1: DECIDE (initial deployment optimization) ===
        self._log("decide", "Initial ACE deployment optimization started")
        plan = self.deployer.optimize()
        self.report.deployment_plan = plan.to_dict()
        opt_result = self.optimizer.evaluate()
        self.report.optimization_results.append(opt_result.to_dict())
        self._log(
            "decide",
            f"Deployment complete: {len(plan.transfers)} transfers, "
            f"vulnerability -{plan.vulnerability_reduction_pct:.1f}%, "
            f"strike retention {plan.strike_retention_pct:.1f}%",
        )

        # === PHASE 2: SENSE (threat detection) ===
        self._log(
            "sense",
            f"Threat detected: {threat_package.scenario_name}, "
            f"{threat_package.total_warheads} warheads targeting "
            f"{len(threat_package.targeted_bases)} bases",
        )

        # === PHASE 3: ACT (emergency evacuation) ===
        all_transfer_plans = []
        for threat in threat_package.threats:
            tplan = self.transfer_planner.plan_evacuation(threat)
            self.report.transfer_plans.append(tplan.to_dict())
            all_transfer_plans.append(tplan)
            self._log(
                "act",
                f"Evacuation {threat.target_base_id}: "
                f"{tplan.total_aircraft_evacuated} evacuated, "
                f"{tplan.total_aircraft_stranded} stranded, "
                f"rate {tplan.evacuation_rate:.0f}%",
            )

        # Execute all transfer plans
        for tplan in all_transfer_plans:
            exec_result = self.transfer_planner.execute_plan(tplan)
            self._log(
                "act",
                f"Transfer execution: {exec_result['executed']} completed, "
                f"{exec_result['failed']} failed",
            )

        # === PHASE 4: SENSE (damage assessment) ===
        damage_report = self.damage_assessor.assess_scenario(threat_package)
        self.report.damage_report = damage_report.to_dict()
        self._log(
            "sense",
            f"Damage assessment: {damage_report.total_aircraft_lost} aircraft lost, "
            f"{damage_report.runways_disabled} runways disabled, "
            f"recovery {damage_report.estimated_recovery_hours:.0f}h",
        )

        # === PHASE 5: ADAPT (re-optimization after damage) ===
        self._log("adapt", "Post-strike re-optimization started")
        # Remove destroyed aircraft from fleet
        for base_result in damage_report.bases_hit:
            base = self.network.get(base_result.base_id)
            if base:
                destroyed = base_result.aircraft_destroyed
                survivors = base.current_aircraft[destroyed:]
                base.current_aircraft = survivors
                # Also mark in fleet
                killed_uids = set()
                for ac in self.fleet.aircraft:
                    if ac.base_id == base_result.base_id and ac.status == "grounded":
                        if len(killed_uids) < destroyed:
                            ac.status = "destroyed"
                            killed_uids.add(ac.uid)

        # Re-run deployment optimization
        self.deployer = DeploymentOptimizer(self.network, self.fleet)
        recovery_plan = self.deployer.optimize()
        self.report.deployment_plan["recovery"] = recovery_plan.to_dict()
        opt_result_2 = self.optimizer.evaluate()
        self.report.optimization_results.append(opt_result_2.to_dict())
        self._log(
            "adapt",
            f"Recovery deployment: {len(recovery_plan.transfers)} transfers, "
            f"vulnerability {recovery_plan.network_vulnerability_after:.1f}, "
            f"score {opt_result_2.total_score:.3f}",
        )

        # === FINAL STATE ===
        self.report.final_state = self._snapshot()
        self._log("adapt", "ASDA simulation complete")

        return self.report

    def _snapshot(self) -> dict:
        return {
            "network": self.network.status_report(),
            "fleet": self.fleet.summary(),
            "optimization": self.optimizer.evaluate().to_dict(),
        }

    def _log(self, phase: str, summary: str):
        self.cycle_count += 1
        from datetime import datetime

        ts = datetime.now().strftime("%H:%M:%S")
        result = CycleResult(
            cycle_num=self.cycle_count,
            phase=phase,
            timestamp=ts,
            summary=summary,
        )
        self.report.cycles.append(result)

    def save_report(self, path: Optional[str] = None):
        if not path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            path = os.path.join(OUTPUT_DIR, "asda_simulation_report.json")
        self.report.to_json(path)
        return path
