"""
Multi-Objective Optimization Engine
Evaluates deployment plans across multiple dimensions using Pareto analysis.
Maps to DTB Model: War Engine (optimization core)
Maps to ASDA: Decide (multi-criteria decision making)
"""

import math
from dataclasses import dataclass, field
from typing import Optional
from models.base import BaseNetwork
from models.aircraft import AircraftFleet


@dataclass
class Objective:
    name: str
    weight: float
    value: float = 0.0
    normalized: float = 0.0
    target: str = "minimize"  # minimize or maximize


@dataclass
class OptimizationResult:
    objectives: list[Objective] = field(default_factory=list)
    total_score: float = 0.0
    pareto_optimal: bool = False
    dominated_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_score": round(self.total_score, 4),
            "pareto_optimal": self.pareto_optimal,
            "objectives": [
                {
                    "name": o.name,
                    "weight": o.weight,
                    "value": round(o.value, 4),
                    "normalized": round(o.normalized, 4),
                    "target": o.target,
                }
                for o in self.objectives
            ],
        }


class MultiObjectiveOptimizer:
    """
    Multi-objective optimization framework for ACE deployment decisions.

    Objectives:
    1. Minimize network vulnerability (weighted)
    2. Maximize strike capability retention
    3. Minimize total transfer distance (logistics cost)
    4. Maximize coverage diversity (spread across regions)
    5. Minimize single-point-of-failure risk
    6. Minimize political risk exposure (P10: ally access uncertainty)
    """

    def __init__(self, network: BaseNetwork, fleet: AircraftFleet):
        self.network = network
        self.fleet = fleet

    def evaluate(self, plan=None) -> OptimizationResult:
        """Evaluate current network state across all objectives."""
        result = OptimizationResult()

        # Objective 1: Network vulnerability (minimize)
        v = self.network.network_vulnerability
        result.objectives.append(
            Objective(
                name="network_vulnerability", weight=0.28, value=v, target="minimize"
            )
        )

        # Objective 2: Strike capability retention (maximize)
        s = self.network.network_strike_capability
        result.objectives.append(
            Objective(name="strike_capability", weight=0.24, value=s, target="maximize")
        )

        # Objective 3: Distribution diversity (maximize)
        diversity = self._compute_diversity()
        result.objectives.append(
            Objective(
                name="distribution_diversity",
                weight=0.13,
                value=diversity,
                target="maximize",
            )
        )

        # Objective 4: Single-point-of-failure risk (minimize)
        spof_risk = self._compute_spof_risk()
        result.objectives.append(
            Objective(name="spof_risk", weight=0.13, value=spof_risk, target="minimize")
        )

        # Objective 5: Defense coverage (maximize)
        defense_cov = self._compute_defense_coverage()
        result.objectives.append(
            Objective(
                name="defense_coverage",
                weight=0.12,
                value=defense_cov,
                target="maximize",
            )
        )

        # Objective 6: Political risk exposure (minimize, P10)
        # Σ asset value × (1 - access capacity factor): capability stranded
        # in restricted/denied ally bases counts as politically at-risk.
        pol_risk = self._compute_political_risk_exposure()
        result.objectives.append(
            Objective(
                name="political_risk_exposure",
                weight=0.10,
                value=pol_risk,
                target="minimize",
            )
        )

        # Normalize and compute weighted score
        for obj in result.objectives:
            if obj.target == "minimize":
                obj.normalized = 1.0 / (1.0 + obj.value) if obj.value > 0 else 1.0
            else:
                obj.normalized = min(1.0, obj.value / 1000.0) if obj.value > 0 else 0.0

        result.total_score = sum(o.weight * o.normalized for o in result.objectives)
        return result

    def _compute_diversity(self) -> float:
        """Shannon entropy of aircraft distribution across regions."""
        from collections import Counter

        region_counts = Counter()
        for b in self.network.bases.values():
            n = len(b.current_aircraft)
            if n > 0:
                region_counts[b.region] += n
        total = sum(region_counts.values())
        if total == 0 or len(region_counts) <= 1:
            return 0.0
        entropy = 0.0
        for count in region_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = math.log2(len(region_counts))
        return (entropy / max_entropy * 100) if max_entropy > 0 else 0.0

    def _compute_spof_risk(self) -> float:
        """Risk that one base loss catastrophically degrades capability."""
        base_values = []
        for b in self.network.bases.values():
            if b.current_aircraft:
                base_val = sum(a.value for a in b.current_aircraft)
                base_values.append(base_val)
        if not base_values:
            return 0.0
        total_val = sum(base_values)
        max_val = max(base_values)
        # Risk = concentration ratio (higher = worse)
        return (max_val / total_val * 100) if total_val > 0 else 0.0

    def _compute_defense_coverage(self) -> float:
        """Average defense level weighted by aircraft count."""
        total_weight = 0
        total_score = 0
        for b in self.network.bases.values():
            n_ac = len(b.current_aircraft)
            if n_ac > 0:
                total_weight += n_ac
                total_score += n_ac * b.defense_level
        return (total_score / total_weight * 33.3) if total_weight > 0 else 0.0

    def _compute_political_risk_exposure(self) -> float:
        """P10: Σ asset value × (1 - access capacity factor) across ally bases."""
        political = getattr(self.network, "political", None)
        if political is None:
            return 0.0
        assets_by_base = {}
        for b in self.network.bases.values():
            value = sum(
                getattr(a, "value", 0) for a in b.current_aircraft
            )
            if value > 0:
                assets_by_base[b.id] = value
        return political.political_risk_exposure(assets_by_base)

    def compare_plans(
        self, plan_a: OptimizationResult, plan_b: OptimizationResult
    ) -> str:
        """Compare two plans and determine dominance."""
        a_dominates = True
        b_dominates = True
        for oa, ob in zip(plan_a.objectives, plan_b.objectives):
            if oa.target == "minimize":
                if oa.value > ob.value:
                    a_dominates = False
                if ob.value > oa.value:
                    b_dominates = False
            else:
                if oa.value < ob.value:
                    a_dominates = False
                if ob.value < oa.value:
                    b_dominates = False
        if a_dominates:
            return "A_dominates"
        elif b_dominates:
            return "B_dominates"
        return "incomparable"
