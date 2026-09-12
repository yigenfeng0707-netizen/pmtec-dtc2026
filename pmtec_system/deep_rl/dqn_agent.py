"""
DQN Agent - Deep Q-Network for PMTEC ASDA decision-making.
Uses stable_baselines3 DQN with PyTorch backend (CPU or XPU mode).
Trains on PMTECEnv, persists model, provides inference for grpc_server.

P2: Added XPU (Intel Arc GPU) auto-detection for GPU-accelerated training.
"""

import json
import os
import time

import numpy as np
import torch
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from torch import nn


def detect_best_device() -> str:
    """Auto-detect best available compute device.

    Priority: xpu (Intel Arc GPU) > cuda (NVIDIA) > cpu
    """
    try:
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu:0"
    except Exception:
        pass
    try:
        if torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


# Model paths
_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "models",
)


class TrainingLogger(BaseCallback):
    """Custom callback to log DQN training progress."""

    def __init__(self, log_interval=10, verbose=1):
        super().__init__(verbose)
        self.log_interval = log_interval
        self.episode_rewards = []
        self.episode_intercept_rates = []

    def _on_step(self):
        if self.n_calls % self.log_interval == 0:
            infos = self.locals.get("infos", [])
            for info in infos:
                if "intercept_rate" in info:
                    self.episode_intercept_rates.append(info["intercept_rate"])
        return True


