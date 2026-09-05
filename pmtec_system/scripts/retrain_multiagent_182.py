#!/usr/bin/env python3
"""
P8: Multi-Agent 182-dim Retraining Script.
Retrains both IQL and MADDPG with the current 182-dim observation space,
replacing old 122-dim models that get skipped on load.
"""

import os
import sys
import json
import time
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from deep_rl.dqn_agent import detect_best_device
from deep_rl.multi_agent_env import MultiAgentPMTECEnv
from deep_rl.multi_agent_dqn import MultiAgentDQN
from deep_rl.maddpg_agent import MADDPGAgent

MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
REPORT_PATH = os.path.join(MODEL_DIR, "p8_retraining_report.json")


def main():
    print("=" * 70)
    print("PMTEC P8: Multi-Agent 182-dim Retraining")
    print("=" * 70)

    device = detect_best_device()
    print(f"[P8] Device: {device}")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": str(device),
        "obs_dim": 182,
        "iql": {},
        "maddpg": {},
    }

    # === 1. IQL Retraining ===
    print("\n" + "-" * 50)
    print("[1/2] IQL (Independent Q-Learning) Retraining")
    print("-" * 50)

    # Delete old models so is_trained() returns False
    for path in [
        os.path.join(MODEL_DIR, "pmtec_iql_intercept.zip"),
        os.path.join(MODEL_DIR, "pmtec_iql_dispersal.zip"),
    ]:
        if os.path.exists(path):
            os.remove(path)
            print(f"  Deleted old model: {os.path.basename(path)}")

    iql_agent = MultiAgentDQN(device=device)
    print(f"  is_trained (pre): {iql_agent.is_trained()}")

    ma_env = MultiAgentPMTECEnv(duration=120, seed=42)
    t0 = time.time()
    iql_result = iql_agent.train(total_timesteps=6000, ma_env=ma_env)
    iql_elapsed = time.time() - t0
    report["iql"] = iql_result
    report["iql"]["elapsed_seconds"] = round(iql_elapsed, 1)

    # Verify IQL models load correctly
    iql_verify = MultiAgentDQN(device=device)
    loaded_ok = iql_verify.load()
    print(f"  IQL load verification: {loaded_ok}")
    assert loaded_ok, "IQL models failed to load after retraining!"

    # Quick sanity inference
    test_obs = np.random.rand(182).astype(np.float32)
    iql_actions = iql_verify.predict(test_obs)
    print(f"  IQL inference test: actions={iql_actions}")
    assert "intercept" in iql_actions and "dispersal" in iql_actions

    report["iql"]["load_verification"] = loaded_ok
    report["iql"]["inference_test"] = iql_actions

    # === 2. MADDPG Retraining ===
    print("\n" + "-" * 50)
    print("[2/2] MADDPG (Multi-Agent DDPG) Retraining")
    print("-" * 50)

    for path in [
        os.path.join(MODEL_DIR, "pmtec_maddpg_intercept.pt"),
        os.path.join(MODEL_DIR, "pmtec_maddpg_dispersal.pt"),
    ]:
        if os.path.exists(path):
            os.remove(path)
            print(f"  Deleted old model: {os.path.basename(path)}")

    maddpg_agent = MADDPGAgent(device=device)
    print(f"  is_trained (pre): {maddpg_agent.is_trained()}")

    ma_env2 = MultiAgentPMTECEnv(duration=120, seed=42)
    t0 = time.time()
    maddpg_result = maddpg_agent.train(total_timesteps=6000, ma_env=ma_env2)
    maddpg_elapsed = time.time() - t0
    report["maddpg"] = maddpg_result
    report["maddpg"]["elapsed_seconds"] = round(maddpg_elapsed, 1)

    # Verify MADDPG models load correctly
    maddpg_verify = MADDPGAgent(device=device)
    loaded_ok2 = maddpg_verify.load()
    print(f"  MADDPG load verification: {loaded_ok2}")
    assert loaded_ok2, "MADDPG models failed to load after retraining!"

    # Quick sanity inference
    maddpg_actions = maddpg_verify.predict(test_obs)
    print(f"  MADDPG inference test: actions={maddpg_actions}")
    assert "intercept" in maddpg_actions and "dispersal" in maddpg_actions

    report["maddpg"]["load_verification"] = loaded_ok2
    report["maddpg"]["inference_test"] = maddpg_actions

    # === Summary ===
    print("\n" + "=" * 70)
    print("P8 Retraining Complete")
    print("=" * 70)
    print(
        f"  IQL:    {iql_elapsed:.1f}s, 6000 steps, avg_reward={iql_result.get('avg_reward', 'N/A')}"
    )
    print(
        f"  MADDPG: {maddpg_elapsed:.1f}s, 6000 steps, avg_reward={maddpg_result.get('avg_reward_last_10', 'N/A')}"
    )
    print(f"  IQL models:    pmtec_iql_intercept.zip, pmtec_iql_dispersal.zip")
    print(f"  MADDPG models: pmtec_maddpg_intercept.pt, pmtec_maddpg_dispersal.pt")
    print(f"  All models now use OBS_DIM=182")

    # Check file sizes
    for f in [
        "pmtec_iql_intercept.zip",
        "pmtec_iql_dispersal.zip",
        "pmtec_maddpg_intercept.pt",
        "pmtec_maddpg_dispersal.pt",
    ]:
        path = os.path.join(MODEL_DIR, f)
        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            print(f"  {f}: {size_kb:.1f} KB")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
