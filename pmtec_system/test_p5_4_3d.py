#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P5-4: 3D Rendering Optimization Test
Verify shared geometry, delta-time animation, pixel ratio cap,
FPS counter, AI decision panel, MADDPG/JPDA data injection.
"""

import os
import sys
import json
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PMTEC_HEADLESS"] = "1"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def test_p5_4_3d_optimization():
    print("=" * 60)
    print("P5-4: 3D Rendering Optimization Test")
    print("=" * 60)

    results = []

    # 1. Generate 3D HTML from simulation
    print("\n[1] Running 60s simulation to generate state...")
    from services.grpc_server import PMTECEngine

    engine = PMTECEngine()
    ok, msg = engine.start_simulation("P5-4-3D-Test", 60, 42)
    print(f"  Start: {msg}")

    waited = 0
    while engine._running and waited < 70:
        time.sleep(5)
        waited += 5

    state = engine.get_state_dict()
    results.append(
        (
            "Simulation completes",
            state.get("total_entities", 0) > 0,
            f"entities={state.get('total_entities')}",
        )
    )

    # 2. Generate 3D HTML
    print("\n[2] Generating 3D HTML...")
    from visualization.three_d_display import ThreeDDisplay

    display = ThreeDDisplay()
    output_path = os.path.join(_SCRIPT_DIR, "data", "output", "pmtec_3d_p5_test.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_path = display.generate_html(state, output_path=output_path)
    results.append(("HTML generated", result_path == output_path, ""))
    results.append(("File exists", os.path.exists(output_path), ""))

    # 3. Read and verify HTML content
    print("\n[3] Verifying HTML content...")
    with open(output_path, "r", encoding="utf-8") as f:
        html = f.read()

    file_size = len(html)
    results.append(("HTML non-empty", file_size > 1000, f"size={file_size} bytes"))

    # P5-4 Optimization checks
    # 4. Shared geometry cache
    print("\n[4] Checking shared geometry cache (GEO object)...")
    results.append(("Has GEO cache", "var GEO" in html, ""))
    results.append(
        ("GEO.aircraft shared", "aircraft: new THREE.BoxGeometry" in html, "")
    )
    results.append(
        ("GEO.missile shared", "missile: new THREE.ConeGeometry" in html, "")
    )
    results.append(("GEO.sensorDome shared", "sensorDome:" in html, ""))
    results.append(("GEO.kalmanSphere shared", "kalmanSphere:" in html, ""))
    results.append(("GEO.terrain shared", "terrain:" in html, ""))

    # 5. Shared material cache
    print("\n[5] Checking shared material cache (MAT object)...")
    results.append(("Has MAT cache", "var MAT" in html, ""))
    results.append(("MAT.friendly shared", "friendly:" in html, ""))
    results.append(("MAT.hostile shared", "hostile:" in html, ""))
    results.append(("MAT.kalmanHigh shared", "kalmanHigh:" in html, ""))

    # 6. Pixel ratio cap
    print("\n[6] Checking pixel ratio cap...")
    results.append(
        ("Pixel ratio cap", "Math.min(window.devicePixelRatio, 2)" in html, "")
    )
    # Should appear at least twice (init + onResize)
    cap_count = html.count("Math.min(window.devicePixelRatio, 2)")
    results.append(
        ("Pixel ratio cap in init+resize", cap_count >= 2, f"count={cap_count}")
    )

    # 7. Delta-time animation
    print("\n[7] Checking delta-time animation...")
    results.append(("Has THREE.Clock", "new THREE.Clock()" in html, ""))
    results.append(("Uses getDelta", "clock.getDelta()" in html, ""))
    results.append(("Uses elapsed time", "clock.elapsedTime" in html, ""))
    results.append(("No fixed 0.016", "animTime += 0.016" not in html, ""))

    # 8. Conditional animation (animMeshes array)
    print("\n[8] Checking conditional animation...")
    results.append(("Has animMeshes array", "var animMeshes" in html, ""))
    results.append(
        (
            "Iterates animMeshes not entityMeshes",
            "for (var i = 0; i < animMeshes.length" in html,
            "",
        )
    )
    results.append(("Static flag on meshes", "userData.isStatic" in html, ""))
    # Count isStatic occurrences (should be on most static meshes)
    static_count = html.count("isStatic")
    results.append(
        ("Multiple static flags", static_count >= 5, f"count={static_count}")
    )

    # 9. Batched LineSegments
    print("\n[9] Checking batched LineSegments...")
    results.append(("Kalman velocity batched", "THREE.LineSegments" in html, ""))
    results.append(("Trajectory batched positions", "trajPositions" in html, ""))

    # 10. FPS counter
    print("\n[10] Checking FPS counter...")
    results.append(("Has FPS div", 'id="fps"' in html, ""))
    results.append(("Has FPS value element", 'id="fps-val"' in html, ""))
    results.append(("Has draw call counter", 'id="draw-val"' in html, ""))
    results.append(("Renders renderer.info", "renderer.info.render.calls" in html, ""))

    # 11. AI Decision Panel (MADDPG + JPDA)
    print("\n[11] Checking AI decision panel...")
    results.append(("Has AI panel div", 'id="ai-panel"' in html, ""))
    results.append(("Has ai-algo element", 'id="ai-algo"' in html, ""))
    results.append(("Has ai-trained element", 'id="ai-trained"' in html, ""))
    results.append(("Has ai-steps element", 'id="ai-steps"' in html, ""))
    results.append(("Has ai-jpda element", 'id="ai-jpda"' in html, ""))
    results.append(("MADDPG data injected", "maddpgInfo" in html, ""))
    results.append(("JPDA data injected", "jpdaInfo" in html, ""))
    results.append(("updateAIPanel function", "function updateAIPanel" in html, ""))

    # 12. Reduced polygon counts (compare to P4)
    print("\n[12] Checking reduced polygon counts...")
    # P4 had SphereGeometry(range, 24, 16, ...) for sensor domes
    # P5 should have lower segments
    results.append(("Sensor dome segments <= 12", "12, 8" in html, ""))
    results.append(("No 24-segment spheres", html.count("24, 16") == 0, ""))
    results.append(("No 32, 16 terrain segments", "64, 32" not in html, ""))
    results.append(("Terrain segments reduced", "32, 16" in html, ""))

    # 13. Power preference
    print("\n[13] Checking power preference...")
    results.append(("High-performance WebGL", "powerPreference" in html, ""))
    results.append(("Power high-performance value", "'high-performance'" in html, ""))

    # 14. P5 badge
    print("\n[14] Checking P5 branding...")
    results.append(("P5 in title", "P5" in html, ""))
    results.append(("P5 badge class", "badge-p5" in html, ""))
    results.append(("P5 in header", "P5 Optimized" in html, ""))

    # 15. Verify no P4 references left
    print("\n[15] Checking no P4 remnants...")
    results.append(("No P4 template reference", "_THREE_D_TEMPLATE_P4" not in html, ""))
    results.append(("No P4 badge", "badge-p4" not in html, ""))

    # 16. Verify entity data is injected
    print("\n[16] Checking entity data injection...")
    results.append(("Aircraft data injected", "var aircraft = [" in html, ""))
    results.append(("Missiles data injected", "var missiles = [" in html, ""))
    results.append(("Sensors data injected", "var sensors = [" in html, ""))
    results.append(("Kalman tracks injected", "var kalmanTracks = " in html, ""))

    # 17. MADDPG algorithm value check
    print("\n[17] Checking MADDPG algorithm in HTML...")
    # The algorithm should be MADDPG (Multi-Agent DDPG)
    ma_stats = state.get("ma_dqn_stats", {})
    algo = ma_stats.get("algorithm", "")
    results.append(("MADDPG algo in state", "MADDPG" in algo, algo[:40]))
    results.append(("MADDPG algo in HTML", "MADDPG" in html, ""))

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
    ok = test_p5_4_3d_optimization()
    sys.exit(0 if ok else 1)
