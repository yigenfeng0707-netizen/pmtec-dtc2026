#!/usr/bin/env python3
"""
PMTEC Monte Carlo Validation Framework

Runs 100+ episodes across 4 diverse adversary strategies to validate
that the DQN model (pmtec_dqn_p6.zip, 182-dim, 200K steps) achieves
stable intercept rates with Wilson confidence intervals.

Adversary Strategies:
  1. Saturation Attack  - 8-12 simultaneous mixed-type missiles
  2. Stealth Breakthrough - Few hypersonic threats + extreme weather
  3. Electronic Warfare   - Heavy EW jamming + cyber attacks
  4. Decoy Swarm          - Many cruise missiles to exhaust interceptors

Usage:
  python scripts/monte_carlo_validation.py [--episodes 100] [--workers 4]
  python scripts/monte_carlo_validation.py --episodes 200 --workers 8
"""

import os
import sys
import json
import time
import argparse
import math
import multiprocessing as mp
from dataclasses import dataclass, field, asdict
from typing import Optional

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from deep_rl.pmtec_env import (
    PMTECEnv,
    OBS_DIM,
    NUM_BASES,
    BASE_FEATURES,
    GLOBAL_FEATURES,
    MAX_THREATS,
    THREAT_FEATURES,
    NUM_ACTIONS,
    ASDA_CYCLE_SECONDS,
    THREAT_TYPES,
)
from deep_rl.dqn_agent import DQNAgent
import numpy as np


# ============================================================
#  Adversary Strategies
# ============================================================


@dataclass
class AdversaryStrategy:
    """Configuration for a specific adversary attack pattern."""

    name: str
    description: str
    # Threat spawn parameters
    n_threats_min: int = 2
    n_threats_max: int = 5
    threat_pool: tuple = ("ballistic", "cruise", "hypersonic")
    ew_prob: float = 0.30
    cyber_prob: float = 0.25
    # Weather: 0=clear, 1=light, 2=moderate, 3=severe
    weather_index: int = 0
    # Missile TTI range (seconds)
    tti_min: float = 30.0
    tti_max: float = 120.0
    # Distance cap (km) for sensor coverage
    distance_cap: float = 120.0
    # Speed multiplier for threat types
    speed_multiplier: float = 1.0


STRATEGIES = [
    AdversaryStrategy(
        name="saturation_attack",
        description="8-12 simultaneous mixed-type missiles to overwhelm defenses",
        n_threats_min=8,
        n_threats_max=12,
        threat_pool=("ballistic", "cruise", "hypersonic", "ballistic", "cruise"),
        ew_prob=0.20,
        cyber_prob=0.15,
        weather_index=0,  # clear weather - pure volume attack
        tti_min=40.0,
        tti_max=100.0,
    ),
    AdversaryStrategy(
        name="stealth_breakthrough",
        description="Few hypersonic threats with extreme weather to evade detection",
        n_threats_min=2,
        n_threats_max=4,
        threat_pool=("hypersonic", "hypersonic", "ballistic"),
        ew_prob=0.10,
        cyber_prob=0.05,
        weather_index=3,  # severe weather
        tti_min=20.0,
        tti_max=60.0,  # shorter TTI = less reaction time
        speed_multiplier=1.2,  # 20% faster
    ),
    AdversaryStrategy(
        name="electronic_warfare",
        description="Heavy EW jamming + cyber attacks to blind sensors and disrupt C2",
        n_threats_min=3,
        n_threats_max=6,
        threat_pool=("ballistic", "cruise", "hypersonic"),
        ew_prob=0.80,
        cyber_prob=0.70,
        weather_index=2,  # moderate weather compounds EW effect
        tti_min=35.0,
        tti_max=90.0,
    ),
    AdversaryStrategy(
        name="decoy_swarm",
        description="Many low-value cruise missiles to exhaust interceptor supply",
        n_threats_min=6,
        n_threats_max=10,
        threat_pool=("cruise", "cruise", "cruise", "ballistic"),  # mostly cruise
        ew_prob=0.15,
        cyber_prob=0.10,
        weather_index=1,  # light weather
        tti_min=50.0,
        tti_max=120.0,  # longer TTI but high volume
    ),
]


