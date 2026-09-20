#!/usr/bin/env python3
"""
PMTEC Digital Battlefield Simulation System - DTC 2026 Level 3
Entry point: starts gRPC server, runs PMTEC scenario, generates tactical display.
DTB Model: 4 gRPC services (WarEngine, BattleNetwork, ApplicationStore, PlugAndPlay)
ASDA: Act -> Sense -> Decide -> Adapt loop
LVC: Live (sensors) + Virtual (CGF) + Constructive (command)
"""

import argparse
import json
import os
import sys
import time

# Ensure project root in path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import (
    ASDA_CYCLE_SECONDS,
    ASDA_PHASES,
    DTB_COMPONENTS,
    GRPC_HOST,
    GRPC_PORT,
    OUTPUT_DIR,
    SIM_DURATION_SECONDS,
    SIM_RANDOM_SEED,
)
from services.grpc_server import PMTECServer
from visualization.tactical_display import TacticalDisplay

# P0-1: Realtime tactical display
try:
    from realtime.realtime_display import RealtimeDisplay

    HAS_REALTIME = True
except ImportError:
    HAS_REALTIME = False

# P0-2: 3D battlefield visualization
try:
    from visualization.three_d_display import ThreeDDisplay

    HAS_3D = True
except ImportError:
    HAS_3D = False

# P1-1: SPEAR Interactive Replay Timeline
try:
    from visualization.spear_timeline import SpearTimeline

    HAS_SPEAK_TIMELINE = True
except ImportError:
    HAS_SPEAK_TIMELINE = False


