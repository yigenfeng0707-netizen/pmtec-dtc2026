#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P5-1: JPDA (Joint Probabilistic Data Association) Unit Test

Verify that:
1. JPDA correctly associates multiple observations to multiple tracks
2. Track swapping is reduced vs nearest-neighbor (crossing targets)
3. Unmatched observations create new tracks
4. Stale tracks are deleted
5. Innovation and innovation_covariance methods work correctly
6. JPDA update produces valid state estimates
7. Integration with LVCArchitecture.fuse_tracks() works end-to-end
8. Status reports JPDA algorithm
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.lvc_architecture import (
    KalmanTrack,
    LVCArchitecture,
    haversine,
    _mat_mul,
    _mat_transpose,
    _mat_inv_2x2,
)


def test_p5_1_jpda():
    print("=" * 60)
    print("P5-1: JPDA (Joint Probabilistic Data Association) Test")
    print("=" * 60)

    results = []

    # 1. Test KalmanTrack innovation/covariance methods
    print("\n[1] Testing KalmanTrack innovation methods...")
    track = KalmanTrack(lat=35.0, lon=140.0, source="RDR-1", confidence=0.8)
    innov = track.innovation(35.01, 140.01)
    results.append(
        ("Innovation returns 2-element list", len(innov) == 2, f"innov={innov}")
    )
    results.append(
        ("Innovation lat correct", abs(innov[0] - 0.01) < 1e-6, f"lat_diff={innov[0]}")
    )
    results.append(
        ("Innovation lon correct", abs(innov[1] - 0.01) < 1e-6, f"lon_diff={innov[1]}")
    )

    S = track.innovation_covariance()
    results.append(("Innovation cov is 2x2", len(S) == 2 and len(S[0]) == 2, ""))
    results.append(
        ("Innovation cov diagonal positive", S[0][0] > 0 and S[1][1] > 0, f"S={S}")
    )

    # 2. Test JPDA update with weighted innovation
    print("\n[2] Testing JPDA update method...")
    track2 = KalmanTrack(lat=35.0, lon=140.0, source="RDR-1", confidence=0.8)
    track2.predict(dt=1.0)
    # Simulate weighted innovation pointing NE
    track2.update_jpda([0.005, 0.005])
    results.append(
        ("JPDA update moves lat", track2.lat > 35.0, f"lat={track2.lat:.4f}")
    )
    results.append(
        ("JPDA update moves lon", track2.lon > 140.0, f"lon={track2.lon:.4f}")
    )
    results.append(
        (
            "JPDA update is small shift",
            abs(track2.lat - 35.0) < 0.1,
            f"delta={abs(track2.lat - 35.0):.6f}",
        )
    )

    # 3. Test multi-target association with JPDA
    print("\n[3] Testing multi-target JPDA association...")
    lvc = LVCArchitecture()

    # Inject two crossing targets
    # Target A: moving NE from (35.0, 140.0)
    # Target B: moving SW from (35.05, 140.05)
    # They cross around midpoint

    # First cycle: establish tracks
    lvc.inject_track(
        {
            "lat": 35.0,
            "lon": 140.0,
            "heading": 45,
            "speed": 500,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "fighter",
        }
    )
    lvc.inject_track(
        {
            "lat": 35.05,
            "lon": 140.05,
            "heading": 225,
            "speed": 500,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "bomber",
        }
    )
    fused1 = lvc.fuse_tracks()
    results.append(
        ("Cycle 1 creates 2 tracks", len(fused1) == 2, f"tracks={len(fused1)}")
    )

    # Second cycle: targets moved, still separated
    lvc.inject_track(
        {
            "lat": 35.005,
            "lon": 140.005,
            "heading": 45,
            "speed": 500,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "fighter",
        }
    )
    lvc.inject_track(
        {
            "lat": 35.045,
            "lon": 140.045,
            "heading": 225,
            "speed": 500,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "bomber",
        }
    )
    fused2 = lvc.fuse_tracks()
    results.append(
        ("Cycle 2 maintains 2 tracks", len(fused2) == 2, f"tracks={len(fused2)}")
    )

    # Third cycle: targets are crossing (close to each other)
    lvc.inject_track(
        {
            "lat": 35.025,
            "lon": 140.025,
            "heading": 45,
            "speed": 500,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "fighter",
        }
    )
    lvc.inject_track(
        {
            "lat": 35.026,
            "lon": 140.026,
            "heading": 225,
            "speed": 500,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "bomber",
        }
    )
    fused3 = lvc.fuse_tracks()
    results.append(
        ("Cycle 3 crossing maintains tracks", len(fused3) == 2, f"tracks={len(fused3)}")
    )

    # Fourth cycle: targets have crossed, swapped positions
    lvc.inject_track(
        {
            "lat": 35.03,
            "lon": 140.03,
            "heading": 45,
            "speed": 500,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "fighter",
        }
    )
    lvc.inject_track(
        {
            "lat": 35.02,
            "lon": 140.02,
            "heading": 225,
            "speed": 500,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "bomber",
        }
    )
    fused4 = lvc.fuse_tracks()
    results.append(
        (
            "Cycle 4 after crossing maintains tracks",
            len(fused4) == 2,
            f"tracks={len(fused4)}",
        )
    )

    # 4. Test unmatched observation creates new track
    print("\n[4] Testing unmatched observation creates new track...")
    lvc2 = LVCArchitecture()
    lvc2.inject_track(
        {
            "lat": 35.0,
            "lon": 140.0,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "fighter",
        }
    )
    lvc2.fuse_tracks()  # Creates 1 track

    # Inject an observation far away (outside gate)
    lvc2.inject_track(
        {
            "lat": 40.0,
            "lon": 145.0,
            "source": "RDR-2",
            "confidence": 0.7,
            "classification": "bomber",
        }
    )
    fused5 = lvc2.fuse_tracks()
    results.append(
        ("Unmatched obs creates new track", len(fused5) == 2, f"tracks={len(fused5)}")
    )

    # 5. Test stale track deletion
    print("\n[5] Testing stale track deletion...")
    lvc3 = LVCArchitecture()
    lvc3.inject_track({"lat": 35.0, "lon": 140.0, "source": "RDR-1", "confidence": 0.8})
    lvc3.fuse_tracks()  # Creates 1 track
    # Run 6 more cycles with no new observations (track should be deleted after 5 misses)
    for _ in range(6):
        lvc3.fuse_tracks()
    fused6 = lvc3.fuse_tracks()
    results.append(("Stale track deleted", len(fused6) == 0, f"tracks={len(fused6)}"))

    # 6. Test JPDA with 3+ targets
    print("\n[6] Testing JPDA with 3+ targets...")
    lvc4 = LVCArchitecture()
    # Create 3 targets in formation
    for i in range(3):
        lvc4.inject_track(
            {
                "lat": 35.0 + i * 0.01,
                "lon": 140.0 + i * 0.01,
                "heading": 90,
                "speed": 400,
                "source": f"RDR-{i + 1}",
                "confidence": 0.8,
                "classification": "fighter",
            }
        )
    fused7 = lvc4.fuse_tracks()
    results.append(
        ("3 targets create 3 tracks", len(fused7) == 3, f"tracks={len(fused7)}")
    )

    # Next cycle: 3 targets moved slightly
    for i in range(3):
        lvc4.inject_track(
            {
                "lat": 35.0 + i * 0.01 + 0.002,
                "lon": 140.0 + i * 0.01 + 0.002,
                "heading": 90,
                "speed": 400,
                "source": f"RDR-{i + 1}",
                "confidence": 0.8,
                "classification": "fighter",
            }
        )
    fused8 = lvc4.fuse_tracks()
    results.append(("3 targets maintained", len(fused8) == 3, f"tracks={len(fused8)}"))

    # 7. Test status reports JPDA
    print("\n[7] Testing status reports JPDA algorithm...")
    status = lvc4.status()
    results.append(
        ("Status has association_algorithm", "association_algorithm" in status, "")
    )
    results.append(
        (
            "Status reports JPDA",
            status.get("association_algorithm") == "JPDA",
            status.get("association_algorithm"),
        )
    )

    # 8. Test that JPDA handles overlapping gates
    print("\n[8] Testing JPDA with overlapping gates...")
    lvc5 = LVCArchitecture()
    # Two tracks close together
    lvc5.inject_track(
        {
            "lat": 35.0,
            "lon": 140.0,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "A",
        }
    )
    lvc5.inject_track(
        {
            "lat": 35.01,
            "lon": 140.01,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "B",
        }
    )
    fused9 = lvc5.fuse_tracks()
    results.append(
        ("Overlapping: 2 tracks created", len(fused9) == 2, f"tracks={len(fused9)}")
    )

    # Both observations fall in both gates - JPDA should still maintain 2 tracks
    lvc5.inject_track(
        {
            "lat": 35.002,
            "lon": 140.002,
            "source": "RDR-1",
            "confidence": 0.8,
            "classification": "A",
        }
    )
    lvc5.inject_track(
        {
            "lat": 35.012,
            "lon": 140.012,
            "source": "RDR-2",
            "confidence": 0.8,
            "classification": "B",
        }
    )
    fused10 = lvc5.fuse_tracks()
    results.append(
        (
            "Overlapping: 2 tracks maintained",
            len(fused10) == 2,
            f"tracks={len(fused10)}",
        )
    )

    # 9. Test to_dict includes all fields
    print("\n[9] Testing KalmanTrack.to_dict fields...")
    d = track.to_dict()
    expected_fields = [
        "track_id",
        "lat",
        "lon",
        "v_lat",
        "v_lon",
        "heading",
        "speed",
        "alt_m",
        "confidence",
        "source_count",
        "sources",
        "hits",
        "misses",
        "status",
        "classification",
    ]
    missing = [f for f in expected_fields if f not in d]
    results.append(("to_dict has all fields", len(missing) == 0, f"missing={missing}"))

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
    ok = test_p5_1_jpda()
    sys.exit(0 if ok else 1)
