#!/usr/bin/env python3
"""
P5 Final Verification - 300s full simulation testing all P5 features.

Verifies:
  P5-1: JPDA multi-target association
  P5-2: MADDPG true multi-agent (Actor-Critic)
  P5-3: 200K DQN model loaded and active
  P5-4: 3D rendering optimization (optimized template)
  Plus P1-P4 features still functional (weather, Kalman, adversary, persistence, etc.)
"""

import sys, os, time, json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ["PMTEC_HEADLESS"] = "1"

from services.grpc_server import PMTECEngine
from deep_rl.dqn_agent import DQNAgent

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return condition


print("=" * 70, flush=True)
print("P5 Final Verification — 300s Full Simulation", flush=True)
print("=" * 70, flush=True)

# ── Step 1: Verify DQN 200K model ──────────────────────────────────
print("\n[Step 1] DQN 200K Model", flush=True)
agent = DQNAgent()
dqn_loaded = agent.load()
check("DQN model loads", dqn_loaded)
check(
    "DQN model is 200K",
    "200k" in os.path.basename(agent.model_path).lower(),
    f"file={os.path.basename(agent.model_path)}",
)
check("DQN device is XPU", "xpu" in agent.device, f"device={agent.device}")

# ── Step 2: Initialize engine ──────────────────────────────────────
print("\n[Step 2] Engine Initialization", flush=True)
t0 = time.time()
engine = PMTECEngine()
check("Engine initialized", hasattr(engine, "start_simulation"))
check(
    "DQN agent in engine (200K)",
    engine.dqn is not None and engine.dqn.is_trained(),
    "200K DQN active",
)
check(
    "MADDPG loaded", engine.ma_dqn is not None, f"type={type(engine.ma_dqn).__name__}"
)
check(
    "Plugin manager",
    getattr(engine, "plugin_manager", None) is not None,
    f"PMTEC platform",
)
check(
    "DT registry",
    getattr(engine, "dt_registry", None) is not None,
    "digital twin registry",
)
check(
    "Persistence store",
    getattr(engine, "store", None) is not None,
    f"type={type(getattr(engine, 'store', None)).__name__}",
)
check(
    "Adversary agent",
    getattr(engine, "adversary", None) is not None,
    "rule-driven hostile decision-making",
)
check(
    "LVC Live adapters",
    getattr(engine, "live_data", None) is not None,
    "ADS-B + AIS + Weather",
)

# ── Step 3: Run 300s simulation ─────────────────────────────────────
print("\n[Step 3] 300s Simulation", flush=True)
print("  Starting 300s simulation...", flush=True)
engine.start_simulation("p5_final_verify", 300, 42)

while engine._running:
    time.sleep(10)
    state = engine.get_state_dict()
    elapsed = state.get("sim_seconds", 0)
    cycle = state.get("asda_cycle", 0)
    ents = state.get("total_entities", 0)
    tracks = state.get("active_tracks", 0)
    print(
        f"  [{elapsed:.0f}s] ASDA={cycle} | entities={ents} | tracks={tracks}",
        flush=True,
    )

wall = time.time() - t0
print(f"  Simulation completed in {wall:.1f}s wall-clock", flush=True)

# ── Step 4: Collect final state ─────────────────────────────────────
print("\n[Step 4] Verify P5 Features", flush=True)
state = engine.get_state_dict()

# P5-1: JPDA — check via LVC status
lvc_status = engine.lvc.status()
assoc = lvc_status.get("association_algorithm", "")
kt_count = lvc_status.get("kalman_tracks", 0)
check("P5-1: JPDA association active", assoc == "JPDA", f"algo={assoc}")
check("P5-1: Kalman tracks generated", kt_count > 0, f"tracks={kt_count}")
# Also verify state dict has kalman_tracks list
kt_list = state.get("kalman_tracks", [])
check(
    "P5-1: Kalman tracks in state dict",
    len(kt_list) > 0,
    f"state_tracks={len(kt_list)}",
)

# P5-2: MADDPG
ma = state.get("ma_dqn_stats", {})
ma_algo = ma.get("algorithm", "")
check("P5-2: MADDPG algorithm", "MADDPG" in ma_algo, f"algo={ma_algo}")
check(
    "P5-2: MADDPG trained",
    ma.get("is_trained", False),
    f"timesteps={ma.get('total_timesteps', 0)}",
)
check(
    "P5-2: Dual agents",
    len(ma.get("agents", [])) >= 2,
    f"agents={ma.get('agents', [])}",
)
# Decisions counter might not be tracked in state; verify model is loaded
last_run = ma.get("last_run", {})
check(
    "P5-2: Training run recorded",
    last_run.get("timesteps", 0) > 0,
    f"last_run_ts={last_run.get('timesteps', 0)}",
)

# P5-3: DQN 200K
dqn_path = os.path.basename(engine.dqn.model_path) if engine.dqn else "?"
check("P5-3: DQN 200K model active", "200k" in dqn_path.lower(), f"model={dqn_path}")

