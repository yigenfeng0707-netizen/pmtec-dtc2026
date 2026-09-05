"""
P5-2: MADDPG (Multi-Agent Deep Deterministic Policy Gradient) for PMTEC.

Replaces IQL with true centralized-training decentralized-execution:
  - Each agent has its own Actor (local obs -> action logits -> softmax)
  - Each agent has its own Critic (all obs + all actions -> Q-value)
  - Target networks with soft update (tau=0.005)
  - Shared replay buffer with full transition tuples
  - Discrete action support via Gumbel-Softmax approximation

Key difference from IQL:
  - IQL: each agent's critic only sees its own (obs, action)
  - MADDPG: each agent's critic sees ALL agents' (obs, actions) -> stable multi-agent training

Integration: drop-in replacement for MultiAgentDQN in grpc_server.py.
"""

import os
import json
import time
import math
import random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque
from typing import Optional

from deep_rl.dqn_agent import detect_best_device
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


class ActorNet(nn.Module):
    """Actor network: local observation -> action probabilities (softmax)."""

    def __init__(self, obs_dim: int, action_dim: int, hidden=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, action_dim),
        )

    def forward(self, obs):
        logits = self.net(obs)
        return F.softmax(logits, dim=-1)

    def get_action(self, obs, deterministic=True):
        """Sample or argmax action from policy."""
        with torch.no_grad():
            probs = self.forward(obs)
            if deterministic:
                return probs.argmax(dim=-1)
            else:
                dist = torch.distributions.Categorical(probs)
                return dist.sample()


class CriticNet(nn.Module):
    """Critic network: (all obs + all actions) -> Q-value.

    Centralized critic sees full state and all agents' actions.
    """

    def __init__(self, obs_all_dim: int, action_all_dim: int, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_all_dim + action_all_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, 1),
        )

    def forward(self, obs_all, action_all_onehot):
        x = torch.cat([obs_all, action_all_onehot], dim=-1)
        return self.net(x)


class ReplayBuffer:
    """Experience replay buffer for multi-agent transitions."""

    def __init__(self, capacity: int = 50000):
        self.buffer = deque(maxlen=capacity)

    def push(self, obs_i, obs_d, a_i, a_d, reward, next_obs_i, next_obs_d, done):
        self.buffer.append(
            (obs_i, obs_d, a_i, a_d, reward, next_obs_i, next_obs_d, done)
        )

    def sample(self, batch_size):
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        obs_i, obs_d, a_i, a_d, rewards, nobs_i, nobs_d, dones = zip(*batch)
        return (
            np.array(obs_i, dtype=np.float32),
            np.array(obs_d, dtype=np.float32),
            np.array(a_i, dtype=np.int64),
            np.array(a_d, dtype=np.int64),
            np.array(rewards, dtype=np.float32),
            np.array(nobs_i, dtype=np.float32),
            np.array(nobs_d, dtype=np.float32),
            np.array(dones, dtype=np.float32),
        )

    def __len__(self):
        return len(self.buffer)


