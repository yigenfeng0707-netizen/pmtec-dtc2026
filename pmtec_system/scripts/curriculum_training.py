#!/usr/bin/env python3
"""
PMTEC P1 Curriculum Learning - Stealth Breakthrough Specialization

Trains a DQN model in 3 stages of increasing difficulty, starting from the
P6 baseline (pmtec_dqn_p6.zip, 182-dim, 200K steps), to specifically
improve intercept rates against stealth breakthrough attacks:

  Stage 1 (Foundation):  1-2 hypersonic, moderate weather, TTI 40-80s
  Stage 2 (Compounded):  2-3 hypersonic, heavy weather,  TTI 30-65s, +10% speed
  Stage 3 (Extreme):     2-4 hypersonic, extreme weather, TTI 20-60s, +20% speed

Each stage loads the previous stage's model for incremental training.
Final model is saved as pmtec_dqn_p7.zip.

Usage:
  python scripts/curriculum_training.py
  python scripts/curriculum_training.py --stage1-steps 60000 --stage2-steps 60000 --stage3-steps 80000
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass

import numpy as np
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env import DummyVecEnv
from torch import nn

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from deep_rl.dqn_agent import detect_best_device
from deep_rl.pmtec_env import (
    PMTECEnv,
)

# Model paths
_MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
_BASELINE_MODEL = os.path.join(_MODEL_DIR, "pmtec_dqn_p6.zip")
_STAGE1_MODEL = os.path.join(_MODEL_DIR, "pmtec_dqn_p7_v2_s1.zip")
_STAGE2_MODEL = os.path.join(_MODEL_DIR, "pmtec_dqn_p7_v2_s2.zip")
_FINAL_MODEL = os.path.join(_MODEL_DIR, "pmtec_dqn_p7_v2.zip")


# ============================================================
#  Stage Configurations
# ============================================================


@dataclass
class StageConfig:
    """Configuration for a curriculum learning stage."""

    name: str
    description: str
    n_threats_min: int
    n_threats_max: int
    weather_index: int  # 0=clear, 1=light, 2=moderate, 3=severe
    tti_min: float
    tti_max: float
    speed_multiplier: float
    ew_prob: float
    cyber_prob: float
    total_timesteps: int
    learning_rate: float
    exploration_final_eps: float
    buffer_size: int


STAGES = [
    # Stage 1: Foundation - Learn to intercept hypersonic threats
    StageConfig(
        name="stage1_foundation",
        description="Foundation: 1-2 hypersonic missiles, moderate weather, TTI 40-80s",
        n_threats_min=1,
        n_threats_max=2,
        weather_index=1,  # light weather
        tti_min=40.0,
        tti_max=80.0,
        speed_multiplier=1.0,
        ew_prob=0.05,
        cyber_prob=0.05,
        total_timesteps=60000,
        learning_rate=5e-5,  # lower LR for fine-tuning
        exploration_final_eps=0.08,
        buffer_size=20000,
    ),
    # Stage 2: Compounded - Add weather degradation + faster threats
    StageConfig(
        name="stage2_compounded",
        description="Compounded: 2-3 hypersonic, heavy weather, TTI 30-65s, +10% speed",
        n_threats_min=2,
        n_threats_max=3,
        weather_index=2,  # moderate weather
        tti_min=30.0,
        tti_max=65.0,
        speed_multiplier=1.1,
        ew_prob=0.10,
        cyber_prob=0.05,
        total_timesteps=60000,
        learning_rate=3e-5,
        exploration_final_eps=0.06,
        buffer_size=20000,
    ),
    # Stage 3: Extreme - Full stealth breakthrough conditions
    StageConfig(
        name="stage3_extreme",
        description="Extreme: 2-4 hypersonic, extreme weather, TTI 20-60s, +20% speed",
        n_threats_min=2,
        n_threats_max=4,
        weather_index=3,  # severe weather
        tti_min=20.0,
        tti_max=60.0,
        speed_multiplier=1.2,
        ew_prob=0.10,
        cyber_prob=0.05,
        total_timesteps=80000,
        learning_rate=2e-5,
        exploration_final_eps=0.05,
        buffer_size=30000,
    ),
]


# ============================================================
#  Curriculum Environment
# ============================================================


class CurriculumEnv(PMTECEnv):
    """PMTEC environment configured for a specific curriculum stage.

    Overrides threat spawning and weather to match the stealth-breakthrough
    scenario at the specified difficulty level.
    """

    def __init__(
        self,
        stage_config: StageConfig,
        duration: int = 120,
        seed: int = 42,
        randomize_seed: bool = True,
        political: bool = False,
    ):
        super().__init__(duration=duration, seed=seed, political=political)
        self._stage = stage_config
        self._randomize_seed = randomize_seed
        self._episode_counter = 0

    def reset(self, seed: int | None = None, options: dict | None = None):
        """Override reset to randomize seed per episode for diversity."""
        if self._randomize_seed and seed is None:
            # Use a different seed each episode to avoid overfitting
            self._episode_counter += 1
            seed = (self._episode_counter * 7919 + self.base_seed) % 100000
        return super().reset(seed=seed, options=options)

    def _roll_weather(self) -> dict:
        """Force weather condition based on stage config."""
        conditions = [
            {
                "detection_range_factor": 1.0,
                "visibility_factor": 1.0,
                "crosswind_component": 0.05,
            },
            {
                "detection_range_factor": 0.7,
                "visibility_factor": 0.7,
                "crosswind_component": 0.3,
            },
            {
                "detection_range_factor": 0.45,
                "visibility_factor": 0.4,
                "crosswind_component": 0.5,
            },
            {
                # P7-v2: raised from 0.3 to 0.5 (synced with pmtec_env.py)
                "detection_range_factor": 0.5,
                "visibility_factor": 0.35,
                "crosswind_component": 0.7,
            },
        ]
        return dict(conditions[self._stage.weather_index])

    def _spawn_threats(self):
        """Spawn threats matching the stage's stealth-breakthrough profile."""
        n_threats = self._rng.randint(
            self._stage.n_threats_min, self._stage.n_threats_max
        )
        for i in range(n_threats):
            target = self._rng.choice(self._bases)
            threat_type = "hypersonic"  # all hypersonic for stealth training
            base_speed = 5000
            speed = int(base_speed * self._stage.speed_multiplier)
            tti = self._rng.uniform(self._stage.tti_min, self._stage.tti_max)
            distance_km = min(speed * tti / 3600.0, 120.0)

            bearing = self._rng.uniform(0, 2 * math.pi)
            lat_offset = distance_km / 111.0 * math.cos(bearing)
            lon_offset = (
                distance_km
                / (111.0 * max(0.1, math.cos(math.radians(target["lat"]))))
                * math.sin(bearing)
            )
            self._missiles.append(
                {
                    "id": f"MSL-{self._asda_cycle}-{i}",
                    "target_base": target["id"],
                    "type": threat_type,
                    "speed_kmh": speed,
                    "lat": target["lat"] + lat_offset,
                    "lon": target["lon"] + lon_offset,
                    "status": "active",
                    "time_to_impact": tti,
                    "cep": self._rng.uniform(50, 300),
                    "intercepted": False,
                }
            )

        # EW threats (stage-dependent)
        if self._rng.random() < self._stage.ew_prob:
            target = self._rng.choice(self._bases)
            self._ew_threats.append(
                {
                    "id": f"EW-{self._asda_cycle}-{len(self._ew_threats)}",
                    "target_base": target["id"],
                    "jammer_lat": target["lat"] + self._rng.uniform(-5, 5),
                    "jammer_lon": target["lon"] + self._rng.uniform(-8, 8),
                    "jamming_power": self._rng.uniform(0.5, 0.9),
                    "status": "active",
                    "duration": self._rng.randint(2, 5),
                }
            )

        # Cyber threats (stage-dependent)
        if self._rng.random() < self._stage.cyber_prob:
            target = self._rng.choice(self._bases)
            self._cyber_threats.append(
                {
                    "id": f"CYB-{self._asda_cycle}-{len(self._cyber_threats)}",
                    "target_base": target["id"],
                    "phase": 0,
                    "effectiveness": 0.0,
                    "status": "active",
                    "duration": self._rng.randint(3, 6),
                }
            )


