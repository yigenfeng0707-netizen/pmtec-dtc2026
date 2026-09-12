#!/usr/bin/env python3
"""
Batch Training Script for PMTEC Multi-Agent RL (P8-v3).

Solves the 600s timeout problem: run this script multiple times to
accumulate training steps. Each invocation loads existing models and
continues training (incremental checkpoint/resume).

Usage:
    python deep_rl/train_batch.py --algo iql --steps 3000
    python deep_rl/train_batch.py --algo maddpg --steps 10000
    python deep_rl/train_batch.py --algo both --steps 3000

Run multiple times to accumulate 50K+ steps from a 10K baseline.
The script tracks total accumulated steps in model metadata.

Environment: pmtec-xpu (D:/miniconda3/envs/pmtec-xpu/python.exe)
"""

import argparse
import json
import os
import sys
import time

# Setup paths
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from deep_rl.dqn_agent import detect_best_device
from deep_rl.maddpg_agent import MADDPGAgent
from deep_rl.multi_agent_dqn import MultiAgentDQN
from deep_rl.pmtec_env import OBS_DIM, PMTECEnv

_MODEL_DIR = os.path.join(_PROJECT_ROOT, "data", "models")


def get_accumulated_steps(algo: str) -> int:
    """Read accumulated steps from metadata files."""
    if algo == "iql":
        meta_file = os.path.join(_MODEL_DIR, "pmtec_iql_intercept.metadata.json")
    else:
        meta_file = os.path.join(_MODEL_DIR, "pmtec_maddpg_intercept.metadata.json")

    if os.path.exists(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            return meta.get("timesteps", 0)
        except Exception:
            pass
    return 0


def train_iql_batch(steps: int) -> dict:
    """Train IQL for a batch of steps, resuming from existing models."""
    device = detect_best_device()
    accumulated_before = get_accumulated_steps("iql")
    print(f"\n{'=' * 60}")
    print(f"IQL Batch Training: {steps} steps")
    print(f"Device: {device}, OBS_DIM: {OBS_DIM}")
    print(f"Accumulated steps before: {accumulated_before}")
    print(f"Target after this batch: {accumulated_before + steps}")
    print(f"{'=' * 60}\n")

    iql = MultiAgentDQN(device=device)

    # Resume from existing models
    t0 = time.time()
    result = iql.train(total_timesteps=steps, resume=True)
    elapsed = time.time() - t0

    print(f"\nIQL batch done in {elapsed:.1f}s")
    print(f"Result: {result}")

    # Inference verification
    env = PMTECEnv()
    obs, _ = env.reset()
    ai = iql.predict(obs, agent_id="intercept")
    ad = iql.predict(obs, agent_id="dispersal")
    print(f"Inference: intercept={ai}, dispersal={ad}")

    new_total = accumulated_before + steps
    return {
        "algo": "IQL",
        "batch_steps": steps,
        "accumulated_before": accumulated_before,
        "accumulated_after": new_total,
        "elapsed_sec": round(elapsed, 1),
        "device": str(device),
        "inference": {"intercept": int(ai), "dispersal": int(ad)},
        "result": str(result)[:500],
    }


def train_maddpg_batch(steps: int) -> dict:
    """Train MADDPG for a batch of steps, resuming from existing models."""
    device = detect_best_device()
    accumulated_before = get_accumulated_steps("maddpg")
    print(f"\n{'=' * 60}")
    print(f"MADDPG Batch Training: {steps} steps")
    print(f"Device: {device}, OBS_DIM: {OBS_DIM}")
    print(f"Accumulated steps before: {accumulated_before}")
    print(f"Target after this batch: {accumulated_before + steps}")
    print(f"{'=' * 60}\n")

    maddpg = MADDPGAgent(device=device)

    # Load existing models for warm start
    maddpg.load()

    t0 = time.time()
    result = maddpg.train(total_timesteps=steps)
    elapsed = time.time() - t0

    print(f"\nMADDPG batch done in {elapsed:.1f}s")
    print(f"Result: {result}")

    # Inference verification
    env = PMTECEnv()
    obs, _ = env.reset()
    am = maddpg.predict(obs, agent_id="intercept")
    ad = maddpg.predict(obs, agent_id="dispersal")
    print(f"Inference: intercept={am}, dispersal={ad}")

    new_total = accumulated_before + steps
    return {
        "algo": "MADDPG",
        "batch_steps": steps,
        "accumulated_before": accumulated_before,
        "accumulated_after": new_total,
        "elapsed_sec": round(elapsed, 1),
        "device": str(device),
        "inference": {"intercept": int(am), "dispersal": int(ad)},
        "result": str(result)[:500],
    }


def update_metadata(algo: str, batch_result: dict):
    """Update model metadata after batch training."""
    try:
        from model_metadata import ModelMetadataManager

        mgr = ModelMetadataManager()

        if algo == "iql":
            files = [
                ("pmtec_iql_intercept.zip", "intercept"),
                ("pmtec_iql_dispersal.zip", "dispersal"),
            ]
        else:
            files = [
                ("pmtec_maddpg_intercept.pt", "intercept"),
                ("pmtec_maddpg_dispersal.pt", "dispersal"),
            ]

        new_total = batch_result["accumulated_after"]

        for filename, role in files:
            mgr.write(
                filename,
                {
                    "algorithm": batch_result["algo"],
                    "role": role,
                    "timesteps": new_total,
                    "obs_dim": OBS_DIM,
                    "n_actions": 3,
                    "device": batch_result["device"],
                    "training_time_sec": batch_result["elapsed_sec"],
                    "notes": (
                        f"P8-v3 batch training: +{batch_result['batch_steps']} steps "
                        f"(total {new_total}, incremental resume)"
                    ),
                    "inference": str(batch_result["inference"]),
                },
            )
            print(f"Metadata updated: {filename} (timesteps={new_total})")

    except Exception as e:
        print(f"Metadata update failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="PMTEC Batch Training")
    parser.add_argument(
        "--algo",
        choices=["iql", "maddpg", "both"],
        default="both",
        help="Algorithm to train",
    )
    parser.add_argument(
        "--steps", type=int, default=3000, help="Steps per batch (default: 3000)"
    )
    args = parser.parse_args()

    results = {}

    if args.algo in ("iql", "both"):
        r = train_iql_batch(args.steps)
        results["iql"] = r
        update_metadata("iql", r)

    if args.algo in ("maddpg", "both"):
        r = train_maddpg_batch(args.steps)
        results["maddpg"] = r
        update_metadata("maddpg", r)

    # Save batch summary
    summary = {
        "timestamp": time.time(),
        "batch_steps": args.steps,
        "results": results,
    }
    summary_path = os.path.join(_MODEL_DIR, "batch_training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nBatch summary saved to {summary_path}")

    # Print accumulated totals
    if args.algo in ("iql", "both"):
        total_iql = get_accumulated_steps("iql")
        print(f"IQL total accumulated: {total_iql} steps")
    if args.algo in ("maddpg", "both"):
        total_maddpg = get_accumulated_steps("maddpg")
        print(f"MADDPG total accumulated: {total_maddpg} steps")


if __name__ == "__main__":
    main()
