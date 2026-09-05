"""
UCB1 Multi-Armed Bandit for Intercept Strategy Selection.
Selects among 3 intercept modes: direct, predictive, saturation.
Pure NumPy, no GPU dependency.
"""

import math
import json
import os
from typing import Optional


class UCB1Intercept:
    """UCB1 algorithm for selecting optimal intercept strategy."""

    STRATEGIES = ["direct", "predictive", "saturation"]

    def __init__(self, strategy_params: Optional[dict] = None):
        self.strategy_params = strategy_params or {}
        self.counts = {s: 0 for s in self.STRATEGIES}
        self.rewards = {s: 0.0 for s in self.STRATEGIES}
        self.total_rounds = 0
        self.last_choice = "direct"
        self.history: list[dict] = []

    def select(self) -> str:
        """Select intercept strategy using UCB1."""
        self.total_rounds += 1
        untried = [s for s in self.STRATEGIES if self.counts[s] == 0]
        if untried:
            self.last_choice = untried[0]
            return self.last_choice

        ucb_values = {}
        for s in self.STRATEGIES:
            avg = self.rewards[s] / max(self.counts[s], 1)
            exploration = math.sqrt(
                2 * math.log(self.total_rounds) / max(self.counts[s], 1)
            )
            ucb_values[s] = avg + exploration

        self.last_choice = max(ucb_values, key=ucb_values.get)
        return self.last_choice

    def update(self, strategy: str, reward: float):
        """Update reward for a strategy. reward in [0, 1] (1=success, 0=failure)."""
        if strategy not in self.STRATEGIES:
            return
        self.counts[strategy] += 1
        self.rewards[strategy] += reward
        self.history.append(
            {
                "round": self.total_rounds,
                "strategy": strategy,
                "reward": round(reward, 3),
                "avg_reward": round(
                    self.rewards[strategy] / max(self.counts[strategy], 1), 3
                ),
            }
        )

    def get_success_rates(self) -> dict:
        """Get current success rate per strategy."""
        return {
            s: round(self.rewards[s] / max(self.counts[s], 1), 3)
            for s in self.STRATEGIES
        }

    def get_best_strategy(self) -> str:
        """Get the current best-performing strategy."""
        rates = self.get_success_rates()
        return max(rates, key=rates.get)

    def to_dict(self) -> dict:
        return {
            "total_rounds": self.total_rounds,
            "counts": self.counts,
            "rewards": self.rewards,
            "success_rates": self.get_success_rates(),
            "best_strategy": self.get_best_strategy(),
            "last_choice": self.last_choice,
            "history": self.history[-50:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UCB1Intercept":
        obj = cls()
        obj.total_rounds = data.get("total_rounds", 0)
        obj.counts = data.get("counts", {s: 0 for s in cls.STRATEGIES})
        obj.rewards = data.get("rewards", {s: 0.0 for s in cls.STRATEGIES})
        obj.history = data.get("history", [])
        obj.last_choice = data.get("last_choice", "direct")
        return obj
