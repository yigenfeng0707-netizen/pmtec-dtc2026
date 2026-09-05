#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P4-4: Multi-Agent RL Test
Verify IQL integration: both agents load, predict, and drive ASDA decisions.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PMTEC_HEADLESS"] = "1"

from deep_rl.multi_agent_env import (
    MultiAgentPMTECEnv,
    INTERCEPT_AGENT,
    DISPERSAL_AGENT,
    INTERCEPT_ACTIONS,
    DISPERSAL_ACTIONS,
)
from deep_rl.multi_agent_dqn import MultiAgentDQN
from deep_rl.pmtec_env import OBS_DIM


def test_p4_4_multi_agent_rl():
    """Test P4-4 multi-agent RL system."""
    print("=" * 60)
    print("P4-4: Multi-Agent RL (IQL) Test")
    print("=" * 60)

    results = []

    # 1. Verify multi-agent environment
    print("\n[1] Testing MultiAgentPMTECEnv...")
    ma_env = MultiAgentPMTECEnv(duration=120, seed=42)
    obs_dict, info_dict = ma_env.reset(seed=42)

    results.append(("Env reset returns dict", isinstance(obs_dict, dict), ""))
    results.append(("Has intercept obs", INTERCEPT_AGENT in obs_dict, ""))
    results.append(("Has dispersal obs", DISPERSAL_AGENT in obs_dict, ""))
    results.append(
        (
            "Obs shape correct",
            obs_dict[INTERCEPT_AGENT].shape == (OBS_DIM,),
            f"shape={obs_dict[INTERCEPT_AGENT].shape}",
        )
    )
    results.append(
        (
            "Intercept action space",
            ma_env.intercept_action_space.n == INTERCEPT_ACTIONS,
            f"n={ma_env.intercept_action_space.n}",
        )
    )
    results.append(
        (
            "Dispersal action space",
            ma_env.dispersal_action_space.n == DISPERSAL_ACTIONS,
            f"n={ma_env.dispersal_action_space.n}",
        )
    )

    # Step with random actions
    actions = {INTERCEPT_AGENT: 1, DISPERSAL_AGENT: 2}
    obs_dict, reward, done, truncated, info = ma_env.step(actions)
    results.append(("Step returns dict obs", isinstance(obs_dict, dict), ""))
    results.append(
        (
            "Step returns scalar reward",
            isinstance(reward, (int, float)),
            f"reward={reward}",
        )
    )
    results.append(
        ("Step info has _combined", "_combined" in info, str(info.get("_combined", {})))
    )

    print(f"  Step: reward={reward:.2f}, combined={info['_combined']}")

    # 2. Verify IQL model loading
    print("\n[2] Testing MultiAgentDQN model loading...")
    trainer = MultiAgentDQN()
    loaded = trainer.load()
    results.append(("IQL models loaded", loaded, ""))
    results.append(("IQL is_trained", trainer.is_trained(), ""))

    # 3. Verify prediction
    print("\n[3] Testing multi-agent prediction...")
    obs = obs_dict[INTERCEPT_AGENT]
    predictions = trainer.predict(obs)
    results.append(("Predict returns dict", isinstance(predictions, dict), ""))
    results.append(
        (
            "Has intercept action",
            INTERCEPT_AGENT in predictions,
            f"action={predictions.get(INTERCEPT_AGENT)}",
        )
    )
    results.append(
        (
            "Has dispersal action",
            DISPERSAL_AGENT in predictions,
            f"action={predictions.get(DISPERSAL_AGENT)}",
        )
    )
    results.append(
        (
            "Intercept action valid",
            0 <= predictions[INTERCEPT_AGENT] < INTERCEPT_ACTIONS,
            f"action={predictions[INTERCEPT_AGENT]}",
        )
    )
    results.append(
        (
            "Dispersal action valid",
            0 <= predictions[DISPERSAL_AGENT] < DISPERSAL_ACTIONS,
            f"action={predictions[DISPERSAL_AGENT]}",
        )
    )

    print(
        f"  Predict: intercept={predictions[INTERCEPT_AGENT]}, dispersal={predictions[DISPERSAL_AGENT]}"
    )

    # 4. Verify integration with PMTECEngine
    print("\n[4] Testing engine integration...")
    from services.grpc_server import PMTECEngine

    engine = PMTECEngine()

    results.append(("Engine has ma_dqn", hasattr(engine, "ma_dqn"), ""))
    results.append(("Engine ma_dqn not None", engine.ma_dqn is not None, ""))
    results.append(
        (
            "Engine ma_dqn trained",
            engine.ma_dqn.is_trained() if engine.ma_dqn else False,
            "",
        )
    )

    # 5. Run short simulation and verify ma_dqn decisions
    print("\n[5] Running 60s simulation with multi-agent IQL...")
    ok, msg = engine.start_simulation("P4-4-Test", 60, 42)
    print(f"  Start: {msg}")

    waited = 0
    while engine._running and waited < 70:
        time.sleep(5)
        waited += 5
        cycle = engine.asda_cycle_count
        entities = len(engine._entities)
        print(f"  [{waited}s] cycle={cycle}, entities={entities}")

    state = engine.get_state_dict()
    ma_stats = state.get("ma_dqn_stats", {})
    print(f"  ma_dqn_stats: {ma_stats}")

    results.append(
        (
            "Simulation completes",
            state.get("total_entities", 0) > 0,
            f"entities={state.get('total_entities')}",
        )
    )
    results.append(
        (
            "MA DQN stats in state",
            bool(ma_stats),
            str(ma_stats.get("algorithm", ""))[:30],
        )
    )

    # Check for ma_dqn_decision events
    ma_events = [
        e for e in engine.spear.events if e.get("event_type") == "ma_dqn_decision"
    ]
    results.append(
        ("MA DQN decision events", len(ma_events) > 0, f"{len(ma_events)} events")
    )
    if ma_events:
        sample = ma_events[0]
        print(f"  Sample event: {sample.get('description', '')}")
        results.append(
            (
                "Event has intercept_strategy",
                "intercept_strategy" in sample.get("data", {}),
                "",
            )
        )
        results.append(
            (
                "Event has dispersal_level",
                "dispersal_level" in sample.get("data", {}),
                "",
            )
        )

    # 6. Verify file existence
    print("\n[6] Checking model files...")
    models_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "models"
    )
    intercept_path = os.path.join(models_dir, "pmtec_iql_intercept.zip")
    dispersal_path = os.path.join(models_dir, "pmtec_iql_dispersal.zip")
    history_path = os.path.join(models_dir, "pmtec_iql_history.json")

    results.append(("Intercept model exists", os.path.exists(intercept_path), ""))
    results.append(("Dispersal model exists", os.path.exists(dispersal_path), ""))
    results.append(("Training history exists", os.path.exists(history_path), ""))

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    for name, ok, detail in results:
        status = "[PASS]" if ok else "[FAIL]"
        print(f"  {status} {name}" + (f" - {detail}" if detail else ""))

    return failed == 0


if __name__ == "__main__":
    ok = test_p4_4_multi_agent_rl()
    sys.exit(0 if ok else 1)