# ============================================================
#  Training Callback
# ============================================================


class CurriculumCallback(BaseCallback):
    """Logs training progress with intercept rate tracking."""

    def __init__(self, stage_name: str, log_interval: int = 50, verbose: int = 1):
        super().__init__(verbose)
        self.stage_name = stage_name
        self.log_interval = log_interval
        self.episode_rewards = []
        self.episode_intercept_rates = []
        self.episode_count = 0

    def _on_step(self):
        infos = self.locals.get("infos", [])
        dones = self.locals.get("dones", [])

        for i, done in enumerate(dones):
            if done:
                self.episode_count += 1
                info = infos[i] if i < len(infos) else {}
                if "intercept_rate" in info:
                    self.episode_intercept_rates.append(info["intercept_rate"])
                reward = (
                    self.locals.get("rewards", [0])[i]
                    if i < len(self.locals.get("rewards", [0]))
                    else 0
                )
                self.episode_rewards.append(reward)

        if self.n_calls % self.log_interval == 0 and self.episode_count > 0:
            recent = (
                self.episode_intercept_rates[-20:]
                if len(self.episode_intercept_rates) >= 20
                else self.episode_intercept_rates
            )
            avg_ir = np.mean(recent) if recent else 0.0
            avg_r = (
                np.mean(self.episode_rewards[-20:])
                if len(self.episode_rewards) >= 20
                else 0.0
            )
            print(
                f"  [{self.stage_name}] step={self.num_timesteps} "
                f"eps={self.episode_count} avg_reward={avg_r:.1f} "
                f"avg_intercept_rate={avg_ir:.1%}"
            )
        return True


