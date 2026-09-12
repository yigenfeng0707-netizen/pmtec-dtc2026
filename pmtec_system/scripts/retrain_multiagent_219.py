#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P12.2/S: Multi-Agent 219-dim Retraining (political observation).

Retrains IQL + MADDPG on the 219-dim political observation (MultiAgentPMTECEnv
with political=True), saving to *_219 tagged filenames so the engine's 182-dim
demo path keeps working unchanged.

Mechanism (zero library changes):
  - Module-level OBS_DIM patched to the env's obs dim BEFORE agent construction
    (agents resolve deep_rl.*.OBS_DIM at __init__ time).
  - Subclasses override model-path properties to tag filenames with _219.

Run: D:/miniconda3/envs/pmtec-xpu/python.exe scripts/retrain_multiagent_219.py
     [--steps 6000]
"""

import argparse
import json
import os
import sys
import time

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from deep_rl.dqn_agent import detect_best_device  # noqa: E402
from deep_rl.multi_agent_env import MultiAgentPMTECEnv  # noqa: E402
import deep_rl.multi_agent_dqn as iql_mod  # noqa: E402
import deep_rl.maddpg_agent as maddpg_mod  # noqa: E402

MODEL_DIR = os.path.join(PROJECT_ROOT, "data", "models")
REPORT_PATH = os.path.join(MODEL_DIR, "p12_multiagent_retraining_report.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=6000)
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    print("=" * 70)
    print("PMTEC P12.2/S: Multi-Agent 219-dim Retraining (political obs)")
    print("=" * 70)

    device = detect_best_device()
    print(f"[S] Device: {device}")

    # ---- 219 维环境（political=True）----
    probe = MultiAgentPMTECEnv(duration=60, seed=42, political=True)
    obs0, _ = probe.reset(seed=42)
    obs_dim = probe.observation_space.shape[0]
    assert obs0[first_agent_key(probe)].shape[0] == obs_dim
    print(f"[S] Political obs dim = {obs_dim}")

    # ---- 模块级维度补丁（构造期解析）----
    iql_mod.OBS_DIM = obs_dim
    maddpg_mod.OBS_DIM = obs_dim

    # ---- 带标签的模型路径子类（不影响引擎的 182 维路径）----
    class IQL219(iql_mod.MultiAgentDQN):
        @property
        def intercept_model_path(self):
            return os.path.join(MODEL_DIR, "pmtec_iql_intercept_219.zip")

        @property
        def dispersal_model_path(self):
            return os.path.join(MODEL_DIR, "pmtec_iql_dispersal_219.zip")

        @property
        def history_path(self):
            return os.path.join(MODEL_DIR, "pmtec_iql_history_219.json")

    class MADDPG219(maddpg_mod.MADDPGAgent):
        @property
        def intercept_model_path(self):
            return os.path.join(MODEL_DIR, "pmtec_maddpg_intercept_219.pt")

        @property
        def dispersal_model_path(self):
            return os.path.join(MODEL_DIR, "pmtec_maddpg_dispersal_219.pt")

        @property
        def history_path(self):
            return os.path.join(MODEL_DIR, "pmtec_maddpg_history_219.json")

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": str(device),
        "obs_dim": obs_dim,
        "political": True,
        "steps_per_agent": args.steps,
        "iql": {},
        "maddpg": {},
    }

    # === 1. IQL (219-dim) ===
    print("\n" + "-" * 50)
    print("[1/2] IQL (Independent Q-Learning) 219-dim Retraining")
    print("-" * 50)
    iql_agent = IQL219(device=device)
    ma_env = MultiAgentPMTECEnv(duration=120, seed=42, political=True)
    t0 = time.time()
    iql_result = iql_agent.train(total_timesteps=args.steps, ma_env=ma_env)
    report["iql"] = iql_result
    report["iql"]["elapsed_seconds"] = round(time.time() - t0, 1)

    iql_verify = IQL219(device=device)
    loaded_ok = iql_verify.load()
    print(f"  IQL 219 load verification: {loaded_ok}")
    test_obs = np.random.rand(obs_dim).astype(np.float32)
    iql_actions = iql_verify.predict(test_obs)
    print(f"  IQL inference: {iql_actions}")
    report["iql"]["load_verification"] = bool(loaded_ok)

    # === 2. MADDPG (219-dim) ===
    print("\n" + "-" * 50)
    print("[2/2] MADDPG (Multi-Agent DDPG) 219-dim Retraining")
    print("-" * 50)
    maddpg_agent = MADDPG219(device=device)
    ma_env2 = MultiAgentPMTECEnv(duration=120, seed=42, political=True)
    t0 = time.time()
    maddpg_result = maddpg_agent.train(total_timesteps=args.steps, ma_env=ma_env2)
    report["maddpg"] = maddpg_result
    report["maddpg"]["elapsed_seconds"] = round(time.time() - t0, 1)

    maddpg_verify = MADDPG219(device=device)
    loaded_ok2 = maddpg_verify.load()
    print(f"  MADDPG 219 load verification: {loaded_ok2}")
    maddpg_actions = maddpg_verify.predict(test_obs)
    print(f"  MADDPG inference: {maddpg_actions}")
    report["maddpg"]["load_verification"] = bool(loaded_ok2)

    # === Summary ===
    print("\n" + "=" * 70)
    print("P12.2/S Multi-Agent 219-dim Retraining Complete")
    print("=" * 70)
    print(f"  IQL:    {report['iql']['elapsed_seconds']}s, avg_reward={iql_result.get('avg_reward', 'N/A')}")
    print(f"  MADDPG: {report['maddpg']['elapsed_seconds']}s, "
          f"avg_reward_last10={maddpg_result.get('avg_reward_last_10', 'N/A')}")
    print(f"  Models (tagged _219, engine 182-dim path untouched):")
    for f in ("pmtec_iql_intercept_219.zip", "pmtec_iql_dispersal_219.zip",
              "pmtec_maddpg_intercept_219.pt", "pmtec_maddpg_dispersal_219.pt"):
        p = os.path.join(MODEL_DIR, f)
        print(f"    {f}: {os.path.getsize(p) / 1024:.1f} KB" if os.path.exists(p)
              else f"    {f}: MISSING")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Report: {REPORT_PATH}")


def first_agent_key(env):
    return next(iter(env.observation_space.spaces)) if hasattr(
        env.observation_space, "spaces") else 0


if __name__ == "__main__":
    main()
