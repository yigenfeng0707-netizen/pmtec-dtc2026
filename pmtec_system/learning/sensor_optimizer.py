"""
Sensor Deployment Optimizer - greedy + random perturbation.
Adjusts sensor activation priorities based on historical coverage.
Pure Python, no GPU dependency.
"""

import random
from typing import Optional
from collections import defaultdict


class SensorOptimizer:
    """Optimizes sensor deployment priority using greedy + perturbation."""

    def __init__(self, perturbation_strength: float = 0.15):
        self.perturbation_strength = perturbation_strength
        self.base_priorities: dict[str, float] = {}
        self.coverage_history: list[dict] = []
        self.adjustment_rounds = 0

    def initialize(self, base_ids: list[str]):
        """Initialize uniform priorities for all bases."""
        uniform = 1.0 / max(len(base_ids), 1)
        self.base_priorities = {bid: uniform for bid in base_ids}

    def select_sensors(
        self,
        base_ids: list[str],
        max_active: int = 10,
        current_threats: list = None,
    ) -> list[str]:
        """Select which bases should have active sensors this cycle."""
        if not self.base_priorities:
            self.initialize(base_ids)

        scored = []
        for bid in base_ids:
            base_score = self.base_priorities.get(bid, 0.5)
            threat_boost = 0.0
            if current_threats:
                for t in current_threats:
                    t_lat = getattr(t, "lat", 0)
                    t_lon = getattr(t, "lon", 0)
                    threat_boost += 0.1
            scored.append(
                (bid, base_score + random.uniform(0, self.perturbation_strength))
            )

        scored.sort(key=lambda x: x[1], reverse=True)
        selected = [s[0] for s in scored[:max_active]]
        return selected

    def update(
        self,
        base_coverage: dict[str, float],
        threat_directions: dict[str, int] = None,
    ):
        """Update priorities based on observed coverage."""
        self.adjustment_rounds += 1
        self.coverage_history.append(
            {
                "round": self.adjustment_rounds,
                "coverage": {k: round(v, 3) for k, v in base_coverage.items()},
            }
        )

        for bid, cov in base_coverage.items():
            current = self.base_priorities.get(bid, 0.5)
            low_coverage_penalty = (1.0 - cov) * 0.1
            self.base_priorities[bid] = max(
                0.05, min(1.0, current + low_coverage_penalty - 0.02)
            )

        total = sum(self.base_priorities.values())
        if total > 0:
            for bid in self.base_priorities:
                self.base_priorities[bid] /= total

    def to_dict(self) -> dict:
        return {
            "perturbation_strength": self.perturbation_strength,
            "base_priorities": {
                k: round(v, 4) for k, v in self.base_priorities.items()
            },
            "adjustment_rounds": self.adjustment_rounds,
            "coverage_history": self.coverage_history[-50:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SensorOptimizer":
        obj = cls(perturbation_strength=data.get("perturbation_strength", 0.15))
        obj.base_priorities = data.get("base_priorities", {})
        obj.adjustment_rounds = data.get("adjustment_rounds", 0)
        obj.coverage_history = data.get("coverage_history", [])
        return obj