class MADDPGAgent:
    """MADDPG multi-agent trainer for PMTEC cooperative decision-making.

    Two agents (Intercept + Dispersal) with:
      - Independent Actor networks (decentralized execution)
      - Centralized Critic networks (see all obs + all actions)
      - Soft target updates
      - Epsilon-greedy exploration with decay
    """

    def __init__(
        self,
        lr_actor: float = 1e-4,
        lr_critic: float = 1e-3,
        gamma: float = 0.95,
        tau: float = 0.005,
        buffer_size: int = 50000,
        batch_size: int = 128,
        epsilon_start: float = 0.9,
        epsilon_end: float = 0.05,
        epsilon_decay: float = 0.9995,
        hidden_actor: int = 128,
        hidden_critic: int = 256,
        device: str = "auto",
    ):
        if device == "auto":
            device = detect_best_device()
        self.device = torch.device(device)
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay

        # Action dims
        self.action_dims = {
            INTERCEPT_AGENT: INTERCEPT_ACTIONS,
            DISPERSAL_AGENT: DISPERSAL_ACTIONS,
        }
        total_action_dim = INTERCEPT_ACTIONS + DISPERSAL_ACTIONS  # one-hot total

        # Actor networks (one per agent)
        self.actors = {}
        self.target_actors = {}
        self.actor_opts = {}

        for aid in AGENT_IDS:
            actor = ActorNet(OBS_DIM, self.action_dims[aid], hidden=hidden_actor).to(
                self.device
            )
            target_actor = ActorNet(
                OBS_DIM, self.action_dims[aid], hidden=hidden_actor
            ).to(self.device)
            target_actor.load_state_dict(actor.state_dict())
            target_actor.eval()
            opt = optim.Adam(actor.parameters(), lr=lr_actor)
            self.actors[aid] = actor
            self.target_actors[aid] = target_actor
            self.actor_opts[aid] = opt

        # Critic networks (one per agent, centralized)
        # Critic sees: both obs (2*OBS_DIM) + both actions (one-hot total_action_dim)
        critic_input_obs = 2 * OBS_DIM
        critic_input_action = total_action_dim

        self.critics = {}
        self.target_critics = {}
        self.critic_opts = {}

        for aid in AGENT_IDS:
            critic = CriticNet(
                critic_input_obs, critic_input_action, hidden=hidden_critic
            ).to(self.device)
            target_critic = CriticNet(
                critic_input_obs, critic_input_action, hidden=hidden_critic
            ).to(self.device)
            target_critic.load_state_dict(critic.state_dict())
            target_critic.eval()
            opt = optim.Adam(critic.parameters(), lr=lr_critic)
            self.critics[aid] = critic
            self.target_critics[aid] = target_critic
            self.critic_opts[aid] = opt

        # Replay buffer
        self.replay = ReplayBuffer(capacity=buffer_size)

        self._is_trained = False
        self._training_history: list[dict] = []
        os.makedirs(_MODEL_DIR, exist_ok=True)

    @property
    def intercept_model_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_maddpg_intercept.pt")

    @property
    def dispersal_model_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_maddpg_dispersal.pt")

    @property
    def history_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_maddpg_history.json")

    def is_trained(self) -> bool:
        return os.path.exists(self.intercept_model_path) and os.path.exists(
            self.dispersal_model_path
        )

    def _one_hot(self, action_idx, dim):
        """Convert action index to one-hot tensor."""
        if isinstance(action_idx, (int, np.integer)):
            action_idx = [action_idx]
        t = torch.zeros(len(action_idx), dim, device=self.device)
        for i, a in enumerate(action_idx):
            t[i, int(a)] = 1.0
        return t

    def _select_action(self, obs_np, agent_id, deterministic=False):
        """Select action for an agent (epsilon-greedy)."""
        if not deterministic and random.random() < self.epsilon:
            return random.randint(0, self.action_dims[agent_id] - 1)
        obs = torch.FloatTensor(obs_np).unsqueeze(0).to(self.device)
        action = self.actors[agent_id].get_action(obs, deterministic=True)
        return int(action.item())

    def train(self, total_timesteps: int = 10000, ma_env: MultiAgentPMTECEnv = None):
        """Train both agents with MADDPG."""
        if ma_env is None:
            ma_env = MultiAgentPMTECEnv(duration=120, seed=42)

        print(f"[MADDPG] Starting training: {total_timesteps} timesteps")
        print(f"[MADDPG] Device: {self.device}")
        print(
            f"[MADDPG] Agents: {INTERCEPT_AGENT} ({INTERCEPT_ACTIONS} actions) + "
            f"{DISPERSAL_AGENT} ({DISPERSAL_ACTIONS} actions)"
        )
        print(
            f"[MADDPG] Centralized critics: obs_dim={2 * OBS_DIM}, action_dim={INTERCEPT_ACTIONS + DISPERSAL_ACTIONS}"
        )

        t0 = time.time()
        episode = 0
        step = 0
        episode_reward = 0
        episode_rewards = []

        obs_dict, _ = ma_env.reset(seed=42)

        while step < total_timesteps:
            # Select actions for both agents
            obs_i = obs_dict[INTERCEPT_AGENT]
            obs_d = obs_dict[DISPERSAL_AGENT]
            a_i = self._select_action(obs_i, INTERCEPT_AGENT, deterministic=False)
            a_d = self._select_action(obs_d, DISPERSAL_AGENT, deterministic=False)

            # Step environment
            next_obs_dict, reward, done, truncated, info = ma_env.step(
                {
                    INTERCEPT_AGENT: a_i,
                    DISPERSAL_AGENT: a_d,
                }
            )
            next_obs_i = next_obs_dict[INTERCEPT_AGENT]
            next_obs_d = next_obs_dict[DISPERSAL_AGENT]

            # Store transition in replay buffer
            self.replay.push(
                obs_i,
                obs_d,
                a_i,
                a_d,
                reward,
                next_obs_i,
                next_obs_d,
                done or truncated,
            )

            episode_reward += reward
            obs_dict = next_obs_dict
            step += 1

            # Decay epsilon
            self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)

            # Train on mini-batch
            if len(self.replay) >= self.batch_size and step % 4 == 0:
                self._update()

            if done or truncated:
                episode += 1
                episode_rewards.append(episode_reward)
                if episode % 10 == 0:
                    avg_r = np.mean(episode_rewards[-10:])
                    print(
                        f"  [MADDPG] Step {step}/{total_timesteps} | Ep {episode} | "
                        f"Avg reward (last 10): {avg_r:.1f} | eps={self.epsilon:.3f}"
                    )
                episode_reward = 0
                obs_dict, _ = ma_env.reset()

        elapsed = time.time() - t0
        self._is_trained = True

        # Save models
        self._save_models()

        entry = {
            "algorithm": "MADDPG",
            "timesteps": total_timesteps,
            "elapsed_seconds": round(elapsed, 1),
            "agents": AGENT_IDS,
            "intercept_actions": INTERCEPT_ACTIONS,
            "dispersal_actions": DISPERSAL_ACTIONS,
            "device": str(self.device),
            "hidden_actor": 128,
            "hidden_critic": 256,
            "gamma": self.gamma,
            "tau": self.tau,
            "batch_size": self.batch_size,
            "buffer_used": len(self.replay),
            "avg_reward_last_10": float(np.mean(episode_rewards[-10:]))
            if episode_rewards
            else 0,
            "total_episodes": episode,
            "timestamp": time.time(),
        }
        self._training_history.append(entry)
        self._save_history()

        print(f"\n[MADDPG] Training complete in {elapsed:.1f}s")
        print(
            f"[MADDPG] Episodes: {episode}, Avg reward (last 10): {entry['avg_reward_last_10']:.1f}"
        )
        print(f"[MADDPG] Intercept model: {self.intercept_model_path}")
        print(f"[MADDPG] Dispersal model: {self.dispersal_model_path}")
        return entry

    def _update(self):
        """Update all agents' actors and critics with a mini-batch."""
        obs_i, obs_d, a_i, a_d, rewards, nobs_i, nobs_d, dones = self.replay.sample(
            self.batch_size
        )

        # Convert to tensors
        obs_i_t = torch.FloatTensor(obs_i).to(self.device)
        obs_d_t = torch.FloatTensor(obs_d).to(self.device)
        a_i_t = torch.LongTensor(a_i).to(self.device)
        a_d_t = torch.LongTensor(a_d).to(self.device)
        rewards_t = torch.FloatTensor(rewards).unsqueeze(1).to(self.device)
        nobs_i_t = torch.FloatTensor(nobs_i).to(self.device)
        nobs_d_t = torch.FloatTensor(nobs_d).to(self.device)
        dones_t = torch.FloatTensor(dones).unsqueeze(1).to(self.device)

        # One-hot encode actions
        a_i_oh = self._one_hot_batch(a_i_t, INTERCEPT_ACTIONS)
        a_d_oh = self._one_hot_batch(a_d_t, DISPERSAL_ACTIONS)
        action_all = torch.cat([a_i_oh, a_d_oh], dim=-1)  # (batch, 6)

        # All observations concatenated for centralized critic
        obs_all = torch.cat([obs_i_t, obs_d_t], dim=-1)  # (batch, 244)
        next_obs_all = torch.cat([nobs_i_t, nobs_d_t], dim=-1)

        for aid in AGENT_IDS:
            # --- Critic update ---
            # Target Q: r + gamma * target_critic(next_obs_all, target_actions) * (1 - done)
            with torch.no_grad():
                # Target actions from target actors
                ta_i = self.target_actors[INTERCEPT_AGENT].get_action(
                    obs_i_t, deterministic=True
                )
                ta_d = self.target_actors[DISPERSAL_AGENT].get_action(
                    obs_d_t, deterministic=True
                )
                ta_i_oh = self._one_hot_batch(ta_i, INTERCEPT_ACTIONS)
                ta_d_oh = self._one_hot_batch(ta_d, DISPERSAL_ACTIONS)
                target_action_all = torch.cat([ta_i_oh, ta_d_oh], dim=-1)
                target_q = self.target_critics[aid](next_obs_all, target_action_all)
                target_q = rewards_t + self.gamma * target_q * (1 - dones_t)

            # Current Q
            current_q = self.critics[aid](obs_all, action_all)
            critic_loss = F.mse_loss(current_q, target_q.detach())

            self.critic_opts[aid].zero_grad()
            critic_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.critics[aid].parameters(), 1.0)
            self.critic_opts[aid].step()

            # --- Actor update ---
            # Maximize Q(s_all, a_all) where a_agent comes from actor
            # Use current actor's output for the agent being trained
            if aid == INTERCEPT_AGENT:
                pa = self.actors[aid](obs_i_t)  # softmax probs
                # Gumbel-softmax for differentiable discrete action
                pa_oh = F.gumbel_softmax(torch.log(pa + 1e-8) + 1e-8, hard=True)
                fixed_action = a_d_oh.detach()
                policy_action_all = torch.cat([pa_oh, fixed_action], dim=-1)
            else:
                pa = self.actors[aid](obs_d_t)
                pa_oh = F.gumbel_softmax(torch.log(pa + 1e-8) + 1e-8, hard=True)
                fixed_action = a_i_oh.detach()
                policy_action_all = torch.cat([fixed_action, pa_oh], dim=-1)

            actor_q = self.critics[aid](obs_all, policy_action_all)
            actor_loss = -actor_q.mean()

            self.actor_opts[aid].zero_grad()
            actor_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.actors[aid].parameters(), 1.0)
            self.actor_opts[aid].step()

        # Soft update target networks
        self._soft_update()

    def _one_hot_batch(self, action_indices, dim):
        """Batch one-hot encoding."""
        n = action_indices.shape[0]
        oh = torch.zeros(n, dim, device=self.device)
        oh.scatter_(1, action_indices.unsqueeze(1), 1.0)
        return oh

    def _soft_update(self):
        """Soft update target networks: theta_target = tau*theta + (1-tau)*theta_target."""
        for aid in AGENT_IDS:
            for param, target_param in zip(
                self.actors[aid].parameters(), self.target_actors[aid].parameters()
            ):
                target_param.data.copy_(
                    self.tau * param.data + (1 - self.tau) * target_param.data
                )
            for param, target_param in zip(
                self.critics[aid].parameters(), self.target_critics[aid].parameters()
            ):
                target_param.data.copy_(
                    self.tau * param.data + (1 - self.tau) * target_param.data
                )

    def _save_models(self):
        """Save actor models (for decentralized execution)."""
        torch.save(
            {
                "actor_state": self.actors[INTERCEPT_AGENT].state_dict(),
                "obs_dim": OBS_DIM,
                "action_dim": INTERCEPT_ACTIONS,
            },
            self.intercept_model_path,
        )
        torch.save(
            {
                "actor_state": self.actors[DISPERSAL_AGENT].state_dict(),
                "obs_dim": OBS_DIM,
                "action_dim": DISPERSAL_ACTIONS,
            },
            self.dispersal_model_path,
        )
        print(f"[MADDPG] Models saved")

    def predict(self, observation, agent_id: str = None) -> dict:
        """Predict actions from both agents (decentralized execution).

        Each agent only uses its own actor (local observation).
        Returns dict {agent_id: action_int}.
        """
        if not self._is_trained:
            self.load()

        obs = np.array(observation, dtype=np.float32)
        if obs.ndim == 1:
            obs = obs.reshape(1, -1)
        obs_t = torch.FloatTensor(obs).to(self.device)

        if agent_id is not None:
            with torch.no_grad():
                action = self.actors[agent_id].get_action(obs_t, deterministic=True)
            return int(action.item())

        result = {}
        for aid in AGENT_IDS:
            with torch.no_grad():
                action = self.actors[aid].get_action(obs_t, deterministic=True)
            result[aid] = int(action.item())
        return result

    def load(self):
        """Load actor models for decentralized execution.

        P6-2: Gracefully handle dimension mismatch when observation space changes.
        Old checkpoints (122-dim) won't load into new networks (182-dim) —
        return False so engine falls back to DQN/IQL.
        """
        loaded = {}
        if os.path.exists(self.intercept_model_path):
            try:
                ckpt = torch.load(
                    self.intercept_model_path,
                    map_location=self.device,
                    weights_only=True,
                )
                self.actors[INTERCEPT_AGENT].load_state_dict(ckpt["actor_state"])
                self.target_actors[INTERCEPT_AGENT].load_state_dict(ckpt["actor_state"])
                loaded[INTERCEPT_AGENT] = True
                print(
                    f"[MADDPG] Intercept actor loaded from {self.intercept_model_path}"
                )
            except RuntimeError as e:
                print(f"[MADDPG] Intercept actor load skipped (dim mismatch): {e}")

        if os.path.exists(self.dispersal_model_path):
            try:
                ckpt = torch.load(
                    self.dispersal_model_path,
                    map_location=self.device,
                    weights_only=True,
                )
                self.actors[DISPERSAL_AGENT].load_state_dict(ckpt["actor_state"])
                self.target_actors[DISPERSAL_AGENT].load_state_dict(ckpt["actor_state"])
                loaded[DISPERSAL_AGENT] = True
                print(
                    f"[MADDPG] Dispersal actor loaded from {self.dispersal_model_path}"
                )
            except RuntimeError as e:
                print(f"[MADDPG] Dispersal actor load skipped (dim mismatch): {e}")

        self._is_trained = len(loaded) == 2
        return self._is_trained

    def _save_history(self):
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self._training_history, f, indent=2, ensure_ascii=False)

    def get_statistics(self) -> dict:
        history = []
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                history = json.load(f)

        return {
            "algorithm": "MADDPG (Multi-Agent DDPG)",
            "is_trained": self.is_trained(),
            "agents": AGENT_IDS,
            "intercept_actions": INTERCEPT_ACTIONS,
            "dispersal_actions": DISPERSAL_ACTIONS,
            "training_runs": len(history),
            "total_timesteps": sum(h.get("timesteps", 0) for h in history),
            "last_run": history[-1] if history else None,
            "device": str(self.device),
            "intercept_model": self.intercept_model_path
            if os.path.exists(self.intercept_model_path)
            else None,
            "dispersal_model": self.dispersal_model_path
            if os.path.exists(self.dispersal_model_path)
            else None,
            "observation_dim": OBS_DIM,
            "observation_layout": "22 bases x 5 feats + 12 global (shared)",
            "architecture": "Actor-Critic (centralized critic, decentralized actor)",
            "critic_input": f"obs({2 * OBS_DIM}) + actions({INTERCEPT_ACTIONS + DISPERSAL_ACTIONS})",
        }