# ============================================================
#  Training Functions
# ============================================================


def train_stage(
    stage: StageConfig,
    load_model_path: str,
    save_model_path: str,
    device: str = "auto",
) -> dict:
    """Train a single curriculum stage.

    Loads the previous model and continues training on the stage-specific env.
    """
    print(f"\n{'=' * 72}")
    print(f"  STAGE: {stage.name}")
    print(f"  {stage.description}")
    print(f"  Threats: {stage.n_threats_min}-{stage.n_threats_max} hypersonic")
    print(f"  Weather index: {stage.weather_index}")
    print(f"  TTI: {stage.tti_min}-{stage.tti_max}s")
    print(f"  Speed multiplier: {stage.speed_multiplier}")
    print(f"  Timesteps: {stage.total_timesteps}")
    print(f"  Learning rate: {stage.learning_rate}")
    print(f"  Load from: {load_model_path}")
    print(f"  Save to:   {save_model_path}")
    print(f"  Device: {device}")
    print(f"{'=' * 72}")

    # Create curriculum environment
    env = CurriculumEnv(stage_config=stage, duration=120, seed=42)
    vec_env = DummyVecEnv([lambda: env])

    # Policy architecture (same as P6 baseline)
    policy_kwargs = {
        "net_arch": [128, 64],
        "activation_fn": nn.ReLU,
    }

    # Load pre-trained model or create new one
    if os.path.exists(load_model_path):
        print(f"[Curriculum] Loading pre-trained model from {load_model_path}")
        model = DQN.load(
            load_model_path,
            env=vec_env,
            device=device,
            learning_rate=stage.learning_rate,
            buffer_size=stage.buffer_size,
            exploration_final_eps=stage.exploration_final_eps,
            exploration_fraction=0.2,  # shorter exploration for fine-tuning
        )
        print("[Curriculum] Model loaded successfully")
    else:
        print("[Curriculum] No pre-trained model found, creating new model")
        model = DQN(
            "MlpPolicy",
            vec_env,
            learning_rate=stage.learning_rate,
            buffer_size=stage.buffer_size,
            batch_size=64,
            gamma=0.95,
            exploration_fraction=0.2,
            exploration_initial_eps=0.5,
            exploration_final_eps=stage.exploration_final_eps,
            target_update_interval=500,
            train_freq=4,
            policy_kwargs=policy_kwargs,
            device=device,
            verbose=1,
        )

    # Train
    callback = CurriculumCallback(stage_name=stage.name)
    t0 = time.time()
    model.learn(
        total_timesteps=stage.total_timesteps,
        callback=callback,
        reset_num_timesteps=True,
        progress_bar=False,
    )
    elapsed = time.time() - t0

    # Save model
    model.save(save_model_path)
    print(f"\n[Curriculum] Stage {stage.name} complete in {elapsed:.1f}s")
    print(f"[Curriculum] Model saved: {save_model_path}")
    print(f"[Curriculum] Episodes: {callback.episode_count}")

    # Collect stage metrics
    recent_ir = (
        callback.episode_intercept_rates[-50:]
        if len(callback.episode_intercept_rates) >= 50
        else callback.episode_intercept_rates
    )
    recent_r = (
        callback.episode_rewards[-50:]
        if len(callback.episode_rewards) >= 50
        else callback.episode_rewards
    )

    metrics = {
        "stage": stage.name,
        "description": stage.description,
        "total_timesteps": stage.total_timesteps,
        "elapsed_seconds": round(elapsed, 1),
        "episodes": callback.episode_count,
        "avg_intercept_rate": round(float(np.mean(recent_ir)), 4) if recent_ir else 0.0,
        "std_intercept_rate": round(float(np.std(recent_ir)), 4) if recent_ir else 0.0,
        "avg_reward": round(float(np.mean(recent_r)), 2) if recent_r else 0.0,
        "std_reward": round(float(np.std(recent_r)), 2) if recent_r else 0.0,
        "learning_rate": stage.learning_rate,
        "exploration_final_eps": stage.exploration_final_eps,
        "device": device,
        "model_path": save_model_path,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(f"[Curriculum] Avg intercept rate: {metrics['avg_intercept_rate']:.1%}")
    print(f"[Curriculum] Avg reward: {metrics['avg_reward']:.1f}")

    return metrics


def evaluate_stage(model_path: str, n_episodes: int = 20) -> dict:
    """Quick evaluation of a model on the stealth-breakthrough scenario."""
    print(f"\n[Evaluation] Testing {model_path} on stealth-breakthrough...")

    # Use the extreme stage config for evaluation
    eval_stage = STAGES[-1]  # stage3 extreme
    env = CurriculumEnv(stage_config=eval_stage, duration=120, seed=999)

    if os.path.exists(model_path):
        model = DQN.load(model_path, device="cpu")
    else:
        print(f"[Evaluation] Model not found: {model_path}")
        return {"model_path": model_path, "error": "model not found"}

    intercept_rates = []
    rewards = []
    for ep in range(n_episodes):
        obs, info = env.reset(seed=999 + ep)
        done = False
        truncated = False
        ep_reward = 0.0
        while not done and not truncated:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)
            ep_reward += reward

        total_msl = len(env._missiles)
        intercepted = sum(1 for m in env._missiles if m["intercepted"])
        ir = intercepted / max(total_msl, 1)
        intercept_rates.append(ir)
        rewards.append(ep_reward)

    result = {
        "model_path": model_path,
        "n_episodes": n_episodes,
        "avg_intercept_rate": round(float(np.mean(intercept_rates)), 4),
        "std_intercept_rate": round(float(np.std(intercept_rates)), 4),
        "min_intercept_rate": round(float(min(intercept_rates)), 4),
        "max_intercept_rate": round(float(max(intercept_rates)), 4),
        "avg_reward": round(float(np.mean(rewards)), 2),
    }
    print(
        f"[Evaluation] Intercept rate: {result['avg_intercept_rate']:.1%} "
        f"(+/- {result['std_intercept_rate']:.1%})"
    )
    print(f"[Evaluation] Reward: {result['avg_reward']:.1f}")
    return result


