"""
Multi-Agent PMTEC Environment for IQL (Independent Q-Learning).

Decomposes the single-agent action space into two cooperative agents:
  - Intercept Agent: 3 actions (direct, predictive, saturation)
  - Dispersal Agent: 3 actions (hold, light dispersal 15%, heavy dispersal 30%)

Each agent sees the full 182-dim observation (shared state).
Agents act simultaneously; combined action drives PMTECEnv.step().
Reward is shared (team reward) - standard IQL approach.

P4-4: Multi-Agent RL for cooperative ASDA decision-making.
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Optional

from deep_rl.pmtec_env import PMTECEnv, OBS_DIM


# Agent IDs
INTERCEPT_AGENT = "intercept"
DISPERSAL_AGENT = "dispersal"
AGENT_IDS = [INTERCEPT_AGENT, DISPERSAL_AGENT]

# Action spaces per agent
INTERCEPT_ACTIONS = 3  # direct, predictive, saturation
DISPERSAL_ACTIONS = 3  # hold, light (15%), heavy (30%)


class MultiAgentPMTECEnv(gym.Env):
    """Multi-agent wrapper around PMTECEnv for IQL training.

    Observation: shared 182-dim vector for both agents.
    Action: dict {agent_id: int} with per-agent action spaces.
    Reward: shared team reward.
    """

    metadata = {"render_modes": [], "is_multi_agent": True}

    def __init__(
        self,
        bases: list = None,
        duration: int = 120,
        seed: int = 42,
        political: bool = False,
    ):
        super().__init__()
        self._inner = PMTECEnv(bases=bases, duration=duration, seed=seed,
                               political=political)

        # Shared observation space (P12-2: expanded when political=True)
        obs_dim = self._inner.observation_space.shape[0]
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(obs_dim,), dtype=np.float32
        )
        # Per-agent action spaces (MultiDiscrete style, but we expose as dict)
        self.action_space = spaces.Dict(
            {
                INTERCEPT_AGENT: spaces.Discrete(INTERCEPT_ACTIONS),
                DISPERSAL_AGENT: spaces.Discrete(DISPERSAL_ACTIONS),
            }
        )
        # Individual action spaces for SB3 compatibility
        self.intercept_action_space = spaces.Discrete(INTERCEPT_ACTIONS)
        self.dispersal_action_space = spaces.Discrete(DISPERSAL_ACTIONS)

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        """Reset episode. Returns dict of per-agent observations."""
        obs, info = self._inner.reset(seed=seed, options=options)
        # Both agents see the same observation
        observations = {
            INTERCEPT_AGENT: obs,
            DISPERSAL_AGENT: obs,
        }
        infos = {
            INTERCEPT_AGENT: info,
            DISPERSAL_AGENT: info,
        }
        return observations, infos

    def step(self, actions: dict):
        """Step with combined actions from both agents.

        Args:
            actions: {INTERCEPT_AGENT: int 0-2, DISPERSAL_AGENT: int 0-2}
        """
        intercept_strategy = actions.get(INTERCEPT_AGENT, 0)
        dispersal_level = actions.get(DISPERSAL_AGENT, 0)

        # Map dispersal level to action bit:
        # 0 = hold (no dispersal), 1 = light (action%2==1), 2 = heavy (action%2==1)
        # The original env used should_disperse = action % 2 == 1
        # For multi-agent, we encode: combined = intercept_strategy * 2 + should_disperse
        # But we also want to control dispersal intensity (light=15% vs heavy=30%)
        if dispersal_level == 0:
            # No dispersal
            combined_action = intercept_strategy * 2  # should_disperse=0
        else:
            # Dispersal (light or heavy)
            combined_action = intercept_strategy * 2 + 1  # should_disperse=1
            # Override dispersal fraction in inner env
            if dispersal_level == 2:
                # Heavy dispersal: temporarily set a flag for 30% dispersal
                self._inner._heavy_dispersal = True

        obs, reward, done, truncated, info = self._inner.step(combined_action)

        # Clean up heavy dispersal flag
        if hasattr(self._inner, "_heavy_dispersal"):
            delattr(self._inner, "_heavy_dispersal")

        # Both agents receive the same observation and shared reward
        observations = {
            INTERCEPT_AGENT: obs,
            DISPERSAL_AGENT: obs,
        }
        infos = {
            INTERCEPT_AGENT: info,
            DISPERSAL_AGENT: info,
        }
        # Add per-agent action info for analysis
        infos["_combined"] = {
            "intercept_strategy": intercept_strategy,
            "dispersal_level": dispersal_level,
            "combined_action": combined_action,
        }
        return observations, reward, done, truncated, infos

    def get_inner_env(self) -> PMTECEnv:
        """Access the underlying PMTECEnv."""
        return self._inner


class SingleAgentWrapper(gym.Env):
    """Wraps one agent's view of the multi-agent env for SB3 training.

    Each agent trains on the full observation but only controls its action.
    The other agent's action is sampled from its current policy (or random).
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        ma_env: MultiAgentPMTECEnv,
        agent_id: str,
        teammate_action_fn=None,
    ):
        super().__init__()
        self._ma_env = ma_env
        self._agent_id = agent_id
        self._teammate_fn = teammate_action_fn or (lambda obs: 0)

        if agent_id == INTERCEPT_AGENT:
            self.action_space = ma_env.intercept_action_space
        else:
            self.action_space = ma_env.dispersal_action_space
        self.observation_space = ma_env.observation_space

    def reset(self, seed=None, options=None):
        obs_dict, info_dict = self._ma_env.reset(seed=seed, options=options)
        return obs_dict[self._agent_id], info_dict[self._agent_id]

    def step(self, action):
        obs = None
        # Get teammate action from its policy
        # We need the current observation to feed to teammate
        # But in SB3, we don't have it here. Use last obs stored in inner env.
        inner = self._ma_env.get_inner_env()
        teammate_obs = inner._get_obs()
        teammate_action = self._teammate_fn(teammate_obs)

        if self._agent_id == INTERCEPT_AGENT:
            actions = {INTERCEPT_AGENT: action, DISPERSAL_AGENT: teammate_action}
        else:
            actions = {INTERCEPT_AGENT: teammate_action, DISPERSAL_AGENT: action}

        obs_dict, reward, done, truncated, info = self._ma_env.step(actions)
        return obs_dict[self._agent_id], reward, done, truncated, info[self._agent_id]

    def set_teammate_fn(self, fn):
        """Update teammate policy function."""
        self._teammate_fn = fn
