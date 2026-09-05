"""
Multi-Agent DQN Trainer using IQL (Independent Q-Learning).

P4-4: Trains two cooperative agents (Intercept + Dispersal) with independent DQNs.
Each agent has its own replay buffer and network, but they share the environment
and team reward. This is the simplest multi-agent RL approach that works with
existing SB3 DQN infrastructure.

Training loop:
  1. Reset env -> both agents see obs
  2. Each agent selects action (epsilon-greedy on own DQN)
  3. Combined action steps env -> shared reward
  4. Each agent stores (obs, action, reward, next_obs, done) in own buffer
  5. Each agent trains own DQN on own buffer
  6. Repeat

Integration: grpc_server.py loads both agent models and queries them for decisions.
"""

import os
import json
import time
import numpy as np
import torch
import torch.nn as nn
from typing import Optional
from stable_baselines3 import DQN
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.callbacks import BaseCallback

from deep_rl.dqn_agent import detect_best_device, TrainingLogger
from deep_rl.multi_agent_env import (
    MultiAgentPMTECEnv,
    SingleAgentWrapper,
    INTERCEPT_AGENT,
    DISPERSAL_AGENT,
    INTERCEPT_ACTIONS,
    DISPERSAL_ACTIONS,
    AGENT_IDS,
)
from deep_rl.pmtec_env import OBS_DIM


_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "models",
)