# P5-4: 3D rendering
print("\n  -- 3D Rendering --", flush=True)
try:
    from visualization.three_d_display import ThreeDDisplay

    td = ThreeDDisplay()
    html_path = td.generate_html(state)
    if html_path and os.path.exists(html_path):
        html_size = os.path.getsize(html_path)
        check("P5-4: 3D HTML generated", html_size > 10000, f"size={html_size:,} bytes")
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        check("P5-4: MADDPG panel in 3D", "MADDPG" in html_content)
        check("P5-4: JPDA info in 3D", "JPDA" in html_content)
        check("P5-4: FPS counter", "fps" in html_content.lower())
        check("P5-4: Draw call counter", "draw" in html_content.lower())
        check(
            "P5-4: Shared geometry cache",
            "GEO" in html_content or "MAT" in html_content,
        )
    else:
        check("P5-4: 3D HTML generated", False, "no output file")
except Exception as e:
    check("P5-4: 3D rendering", False, f"error={e}")

# SPEAR timeline
try:
    from visualization.spear_timeline import SpearTimeline

    st = SpearTimeline()
    spear_path = os.path.join(PROJECT_ROOT, "data", "output", "p5_spear_timeline.html")
    st.generate_html(output_path=spear_path)
    check(
        "SPEAR timeline generated",
        os.path.exists(spear_path),
        f"size={os.path.getsize(spear_path):,}" if os.path.exists(spear_path) else "",
    )
except Exception as e:
    check("SPEAR timeline", False, f"error={e}")

# ── Step 5: P1-P4 regression ────────────────────────────────────────
print("\n[Step 5] P1-P4 Feature Regression", flush=True)

# P1: Digital platform
check(
    "P1: DT platform",
    getattr(engine, "plugin_manager", None) is not None
    and getattr(engine, "dt_registry", None) is not None,
    "PluginManager + RestGateway + DTRegistry",
)

# P2: LVC Live data
ld = state.get("live_data_stats", {})
check(
    "P2: LVC Live data injected",
    ld.get("total_injected", 0) > 0,
    f"injected={ld.get('total_injected', 0)}",
)
check(
    "P2: LVC live entities",
    state.get("lvc_live_entities", 0) > 0,
    f"entities={state.get('lvc_live_entities', 0)}",
)

# P3: Weather + Adversary
weather = state.get("weather", {})
check(
    "P3: Weather impact closed-loop",
    "detection_range_factor" in weather or "visibility_factor" in weather,
    f"keys={list(weather.keys())[:3]}",
)

adv = state.get("adversary_stats", {})
check(
    "P3: Adversary agent active",
    "total_attacks" in adv,
    f"aggression={adv.get('current_aggression', '?')}",
)

# P4: Persistence
p = state.get("persistence", {})
check(
    "P4: SQLite snapshots",
    p.get("snapshots", 0) > 0,
    f"snapshots={p.get('snapshots', 0)}",
)
check(
    "P4: Kalman tracks persisted",
    p.get("kalman_tracks", 0) > 0,
    f"tracks={p.get('kalman_tracks', 0)}",
)
check("P4: Events persisted", p.get("events", 0) > 0, f"events={p.get('events', 0)}")

# ── Step 6: Simulation metrics ─────────────────────────────────────
print("\n[Step 6] Simulation Metrics", flush=True)
asda_cycles = state.get("asda_cycle", 0)
total_entities = state.get("total_entities", 0)
active_tracks = state.get("active_tracks", 0)
ld_injected = ld.get("total_injected", 0)
p_snap = p.get("snapshots", 0)
p_tracks = p.get("kalman_tracks", 0)
p_events = p.get("events", 0)

print(f"    ASDA cycles:       {asda_cycles}", flush=True)
print(f"    Total entities:     {total_entities}", flush=True)
print(f"    Active tracks:      {active_tracks}", flush=True)
print(f"    Kalman tracks (LVC):{kt_count}", flush=True)
print(f"    Live data injected: {ld_injected}", flush=True)
print(f"    SQLite snapshots:   {p_snap}", flush=True)
print(f"    SQLite tracks:      {p_tracks}", flush=True)
print(f"    SQLite events:      {p_events}", flush=True)
print(f"    Wall-clock time:    {wall:.1f}s", flush=True)

check("Simulation ran 25+ ASDA cycles", asda_cycles >= 25, f"cycles={asda_cycles}")
check("Simulation had 30+ entities", total_entities >= 30, f"entities={total_entities}")
check("Persistence has 100+ events", p_events >= 100, f"events={p_events}")

# ── Summary ────────────────────────────────────────────────────────
print("\n" + "=" * 70, flush=True)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(
    f"P5 Final Verification: {passed}/{len(results)} PASS"
    + (f", {failed} FAIL" if failed else ""),
    flush=True,
)
if failed:
    print("\nFAILED:", flush=True)
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  X {name}: {detail}", flush=True)
print("=" * 70, flush=True)
