#!/usr/bin/env python3
"""
Quick comparison: P6 vs P7 model on stealth-breakthrough scenario.
Uses the same StrategyEnv as Monte Carlo validation.
"""

import os, sys, json, time
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from stable_baselines3 import DQN
from scripts.monte_carlo_validation import StrategyEnv, STRATEGIES, wilson_ci

P6_PATH = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p6.zip")
P7_PATH = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p7.zip")


def eval_model(model_path, n_episodes=50):
    """Evaluate a model on stealth_breakthrough strategy."""
    stealth = next(s for s in STRATEGIES if s.name == "stealth_breakthrough")
    model = DQN.load(model_path, device="cpu")

    intercept_rates = []
    total_intercepted = 0
    total_missiles = 0

    for ep in range(n_episodes):
        env = StrategyEnv(strategy=stealth, duration=120, seed=20000 + ep)
        obs, info = env.reset(seed=20000 + ep)
        done = False
        truncated = False

        while not done and not truncated:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)

        intercepted = sum(1 for m in env._missiles if m["intercepted"])
        total_msl = len(env._missiles)
        total_intercepted += intercepted
        total_missiles += total_msl
        intercept_rates.append(intercepted / max(total_msl, 1))

    point, lower, upper = wilson_ci(total_intercepted, total_missiles)
    return {
        "model": os.path.basename(model_path),
        "n_episodes": n_episodes,
        "total_missiles": total_missiles,
        "total_intercepted": total_intercepted,
        "intercept_rate": round(point, 4),
        "ci_lower": round(lower, 4),
        "ci_upper": round(upper, 4),
        "mean_episode_rate": round(float(np.mean(intercept_rates)), 4),
        "std_episode_rate": round(float(np.std(intercept_rates)), 4),
        "min_rate": round(float(min(intercept_rates)), 4),
        "max_rate": round(float(max(intercept_rates)), 4),
    }


print("=" * 72)
print("P6 vs P7 Stealth Breakthrough Comparison (50 episodes each)")
print("=" * 72)

for path, label in [(P6_PATH, "P6 Baseline"), (P7_PATH, "P7 Curriculum")]:
    if os.path.exists(path):
        r = eval_model(path, n_episodes=50)
        print(f"\n{label} ({r['model']}):")
        print(
            f"  Missiles: {r['total_missiles']} | Intercepted: {r['total_intercepted']}"
        )
        print(
            f"  Intercept rate: {r['intercept_rate']:.1%} (CI: [{r['ci_lower']:.3f}, {r['ci_upper']:.3f}])"
        )
        print(
            f"  Episode mean: {r['mean_episode_rate']:.1%} +/- {r['std_episode_rate']:.1%}"
        )
        print(f"  Range: [{r['min_rate']:.1%}, {r['max_rate']:.1%}]")
    else:
        print(f"\n{label}: MODEL NOT FOUND at {path}")

# Also run on all 4 strategies for overall comparison
print("\n" + "=" * 72)
print("Overall comparison (25 episodes per strategy x 4 = 100 total)")
print("=" * 72)

for path, label in [(P6_PATH, "P6"), (P7_PATH, "P7")]:
    if not os.path.exists(path):
        print(f"\n{label}: MODEL NOT FOUND")
        continue

    model = DQN.load(path, device="cpu")
    all_intercepted = 0
    all_missiles = 0

    for strategy in STRATEGIES:
        for ep in range(25):
            env = StrategyEnv(strategy=strategy, duration=120, seed=30000 + ep)
            obs, info = env.reset(seed=30000 + ep)
            done = False
            truncated = False
            while not done and not truncated:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, done, truncated, info = env.step(action)
            all_intercepted += sum(1 for m in env._missiles if m["intercepted"])
            all_missiles += len(env._missiles)

    point, lower, upper = wilson_ci(all_intercepted, all_missiles)
    print(
        f"\n{label} Overall: {all_intercepted}/{all_missiles} = {point:.1%} (CI: [{lower:.3f}, {upper:.3f}])"
    )

# Save comparison report
report = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "p6_stealth": eval_model(P6_PATH, 50) if os.path.exists(P6_PATH) else None,
    "p7_stealth": eval_model(P7_PATH, 50) if os.path.exists(P7_PATH) else None,
}
report_path = os.path.join(PROJECT_ROOT, "data", "p6_vs_p7_comparison.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\nReport saved to: {report_path}")
