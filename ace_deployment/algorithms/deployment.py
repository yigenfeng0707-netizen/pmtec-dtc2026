"""
ACE Deployment Optimizer
Maps to DTB Model: Battle Network (node allocation) + Plug-and-Play (capability distribution)
Maps to ASDA: Decide (multi-objective resource allocation)
"""

import random
from dataclasses import dataclass, field
from typing import Optional
from models.base import BaseNetwork, MilitaryBase
from models.aircraft import Aircraft, AircraftFleet
from config import ACE_HUB_DISPERSION_RATIO, MAX_SPOKE_FILL_RATIO, MIN_SPOKE_CAPACITY


@dataclass
class DeploymentPlan:
    """Result of deployment optimization."""

    transfers: list[dict] = field(
        default_factory=list
    )  # [{ac_uid, ac_type, from_base, to_base, distance_km, rationale}]
    network_vulnerability_before: float = 0.0
    network_vulnerability_after: float = 0.0
    network_strike_before: float = 0.0
    network_strike_after: float = 0.0
    total_transfer_distance_km: float = 0.0
    hubs_depleted: list[str] = field(default_factory=list)
    spokes_reinforced: list[str] = field(default_factory=list)

    @property
    def vulnerability_reduction_pct(self) -> float:
        if self.network_vulnerability_before == 0:
            return 0.0
        return (
            1 - self.network_vulnerability_after / self.network_vulnerability_before
        ) * 100

    @property
    def strike_retention_pct(self) -> float:
        if self.network_strike_before == 0:
            return 100.0
        return self.network_strike_after / self.network_strike_before * 100

    def to_dict(self) -> dict:
        return {
            "total_transfers": len(self.transfers),
            "vulnerability_before": round(self.network_vulnerability_before, 2),
            "vulnerability_after": round(self.network_vulnerability_after, 2),
            "vulnerability_reduction_pct": round(self.vulnerability_reduction_pct, 1),
            "strike_before": round(self.network_strike_before, 2),
            "strike_after": round(self.network_strike_after, 2),
            "strike_retention_pct": round(self.strike_retention_pct, 1),
            "total_transfer_distance_km": round(self.total_transfer_distance_km, 1),
            "hubs_depleted": self.hubs_depleted,
            "spokes_reinforced": self.spokes_reinforced,
            "transfers": self.transfers,
        }


