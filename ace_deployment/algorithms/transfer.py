"""
Emergency Transfer Planner
Maps to DTB Model: Battle Network (rapid node reconfiguration)
Maps to ASDA: Act (execute evacuation) + Adapt (redistribute after threat)
"""

import math
from dataclasses import dataclass, field
from models.base import BaseNetwork, MilitaryBase
from models.aircraft import Aircraft, AircraftFleet
from models.threat import Threat
from config import MAX_SPOKE_FILL_RATIO


@dataclass
class TransferOrder:
    ac_uid: str
    ac_type: str
    callsign: str
    from_base: str
    to_base: str
    to_base_name: str
    distance_km: float
    transfer_time_min: float
    deadline_min: float
    priority: int  # 1=highest
    status: str = "planned"  # planned, executing, completed, failed

    def to_dict(self) -> dict:
        return {
            "ac_uid": self.ac_uid,
            "ac_type": self.ac_type,
            "callsign": self.callsign,
            "from_base": self.from_base,
            "to_base": self.to_base,
            "to_base_name": self.to_base_name,
            "distance_km": round(self.distance_km, 1),
            "transfer_time_min": round(self.transfer_time_min, 1),
            "deadline_min": round(self.deadline_min, 1),
            "priority": self.priority,
            "status": self.status,
            "time_margin_min": round(self.deadline_min - self.transfer_time_min, 1),
            "feasible": self.transfer_time_min < self.deadline_min,
        }


@dataclass
class TransferPlan:
    orders: list[TransferOrder] = field(default_factory=list)
    threat_uid: str = ""
    threat_type: str = ""
    target_base: str = ""
    response_time_min: float = 0.0
    total_aircraft_evacuated: int = 0
    total_aircraft_stranded: int = 0
    total_value_saved: int = 0
    total_value_lost: int = 0

    @property
    def evacuation_rate(self) -> float:
        total = self.total_aircraft_evacuated + self.total_aircraft_stranded
        if total == 0:
            return 0.0
        return self.total_aircraft_evacuated / total * 100

    def to_dict(self) -> dict:
        return {
            "threat_uid": self.threat_uid,
            "threat_type": self.threat_type,
            "target_base": self.target_base,
            "response_time_min": round(self.response_time_min, 1),
            "total_orders": len(self.orders),
            "evacuated": self.total_aircraft_evacuated,
            "stranded": self.total_aircraft_stranded,
            "evacuation_rate_pct": round(self.evacuation_rate, 1),
            "value_saved": self.total_value_saved,
            "value_lost": self.total_value_lost,
            "orders": [
                o.to_dict() for o in sorted(self.orders, key=lambda x: x.priority)
            ],
        }


class TransferPlanner:
    """
    Emergency Transfer Planner for threat-driven aircraft evacuation.

    Algorithm: Priority-based nearest-feasible assignment
    1. Sort aircraft by value (high-value first)
    2. For each aircraft, find nearest base with capacity within response time
    3. Assign to best feasible destination
    4. Mark infeasible aircraft as stranded
    """

    def __init__(self, network: BaseNetwork, fleet: AircraftFleet):
        self.network = network
        self.fleet = fleet

    def plan_evacuation(self, threat: Threat) -> TransferPlan:
        """Plan emergency evacuation of threatened base."""
        plan = TransferPlan(
            threat_uid=threat.uid,
            threat_type=threat.threat_type,
            target_base=threat.target_base_id,
            response_time_min=threat.available_response_time_min(),
        )

        target_base = self.network.get(threat.target_base_id)
        if not target_base:
            return plan

        # Get all aircraft at the threatened base
        base_aircraft = self.fleet.at_base(threat.target_base_id)
        if not base_aircraft:
            return plan

        # Sort by priority: high-value first, then by fuel (lower fuel = harder to move)
        base_aircraft.sort(key=lambda a: (-a.value, a.fuel_pct))

        # Find candidate destination bases
        candidates = self._find_destinations(threat.target_base_id)

        # Assign each aircraft to best destination
        assigned_count = 0
        for priority, ac in enumerate(base_aircraft, 1):
            best_dest = None
            best_dist = float("inf")
            best_time = 0

            for dest, dist in candidates:
                if not dest.can_accept(ac.ac_type):
                    continue
                if dest.id == threat.target_base_id:
                    continue
                transfer_time = ac.transfer_time_hours(dist) * 60
                # Must complete before impact
                if transfer_time >= plan.response_time_min:
                    continue
                # Prefer nearest feasible
                if dist < best_dist:
                    best_dest = dest
                    best_dist = dist
                    best_time = transfer_time

            if best_dest:
                order = TransferOrder(
                    ac_uid=ac.uid,
                    ac_type=ac.ac_type,
                    callsign=ac.callsign,
                    from_base=threat.target_base_id,
                    to_base=best_dest.id,
                    to_base_name=best_dest.name,
                    distance_km=best_dist,
                    transfer_time_min=best_time,
                    deadline_min=plan.response_time_min,
                    priority=priority,
                )
                plan.orders.append(order)
                plan.total_aircraft_evacuated += 1
                plan.total_value_saved += ac.value
                # Reserve capacity at destination
                best_dest.current_aircraft.append(ac)  # Temporarily occupy
            else:
                plan.total_aircraft_stranded += 1
                plan.total_value_lost += ac.value

        # Clean up temporary capacity reservations
        for order in plan.orders:
            dest = self.network.get(order.to_base)
            if dest:
                # Remove temporary placeholder
                dest.current_aircraft = [
                    a
                    for a in dest.current_aircraft
                    if not (hasattr(a, "uid") and a.uid == order.ac_uid)
                ]

        return plan

    def _find_destinations(self, base_id: str) -> list[tuple]:
        """Find candidate destination bases sorted by distance."""
        return self.network.nearby_bases(base_id, max_distance_km=3000)

    def execute_plan(self, plan: TransferPlan) -> dict:
        """Execute the transfer plan - actually move aircraft in the simulation."""
        executed = 0
        failed = 0
        for order in plan.orders:
            ac = None
            for a in self.fleet.aircraft:
                if a.uid == order.ac_uid:
                    ac = a
                    break
            if not ac:
                order.status = "failed"
                failed += 1
                continue
            # Check feasibility one more time
            if order.transfer_time_min >= order.deadline_min:
                order.status = "failed"
                failed += 1
                continue
            # Execute transfer
            self.fleet.remove_from_base(ac, self.network)
            self.fleet.add_to_base(ac, order.to_base, self.network)
            ac.status = "grounded"
            order.status = "completed"
            executed += 1
        return {
            "executed": executed,
            "failed": failed,
            "total_orders": len(plan.orders),
        }
