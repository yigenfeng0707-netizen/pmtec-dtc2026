#!/usr/bin/env python
"""
P5-2: MADDPG (Multi-Agent DDPG) Test
Verify Actor-Critic multi-agent integration: models load, predict, and drive ASDA decisions.
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PMTEC_HEADLESS"] = "1"

from deep_rl.maddpg_agent import MADDPGAgent
from deep_rl.multi_agent_env import (
    DISPERSAL_ACTIONS,
    DISPERSAL_AGENT,
    INTERCEPT_ACTIONS,
    INTERCEPT_AGENT,
)
from deep_rl.pmtec_env import OBS_DIM

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def test_p5_2_maddpg():
    print("=" * 60)
    print("P5-2: MADDPG (Multi-Agent DDPG) Test")
    print("=" * 60)

    results = []

    # 1. Verify MADDPG agent initialization
    print("\n[1] Testing MADDPGAgent initialization...")
    trainer = MADDPGAgent(device="auto")
    results.append(("Agent initializes", trainer is not None, ""))
    results.append(("Has intercept actor", INTERCEPT_AGENT in trainer.actors, ""))
    results.append(("Has dispersal actor", DISPERSAL_AGENT in trainer.actors, ""))
    results.append(("Has intercept critic", INTERCEPT_AGENT in trainer.critics, ""))
    results.append(("Has dispersal critic", DISPERSAL_AGENT in trainer.critics, ""))
    results.append(("Has target actors", len(trainer.target_actors) == 2, ""))
    results.append(("Has target critics", len(trainer.target_critics) == 2, ""))
    results.append(("Has replay buffer", len(trainer.replay) >= 0, ""))
    results.append(("Device is xpu", "xpu" in str(trainer.device), str(trainer.device)))

    # 2. Verify model files exist
    print("\n[2] Checking model files...")
    models_dir = os.path.join(_SCRIPT_DIR, "data", "models")
    intercept_path = os.path.join(models_dir, "pmtec_maddpg_intercept.pt")
    dispersal_path = os.path.join(models_dir, "pmtec_maddpg_dispersal.pt")
    history_path = os.path.join(models_dir, "pmtec_maddpg_history.json")
    results.append(("Intercept model exists", os.path.exists(intercept_path), ""))
    results.append(("Dispersal model exists", os.path.exists(dispersal_path), ""))
    results.append(("Training history exists", os.path.exists(history_path), ""))

    # 3. Verify model loading
    print("\n[3] Testing model loading...")
    loaded = trainer.load()
    results.append(("Models loaded", loaded, ""))
    results.append(("is_trained", trainer.is_trained(), ""))

    # 4. Verify prediction
    print("\n[4] Testing prediction...")
    obs = np.random.rand(OBS_DIM).astype(np.float32)
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

    # 5. Verify single agent prediction
    print("\n[5] Testing single-agent prediction...")
    single = trainer.predict(obs, agent_id=INTERCEPT_AGENT)
    results.append(
        (
            "Single agent predict returns int",
            isinstance(single, int),
            f"action={single}",
        )
    )
    results.append(("Single agent action valid", 0 <= single < INTERCEPT_ACTIONS, ""))

    # 6. Verify statistics
    print("\n[6] Testing statistics...")
    stats = trainer.get_statistics()
    results.append(("Stats has algorithm", "algorithm" in stats, ""))
    results.append(
        (
            "Stats algorithm is MADDPG",
            "MADDPG" in stats.get("algorithm", ""),
            stats.get("algorithm", ""),
        )
    )
    results.append(("Stats has is_trained", stats.get("is_trained", False), ""))
    results.append(
        (
            "Stats has 2 agents",
            len(stats.get("agents", [])) == 2,
            str(stats.get("agents", [])),
        )
    )
    results.append(("Stats has architecture info", "architecture" in stats, ""))
    results.append(("Stats has critic_input", "critic_input" in stats, ""))
    results.append(
        (
            "Stats reports timesteps",
            stats.get("total_timesteps", 0) > 0,
            f"{stats.get('total_timesteps', 0)}",
        )
    )

    # 7. Verify engine integration
    print("\n[7] Testing engine integration...")
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

    # Check if MADDPG is loaded (not IQL)
    if engine.ma_dqn:
        algo = engine.ma_dqn.get_statistics().get("algorithm", "")
        results.append(("Engine uses MADDPG", "MADDPG" in algo, algo[:40]))

    # 8. Run 60s simulation with MADDPG
    print("\n[8] Running 60s simulation with MADDPG...")
    ok, msg = engine.start_simulation("P5-2-Test", 60, 42)
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
    print(f"  ma_dqn_stats algo: {ma_stats.get('algorithm', 'N/A')[:40]}")

    results.append(
        (
            "Simulation completes",
            state.get("total_entities", 0) > 0,
            f"entities={state.get('total_entities')}",
        )
    )
    results.append(("MA DQN stats in state", bool(ma_stats), ""))

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

    # 9. Verify MADDPG is preferred over IQL
    print("\n[9] Verifying MADDPG preferred over IQL...")
    iql_intercept = os.path.join(models_dir, "pmtec_iql_intercept.zip")
    maddpg_intercept = os.path.join(models_dir, "pmtec_maddpg_intercept.pt")
    both_exist = os.path.exists(iql_intercept) and os.path.exists(maddpg_intercept)
    results.append(("Both MADDPG and IQL models exist", both_exist, ""))
    if both_exist:
        # Engine should prefer MADDPG
        algo = (
            engine.ma_dqn.get_statistics().get("algorithm", "") if engine.ma_dqn else ""
        )
        results.append(("MADDPG preferred over IQL", "MADDPG" in algo, algo[:40]))

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    total = len(results)
    print(f"Results: {passed} passed, {failed} failed, {total} total")
    print("=" * 60)

    for name, ok, detail in results:
        status = "[PASS]" if ok else "[FAIL]"
        line = f"  {status} {name}"
        if detail:
            line += f" - {detail}"
        print(line)

    return failed == 0


if __name__ == "__main__":
    ok = test_p5_2_maddpg()
    sys.exit(0 if ok else 1)
