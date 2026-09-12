"""
Q-Learning for Aircraft Dispersal Path Optimization.
State = (current_base_id, threat_direction). Action = transfer_to_base_id.
Reward = -loss_rate (lower loss = higher reward).
Pure NumPy table-based Q-learning, no GPU dependency.
"""

import random
from collections import defaultdict


class QLearningDispersal:
    """Table-based Q-learning for dispersal path selection."""

    def __init__(
        self,
        learning_rate: float = 0.15,
        discount: float = 0.92,
        epsilon: float = 0.3,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.95,
    ):
        self.alpha = learning_rate
        self.gamma = discount
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.q_table: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self.training_rounds = 0

    def _state_key(self, current_base: str, threat_dir: str = "unknown") -> str:
        """Encode state as a string key."""
        return f"{current_base}|{threat_dir}"

    def select_action(
        self, current_base: str, available_bases: list, threat_dir: str = "unknown"
    ) -> str:
        """Select dispersal target using epsilon-greedy."""
        if not available_bases:
            return current_base

        state = self._state_key(current_base, threat_dir)

        if random.random() < self.epsilon:
            return random.choice(available_bases)

        q_values = self.q_table.get(state, {})
        if not q_values:
            return random.choice(available_bases)

        best = max(q_values, key=q_values.get)
        if best in available_bases:
            return best
        return random.choice(available_bases)

    def update(
        self,
        current_base: str,
        target_base: str,
        threat_dir: str,
        reward: float,
        next_base: str,
        next_available: list,
    ):
        """Q-learning update rule."""
        state = self._state_key(current_base, threat_dir)
        next_state = self._state_key(next_base, threat_dir)

        max_next_q = 0.0
        if next_available:
            next_qs = self.q_table.get(next_state, {})
            if next_qs:
                max_next_q = max(next_qs.values())

        current_q = self.q_table[state][target_base]
        self.q_table[state][target_base] = current_q + self.alpha * (
            reward + self.gamma * max_next_q - current_q
        )

    def decay_epsilon(self):
        """Decay exploration rate."""
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.training_rounds += 1

    def get_policy(self) -> dict:
        """Extract current policy (best action per state)."""
        policy = {}
        for state, actions in self.q_table.items():
            if actions:
                policy[state] = max(actions, key=actions.get)
        return policy

    def to_dict(self) -> dict:
        return {
            "alpha": self.alpha,
            "gamma": self.gamma,
            "epsilon": round(self.epsilon, 4),
            "epsilon_min": self.epsilon_min,
            "epsilon_decay": self.epsilon_decay,
            "training_rounds": self.training_rounds,
            "q_table": {s: dict(a) for s, a in self.q_table.items()},
            "policy": self.get_policy(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QLearningDispersal":
        obj = cls(
            learning_rate=data.get("alpha", 0.15),
            discount=data.get("gamma", 0.92),
            epsilon=data.get("epsilon", 0.3),
            epsilon_min=data.get("epsilon_min", 0.05),
            epsilon_decay=data.get("epsilon_decay", 0.95),
        )
        obj.training_rounds = data.get("training_rounds", 0)
        for state, actions in data.get("q_table", {}).items():
            for action, value in actions.items():
                obj.q_table[state][action] = value
        return obj