class DeploymentOptimizer:
    """
    ACE Distributed Deployment Optimizer.

    Objective: Distribute aircraft from hub bases to spoke bases to minimize
    network vulnerability while maximizing strike capability retention.

    Multi-objective function:
        minimize: w1 * V_total + w2 * (1 - S_retention) + w3 * D_total / D_max
    where:
        V_total = sum of base vulnerability indices
        S_retention = strike capability after / strike capability before
        D_total = total transfer distance
    """

    def __init__(
        self,
        network: BaseNetwork,
        fleet: AircraftFleet,
        w_vulnerability: float = 0.5,
        w_strike: float = 0.3,
        w_distance: float = 0.2,
    ):
        self.network = network
        self.fleet = fleet
        self.w1 = w_vulnerability
        self.w2 = w_strike
        self.w3 = w_distance
        self.plan = DeploymentPlan()

    def optimize(self) -> DeploymentPlan:
        """Execute the ACE deployment optimization."""
        # Record initial state
        self.plan.network_vulnerability_before = self.network.network_vulnerability
        self.plan.network_strike_before = self.network.network_strike_capability

        # Phase 1: Identify dispersal candidates from hubs
        hub_aircraft = self._identify_dispersal_candidates()

        # Phase 2: Score candidate spoke bases
        spoke_scores = self._score_spoke_bases()

        # Phase 3: Greedy assignment with local search
        self._greedy_assignment(hub_aircraft, spoke_scores)

        # Phase 4: Local search refinement
        self._local_search()

        # Record final state
        self.plan.network_vulnerability_after = self.network.network_vulnerability
        self.plan.network_strike_after = self.network.network_strike_capability

        return self.plan

    def _identify_dispersal_candidates(self) -> list[Aircraft]:
        """Select aircraft to disperse from hub bases."""
        candidates = []
        for hub in self.network.hubs():
            base_ac = self.fleet.at_base(hub.id)
            # Disperse ACE_HUB_DISPERSION_RATIO of hub aircraft
            n_disperse = int(len(base_ac) * ACE_HUB_DISPERSION_RATIO)
            # Prioritize high-value aircraft for dispersal
            sorted_ac = sorted(base_ac, key=lambda a: a.value, reverse=True)
            for ac in sorted_ac[:n_disperse]:
                candidates.append(ac)
        return candidates

    def _score_spoke_bases(self) -> dict[str, float]:
        """Score each spoke base for suitability as dispersal destination."""
        scores = {}
        for spoke in self.network.spokes():
            if spoke.available_parking < MIN_SPOKE_CAPACITY:
                scores[spoke.id] = 0.0
                continue
            fill_ratio = spoke.utilization
            if fill_ratio > MAX_SPOKE_FILL_RATIO:
                scores[spoke.id] = 0.0
                continue
            # Score: higher capacity, lower vulnerability, better defense, more central
            capacity_score = spoke.available_parking / 40.0
            defense_score = spoke.defense_level / 3.0
            shelter_score = 1.0 if spoke.has_shelters else 0.5
            # Prefer bases with runway > 2400m (can handle fighters)
            runway_score = (
                min(1.0, spoke.runway_m / 3000.0) if spoke.runway_m > 0 else 0.3
            )
            # Prefer bases far from high-threat zones (e.g., far from Taiwan Strait)
            # Use latitude as proxy: higher lat = safer from PLA short-range
            geo_score = max(0.3, min(1.0, (spoke.lat - 20) / 40))
            score = (
                capacity_score * 0.3
                + defense_score * 0.25
                + shelter_score * 0.15
                + runway_score * 0.15
                + geo_score * 0.15
            )
            scores[spoke.id] = score
        return scores

    def _greedy_assignment(self, candidates: list[Aircraft], spoke_scores: dict):
        """Greedy assignment: highest-value aircraft to best-scoring spoke."""
        # Sort candidates by value (high first)
        candidates.sort(key=lambda a: a.value, reverse=True)

        for ac in candidates:
            best_base = None
            best_score = -1
            best_dist = 0

            for spoke_id, score in spoke_scores.items():
                if score <= 0:
                    continue
                spoke = self.network.get(spoke_id)
                if not spoke or not spoke.can_accept(ac.ac_type):
                    continue
                # Check if aircraft can reach this base
                if not ac.can_reach(self.network.get(ac.base_id).distance_to(spoke)):
                    continue
                # Adjust score by distance penalty
                dist = self.network.get(ac.base_id).distance_to(spoke)
                dist_penalty = max(0, 1 - dist / 3000)  # Penalize long transfers
                adjusted_score = score * (0.5 + 0.5 * dist_penalty)
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_base = spoke
                    best_dist = dist

            if best_base:
                self._execute_transfer(ac, best_base, best_dist)
                # Reduce the spoke's available capacity in scoring
                spoke_scores[best_base.id] *= max(
                    0.3, 1 - 1.0 / best_base.parking_capacity
                )
                if best_base.id not in self.plan.spokes_reinforced:
                    self.plan.spokes_reinforced.append(best_base.id)

    def _execute_transfer(self, ac: Aircraft, dest: MilitaryBase, distance: float):
        """Record and execute a transfer."""
        from_base_id = ac.base_id
        # Remove from old base
        self.fleet.remove_from_base(ac, self.network)
        # Add to new base
        self.fleet.add_to_base(ac, dest.id, self.network)
        ac.status = "grounded"

        transfer_record = {
            "ac_uid": ac.uid,
            "ac_type": ac.ac_type,
            "callsign": ac.callsign,
            "from_base": from_base_id,
            "to_base": dest.id,
            "to_base_name": dest.name,
            "distance_km": round(distance, 1),
            "transfer_time_min": round(ac.transfer_time_hours(distance) * 60, 1),
            "rationale": f"Value={ac.value}, dest_score={dest.defense_level}/3 defense",
        }
        self.plan.transfers.append(transfer_record)
        self.plan.total_transfer_distance_km += distance

    def _local_search(self):
        """Try swapping pairs to improve objective."""
        improved = True
        iterations = 0
        max_iter = 50
        while improved and iterations < max_iter:
            improved = False
            iterations += 1
            # Try swapping aircraft between bases if it reduces vulnerability
            all_ac = [a for a in self.fleet.aircraft if a.status == "grounded"]
            for i in range(len(all_ac)):
                for j in range(i + 1, len(all_ac)):
                    a1, a2 = all_ac[i], all_ac[j]
                    if a1.base_id == a2.base_id:
                        continue
                    b1 = self.network.get(a1.base_id)
                    b2 = self.network.get(a2.base_id)
                    v_before = b1.vulnerability_index + b2.vulnerability_index
                    # Simulate swap
                    self.fleet.remove_from_base(a1, self.network)
                    self.fleet.remove_from_base(a2, self.network)
                    self.fleet.add_to_base(a1, b2.id, self.network)
                    self.fleet.add_to_base(a2, b1.id, self.network)
                    v_after = b1.vulnerability_index + b2.vulnerability_index
                    if v_after < v_before:
                        improved = True
                        # Keep the swap
                    else:
                        # Revert
                        self.fleet.remove_from_base(a1, self.network)
                        self.fleet.remove_from_base(a2, self.network)
                        self.fleet.add_to_base(a1, b1.id, self.network)
                        self.fleet.add_to_base(a2, b2.id, self.network)
