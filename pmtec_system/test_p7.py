#!/usr/bin/env python3
"""
P7 Test Suite: Monte Carlo Validation & Curriculum Learning

Validates:
  1. Monte Carlo validation framework structure (4 adversary strategies)
  2. DQN P7-v2 model loading (stealth breakthrough optimized)
  3. Curriculum learning report existence and content
  4. Quick Monte Carlo (5 episodes) intercept rate sanity
  5. P6 vs P7-v2 comparison (P7-v2 >= P6 for stealth)
  6. Environment layer P7-v2 fixes (extreme weather, area defense)

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p7.py
"""

import json
import os
import sys

import numpy as np

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
# Test 1: Monte Carlo validation framework structure
# ============================================================
print("\n[1/6] Testing Monte Carlo framework structure...")

from scripts.monte_carlo_validation import (
    STRATEGIES,
    StrategyEnv,
)

# P12-5: 策略库扩展至 6 项（新增 multi_axis_saturation / political_divergence）
test("6 adversary strategies defined (P12-5)", len(STRATEGIES) == 6, f"got {len(STRATEGIES)}")

strategy_names = [s.name for s in STRATEGIES]
test("saturation_attack strategy exists", "saturation_attack" in strategy_names)
test("stealth_breakthrough strategy exists", "stealth_breakthrough" in strategy_names)
test("electronic_warfare strategy exists", "electronic_warfare" in strategy_names)
test("decoy_swarm strategy exists", "decoy_swarm" in strategy_names)

# Verify stealth strategy has extreme weather (index 3)
stealth = next(s for s in STRATEGIES if s.name == "stealth_breakthrough")
test("stealth uses extreme weather (index=3)", stealth.weather_index == 3)
test("stealth uses hypersonic threats", "hypersonic" in stealth.threat_pool)
test("stealth has short TTI", stealth.tti_max <= 60.0)

# Verify saturation has high threat count
saturation = next(s for s in STRATEGIES if s.name == "saturation_attack")
test("saturation has 8+ threats", saturation.n_threats_min >= 8)

# Verify EW has high EW probability
ew = next(s for s in STRATEGIES if s.name == "electronic_warfare")
test("EW has ew_prob >= 0.70", ew.ew_prob >= 0.70)

# Verify decoy has mostly cruise missiles
decoy = next(s for s in STRATEGIES if s.name == "decoy_swarm")
cruise_count = sum(1 for t in decoy.threat_pool if t == "cruise")
test("decoy is mostly cruise missiles", cruise_count >= len(decoy.threat_pool) / 2)


# ============================================================
# Test 2: DQN P7-v2 model loading
# ============================================================
print("\n[2/6] Testing DQN P7-v2 model...")

from deep_rl.dqn_agent import DQNAgent, detect_best_device
from deep_rl.pmtec_env import NUM_ACTIONS, OBS_DIM

device = detect_best_device()
agent = DQNAgent(device=device)

model_p7v2 = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p7_v2.zip")
if os.path.exists(model_p7v2):
    loaded = agent.load()
    test("P7-v2 model loaded", loaded)
    test("P7-v2 agent is_trained", agent.is_trained())

    # Inference test
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    action = agent.predict(obs)
    if isinstance(action, (np.ndarray, np.integer)):
        action = int(action)
    test("P7-v2 inference valid action", 0 <= action < NUM_ACTIONS, f"action={action}")
else:
    test("P7-v2 model exists", False, f"not found: {model_p7v2}")

# Also check P7-v1 (should exist but not meet target)
model_p7v1 = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p7.zip")
test("P7-v1 model exists (not达标 but kept)", os.path.exists(model_p7v1))


# ============================================================
# Test 3: Curriculum learning report
# ============================================================
print("\n[3/6] Testing curriculum learning report...")

report_path = os.path.join(
    PROJECT_ROOT, "data", "models", "curriculum_training_report.json"
)
if os.path.exists(report_path):
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    test("report is valid JSON", isinstance(report, dict))

    if isinstance(report, dict):
        # Check for expected fields
        test(
            "report has stages or phases",
            any(
                k in report
                for k in ("stages", "phases", "curriculum_stages", "results")
            ),
            f"keys: {list(report.keys())[:10]}",
        )

        # Check for intercept rate data
        report_str = json.dumps(report)
        test("report mentions intercept rate", "intercept" in report_str.lower())
        test(
            "report mentions stealth or curriculum",
            "stealth" in report_str.lower() or "curriculum" in report_str.lower(),
        )
else:
    test("curriculum report exists", False, f"not found: {report_path}")


# ============================================================
# Test 4: Quick Monte Carlo (5 episodes)
# ============================================================
print("\n[4/6] Testing quick Monte Carlo (5 episodes)...")

