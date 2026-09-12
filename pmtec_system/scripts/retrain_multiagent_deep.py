#!/usr/bin/env python3
"""
Multi-Agent Deep Training Script - P8-v2

Extends IQL and MADDPG training from 6K to 50K steps.
Uses XPU acceleration, saves models with metadata.

Run: D:/miniconda3/envs/pmtec-xpu/python.exe scripts/retrain_multiagent_deep.py
"""

import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from deep_rl.dqn_agent import detect_best_device
from deep_rl.maddpg_agent import MADDPGAgent
from deep_rl.multi_agent_dqn import MultiAgentDQN
from deep_rl.multi_agent_env import MultiAgentPMTECEnv
from deep_rl.pmtec_env import OBS_DIM

# Add model_metadata for versioning
sys.path.insert(0, PROJECT_ROOT)
from model_metadata import ModelMetadataManager

TOTAL_STEPS = 50000  # 50K steps (up from 6K)
SEED = 42


def train_iql(device: str) -> dict:
    """Train IQL agents for 50K steps."""
    print(f"\n{'=' * 60}")
    print(f"[IQL] Starting 50K-step training on {device}")
    print(f"{'=' * 60}")

    ma_env = MultiAgentPMTECEnv(duration=120, seed=SEED)
    iql = MultiAgentDQN(device=device)

    t0 = time.time()
    result = iql.train(total_timesteps=TOTAL_STEPS, ma_env=ma_env)
    elapsed = time.time() - t0

    # Inference verification
    obs = ma_env.reset(seed=SEED)
    if isinstance(obs, tuple):
        obs = obs[0]
    intercept_obs = (
        obs.get("intercept", list(obs.values())[0]) if isinstance(obs, dict) else obs
    )
    action_i = iql.predict(intercept_obs, agent_id="intercept")
    action_d = iql.predict(intercept_obs, agent_id="dispersal")

    print(f"\n[IQL] Training complete in {elapsed:.1f}s")
    print(f"[IQL] Inference: intercept={action_i}, dispersal={action_d}")

    # Write metadata
    mgr = ModelMetadataManager()
    for model_file, role in [
        ("pmtec_iql_intercept.zip", "intercept"),
        ("pmtec_iql_dispersal.zip", "dispersal"),
    ]:
        mgr.write(
            model_file,
            {
                "algorithm": "IQL",
                "library": "stable_baselines3",
                "timesteps": TOTAL_STEPS,
                "obs_dim": OBS_DIM,
                "n_actions": 3,
                "agent_role": role,
                "policy_arch": [128, 64],
                "activation": "ReLU",
                "device": device,
                "elapsed_seconds": round(elapsed, 1),
                "avg_reward": result.get("avg_reward")
                if isinstance(result, dict)
                else None,
                "training_type": "deep_50k",
                "notes": "P8-v2 deep training (6K -> 50K).",
            },
        )

    return {
        "algorithm": "IQL",
        "timesteps": TOTAL_STEPS,
        "elapsed": elapsed,
        "intercept_action": action_i,
        "dispersal_action": action_d,
    }


def train_maddpg(device: str) -> dict:
    """Train MADDPG agents for 50K steps."""
    print(f"\n{'=' * 60}")
    print(f"[MADDPG] Starting 50K-step training on {device}")
    print(f"{'=' * 60}")

    ma_env = MultiAgentPMTECEnv(duration=120, seed=SEED)
    maddpg = MADDPGAgent(device=device)

    t0 = time.time()
    result = maddpg.train(total_timesteps=TOTAL_STEPS, ma_env=ma_env)
    elapsed = time.time() - t0

    # Inference verification
    obs = ma_env.reset(seed=SEED)
    if isinstance(obs, tuple):
        obs = obs[0]
    intercept_obs = (
        obs.get("intercept", list(obs.values())[0]) if isinstance(obs, dict) else obs
    )
    action_i = maddpg.predict(intercept_obs, agent_id="intercept")
    action_d = maddpg.predict(intercept_obs, agent_id="dispersal")

    print(f"\n[MADDPG] Training complete in {elapsed:.1f}s")
    print(f"[MADDPG] Inference: intercept={action_i}, dispersal={action_d}")

    # Write metadata
    mgr = ModelMetadataManager()
    for model_file, role in [
        ("pmtec_maddpg_intercept.pt", "intercept"),
        ("pmtec_maddpg_dispersal.pt", "dispersal"),
    ]:
        mgr.write(
            model_file,
            {
                "algorithm": "MADDPG",
                "library": "pytorch",
                "timesteps": TOTAL_STEPS,
                "obs_dim": OBS_DIM,
                "n_actions": 3,
                "agent_role": role,
                "architecture": "Actor-Critic (centralized critic)",
                "device": device,
                "elapsed_seconds": round(elapsed, 1),
                "avg_reward": result.get("avg_reward")
                if isinstance(result, dict)
                else None,
                "training_type": "deep_50k",
                "notes": "P8-v2 deep training (6K -> 50K).",
            },
        )

    return {
        "algorithm": "MADDPG",
        "timesteps": TOTAL_STEPS,
        "elapsed": elapsed,
        "intercept_action": action_i,
        "dispersal_action": action_d,
    }


if __name__ == "__main__":
    device = detect_best_device()
    print(f"\nDevice: {device}")
    print(f"OBS_DIM: {OBS_DIM}")
    print(f"Target: {TOTAL_STEPS} steps per algorithm")

    results = {}

    # Train IQL
    try:
        results["iql"] = train_iql(device)
    except Exception as e:
        print(f"[ERROR] IQL training failed: {e}")
        results["iql"] = {"error": str(e)}

    # Train MADDPG
    try:
        results["maddpg"] = train_maddpg(device)
    except Exception as e:
        print(f"[ERROR] MADDPG training failed: {e}")
        results["maddpg"] = {"error": str(e)}

    # Summary
    print(f"\n{'=' * 60}")
    print("Deep Training Summary")
    print(f"{'=' * 60}")
    for algo, res in results.items():
        if "error" in res:
            print(f"  {algo.upper()}: FAILED - {res['error']}")
        else:
            print(
                f"  {algo.upper()}: {res['timesteps']} steps in {res['elapsed']:.1f}s"
            )
            print(
                f"    Inference: intercept={res['intercept_action']}, dispersal={res['dispersal_action']}"
            )

    # Save summary
    summary_path = os.path.join(
        PROJECT_ROOT, "data", "models", "deep_training_summary.json"
    )
    results["timestamp"] = time.time()
    results["device"] = device
    results["total_steps"] = TOTAL_STEPS
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSummary saved: {summary_path}")
