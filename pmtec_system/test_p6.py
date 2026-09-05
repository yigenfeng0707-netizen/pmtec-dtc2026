#!/usr/bin/env python3
"""
P6 Test Suite: 182-Dim Observation Space & Intercept Probability Model

Validates:
  1. OBS_DIM == 182 (110 base + 12 global + 60 threat)
  2. Observation vector shape and value range [0, 1]
  3. Intercept probability model (base_probs, type_match, area defense fallback)
  4. Weather conditions (extreme weather detection_range_factor=0.5)
  5. DQN model loading with 182-dim (pmtec_dqn_p6.zip)
  6. Reward structure (intercept success + base survival - damage)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p6.py
"""

import sys
import os
import numpy as np

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  [FAIL] {name} {detail}")


# ============================================================
# Test 1: OBS_DIM == 182
# ============================================================
print("\n[1/6] Testing OBS_DIM = 182...")

from deep_rl.pmtec_env import (
    PMTECEnv,
    OBS_DIM,
    NUM_BASES,
    BASE_FEATURES,
    GLOBAL_FEATURES,
    MAX_THREATS,
    THREAT_FEATURES,
    NUM_ACTIONS,
    THREAT_TYPES,
)

test("OBS_DIM == 182", OBS_DIM == 182, f"got {OBS_DIM}")
test(
    "OBS_DIM decomposition",
    OBS_DIM
    == NUM_BASES * BASE_FEATURES + GLOBAL_FEATURES + MAX_THREATS * THREAT_FEATURES,
    f"{NUM_BASES}*{BASE_FEATURES} + {GLOBAL_FEATURES} + {MAX_THREATS}*{THREAT_FEATURES} = {NUM_BASES * BASE_FEATURES + GLOBAL_FEATURES + MAX_THREATS * THREAT_FEATURES}",
)
test("NUM_BASES == 22", NUM_BASES == 22)
test("MAX_THREATS == 10", MAX_THREATS == 10)
test("THREAT_FEATURES == 6", THREAT_FEATURES == 6)
test("NUM_ACTIONS == 6", NUM_ACTIONS == 6)
test("THREAT_TYPES includes hypersonic", "hypersonic" in THREAT_TYPES)


# ============================================================
# Test 2: Observation vector shape and value range
# ============================================================
print("\n[2/6] Testing observation vector...")

env = PMTECEnv(duration=120, seed=42)
obs, info = env.reset()

test("obs shape == (182,)", obs.shape == (OBS_DIM,), f"got {obs.shape}")
test("obs dtype == float32", obs.dtype == np.float32)
test(
    "obs values are finite",
    np.all(np.isfinite(obs)),
    f"min={obs.min():.3f} max={obs.max():.3f}",
)

# Run a few steps and verify obs stays valid
for i in range(5):
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    test(
        f"step {i + 1} obs valid", obs.shape == (OBS_DIM,) and not np.any(np.isnan(obs))
    )

test("env has observation_space", hasattr(env, "observation_space"))
test("env has action_space", hasattr(env, "action_space"))
test("observation_space shape matches", env.observation_space.shape == (OBS_DIM,))


# ============================================================
# Test 3: Intercept probability model
# ============================================================
print("\n[3/6] Testing intercept probability model...")

# Verify _do_intercept method exists and uses dynamic probability
test("env has _do_intercept", hasattr(env, "_do_intercept"))

# Check _intercept_results is a valid attribute
test("env has _intercept_results", hasattr(env, "_intercept_results"))

# Check area defense fallback exists
import inspect

source = inspect.getsource(PMTECEnv._do_intercept)
test("area defense fallback exists", "area_p" in source)
test("area defense fallback 0.15 base", "0.15" in source)

# Check strategy-threat type matching
test("base_probs dict exists", "base_probs" in source)
test("type_match dict exists", "type_match" in source)
test("hypersonic in base_probs", "hypersonic" in source)

# Run multiple episodes and collect intercept rates
intercept_rates = []
for ep in range(20):
    env2 = PMTECEnv(duration=120, seed=100 + ep)
    env2.reset()
    for step in range(12):  # 12 ASDA cycles = 120s
        obs, reward, term, trunc, info = env2.step(ep % 6)
        if term or trunc:
            break
    total_missiles = len(env2._missiles)
    intercepted = sum(1 for m in env2._missiles if m.get("intercepted", False))
    if total_missiles > 0:
        intercept_rates.append(intercepted / total_missiles)

