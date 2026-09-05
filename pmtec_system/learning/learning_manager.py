"""
Learning Manager - Central coordinator for ASDA Adapt learning.
Integrates UCB1 intercept, Q-learning dispersal, sensor optimization.
Provides JSON persistence and SPEAR history extraction.
"""

import json
import os
import time
import math
import random
from typing import Optional
from .ucb1_intercept import UCB1Intercept
from .qlearning_dispersal import QLearningDispersal
from .sensor_optimizer import SensorOptimizer


class LearningManager:
    """Central manager for ASDA Adapt phase online learning."""

    def __init__(self, persistence_path: str = None):
        self.persistence_path = persistence_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "learning_params.json",
        )
        self.ucb1 = UCB1Intercept()
        self.qlearn = QLearningDispersal()
        self.sensor_opt = SensorOptimizer()
        self.cycle_history: list[dict] = []
        self.baseline_intercept_rate: float = 0.0
        self.baseline_loss_rate: float = 0.0
        self._loaded = False
        self.load()

    def load(self):
        """Load learning parameters from JSON file."""
        if self._loaded:
            return
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.ucb1 = UCB1Intercept.from_dict(data.get("ucb1", {}))
                self.qlearn = QLearningDispersal.from_dict(data.get("qlearn", {}))
                self.sensor_opt = SensorOptimizer.from_dict(data.get("sensor_opt", {}))
                self.cycle_history = data.get("cycle_history", [])
                self.baseline_intercept_rate = data.get("baseline_intercept_rate", 0.0)
                self.baseline_loss_rate = data.get("baseline_loss_rate", 0.0)
                print(
                    f"[Learning] Loaded params: "
                    f"UCB1 rounds={self.ucb1.total_rounds}, "
                    f"QLearn rounds={self.qlearn.training_rounds}, "
                    f"Sensor rounds={self.sensor_opt.adjustment_rounds}"
                )
            except Exception as e:
                print(f"[Learning] Load failed, starting fresh: {e}")
        self._loaded = True

    def save(self):
        """Persist learning parameters to JSON file. Returns file path."""
        os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)
        data = {
            "ucb1": self.ucb1.to_dict(),
            "qlearn": self.qlearn.to_dict(),
            "sensor_opt": self.sensor_opt.to_dict(),
            "cycle_history": self.cycle_history[-200:],
            "baseline_intercept_rate": self.baseline_intercept_rate,
            "baseline_loss_rate": self.baseline_loss_rate,
            "last_saved": time.time(),
        }
        with open(self.persistence_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return self.persistence_path

    def select_intercept_strategy(self) -> str:
        """Select intercept strategy for current ASDA Decide phase."""
        return self.ucb1.select()

    def record_intercept_result(self, strategy: str, success: bool):
        """Record intercept outcome. success=True if target destroyed."""
        reward = 1.0 if success else 0.0
        self.ucb1.update(strategy, reward)

    def select_dispersal_target(
        self, current_base: str, available_bases: list, threat_dir: str = "unknown"
    ) -> str:
        """Select dispersal target base using Q-learning."""
        return self.qlearn.select_action(current_base, available_bases, threat_dir)

    def record_dispersal_result(
        self,
        current_base: str,
        target_base: str,
        threat_dir: str,
        loss_rate: float,
        next_base: str,
        next_available: list,
    ):
        """Record dispersal outcome. loss_rate in [0, 1], lower is better."""
        reward = -loss_rate
        self.qlearn.update(
            current_base, target_base, threat_dir, reward, next_base, next_available
        )

    def select_active_sensors(
        self, base_ids: list, max_active: int = 10, current_missiles: list = None
    ) -> list:
        """Select which bases should have active sensors."""
        return self.sensor_opt.select_sensors(base_ids, max_active, current_missiles)

    def record_sensor_coverage(self, base_coverage: dict):
        """Record sensor coverage metrics."""
        self.sensor_opt.update(base_coverage)

    def end_cycle(self, cycle_data: dict):
        """Record cycle summary and decay exploration."""
        self.cycle_history.append(cycle_data)
        self.qlearn.decay_epsilon()
        if len(self.cycle_history) % 5 == 0:
            self.save()

    def get_metrics(self) -> dict:
        """Get current learning metrics for display."""
        return {
            "intercept_strategies": self.ucb1.to_dict(),
            "dispersal_policy_size": len(self.qlearn.q_table),
            "dispersal_training_rounds": self.qlearn.training_rounds,
            "sensor_priorities": len(self.sensor_opt.base_priorities),
            "total_cycles": len(self.cycle_history),
            "baseline_intercept_rate": self.baseline_intercept_rate,
            "baseline_loss_rate": self.baseline_loss_rate,
            "current_intercept_rates": self.ucb1.get_success_rates(),
            "best_intercept_strategy": self.ucb1.get_best_strategy(),
        }

    def get_statistics(self) -> dict:
        """Get summary statistics for end-of-simulation report."""
        return {
            "cycles_completed": len(self.cycle_history),
            "intercept_success_rates": self.ucb1.get_success_rates(),
            "best_intercept_strategy": self.ucb1.get_best_strategy(),
            "ucb1_total_rounds": self.ucb1.total_rounds,
            "qlearning_states": len(self.qlearn.q_table),
            "qlearning_actions": self.qlearn.training_rounds,
            "qlearning_epsilon": round(self.qlearn.epsilon, 4),
            "sensor_deployments": self.sensor_opt.adjustment_rounds,
            "sensor_priorities": len(self.sensor_opt.base_priorities),
        }

    def extract_from_spear(self, spear_events: list, spear_snapshots: list):
        """Extract learning data from SPEAR replay history."""
        intercept_events = [
            e for e in spear_events if e.get("event_type") == "intercept_decision"
        ]
        damage_events = [e for e in spear_events if e.get("event_type") == "damage"]
        transfer_events = [e for e in spear_events if e.get("event_type") == "transfer"]

        if intercept_events or damage_events:
            if not self.baseline_intercept_rate:
                total = len(intercept_events) + len(damage_events)
                if total > 0:
                    self.baseline_intercept_rate = len(intercept_events) / total

        if transfer_events and not self.baseline_loss_rate:
            damage_after_transfer = sum(
                1
                for d in damage_events
                if any(
                    t.get("data", {}).get("to") == d.get("data", {}).get("base")
                    for t in transfer_events
                )
            )
            self.baseline_loss_rate = damage_after_transfer / max(
                len(transfer_events), 1
            )
