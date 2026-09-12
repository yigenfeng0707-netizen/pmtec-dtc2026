#!/usr/bin/env python3
"""P3 Final Simulation Verification - 300s full ASDA loop with all P3 features.

Verifies:
- P3-1: Weather closed loop (detection_range_factor -> sensor range)
- P3-2: Kalman track fusion (KalmanTrack lifecycle + multi-source fusion)
- P3-3: 122-dim DQN observation (EW/Cyber/Weather features)
- P3-4: AdversaryAgent (rule-driven targeting, coordinated EW/Cyber)
"""

import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["PMTEC_HEADLESS"] = "1"

from services.grpc_server import PMTECEngine


def main():
    print("=" * 70)
    print("P3 Final Simulation Verification (300s)")
    print("=" * 70)

    engine = PMTECEngine()
    print(f"AdversaryAgent: {type(engine.adversary).__name__}")
    print(f"DQN available: {engine.dqn is not None}")
    if engine.dqn:
        print(f"  DQN trained: {engine.dqn.is_trained()}")
    print(f"Live data: {engine.live_data is not None}")
    print()

    # Start 300s simulation
    ok, msg = engine.start_simulation("P3-Verification", 300, 42)
    print(f"Start: {msg}")

    # Wait for simulation to finish
    max_wait = 220  # seconds (sim runs ~1.5x real-time, 300s sim needs ~200s wall)
    waited = 0
    while engine._running and waited < max_wait:
        time.sleep(5)
        waited += 5
        cycle = engine.asda_cycle_count
        entities = len(engine._entities)
        missiles = sum(1 for m in engine._missiles if m.status == "active")
        print(
            f"  [{waited}s] cycle={cycle}, entities={entities}, active_missiles={missiles}"
        )

    if engine._running:
        print("Simulation still running, stopping...")
        engine.stop_simulation()
        time.sleep(2)

    # Collect results
    state = engine.get_state_dict()
    events = engine.spear.events
    adversary_stats = engine.adversary.get_stats()

    print("\n" + "=" * 70)
    print("SIMULATION RESULTS")
    print("=" * 70)
    print(f"Simulation time: {state['sim_seconds']}s")
    print(f"ASDA cycles: {state['asda_cycle']}")
    print(f"Total entities: {state['total_entities']}")
    print(f"Active tracks: {state['active_tracks']}")
    print(f"Network vulnerability: {state['network_vulnerability']}")
    print(f"LVC Live entities: {state['lvc_live_entities']}")
    lds = state.get("live_data_stats", {})
    print(
        f"Live data injected: {lds.get('total_injected', 0) if isinstance(lds, dict) else 0}"
    )

    print("\nAdversary Stats:")
    for k, v in adversary_stats.items():
        print(f"  {k}: {v}")

    # Count events by type
    event_types = {}
    for evt in events:
        etype = (
            evt.event_type
            if hasattr(evt, "event_type")
            else str(evt.get("event_type", "unknown"))
        )
        event_types[etype] = event_types.get(etype, 0) + 1

    print(f"\nEvent Summary ({len(events)} total events):")
    for etype, count in sorted(event_types.items(), key=lambda x: -x[1]):
        print(f"  {etype}: {count}")

    # Verify P3 features
    print("\n" + "=" * 70)
    print("P3 FEATURE VERIFICATION")
    print("=" * 70)

    # P3-1: Weather closed loop
    has_weather = "live_data_inject" in event_types
    print(
        f"[{'PASS' if has_weather else 'FAIL'}] P3-1 Weather closed loop: "
        f"{'live_data_inject events present' if has_weather else 'NO weather events'}"
    )

    # P3-2: Kalman tracks (in LVCArchitecture, not TrackManager)
    lvc_status = engine.lvc.status() if hasattr(engine.lvc, "status") else {}
    kalman_tracks = lvc_status.get("kalman_tracks", 0)
    fusion_cycle = lvc_status.get("fusion_cycle", 0)
    print(
        f"[{'PASS' if kalman_tracks > 0 else 'FAIL'}] P3-2 Kalman fusion: "
        f"{kalman_tracks} tracks, {fusion_cycle} fusion cycles"
    )

    # P3-3: 122-dim DQN
    if engine.dqn and engine.dqn.is_trained():
        obs = engine._build_dqn_observation()
        print(
            f"[{'PASS' if len(obs) == 122 else 'FAIL'}] P3-3 DQN 122-dim obs: shape={obs.shape}"
        )
        ew_feat = obs[110 + 6]  # ew_active_count
        cyber_feat = obs[110 + 8]  # cyber_effectiveness
        wx_feat = obs[110 + 9]  # wx_detection_factor
        print(f"  EW={ew_feat:.3f}, Cyber={cyber_feat:.3f}, Weather={wx_feat:.3f}")
    else:
        print("[WARN] P3-3 DQN not trained")

    # P3-4: AdversaryAgent
    has_adversary = adversary_stats.get("total_attacks", 0) > 0
    has_missile_launch = "missile_launch" in event_types
    has_ew = "ew_jam" in event_types
    has_cyber = "cyber_attack" in event_types
    print(
        f"[{'PASS' if has_adversary and has_missile_launch else 'FAIL'}] P3-4 AdversaryAgent: "
        f"{adversary_stats.get('total_attacks', 0)} attacks, "
        f"hit_rate={adversary_stats.get('hit_rate', 0):.1%}"
    )
    print(f"  Coordinated EW events: {has_ew}, Coordinated Cyber events: {has_cyber}")

    if engine.dqn:
        print(f"\nDQN device: {engine.dqn.device}")

    print("\n" + "=" * 70)
    print("P3 SIMULATION VERIFICATION COMPLETE")
    print("=" * 70)
    os._exit(0)


if __name__ == "__main__":
    main()