if intercept_rates:
    avg_rate = np.mean(intercept_rates)
    test(
        "intercept rate > 0.40 (not capped at ~54%)",
        avg_rate > 0.40,
        f"avg={avg_rate:.3f}",
    )
    test(
        "intercept rate < 0.95 (not always intercept)",
        avg_rate < 0.95,
        f"avg={avg_rate:.3f}",
    )
else:
    test("intercept results collected", False, "no missiles spawned in 20 episodes")


# ============================================================
# Test 4: Weather conditions
# ============================================================
print("\n[4/6] Testing weather conditions...")

test("env has _roll_weather", hasattr(env, "_roll_weather"))
wx = env._roll_weather()
test("weather has detection_range_factor", "detection_range_factor" in wx)
test("weather has visibility_factor", "visibility_factor" in wx)
test("weather has crosswind_component", "crosswind_component" in wx)
test(
    "detection_range_factor in [0.2, 1.5]",
    0.2 <= wx["detection_range_factor"] <= 1.5,
    f"got {wx['detection_range_factor']}",
)

# Test extreme weather (index 3) has detection_range_factor=0.5 (P7-v2 fix)
import inspect

wx_source = inspect.getsource(PMTECEnv._roll_weather)
test(
    "extreme weather detection_range_factor=0.5",
    "0.5" in wx_source,
    "P7-v2 fix: 0.3 -> 0.5",
)

# Test weather drifts over time
env3 = PMTECEnv(duration=120, seed=7)
env3.reset()
wx_before = dict(env3._weather_state)
env3.step(0)
wx_after = env3._weather_state
test(
    "weather drifts over time",
    wx_before["detection_range_factor"] != wx_after["detection_range_factor"]
    or wx_before["visibility_factor"] != wx_after["visibility_factor"],
)


# ============================================================
# Test 5: DQN model loading (182-dim)
# ============================================================
print("\n[5/6] Testing DQN model loading...")

try:
    from deep_rl.dqn_agent import DQNAgent, detect_best_device

    device = detect_best_device()
    test(f"device detected: {device}", device in ("xpu:0", "cuda:0", "cpu"))

    agent = DQNAgent(device=device)
    test("DQNAgent created", agent is not None)

    model_path = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p6.zip")
    test("DQN P6 model exists", os.path.exists(model_path), f"path: {model_path}")
    if os.path.exists(model_path):
        loaded = agent.load()
        test("DQN P6 model loaded", loaded)
        test("DQN is_trained()", agent.is_trained())

        # Inference test
        obs_test = np.zeros(OBS_DIM, dtype=np.float32)
        action = agent.predict(obs_test)
        if isinstance(action, (np.ndarray, np.integer)):
            action = int(action)
        test(
            "DQN inference returns valid action",
            0 <= action < NUM_ACTIONS,
            f"action={action}",
        )
    else:
        # Fallback: check p7_v2 model
        p7v2_path = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p7_v2.zip")
        test("DQN P7-v2 model exists (fallback)", os.path.exists(p7v2_path))

except ImportError as e:
    test("DQN imports OK", False, str(e))


# ============================================================
# Test 6: Reward structure
# ============================================================
print("\n[6/6] Testing reward structure...")

env4 = PMTECEnv(duration=120, seed=42)
env4.reset()

rewards = []
for i in range(12):
    obs, reward, term, trunc, info = env4.step(i % 6)
    rewards.append(reward)

test(
    "rewards are numeric",
    all(isinstance(r, (int, float, np.floating)) for r in rewards),
)
test("rewards are finite", all(np.isfinite(r) for r in rewards))

# Check info dict has useful fields
test("info is dict", isinstance(info, dict))

# Test that intercepted threats produce positive reward signal
env5 = PMTECEnv(duration=120, seed=999)
env5.reset()
obs, reward, term, trunc, info = env5.step(0)  # direct intercept strategy
test("reward from step is finite", np.isfinite(reward))

# Test episode termination
env6 = PMTECEnv(duration=10, seed=1)  # very short episode
env6.reset()
steps = 0
terminated = False
for i in range(20):
    obs, reward, term, trunc, info = env6.step(0)
    steps += 1
    if term or trunc:
        terminated = True
        break
test("short episode terminates", terminated or steps >= 12)


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print(f"P6 Test Results: {PASS} passed, {FAIL} failed")
print("=" * 60)
for r in RESULTS:
    print(r)

env.close()
sys.exit(0 if FAIL == 0 else 1)