# ============================================================
#  Custom Environment with Adversary Strategy
# ============================================================


class StrategyEnv(PMTECEnv):
    """PMTEC environment patched with a specific adversary strategy."""

    def __init__(
        self, strategy: AdversaryStrategy, duration: int = 120, seed: int = 42
    ):
        super().__init__(duration=duration, seed=seed)
        self._strategy = strategy

    def _roll_weather(self) -> dict:
        """Force specific weather condition based on strategy."""
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
        return dict(conditions[self._strategy.weather_index])

    def _spawn_threats(self):
        """Override threat spawning with adversary strategy parameters."""
        import random as _rng_mod

        n_threats = self._rng.randint(
            self._strategy.n_threats_min, self._strategy.n_threats_max
        )
        for i in range(n_threats):
            target = self._rng.choice(self._bases)
            threat_type = self._rng.choice(self._strategy.threat_pool)
            base_speed = {"ballistic": 3000, "cruise": 800, "hypersonic": 5000}[
                threat_type
            ]
            speed = int(base_speed * self._strategy.speed_multiplier)
            tti = self._rng.uniform(self._strategy.tti_min, self._strategy.tti_max)
            distance_km = min(speed * tti / 3600.0, self._strategy.distance_cap)

            import math as _math

            bearing = self._rng.uniform(0, 2 * _math.pi)
            lat_offset = distance_km / 111.0 * _math.cos(bearing)
            lon_offset = (
                distance_km
                / (111.0 * max(0.1, _math.cos(_math.radians(target["lat"]))))
                * _math.sin(bearing)
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

        # EW threats
        if self._rng.random() < self._strategy.ew_prob:
            target = self._rng.choice(self._bases)
            self._ew_threats.append(
                {
                    "id": f"EW-{self._asda_cycle}-{len(self._ew_threats)}",
                    "target_base": target["id"],
                    "jammer_lat": target["lat"] + self._rng.uniform(-5, 5),
                    "jammer_lon": target["lon"] + self._rng.uniform(-8, 8),
                    "jamming_power": self._rng.uniform(0.5, 0.95),  # heavier jamming
                    "status": "active",
                    "duration": self._rng.randint(2, 5),
                }
            )

        # Cyber threats
        if self._rng.random() < self._strategy.cyber_prob:
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
#  Wilson Score Confidence Interval
# ============================================================


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple:
    """Wilson score interval for binomial proportion.

    Returns (point_estimate, lower, upper) at 95% confidence (z=1.96).
    """
    if total == 0:
        return (0.0, 0.0, 0.0)
    p = successes / total
    n = total
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (p, max(0.0, center - spread), min(1.0, center + spread))


# ============================================================
#  Episode Runner (for multiprocessing)
# ============================================================


def run_episode(args):
    """Run a single episode and return results.

    Designed for multiprocessing: picklable, no shared state.
    """
    strategy_name, seed, duration, model_path = args

    # Find strategy config
    strategy = next(s for s in STRATEGIES if s.name == strategy_name)

    # Create environment with strategy
    env = StrategyEnv(strategy=strategy, duration=duration, seed=seed)
    obs, info = env.reset(seed=seed)

    # Load DQN agent
    agent = DQNAgent(device="cpu")  # CPU for inference stability in parallel
    loaded = agent.load()
    if not loaded:
        # Fallback: random policy if model not found
        action_fn = lambda o: np.random.randint(0, NUM_ACTIONS)
    else:
        action_fn = lambda o: agent.predict(o, deterministic=True)

    # Run episode
    episode_reward = 0.0
    step_count = 0
    done = False
    truncated = False

    while not done and not truncated:
        action = action_fn(obs)
        obs, reward, done, truncated, info = env.step(action)
        episode_reward += reward
        step_count += 1

    # Collect episode metrics
    total_missiles = len(env._missiles)
    intercepted = sum(1 for m in env._missiles if m["intercepted"])
    destroyed_ac = sum(1 for a in env._aircraft if a["status"] == "destroyed")
    total_ac = len(env._aircraft)
    survived_ac = total_ac - destroyed_ac

    # intercept_rate from info
    final_info = env._get_info()
    env_intercept_rate = final_info.get("intercept_rate", 0.0)

    # Compute "effective" intercept rate = intercepted / total_missiles
    # This is more meaningful than per-attempt rate
    effective_intercept_rate = intercepted / max(total_missiles, 1)

    result = {
        "strategy": strategy_name,
        "seed": seed,
        "duration_sec": duration,
        "steps": step_count,
        "total_missiles": total_missiles,
        "intercepted_missiles": intercepted,
        "missiles_through": total_missiles - intercepted,
        "intercept_rate": effective_intercept_rate,
        "env_intercept_rate": env_intercept_rate,
        "episode_reward": round(episode_reward, 2),
        "destroyed_aircraft": destroyed_ac,
        "survived_aircraft": survived_ac,
        "aircraft_survival_rate": survived_ac / max(total_ac, 1),
        "model_loaded": loaded,
        "obs_dim": OBS_DIM,
    }

    return result


# ============================================================
#  Main Validation Orchestrator
# ============================================================


def run_validation(
    episodes_per_strategy: int = 25,
    n_workers: int = 4,
    duration: int = 120,
    model_path: str = None,
):
    """Run Monte Carlo validation across all adversary strategies.

    Args:
        episodes_per_strategy: Number of episodes per strategy (total = x4)
        n_workers: Number of parallel workers
        duration: Episode duration in seconds
        model_path: Override model path (default: auto-detect pmtec_dqn_p6.zip)

    Returns:
        Dict with full validation results
    """
    # Default model path
    if model_path is None:
        model_path = os.path.join(PROJECT_ROOT, "data", "models", "pmtec_dqn_p6.zip")

    print("=" * 72)
    print("PMTEC Monte Carlo Intercept Rate Validation")
    print("=" * 72)
    print(f"Model: {model_path}")
    model_exists = os.path.exists(model_path)
    print(f"Model exists: {model_exists}")
    print(f"Observation dim: {OBS_DIM}")
    print(f"Episodes per strategy: {episodes_per_strategy}")
    print(f"Total episodes: {episodes_per_strategy * len(STRATEGIES)}")
    print(f"Parallel workers: {n_workers}")
    print(f"Episode duration: {duration}s")
    print()

    # Build task list with deterministic seeds
    strategy_seed_offset = {
        "saturation_attack": 10000,
        "stealth_breakthrough": 20000,
        "electronic_warfare": 30000,
        "decoy_swarm": 40000,
    }
    tasks = []
    for strategy in STRATEGIES:
        offset = strategy_seed_offset[strategy.name]
        for i in range(episodes_per_strategy):
            seed = offset + i
            tasks.append((strategy.name, seed, duration, model_path))

    # Run episodes
    t0 = time.time()

    if n_workers > 1:
        with mp.Pool(n_workers) as pool:
            results = pool.map(run_episode, tasks)
    else:
        results = [run_episode(t) for t in tasks]

    elapsed = time.time() - t0

    # Aggregate results by strategy
    strategy_results = {}
    all_intercepts = 0
    all_missiles = 0

    for strategy in STRATEGIES:
        strat_results = [r for r in results if r["strategy"] == strategy.name]
        n = len(strat_results)
        total_intercepted = sum(r["intercepted_missiles"] for r in strat_results)
        total_missiles = sum(r["total_missiles"] for r in strat_results)
        total_through = total_missiles - total_intercepted

        # Wilson CI
        point, lower, upper = wilson_ci(total_intercepted, total_missiles)

        # Per-episode stats
        ep_rates = [r["intercept_rate"] for r in strat_results]
        ep_rewards = [r["episode_reward"] for r in strat_results]
        ep_survival = [r["aircraft_survival_rate"] for r in strat_results]

        strategy_results[strategy.name] = {
            "description": strategy.description,
            "n_episodes": n,
            "total_missiles": total_missiles,
            "total_intercepted": total_intercepted,
            "total_through": total_through,
            "intercept_rate": round(point, 4),
            "intercept_rate_ci_lower": round(lower, 4),
            "intercept_rate_ci_upper": round(upper, 4),
            "intercept_rate_mean": round(np.mean(ep_rates), 4),
            "intercept_rate_std": round(np.std(ep_rates), 4),
            "intercept_rate_min": round(min(ep_rates), 4),
            "intercept_rate_max": round(max(ep_rates), 4),
            "mean_reward": round(np.mean(ep_rewards), 2),
            "std_reward": round(np.std(ep_rewards), 2),
            "mean_survival_rate": round(np.mean(ep_survival), 4),
            "std_survival_rate": round(np.std(ep_survival), 4),
        }

        all_intercepts += total_intercepted
        all_missiles += total_missiles

    # Overall stats
    overall_point, overall_lower, overall_upper = wilson_ci(
        all_intercepts, all_missiles
    )
    all_rates = [r["intercept_rate"] for r in results]
    all_rewards = [r["episode_reward"] for r in results]

    overall = {
        "n_episodes": len(results),
        "total_missiles": all_missiles,
        "total_intercepted": all_intercepts,
        "total_through": all_missiles - all_intercepts,
        "intercept_rate": round(overall_point, 4),
        "intercept_rate_ci_lower": round(overall_lower, 4),
        "intercept_rate_ci_upper": round(overall_upper, 4),
        "intercept_rate_mean": round(np.mean(all_rates), 4),
        "intercept_rate_std": round(np.std(all_rates), 4),
        "intercept_rate_min": round(min(all_rates), 4),
        "intercept_rate_max": round(max(all_rates), 4),
        "mean_reward": round(np.mean(all_rewards), 2),
        "std_reward": round(np.std(all_rewards), 2),
        "elapsed_seconds": round(elapsed, 1),
    }

    # Threshold check
    target_rate = 0.70
    passes_threshold = overall_point >= target_rate
    ci_passes = overall_lower >= target_rate

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model_path": model_path,
        "model_exists": model_exists,
        "obs_dim": OBS_DIM,
        "episodes_per_strategy": episodes_per_strategy,
        "total_episodes": len(results),
        "n_workers": n_workers,
        "episode_duration_sec": duration,
        "strategies": {s.name: s.description for s in STRATEGIES},
        "per_strategy": strategy_results,
        "overall": overall,
        "target_intercept_rate": target_rate,
        "passes_threshold": passes_threshold,
        "ci_passes_threshold": ci_passes,
        "all_episodes": results,
    }

    return report


