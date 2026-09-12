#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PMTEC P12.2: DQN Retraining with Political Access Observation (219-dim)

Extends the P7 stealth-breakthrough curriculum (scripts/curriculum_training.py)
with the P12-2 political observation expansion:

  182-dim (legacy)  ->  182 + N_ally + 1 = 219-dim (political=True)
    + 36 dims: per-ally-site access capacity factor (Full=1.0/Restricted/Denied=0.0)
    + 1 dim:   global conflict escalation level

Political dynamics per ASDA cycle: grey-zone provocation probability scales with
escalation (RAND adversary divergence strategy); escalation drives extra threat
waves; per-episode baseline perturbation models access uncertainty.

Since the 219-dim observation is incompatible with the 182-dim P6/P7 weights,
training starts from a FRESH network and chains stages s1 -> s2 -> s3.

Usage:
  python scripts/retrain_dqn_219.py                  # full 3-stage curriculum
  python scripts/retrain_dqn_219.py --stage1-steps 60000 --stage2-steps 60000 --stage3-steps 80000
  python scripts/retrain_dqn_219.py --quick          # smoke verification (~5K steps)
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import torch.nn as nn
from stable_baselines3 import DQN
from stable_baselines3.common.vec_env import DummyVecEnv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Same-directory module import (script lives in scripts/)
from curriculum_training import STAGES, CurriculumEnv, CurriculumCallback  # noqa: E402
from deep_rl.dqn_agent import detect_best_device  # noqa: E402

_MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
_SUMMARY_PATH = os.path.join(_MODEL_DIR, "pmtec_dqn_p12_training.json")


def train_stage_219(
    stage,
    load_model_path,
    save_model_path,
    device="auto",
):
    """Train one curriculum stage on the 219-dim political observation env.

    Stage 1 must start fresh (182-dim P6/P7 weights are incompatible).
    Later stages chain-load the previous stage's 219-dim checkpoint.
    """
    print(f"\n{'=' * 72}")
    print(f"  STAGE: {stage.name}")
    print(f"  {stage.description}")
    print(f"  Threats: {stage.n_threats_min}-{stage.n_threats_max} hypersonic | "
          f"weather={stage.weather_index} | TTI {stage.tti_min}-{stage.tti_max}s")
    print(f"  Steps: {stage.total_timesteps} | LR {stage.learning_rate} | "
          f"eps_final {stage.exploration_final_eps}")
    print(f"  Load: {load_model_path or '(fresh 219-dim network)'}")
    print(f"  Save: {save_model_path}")
    print(f"  Device: {device}")
    print(f"{'=' * 72}")

    env = CurriculumEnv(stage_config=stage, duration=120, seed=42, political=True)
    obs, _ = env.reset(seed=42)
    obs_dim = env.observation_space.shape[0]
    print(f"[P12] Political observation dim = {obs_dim} "
          f"({36 if obs_dim == 219 else obs_dim - 183} ally dims + escalation)")
    vec_env = DummyVecEnv([lambda: env])

    policy_kwargs = {"net_arch": [128, 64], "activation_fn": nn.ReLU}

    if load_model_path and os.path.exists(load_model_path):
        print(f"[P12] Loading previous 219-dim checkpoint: {load_model_path}")
        model = DQN.load(
            load_model_path,
            env=vec_env,
            device=device,
            learning_rate=stage.learning_rate,
            buffer_size=stage.buffer_size,
            exploration_final_eps=stage.exploration_final_eps,
            exploration_fraction=0.2,
        )
    else:
        # Fresh network: longer exploration for the new observation space
        print("[P12] Creating fresh 219-dim DQN network")
        model = DQN(
            "MlpPolicy",
            vec_env,
            learning_rate=stage.learning_rate,
            buffer_size=stage.buffer_size,
            batch_size=64,
            gamma=0.95,
            exploration_fraction=0.3,
            exploration_initial_eps=1.0,
            exploration_final_eps=stage.exploration_final_eps,
            target_update_interval=500,
            train_freq=4,
            policy_kwargs=policy_kwargs,
            device=device,
            verbose=1,
        )

    callback = CurriculumCallback(stage_name=stage.name)
    t0 = time.time()
    model.learn(
        total_timesteps=stage.total_timesteps,
        callback=callback,
        reset_num_timesteps=True,
    )
    elapsed = time.time() - t0

    model.save(save_model_path)
    print(f"[P12] Stage saved: {save_model_path} ({elapsed:.0f}s)")

    ep_ir = callback.episode_intercept_rates
    return {
        "stage": stage.name,
        "steps": stage.total_timesteps,
        "obs_dim": obs_dim,
        "elapsed_seconds": round(elapsed, 1),
        "episodes": callback.episode_count,
        "avg_intercept_rate_last20": (
            round(float(np.mean(ep_ir[-20:])), 4) if ep_ir else None
        ),
        "avg_reward_last20": (
            round(float(np.mean(callback.episode_rewards[-20:])), 2)
            if callback.episode_rewards else None
        ),
        "model_path": save_model_path,
    }


def main():
    parser = argparse.ArgumentParser(
        description="P12.2 DQN retraining (219-dim political observation)"
    )
    parser.add_argument("--stage1-steps", type=int, default=None)
    parser.add_argument("--stage2-steps", type=int, default=None)
    parser.add_argument("--stage3-steps", type=int, default=None)
    parser.add_argument(
        "--tag", type=str, default="p12",
        help="Model tag: pmtec_dqn_<tag>_s1/s2.zip + pmtec_dqn_<tag>.zip",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Smoke verification with tiny step counts",
    )
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    steps = [
        args.stage1_steps or (2000 if args.quick else STAGES[0].total_timesteps),
        args.stage2_steps or (1500 if args.quick else STAGES[1].total_timesteps),
        args.stage3_steps or (1500 if args.quick else STAGES[2].total_timesteps),
    ]
    for stage, n in zip(STAGES, steps):
        stage.total_timesteps = n

    device = args.device if args.device != "auto" else detect_best_device()
    s1 = os.path.join(_MODEL_DIR, f"pmtec_dqn_{args.tag}_s1.zip")
    s2 = os.path.join(_MODEL_DIR, f"pmtec_dqn_{args.tag}_s2.zip")
    final = os.path.join(_MODEL_DIR, f"pmtec_dqn_{args.tag}.zip")

    print("=" * 72)
    print("PMTEC P12.2 DQN Retraining - Political Access Observation (219-dim)")
    print("=" * 72)
    print(f"Device: {device} | Tag: {args.tag} | Steps: {steps}")

    results = []
    t0 = time.time()
    results.append(train_stage_219(STAGES[0], None, s1, device))
    results.append(train_stage_219(STAGES[1], s1, s2, device))
    results.append(train_stage_219(STAGES[2], s2, final, device))

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tag": args.tag,
        "obs_dim": 219,
        "political": True,
        "device": device,
        "total_elapsed_seconds": round(time.time() - t0, 1),
        "stages": results,
        "final_model": final,
    }
    with open(_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 72)
    print("P12.2 TRAINING COMPLETE")
    print("=" * 72)
    for r in results:
        ir = r.get("avg_intercept_rate_last20")
        ir_str = f"{ir:.1%}" if ir is not None else "n/a"
        print(f"  {r['stage']}: {r['steps']} steps | "
              f"avg_IR(last20)={ir_str} | {r['elapsed_seconds']}s")
    print(f"Final model: {final}")
    print(f"Summary: {_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
