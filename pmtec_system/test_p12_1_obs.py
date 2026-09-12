#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P12-1/P12-2 Test Suite: Observation Space Expansion (political access features)

Validates:
  1. Backward compatibility: default PMTECEnv keeps the 182-dim observation
     (existing DQN/MADDPG/IQL models remain loadable)
  2. political=True: obs dim = 182 + N_ally + 1 (per-site capacity + escalation)
  3. Political dynamics: obs political slice evolves across ASDA cycles
     (grey-zone events driven by missile activity, escalation accumulates)
  4. Multi-agent wrapper pass-through (MultiAgentPMTECEnv political=True)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p12_1_obs.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import numpy as np  # noqa: E402

PASS, FAIL = 0, 0


def test(name, condition, detail=""):
    global PASS, FAIL
    tag = "PASS" if condition else "FAIL"
    print(f"  [{tag}] {name}" + (f" | {detail}" if detail else ""))
    PASS += int(bool(condition))
    FAIL += int(not condition)


# ============================================================
# 1) 后向兼容：默认 182 维不变
# ============================================================
print("\n[1/4] 默认环境后向兼容（182 维观测不变）...")
from deep_rl.pmtec_env import PMTECEnv, OBS_DIM  # noqa: E402

env0 = PMTECEnv(duration=60, seed=42)
obs0, _ = env0.reset(seed=42)
test("默认观测维度 = 182", obs0.shape == (OBS_DIM,), f"(实际 {obs0.shape})")
test("默认 observation_space = 182",
     env0.observation_space.shape == (OBS_DIM,))
test("默认无政治模型", env0._political_model is None)

# ============================================================
# 2) political=True 扩维
# ============================================================
print("\n[2/4] 政治观测扩维（political=True）...")
env = PMTECEnv(duration=120, seed=42, political=True)
obs, info = env.reset(seed=42)

n_ally = len(env._political_ally_ids)
expected = OBS_DIM + n_ally + 1
test("盟友站点数 > 0", n_ally > 0, f"({n_ally} 个盟友站点)")
test(f"扩维观测维度 = 182 + {n_ally} + 1 = {expected}",
     obs.shape == (expected,), f"(实际 {obs.shape})")
test("observation_space 同步扩维",
     env.observation_space.shape == (expected,))
test("扩维观测值无 NaN/Inf", bool(np.isfinite(obs).all()),
     f"(min={obs.min():.3f}, max={obs.max():.3f})")
# 注: political=True 在 reset 时扰动盟友基线并消耗 RNG 流, 主干 182 维
# 与默认模式为同分布但不同抽样, 故仅做均值级一致性校验
test("182 维主干均值与默认模式无系统性偏移",
     abs(obs[:OBS_DIM].mean() - obs0.mean()) < 0.5,
     f"({obs[:OBS_DIM].mean():.3f} vs {obs0.mean():.3f})")

# 政治切片取值范围
pol_slice = obs[OBS_DIM:]
test("盟友容量因子 ∈ [0,1]",
     bool(((pol_slice[:-1] >= 0.0) & (pol_slice[:-1] <= 1.0)).all()))
test("升级度 ∈ [0,1]", 0.0 <= pol_slice[-1] <= 1.0, f"{pol_slice[-1]:.3f}")

# ============================================================
# 3) 政治动力学：观测随 ASDA 周期演化
# ============================================================
print("\n[3/4] 政治动力学演化（灰色地带事件 + 升级累积）...")
slices = []
threat_counts = []
for i in range(30):
    obs, r, term, trunc, info = env.step(env.action_space.sample())
    if term or trunc:
        obs, info = env.reset()
    slices.append(obs[OBS_DIM:].copy())
    threat_counts.append(sum(1 for m in env._missiles if m["status"] == "active"))

arr = np.stack(slices)  # (30, n_ally+1)
esc_series = arr[:, -1]
print(f"    升级度序列: {esc_series[0]:.3f} -> {esc_series[-1]:.3f} "
      f"(max {esc_series.max():.3f})")
print(f"    威胁数峰值: {max(threat_counts)} (升级驱动的额外波次已启用)")
test("升级度随周期演化（观测非恒定）",
     float(esc_series.max() - esc_series.min()) > 0.005,
     f"range={esc_series.max() - esc_series.min():.3f}")
test("盟友容量因子出现降级（<1.0）",
     bool((arr[:, :-1] < 0.999).any()),
     f"(最低 {arr[:, :-1].min():.3f})")
test("全部步骤观测有限", bool(np.isfinite(arr).all()))

# ============================================================
# 4) 多智能体包装透传
# ============================================================
print("\n[4/4] 多智能体包装透传（MultiAgentPMTECEnv）...")
from deep_rl.multi_agent_env import MultiAgentPMTECEnv  # noqa: E402

ma_env = MultiAgentPMTECEnv(duration=60, seed=42, political=True)
ma_obs, ma_info = ma_env.reset(seed=42)
first_agent = next(iter(ma_obs))
ma_shape = ma_obs[first_agent].shape
test("多智能体共享观测同步扩维",
     ma_shape == (expected,) and ma_env.observation_space.shape == (expected,),
     f"(实际 {ma_shape})")
action = {a: ma_env.action_space[a].sample() for a in ma_env.action_space.spaces}
ma_obs2, ma_rew, ma_done, ma_trunc, ma_info = ma_env.step(action)
test("多智能体 step 正常", bool(np.isfinite(ma_obs2[first_agent]).all()))

ma_env0 = MultiAgentPMTECEnv(duration=60, seed=42)
ma_obs0, _ = ma_env0.reset(seed=42)
test("多智能体默认仍为 182 维（后向兼容）",
     next(iter(ma_obs0.values())).shape == (OBS_DIM,))

# ============================================================
# 汇总
# ============================================================
print("\n" + "=" * 56)
print(f"P12-1/P12-2 测试: {PASS} 通过 / {FAIL} 失败")
if FAIL:
    sys.exit(1)
print("P12-2 观测空间扩维达成：182 维默认不变 + 政治观测可选扩维 ✓")