def print_report(report: dict):
    """Print formatted validation report to console."""
    print()
    print("=" * 72)
    print("VALIDATION RESULTS")
    print("=" * 72)
    print()

    # Per-strategy results
    print(
        f"{'Strategy':<24} {'Missiles':>8} {'Intercept':>10} {'Rate':>8} {'95% CI':>16} {'Reward':>8}"
    )
    print("-" * 80)

    for name, stats in report["per_strategy"].items():
        ci_str = f"[{stats['intercept_rate_ci_lower']:.3f}, {stats['intercept_rate_ci_upper']:.3f}]"
        print(
            f"{name:<24} {stats['total_missiles']:>8} "
            f"{stats['total_intercepted']:>10} "
            f"{stats['intercept_rate']:>8.1%} {ci_str:>16} "
            f"{stats['mean_reward']:>8.1f}"
        )

    print("-" * 80)

    # Overall
    o = report["overall"]
    ci_str = f"[{o['intercept_rate_ci_lower']:.3f}, {o['intercept_rate_ci_upper']:.3f}]"
    print(
        f"{'OVERALL':<24} {o['total_missiles']:>8} "
        f"{o['total_intercepted']:>10} "
        f"{o['intercept_rate']:>8.1%} {ci_str:>16} "
        f"{o['mean_reward']:>8.1f}"
    )

    print()
    print(f"Episodes: {o['n_episodes']} | Elapsed: {o['elapsed_seconds']}s")
    print(f"Target: >= {report['target_intercept_rate']:.0%} intercept rate")

    if report["passes_threshold"]:
        print(
            f"  PASS: Overall intercept rate {o['intercept_rate']:.1%} >= {report['target_intercept_rate']:.0%}"
        )
    else:
        print(
            f"  FAIL: Overall intercept rate {o['intercept_rate']:.1%} < {report['target_intercept_rate']:.0%}"
        )

    if report["ci_passes_threshold"]:
        print(
            f"  CI PASS: Lower bound {o['intercept_rate_ci_lower']:.1%} >= {report['target_intercept_rate']:.0%}"
        )
    else:
        print(
            f"  CI FAIL: Lower bound {o['intercept_rate_ci_lower']:.1%} < {report['target_intercept_rate']:.0%}"
        )

    # Episode-level distribution
    rates = [ep["intercept_rate"] for ep in report["all_episodes"]]
    print()
    print("Episode-level intercept rate distribution:")
    print(f"  Mean:   {np.mean(rates):.1%}")
    print(f"  Std:    {np.std(rates):.1%}")
    print(f"  Min:    {min(rates):.1%}")
    print(f"  Max:    {max(rates):.1%}")
    print(f"  P25:    {np.percentile(rates, 25):.1%}")
    print(f"  Median: {np.percentile(rates, 50):.1%}")
    print(f"  P75:    {np.percentile(rates, 75):.1%}")
    print(f"  P95:    {np.percentile(rates, 95):.1%}")

    # Per-strategy detailed breakdown
    print()
    print("Per-strategy detail:")
    for name, stats in report["per_strategy"].items():
        print(f"  {name}:")
        print(
            f"    Intercept rate: {stats['intercept_rate']:.1%} "
            f"(CI: [{stats['intercept_rate_ci_lower']:.3f}, {stats['intercept_rate_ci_upper']:.3f}])"
        )
        print(
            f"    Episode mean: {stats['intercept_rate_mean']:.1%} +/- {stats['intercept_rate_std']:.1%}"
        )
        print(
            f"    Survival rate: {stats['mean_survival_rate']:.1%} +/- {stats['std_survival_rate']:.1%}"
        )
        print(f"    Reward: {stats['mean_reward']:.1f} +/- {stats['std_reward']:.1f}")

    print()
    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(
        description="PMTEC Monte Carlo Intercept Rate Validation"
    )
    parser.add_argument(
        "--episodes",
        type=int,
        default=25,
        help="Episodes per adversary strategy (default: 25, total = x4 = 100)",
    )
    parser.add_argument(
        "--workers", type=int, default=4, help="Number of parallel workers (default: 4)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=120,
        help="Episode duration in seconds (default: 120)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override model path (default: auto-detect pmtec_dqn_p6.zip)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: data/monte_carlo_results.json)",
    )
    args = parser.parse_args()

    # Run validation
    report = run_validation(
        episodes_per_strategy=args.episodes,
        n_workers=args.workers,
        duration=args.duration,
        model_path=args.model,
    )

    # Print report
    print_report(report)

    # Save JSON
    output_path = args.output or os.path.join(
        PROJECT_ROOT, "data", "monte_carlo_results.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")

    # Exit code
    if report["passes_threshold"]:
        print("EXIT CODE: 0 (PASS)")
        sys.exit(0)
    else:
        print("EXIT CODE: 1 (FAIL - intercept rate below target)")
        sys.exit(1)


if __name__ == "__main__":
    main()