# ============================================================
#  Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="PMTEC P1 Curriculum Learning - Stealth Breakthrough Training"
    )
    parser.add_argument(
        "--stage1-steps",
        type=int,
        default=60000,
        help="Timesteps for Stage 1 (default: 60000)",
    )
    parser.add_argument(
        "--stage2-steps",
        type=int,
        default=60000,
        help="Timesteps for Stage 2 (default: 60000)",
    )
    parser.add_argument(
        "--stage3-steps",
        type=int,
        default=80000,
        help="Timesteps for Stage 3 (default: 80000)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Compute device (auto/xpu:0/cuda:0/cpu)",
    )
    parser.add_argument(
        "--skip-stage1",
        action="store_true",
        help="Skip stage 1 (use existing s1 model)",
    )
    parser.add_argument(
        "--skip-stage2",
        action="store_true",
        help="Skip stage 2 (use existing s2 model)",
    )
    args = parser.parse_args()

    # Update stage timesteps
    STAGES[0].total_timesteps = args.stage1_steps
    STAGES[1].total_timesteps = args.stage2_steps
    STAGES[2].total_timesteps = args.stage3_steps

    # Detect device
    device = args.device
    if device == "auto":
        device = detect_best_device()
    print(f"[Curriculum] Using device: {device}")

    # Verify baseline model exists
    if not os.path.exists(_BASELINE_MODEL):
        print(f"[ERROR] Baseline model not found: {_BASELINE_MODEL}")
        print(
            "[ERROR] Please ensure pmtec_dqn_p6.zip exists before running curriculum training."
        )
        sys.exit(1)

    print(f"[Curriculum] Baseline model: {_BASELINE_MODEL}")
    print(f"[Curriculum] Final model will be saved to: {_FINAL_MODEL}")
    print(
        f"[Curriculum] Total timesteps: {args.stage1_steps + args.stage2_steps + args.stage3_steps}"
    )

    all_metrics = []
    all_evals = []

    # ---- Stage 1 ----
    if args.skip_stage1 and os.path.exists(_STAGE1_MODEL):
        print("[Curriculum] Skipping Stage 1 (using existing model)")
    else:
        metrics_1 = train_stage(
            STAGES[0],
            load_model_path=_BASELINE_MODEL,
            save_model_path=_STAGE1_MODEL,
            device=device,
        )
        all_metrics.append(metrics_1)
        eval_1 = evaluate_stage(_STAGE1_MODEL, n_episodes=20)
        all_evals.append(eval_1)

    # ---- Stage 2 ----
    if args.skip_stage2 and os.path.exists(_STAGE2_MODEL):
        print("[Curriculum] Skipping Stage 2 (using existing model)")
    else:
        metrics_2 = train_stage(
            STAGES[1],
            load_model_path=_STAGE1_MODEL,
            save_model_path=_STAGE2_MODEL,
            device=device,
        )
        all_metrics.append(metrics_2)
        eval_2 = evaluate_stage(_STAGE2_MODEL, n_episodes=20)
        all_evals.append(eval_2)

    # ---- Stage 3 (Final) ----
    metrics_3 = train_stage(
        STAGES[2],
        load_model_path=_STAGE2_MODEL,
        save_model_path=_FINAL_MODEL,
        device=device,
    )
    all_metrics.append(metrics_3)
    eval_3 = evaluate_stage(_FINAL_MODEL, n_episodes=30)
    all_evals.append(eval_3)

    # ---- Summary ----
    print("\n" + "=" * 72)
    print("CURRICULUM TRAINING SUMMARY")
    print("=" * 72)
    print(f"\n{'Stage':<28} {'Steps':>8} {'Time':>8} {'IR':>8} {'Reward':>8}")
    print("-" * 64)
    for m in all_metrics:
        print(
            f"{m['stage']:<28} {m['total_timesteps']:>8} "
            f"{m['elapsed_seconds']:>7.0f}s {m['avg_intercept_rate']:>8.1%} "
            f"{m['avg_reward']:>8.1f}"
        )
    print("-" * 64)

    print(f"\n{'Evaluation':<28} {'IR':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print("-" * 64)
    for e in all_evals:
        stage_name = os.path.basename(e["model_path"]).replace(".zip", "")
        print(
            f"{stage_name:<28} {e['avg_intercept_rate']:>8.1%} "
            f"{e['std_intercept_rate']:>8.1%} "
            f"{e['min_intercept_rate']:>8.1%} "
            f"{e['max_intercept_rate']:>8.1%}"
        )
    print("-" * 64)

    # Save training report
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "baseline_model": _BASELINE_MODEL,
        "final_model": _FINAL_MODEL,
        "device": device,
        "total_timesteps": args.stage1_steps + args.stage2_steps + args.stage3_steps,
        "stages": all_metrics,
        "evaluations": all_evals,
        "target_intercept_rate": 0.70,
        "baseline_stealth_ir": 0.537,  # from Monte Carlo P6 results
        "final_stealth_ir": all_evals[-1]["avg_intercept_rate"] if all_evals else 0.0,
        "improvement": round(all_evals[-1]["avg_intercept_rate"] - 0.537, 4)
        if all_evals
        else 0.0,
        "passes_target": all_evals[-1]["avg_intercept_rate"] >= 0.70
        if all_evals
        else False,
    }

    report_path = os.path.join(_MODEL_DIR, "curriculum_training_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nTraining report saved to: {report_path}")

    if report["passes_target"]:
        print(
            f"\n*** TARGET ACHIEVED: Stealth intercept rate "
            f"{report['final_stealth_ir']:.1%} >= 70% ***"
        )
    else:
        print(
            f"\n*** BELOW TARGET: Stealth intercept rate "
            f"{report['final_stealth_ir']:.1%} < 70% ***"
        )
        print(
            "*** Consider: more timesteps, reward shaping, or hyperparameter tuning ***"
        )

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