def run_simulation(
    scenario_name: str = "PMTEC-Pacific",
    duration: int = SIM_DURATION_SECONDS,
    seed: int = SIM_RANDOM_SEED,
    generate_display: bool = True,
    export_report: bool = True,
    start_grpc: bool = True,
    saturation: bool = False,
):
    """Run the PMTEC simulation."""
    # P13: saturation scenario - heavier, more concurrent adversary pressure
    if saturation:
        os.environ["PMTEC_ADVERSARY_AGGRESSION"] = "0.8"
        os.environ["PMTEC_ADVERSARY_MAX_CONCURRENT"] = "12"
        os.environ["PMTEC_ADVERSARY_SALVO_MAX"] = "4"
        scenario_name = f"{scenario_name}-Saturation"
        print(
            "[SATURATION] aggression=0.8, max_concurrent=12, salvo_max=4"
        )
    print("=" * 70)
    print("PMTEC Digital Battlefield Simulation System")
    print("DTC 2026 Level 3 - Digital Twin Battlefield")
    print("=" * 70)
    print()

    # 1. Initialize PMTEC server (gRPC + simulation engine)
    server = PMTECServer(GRPC_HOST, GRPC_PORT)
    engine = server.engine

    # Load base data from Level 1
    base_count = engine.load_bases()
    print(f"[1/7] Loaded {base_count} military bases from Level 1 GeoJSON")

    # 2. Start gRPC server if requested
    if start_grpc:
        server.start()
        print(f"[2/7] gRPC server started at {server.address}")
        print(
            "       Services: WarEngine, BattleNetwork, ApplicationStore, PlugAndPlay"
        )
        print(f"       DTB Components: {len(DTB_COMPONENTS)}")
        for name, desc in DTB_COMPONENTS.items():
            print(f"         - {name}: {desc[:50]}...")
    else:
        print("[2/7] gRPC server skipped (standalone mode)")

    # P0-1: Start realtime WebSocket server and generate realtime display HTML
    realtime_display_path = None
    if HAS_REALTIME and engine.realtime:
        ws_ok = engine.realtime.start()
        if ws_ok:
            print("[2.5] Realtime WebSocket server: ws://localhost:8765")
        else:
            print("[2.5] Realtime: WebSocket unavailable (using file-based updates)")
        rd = RealtimeDisplay()
        realtime_display_path = rd.generate_html()
        print(f"       Realtime display: {realtime_display_path}")
    else:
        print("[2.5] Realtime display: module not available")

    # P1-2: Start REST API gateway
    if engine.rest_gateway:
        engine.rest_gateway.start()
        print("[2.6] REST API gateway: http://localhost:8080/api/v1/health")
    else:
        print("[2.6] REST API gateway: not available")

    # 3. Start simulation
    print(f"[3/7] Starting simulation: {scenario_name}")
    print(
        f"       Duration: {duration}s | Seed: {seed} | ASDA cycle: {ASDA_CYCLE_SECONDS}s"
    )
    print(f"       ASDA phases: {' -> '.join(ASDA_PHASES)}")
    print()

    success, msg = engine.start_simulation(scenario_name, duration, seed)
    if not success:
        print(f"ERROR: {msg}")
        return

    # 4. Monitor simulation progress
    print("[4/7] Simulation running...")
    if realtime_display_path:
        print(
            f"       Open realtime display: file:///{realtime_display_path.replace(os.sep, '/')}"
        )
    last_cycle = 0
    last_phase = ""
    while engine._running:
        state = engine.get_state_dict()
        cycle = state["asda_cycle"]
        phase = state["asda_phase"]
        if cycle != last_cycle or phase != last_phase:
            active_entities = state["total_entities"]
            active_tracks = state["active_tracks"]
            net_vuln = state["network_vulnerability"]
            print(
                f"  T+{state['sim_seconds']:6.0f}s | ASDA#{cycle} {phase:8s} | "
                f"Entities: {active_entities:3d} | Tracks: {active_tracks:3d} | "
                f"Vuln: {net_vuln:.1%}"
            )
            last_cycle = cycle
            last_phase = phase

        # Check if simulation is done
        if state["sim_seconds"] >= duration:
            break
        time.sleep(0.5)

    # Stop simulation
    engine.stop_simulation()
    print()

    # 5. Generate outputs
    print("[5/7] Generating outputs...")
    final_state = engine.get_state_dict()

    # Generate tactical display HTML
    display_path = None
    if generate_display:
        display = TacticalDisplay()
        events_for_display = engine.spear.events[-200:]
        display_path = display.generate_html(final_state, events_for_display)
        print(f"       Tactical display (2D): {display_path}")

    # P0-2: Generate 3D battlefield display HTML
    three_d_path = None
    if HAS_3D and generate_display:
        td = ThreeDDisplay()
        three_d_path = td.generate_html(final_state, engine.spear.events[-200:])
        if three_d_path:
            print(f"       3D display: {three_d_path}")

    # Export SPEAR report
    report_path = None
    if export_report:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        report_path = os.path.join(OUTPUT_DIR, "pmtec_spear_report.json")
        engine.spear.export_json(report_path)
        print(f"       SPEAR report: {report_path}")

    # Also export final state
    state_path = os.path.join(OUTPUT_DIR, "pmtec_final_state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(final_state, f, indent=2, ensure_ascii=False, default=str)
    print(f"       Final state: {state_path}")

    # P13: LLM AI situational analysis
    ai_analysis = None
    try:
        from services.llm_analyst import LLMAnalyst

        ai_analyst = LLMAnalyst()
        spear_report = engine.spear.generate_report()
        ai_analysis = ai_analyst.generate_report_files(
            final_state, spear_report, engine.spear.events[-500:]
        )
        if ai_analysis:
            # P13: cache on engine for REST /api/v1/analysis
            engine._ai_analysis = {
                "status": "generated",
                "model": ai_analyst.model,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "md_path": ai_analysis["md_path"],
                "html_path": ai_analysis["html_path"],
                "docx_path": ai_analysis.get("docx_path"),
                "markdown": ai_analysis["markdown"],
                "usage": ai_analyst.last_usage,
            }
            print(f"       AI situational analysis (md):  {ai_analysis['md_path']}")
            print(f"       AI situational analysis (html): {ai_analysis['html_path']}")
        else:
            print("       AI situational analysis: unavailable (skipped)")
    except Exception as e:  # graceful degradation: never break the sim pipeline
        print(f"       AI situational analysis: failed ({e})")

    # P0-3: Save learning parameters
    learning_path = None
    if engine.learning:
        learning_path = engine.learning.save()
        if learning_path:
            print(f"       Learning params: {learning_path}")

    # P0-1: Stop realtime server
    if engine.realtime:
        engine.realtime.stop()
        print("       Realtime server stopped")

    # P1-2: Stop REST gateway
    if engine.rest_gateway:
        engine.rest_gateway.stop()
        print("       REST gateway stopped")

    # P1-2: Shutdown plugins
    if engine.plugin_manager:
        engine.plugin_manager.shutdown()
        print("       Plugins shut down")

    # P1-1: Generate SPEAR interactive replay timeline
    spear_timeline_path = None
    if HAS_SPEAK_TIMELINE:
        try:
            timeline = SpearTimeline()
            timeline.load_from_spear(engine.spear, engine._bases)
            spear_timeline_path = timeline.generate_html()
            print(f"       SPEAR timeline: {spear_timeline_path}")
        except Exception as e:
            print(f"       SPEAR timeline error: {e}")

    # Stop gRPC server
    if start_grpc:
        server.stop()
        print("\ngRPC server stopped.")

    # Print summary
    print()
    print("=" * 70)
    print("PMTEC Simulation Complete - Summary")
    print("=" * 70)
    report = engine.spear.generate_report()
    print(f"  Simulation time: {final_state['sim_seconds']:.0f}s")
    print(f"  ASDA cycles: {final_state['asda_cycle']}")
    print(f"  Total events: {report['total_events']}")
    print(f"  Active entities: {final_state['total_entities']}")
    print(f"  Active tracks: {final_state['active_tracks']}")
    print(f"  Network vulnerability: {final_state['network_vulnerability']:.1%}")
    print()
    print("  Event distribution:")
    for evt_type, count in sorted(report["event_distribution"].items()):
        print(f"    {evt_type:25s}: {count:4d}")
    print()
    print("  ASDA phase activity:")
    for phase, count in report["asda_phase_activity"].items():
        print(f"    {phase:8s}: {count:4d} events")
    print()
    print("  DTB Model services demonstrated:")
    for name, desc in DTB_COMPONENTS.items():
        print(f"    {name}: {desc}")
    print()

    # P0-3: Print learning summary
    if engine.learning:
        lstats = engine.learning.get_statistics()
        print("  ASDA Learning (P0-3 UCB1/Q-Learning):")
        print(f"    Cycles completed: {lstats.get('cycles_completed', 0)}")
        print("    Intercept strategy success rates:")
        for s, r in lstats.get("intercept_success_rates", {}).items():
            print(f"      {s:15s}: {r:.0%}")
        print(f"    Q-learning states explored: {lstats.get('qlearning_states', 0)}")
        print(f"    Q-learning actions taken: {lstats.get('qlearning_actions', 0)}")
        print(f"    Sensor deployments: {lstats.get('sensor_deployments', 0)}")
        print()

    # Deep RL: Print DQN agent summary
    if engine.dqn:
        dstats = engine.dqn.get_statistics()
        print("  Deep RL (DQN + PyTorch):")
        print(f"    Algorithm: {dstats.get('algorithm', 'DQN')}")
        print(f"    Trained: {dstats.get('is_trained', False)}")
        print(f"    Training runs: {dstats.get('training_runs', 0)}")
        print(f"    Total timesteps: {dstats.get('total_timesteps', 0)}")
        last = dstats.get("last_run", {})
        if last:
            print(
                f"    Last training: {last.get('elapsed_seconds', 0):.1f}s on {last.get('device', 'cpu')}"
            )
        print(f"    Policy: {dstats.get('policy_arch', 'N/A')}")
        print(f"    Device: {dstats.get('device', 'cpu')}")
        print()

    # P1: Print platform and threat summary
    if engine.plugin_manager:
        plugins = engine.plugin_manager.list_plugins()
        print(f"  Platform (P1-2): {len(plugins)} plugins registered")
        for p in plugins:
            print(
                f"    {p['plugin_id']}: {p['name']} v{p['version']} ({'active' if p['active'] else 'inactive'})"
            )
        # Threat summary from multi-threat plugin
        mt = engine.plugin_manager.get_plugin("builtin-multi-threat")
        if mt:
            ts = mt.call("get_threat_summary") or {}
            print("  Multi-Threat (P1-3):")
            print(f"    Active EW threats: {ts.get('ew_active', 0)}")
            print(f"    Active cyber threats: {ts.get('cyber_active', 0)}")
            print(f"    Detected cyber threats: {ts.get('cyber_detected', 0)}")
        print()
    if engine.dt_registry:
        dt_stats = engine.dt_registry.aggregate_stats()
        print(f"  Digital Twin Registry: {dt_stats['total_instances']} instance(s)")
        if engine.twin_sync:
            ts = engine.twin_sync.summary()
            print(
                f"  Digital Twin Sync: {ts['total_twins']} twins, "
                f"avg fidelity {ts['avg_fidelity']:.1%}, "
                f"{ts['engine_syncs']} engine syncs"
            )
        print()
    if display_path:
        print(f"  2D tactical display: file:///{display_path.replace(os.sep, '/')}")
    if three_d_path:
        print(f"  3D display:          file:///{three_d_path.replace(os.sep, '/')}")
    if realtime_display_path:
        print(
            f"  Realtime display:    file:///{realtime_display_path.replace(os.sep, '/')}"
        )
    if spear_timeline_path:
        print(
            f"  SPEAR timeline:      file:///{spear_timeline_path.replace(os.sep, '/')}"
        )
    if ai_analysis:
        print(
            f"  AI analysis (html):  file:///{ai_analysis['html_path'].replace(os.sep, '/')}"
        )
    if report_path:
        print(f"  SPEAR report:        {report_path}")
    if learning_path:
        print(f"  Learning params:     {learning_path}")
    print("=" * 70)

    return {
        "state": final_state,
        "report": report,
        "display_path": display_path,
        "report_path": report_path,
        "three_d_path": three_d_path,
        "realtime_display_path": realtime_display_path,
        "spear_timeline_path": spear_timeline_path,
        "learning_path": learning_path,
        "ai_analysis": ai_analysis,
    }


def main():
    parser = argparse.ArgumentParser(
        description="PMTEC Digital Battlefield Simulation - DTC 2026 Level 3"
    )
    parser.add_argument(
        "--scenario",
        default="PMTEC-Pacific",
        help="Scenario name (default: PMTEC-Pacific)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=SIM_DURATION_SECONDS,
        help=f"Duration in seconds (default: {SIM_DURATION_SECONDS})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SIM_RANDOM_SEED,
        help=f"Random seed (default: {SIM_RANDOM_SEED})",
    )
    parser.add_argument(
        "--no-grpc",
        action="store_true",
        help="Run without gRPC server (standalone mode)",
    )
    parser.add_argument(
        "--no-display", action="store_true", help="Skip tactical display generation"
    )
    parser.add_argument(
        "--no-report", action="store_true", help="Skip SPEAR report export"
    )
    parser.add_argument(
        "--saturation",
        action="store_true",
        help="Saturation attack scenario (aggression=0.8, max 12 concurrent threats)",
    )
    args = parser.parse_args()

    run_simulation(
        scenario_name=args.scenario,
        duration=args.duration,
        seed=args.seed,
        generate_display=not args.no_display,
        export_report=not args.no_report,
        start_grpc=not args.no_grpc,
        saturation=args.saturation,
    )


if __name__ == "__main__":
    main()