class DQNAgent:
    """DQN agent wrapping stable_baselines3 for PMTEC ASDA decisions."""

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
        self.learning_rate = learning_rate
        self.buffer_size = buffer_size
        self.batch_size = batch_size
        self.gamma = gamma
        self.exploration_fraction = exploration_fraction
        self.exploration_initial_eps = exploration_initial_eps
        self.exploration_final_eps = exploration_final_eps
        self.target_update_interval = target_update_interval
        self.train_freq = train_freq
        # P2: Auto-detect XPU if device is "auto"
        if device == "auto":
            device = detect_best_device()
        self.device = device
        self._model: DQN | None = None
        self._is_trained = False
        self._training_history: list[dict] = []

        # Ensure model directory exists
        os.makedirs(_MODEL_DIR, exist_ok=True)

    @property
    def model_path(self) -> str:
        """Prefer P6 (182-dim) model, then 200K, then 50K model."""
        path_p6 = os.path.join(_MODEL_DIR, "pmtec_dqn_p6.zip")
        path_200k = os.path.join(_MODEL_DIR, "pmtec_dqn_200k.zip")
        path_50k = os.path.join(_MODEL_DIR, "pmtec_dqn.zip")
        if os.path.exists(path_p6):
            return path_p6
        if os.path.exists(path_200k):
            return path_200k
        return path_50k

    @property
    def history_path(self) -> str:
        return os.path.join(_MODEL_DIR, "pmtec_dqn_history.json")

    def is_trained(self) -> bool:
        return self._is_trained or os.path.exists(self.model_path)

    def train(
        self,
        env,
        total_timesteps: int = 5000,
        callback: BaseCallback | None = None,
    ):
        """Train DQN on the given environment."""
        vec_env = DummyVecEnv([lambda: env])

        # Custom policy: MLP (128, 64) for 182-dim observation (P6-1 expanded)
        policy_kwargs = {
            "net_arch": [128, 64],
            "activation_fn": nn.ReLU,
        }

        self._model = DQN(
            "MlpPolicy",
            vec_env,
            learning_rate=self.learning_rate,
            buffer_size=self.buffer_size,
            batch_size=self.batch_size,
            gamma=self.gamma,
            exploration_fraction=self.exploration_fraction,
            exploration_initial_eps=self.exploration_initial_eps,
            exploration_final_eps=self.exploration_final_eps,
            target_update_interval=self.target_update_interval,
            train_freq=self.train_freq,
            policy_kwargs=policy_kwargs,
            device=self.device,
            verbose=1,
        )

        logger = callback or TrainingLogger()
        print(f"[DQN] Starting training: {total_timesteps} timesteps on {self.device}")

        t0 = time.time()
        self._model.learn(
            total_timesteps=total_timesteps,
            callback=logger,
            progress_bar=False,
        )
        elapsed = time.time() - t0

        # Save model
        self._model.save(self.model_path)
        self._is_trained = True

        # Record training history
        entry = {
            "timesteps": total_timesteps,
            "elapsed_seconds": round(elapsed, 1),
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "gamma": self.gamma,
            "exploration_final": self.exploration_final_eps,
            "net_arch": [128, 64],
            "device": self.device,
            "timestamp": time.time(),
        }
        self._training_history.append(entry)
        self._save_history()

        print(f"[DQN] Training complete in {elapsed:.1f}s")
        print(f"[DQN] Model saved: {self.model_path}")
        return self._training_history[-1]

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> int:
        """Predict action from observation. Returns discrete action 0-5."""
        if self._model is None:
            self.load()
        if self._model is None:
            return np.random.randint(0, 6)

        obs = np.array(observation, dtype=np.float32)
        if obs.ndim == 1:
            obs = obs.reshape(1, -1)
        action, _ = self._model.predict(obs, deterministic=deterministic)
        # Handle both scalar and array returns
        if isinstance(action, (np.ndarray, np.generic)):
            action = int(action.item()) if action.ndim == 0 else int(action.flat[0])
        return int(action)

    def load(self):
        """Load trained DQN model from disk.

        P6-2: Check model observation dimension matches current OBS_DIM (182).
        Old models trained on 122-dim are skipped to avoid runtime errors.
        """
        from deep_rl.pmtec_env import OBS_DIM

        if os.path.exists(self.model_path):
            try:
                model = DQN.load(self.model_path, device=self.device)
                # Verify observation dimension matches
                model_obs_dim = model.observation_space.shape[0]
                if model_obs_dim != OBS_DIM:
                    print(
                        f"[DQN] Model at {self.model_path} has obs_dim={model_obs_dim} "
                        f"but current OBS_DIM={OBS_DIM} — skipping (needs retraining)"
                    )
                    self._model = None
                    self._is_trained = False
                    return False
                self._model = model
                self._is_trained = True
                print(f"[DQN] Model loaded from {self.model_path}")
                return True
            except Exception as e:
                print(f"[DQN] Model load failed: {e}")
                self._model = None
                self._is_trained = False
                return False
        print(f"[DQN] No trained model found at {self.model_path}")
        return False

    def _save_history(self):
        """Save training history to JSON."""
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self._training_history, f, indent=2, ensure_ascii=False)

    def load_history(self) -> list:
        """Load training history from JSON."""
        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def get_q_values(self, observation: np.ndarray) -> np.ndarray:
        """Get Q-values for all actions given observation."""
        if self._model is None:
            self.load()
        if self._model is None:
            return np.zeros(6, dtype=np.float32)

        obs = torch.as_tensor(observation, dtype=torch.float32)
        if obs.ndim == 1:
            obs = obs.unsqueeze(0)
        with torch.no_grad():
            q = self._model.q_net(obs)
        return q.squeeze().numpy()

    def get_statistics(self) -> dict:
        """Get agent statistics for reporting."""
        history = self.load_history()
        return {
            "is_trained": self.is_trained(),
            "model_path": self.model_path if os.path.exists(self.model_path) else None,
            "training_runs": len(history),
            "total_timesteps": sum(h.get("timesteps", 0) for h in history),
            "last_run": history[-1] if history else None,
            "device": self.device,
            "algorithm": "DQN (stable_baselines3)",
            "policy_arch": "[128, 64] ReLU",
            "action_space": "Discrete(6) - 3 intercept strategies x 2 dispersal options",
            "observation_dim": 182,
            "observation_layout": "22 bases x 5 feats + 12 global + 10 threats x 6 feats (EW/Cyber/Weather/PerThreat)",
        }