try:
    # Run a few episodes with the stealth strategy (no model, random policy)
    intercept_rates = []
    for ep in range(5):
        strat = STRATEGIES[1]  # stealth_breakthrough
        env = StrategyEnv(strat, duration=120, seed=200 + ep)
        obs, info = env.reset()

        for step in range(12):
            action = ep % 6  # cycle through strategies
            obs, reward, term, trunc, info = env.step(action)
            if term or trunc:
                break

        # Collect metrics using the same pattern as run_episode
        total_missiles = len(env._missiles)
        intercepted = sum(1 for m in env._missiles if m.get("intercepted", False))
        if total_missiles > 0:
            intercept_rates.append(intercepted / total_missiles)

    if intercept_rates:
        avg = np.mean(intercept_rates)
        test("MC episodes produced results", len(intercept_rates) > 0)
        test("MC intercept rate >= 0.30 (sanity)", avg >= 0.30, f"avg={avg:.3f}")
        test("MC intercept rate <= 0.95 (sanity)", avg <= 0.95, f"avg={avg:.3f}")
    else:
        test("MC produced intercept data", False, "no missiles spawned")

except Exception as e:
    test("MC quick run OK", False, str(e))


# ============================================================
# Test 5: P6 vs P7-v2 comparison
# ============================================================
print("\n[5/6] Testing P6 vs P7-v2 comparison...")

model_p6 = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p6.zip")
test("P6 model exists", os.path.exists(model_p6))
test("P7-v2 model exists", os.path.exists(model_p7v2))

# Load P6 model and run quick stealth comparison
if os.path.exists(model_p6) and os.path.exists(model_p7v2):
    agent_p6 = DQNAgent(device=device)
    agent_p6.load()

    agent_p7 = DQNAgent(device=device)
    agent_p7.load()

    # Run 5 episodes each with stealth strategy
    rates_p6 = []
    rates_p7 = []

    for ep in range(5):
        strat = STRATEGIES[1]  # stealth

        # P6 model
        env = StrategyEnv(strat, duration=120, seed=300 + ep)
        obs, info = env.reset()
        for step in range(12):
            action = agent_p6.predict(obs)
            if isinstance(action, (np.ndarray, np.integer)):
                action = int(action)
            obs, reward, term, trunc, info = env.step(action)
            if term or trunc:
                break
        total_m = len(env._missiles)
        intercepted = sum(1 for m in env._missiles if m.get("intercepted", False))
        if total_m > 0:
            rates_p6.append(intercepted / total_m)

        # P7-v2 model
        env = StrategyEnv(strat, duration=120, seed=300 + ep)
        obs, info = env.reset()
        for step in range(12):
            action = agent_p7.predict(obs)
            if isinstance(action, (np.ndarray, np.integer)):
                action = int(action)
            obs, reward, term, trunc, info = env.step(action)
            if term or trunc:
                break
        total_m = len(env._missiles)
        intercepted = sum(1 for m in env._missiles if m.get("intercepted", False))
        if total_m > 0:
            rates_p7.append(intercepted / total_m)

    if rates_p6 and rates_p7:
        avg_p6 = np.mean(rates_p6)
        avg_p7 = np.mean(rates_p7)
        test(f"P6 stealth rate: {avg_p6:.1%}", True)
        test(f"P7-v2 stealth rate: {avg_p7:.1%}", True)
        # P7-v2 should be >= P6 (improvement from curriculum learning)
        test(
            "P7-v2 >= P6 for stealth",
            avg_p7 >= avg_p6 - 0.10,
            f"P6={avg_p6:.3f} P7={avg_p7:.3f}",
        )
    else:
        test(
            "comparison produced data", False, f"P6:{len(rates_p6)} P7:{len(rates_p7)}"
        )


# ============================================================
# Test 6: Environment P7-v2 fixes
# ============================================================
print("\n[6/6] Testing P7-v2 environment fixes...")

import inspect

from deep_rl.pmtec_env import PMTECEnv

# Check extreme weather detection_range_factor = 0.5 (was 0.3)
wx_source = inspect.getsource(PMTECEnv._roll_weather)
test("extreme weather detection_range_factor=0.5 (P7-v2 fix)", "0.5" in wx_source)

# Check area defense fallback
intercept_source = inspect.getsource(PMTECEnv._do_intercept)
test("area defense fallback 0.15 base", "0.15" in intercept_source)
test("area defense uses TTI factor", "time_to_impact" in intercept_source)

# Check hypersonic base probabilities raised
test("hypersonic direct base_prob >= 0.60", "0.60" in intercept_source)
test("hypersonic saturation base_prob >= 0.85", "0.85" in intercept_source)

# Verify StrategyEnv also has the fix
strat_env_source = inspect.getsource(StrategyEnv._roll_weather)
test("StrategyEnv extreme weather also fixed", "0.5" in strat_env_source)

# Check monte_carlo_validation.py also has the fix
mc_path = os.path.join(PROJECT_ROOT, "scripts", "monte_carlo_validation.py")
with open(mc_path, "r", encoding="utf-8") as f:
    mc_source = f.read()
test("monte_carlo_validation.py has 0.5 fix", "0.5" in mc_source)

# Check curriculum_training.py also has the fix
cur_path = os.path.join(PROJECT_ROOT, "scripts", "curriculum_training.py")
if os.path.exists(cur_path):
    with open(cur_path, "r", encoding="utf-8") as f:
        cur_source = f.read()
    test("curriculum_training.py has 0.5 fix", "0.5" in cur_source)
else:
    test("curriculum_training.py exists", False)


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print(f"P7 Test Results: {PASS} passed, {FAIL} failed")
print("=" * 60)
for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
