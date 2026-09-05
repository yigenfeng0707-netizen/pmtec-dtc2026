#!/usr/bin/env python3
"""P4-1 Persistence layer verification.

Tests:
1. SimulationStateStore initializes and creates tables
2. 60s simulation persists snapshots, tracks, events to SQLite
3. Query API returns persisted data
4. Checkpoint save/load works
"""

import sys, os, time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["PMTEC_HEADLESS"] = "1"

from services.grpc_server import PMTECEngine


def main():
    print("=" * 70)
    print("P4-1 Persistence Layer Verification (60s sim)")
    print("=" * 70)

    engine = PMTECEngine()
    print(f"Store available: {engine.store is not None}")
    if not engine.store:
        print("[FAIL] Persistence not available")
        return False

    # Save a manual checkpoint before sim
    engine.store.save_checkpoint("pre_sim", 0, 0.0, {"test": "checkpoint"})
    ckpts = engine.store.list_checkpoints()
    print(f"Checkpoint saved: {ckpts}")

    # Run 60s simulation
    ok, msg = engine.start_simulation("P4-Persistence-Test", 60, 42)
    print(f"Start: {msg}")

    max_wait = 50
    waited = 0
    while engine._running and waited < max_wait:
        time.sleep(5)
        waited += 5
        print(f"  [{waited}s] cycle={engine.asda_cycle_count}")

    if engine._running:
        engine.stop_simulation()
        time.sleep(2)

    # Verify persisted data
    summary = engine.store.get_summary()
    print(f"\n{'=' * 70}")
    print("PERSISTENCE SUMMARY")
    print(f"{'=' * 70}")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    # Check snapshots
    snaps = engine.store.get_snapshots(limit=5)
    print(f"\nRecent snapshots ({len(snaps)}):")
    for s in snaps[:3]:
        print(
            f"  cycle={s['cycle']}, entities={s['total_entities']}, "
            f"tracks={s['active_tracks']}, kalman={s['kalman_track_count']}, "
            f"vuln={s['network_vulnerability']}"
        )

    # Check events
    evt_stats = engine.store.get_event_stats()
    print(f"\nEvent stats: {evt_stats}")

    # Check Kalman tracks
    if snaps:
        last_cycle = snaps[0]["cycle"]
        ktracks = engine.store.get_kalman_tracks(last_cycle)
        print(f"\nKalman tracks at cycle {last_cycle}: {len(ktracks)}")

    # Verify checkpoint
    loaded = engine.store.load_checkpoint("pre_sim")
    print(
        f"\nCheckpoint loaded: cycle={loaded['cycle']}, sim_seconds={loaded['sim_seconds']}"
    )

    # All checks pass
    all_pass = True
    checks = [
        ("snapshots > 0", summary.get("snapshots", 0) > 0),
        ("events > 0", summary.get("events", 0) > 0),
        ("checkpoints > 0", summary.get("checkpoints", 0) > 0),
        ("last_cycle > 0", summary.get("last_cycle", 0) > 0),
    ]
    print(f"\n{'=' * 70}")
    print("P4-1 VERIFICATION")
    print(f"{'=' * 70}")
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_pass = False

    print(f"\nResult: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