class MultiAgentDQN:
    """IQL multi-agent DQN for PMTEC cooperative decision-making.

    Two agents:
      - Intercept Agent: 3 actions (direct, predictive, saturation)
      - Dispersal Agent: 3 actions (hold, light 15%, heavy 30%)
    """

    def __init__(
        self,
        learning_rate: float = 1e-4,
        buffer_size: int = 20000,
        batch_size: int = 64,
        gamma: float = 0.95,
        exploration_fraction: float = 0.3,
        exploration_initial_eps: float = 1.0,
        exploration_final_eps: float = 0.05,
        target_update_interval: int = 500,
        train_freq: int = 4,
        device: str = "auto",
    ):
        if device == "auto":
            device = detect_best_device()
        self.device = device
        self.lr = learning_rate
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.gamma = gamma
        self._is_trained = False
        self._training_history: list[dict] = []

        # Per-agent DQN configs
        self._agent_config = {
            "learning_rate": learning_rate,
            "buffer_size": buffer_size,
            "batch_size": batch_size,
            "gamma": gamma,
            "exploration_fraction": exploration_fraction,
            "exploration_initial_eps": exploration_initial_eps,
            "exploration_final_eps": exploration_final_eps,
            "target_update_interval": target_update_interval,
            "train_freq": train_freq,
            "device": device,
        }

        # Per-agent models (lazy init)
        self._models: dict[str, Optional[DQN]] = {
            INTERCEPT_AGENT: None,
            DISPERSAL_AGENT: None,
        }

        os.makedirs(_MODEL_DIR, exist_ok=True)

    @property
    def intercept_model_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_iql_intercept.zip")

    @property
    def dispersal_model_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_iql_dispersal.zip")

    @property
    def history_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_iql_history.json")

    def is_trained(self) -> bool:
        return os.path.exists(self.intercept_model_path) and os.path.exists(
            self.dispersal_model_path
        )

    def train(
        self,
        total_timesteps: int = 10000,
        ma_env: MultiAgentPMTECEnv = None,
        resume: bool = False,
    ):
        """Train both agents with IQL.

        Each agent trains on its own SingleAgentWrapper, where the teammate
        uses the other agent's current policy (updated periodically).

        Args:
            total_timesteps: Steps per agent (split across 3 rounds).
            ma_env: Custom multi-agent env. If None, creates default.
            resume: If True, load existing models and continue training
                    (incremental checkpoint). Models keep their learned
                    weights and replay buffers.
        """
        if ma_env is None:
            ma_env = MultiAgentPMTECEnv(duration=120, seed=42)

        # Resume: load existing models to continue training
        if resume and self._models[INTERCEPT_AGENT] is None:
            self.load()

        # Initial teammate policies: random
        intercept_fn = lambda obs: np.random.randint(0, INTERCEPT_ACTIONS)
        dispersal_fn = lambda obs: np.random.randint(0, DISPERSAL_ACTIONS)

        # Create single-agent wrappers
        intercept_env = SingleAgentWrapper(
            ma_env, INTERCEPT_AGENT, teammate_action_fn=dispersal_fn
        )
        dispersal_env = SingleAgentWrapper(
            ma_env, DISPERSAL_AGENT, teammate_action_fn=intercept_fn
        )

        policy_kwargs = {
            "net_arch": [128, 64],
            "activation_fn": nn.ReLU,
        }

        # Create both DQNs (skip if resuming with loaded models)
        if self._models[INTERCEPT_AGENT] is None:
            self._models[INTERCEPT_AGENT] = DQN(
                "MlpPolicy",
                DummyVecEnv([lambda: intercept_env]),
                policy_kwargs=policy_kwargs,
                **self._agent_config,
                verbose=1,
            )
        else:
            # Resume: set new env on existing model
            self._models[INTERCEPT_AGENT].set_env(DummyVecEnv([lambda: intercept_env]))

        if self._models[DISPERSAL_AGENT] is None:
            self._models[DISPERSAL_AGENT] = DQN(
                "MlpPolicy",
                DummyVecEnv([lambda: dispersal_env]),
                policy_kwargs=policy_kwargs,
                **self._agent_config,
                verbose=1,
            )
        else:
            self._models[DISPERSAL_AGENT].set_env(DummyVecEnv([lambda: dispersal_env]))

        print(f"[IQL] Starting training: {total_timesteps} timesteps per agent")
        print(f"[IQL] Device: {self.device}")
        print(
            f"[IQL] Agents: {INTERCEPT_AGENT} ({INTERCEPT_ACTIONS} actions) + "
            f"{DISPERSAL_AGENT} ({DISPERSAL_ACTIONS} actions)"
        )

        # IQL training: alternate training rounds
        # Phase 1: Train intercept agent with random teammate
        # Phase 2: Update teammate policy, train dispersal agent
        # Phase 3: Repeat with updated policies
        round_steps = total_timesteps // 3
        t0 = time.time()

        for round_idx in range(3):
            phase = round_idx + 1
            print(
                f"\n[IQL] Round {phase}/3: Training both agents ({round_steps} steps each)"
            )

            # Update teammate functions with current policies
            if self._models[INTERCEPT_AGENT] is not None:

                def make_intercept_fn(model):
                    def fn(obs):
                        obs = np.array(obs, dtype=np.float32)
                        if obs.ndim == 1:
                            obs = obs.reshape(1, -1)
                        a, _ = model.predict(obs, deterministic=True)
                        if isinstance(a, (np.ndarray, np.generic)):
                            a = int(a.item()) if a.ndim == 0 else int(a.flat[0])
                        return int(a)

                    return fn

                intercept_fn = make_intercept_fn(self._models[INTERCEPT_AGENT])
                dispersal_env.set_teammate_fn(intercept_fn)

            if self._models[DISPERSAL_AGENT] is not None:

                def make_dispersal_fn(model):
                    def fn(obs):
                        obs = np.array(obs, dtype=np.float32)
                        if obs.ndim == 1:
                            obs = obs.reshape(1, -1)
                        a, _ = model.predict(obs, deterministic=True)
                        if isinstance(a, (np.ndarray, np.generic)):
                            a = int(a.item()) if a.ndim == 0 else int(a.flat[0])
                        return int(a)

                    return fn

                dispersal_fn = make_dispersal_fn(self._models[DISPERSAL_AGENT])
                intercept_env.set_teammate_fn(dispersal_fn)

            # Train intercept agent
            print(f"  [IQL] Training {INTERCEPT_AGENT} agent...")
            self._models[INTERCEPT_AGENT].learn(
                total_timesteps=round_steps,
                progress_bar=False,
                reset_num_timesteps=False,
            )

            # Train dispersal agent
            print(f"  [IQL] Training {DISPERSAL_AGENT} agent...")
            self._models[DISPERSAL_AGENT].learn(
                total_timesteps=round_steps,
                progress_bar=False,
                reset_num_timesteps=False,
            )

            # Per-round checkpoint save (protects against timeout)
            self._models[INTERCEPT_AGENT].save(self.intercept_model_path)
            self._models[DISPERSAL_AGENT].save(self.dispersal_model_path)
            print(f"  [IQL] Round {phase}/3 checkpoint saved")

        elapsed = time.time() - t0

        # Final save (redundant with last checkpoint, but ensures _is_trained flag)
        self._models[INTERCEPT_AGENT].save(self.intercept_model_path)
        self._models[DISPERSAL_AGENT].save(self.dispersal_model_path)
        self._is_trained = True

        entry = {
            "algorithm": "IQL",
            "timesteps": total_timesteps,
            "elapsed_seconds": round(elapsed, 1),
            "agents": AGENT_IDS,
            "intercept_actions": INTERCEPT_ACTIONS,
            "dispersal_actions": DISPERSAL_ACTIONS,
            "device": self.device,
            "net_arch": [128, 64],
            "timestamp": time.time(),
        }
        self._training_history.append(entry)
        self._save_history()

        print(f"\n[IQL] Training complete in {elapsed:.1f}s")
        print(f"[IQL] Intercept model: {self.intercept_model_path}")
        print(f"[IQL] Dispersal model: {self.dispersal_model_path}")
        return entry

    def predict(self, observation: np.ndarray, agent_id: str = None) -> dict:
        """Predict actions from both agents (or a specific agent).

        Returns dict {agent_id: action} when agent_id is None,
        or a single int when agent_id is specified.
        """
        if self._models[INTERCEPT_AGENT] is None:
            self.load()

        obs = np.array(observation, dtype=np.float32)
        if obs.ndim == 1:
            obs = obs.reshape(1, -1)

        if agent_id is not None:
            model = self._models.get(agent_id)
            if model is None:
                return 0
            a, _ = model.predict(obs, deterministic=True)
            if isinstance(a, (np.ndarray, np.generic)):
                a = int(a.item()) if a.ndim == 0 else int(a.flat[0])
            return int(a)

        # Both agents
        result = {}
        for aid in AGENT_IDS:
            model = self._models.get(aid)
            if model is None:
                result[aid] = 0
            else:
                a, _ = model.predict(obs, deterministic=True)
                if isinstance(a, (np.ndarray, np.generic)):
                    a = int(a.item()) if a.ndim == 0 else int(a.flat[0])
                result[aid] = int(a)
        return result

    def load(self):
        """Load both agent models.

        P6-2: Gracefully handle dimension mismatch when observation space changes.
        """
        from deep_rl.pmtec_env import OBS_DIM

        loaded = {}
        if os.path.exists(self.intercept_model_path):
            try:
                model = DQN.load(self.intercept_model_path, device=self.device)
                if model.observation_space.shape[0] != OBS_DIM:
                    print(
                        f"[IQL] Intercept model obs_dim={model.observation_space.shape[0]} != {OBS_DIM} — skipping"
                    )
                else:
                    self._models[INTERCEPT_AGENT] = model
                    loaded[INTERCEPT_AGENT] = True
                    print(
                        f"[IQL] Intercept model loaded from {self.intercept_model_path}"
                    )
            except Exception as e:
                print(f"[IQL] Intercept model load skipped: {e}")

        if os.path.exists(self.dispersal_model_path):
            try:
                model = DQN.load(self.dispersal_model_path, device=self.device)
                if model.observation_space.shape[0] != OBS_DIM:
                    print(
                        f"[IQL] Dispersal model obs_dim={model.observation_space.shape[0]} != {OBS_DIM} — skipping"
                    )
                else:
                    self._models[DISPERSAL_AGENT] = model
                    loaded[DISPERSAL_AGENT] = True
                    print(
                        f"[IQL] Dispersal model loaded from {self.dispersal_model_path}"
                    )
            except Exception as e:
                print(f"[IQL] Dispersal model load skipped: {e}")

        self._is_trained = len(loaded) == 2
        return self._is_trained

    def _save_history(self):
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self._training_history, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list:
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_statistics(self) -> dict:
        history = self.load_history()
        return {
            "algorithm": "IQL (Independent Q-Learning)",
            "is_trained": self.is_trained(),
            "agents": AGENT_IDS,
            "intercept_actions": INTERCEPT_ACTIONS,
            "dispersal_actions": DISPERSAL_ACTIONS,
            "training_runs": len(history),
            "total_timesteps": sum(h.get("timesteps", 0) for h in history),
            "last_run": history[-1] if history else None,
            "device": self.device,
            "intercept_model": (
                self.intercept_model_path
                if os.path.exists(self.intercept_model_path)
                else None
            ),
            "dispersal_model": (
                self.dispersal_model_path
                if os.path.exists(self.dispersal_model_path)
                else None
            ),
            "observation_dim": OBS_DIM,
            "observation_layout": "22 bases x 5 feats + 12 global (shared)",
        }
