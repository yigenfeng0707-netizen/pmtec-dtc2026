#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ACE Deployment Engine - Main CLI Entry Point
DTC 2026 Level 2: ACE Distributed Deployment & Strike Response Algorithm

Usage:
  python main.py                    Run full simulation with default scenario
  python main.py --scenario salvo   Run PLA missile salvo scenario
  python main.py --scenario single  Run single-strike scenario
  python main.py --interactive       Interactive mode
"""

import argparse
import json
import os
import sys

# Add project root to path for standalone execution
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.base import BaseNetwork
from models.aircraft import Aircraft, AircraftFleet
from models.threat import Threat, ThreatPackage
from algorithms.deployment import DeploymentOptimizer
from algorithms.transfer import TransferPlanner
from algorithms.damage import DamageAssessor
from algorithms.optimization import MultiObjectiveOptimizer
from engine.asda_engine import ASDAEngine
from visualization.map_viz import MapVisualizer
from config import BASES_GEOJSON, OUTPUT_DIR


def run_simulation(scenario_name: str = "salvo", n_sim: int = 100, seed: int = 42):
    """Run complete ASDA simulation and generate all outputs."""
    print("=" * 70)
    print("ACE DEPLOYMENT ENGINE - DTC 2026 Level 2")
    print("ACE Distributed Deployment & Strike Response Algorithm")
    print("=" * 70)

    # Initialize engine
    engine = ASDAEngine(geojson_path=BASES_GEOJSON, seed=seed)
    engine.damage_assessor = DamageAssessor(
        engine.network, engine.fleet, n_simulations=n_sim
    )
    engine.initialize_fleet()

    print(f"\n[INIT] Loaded {len(engine.network.bases)} bases from GeoJSON")
    print(
        f"[INIT] Fleet: {engine.fleet.total} aircraft across "
        f"{len([b for b in engine.network.bases.values() if b.current_aircraft])} bases"
    )
    print(f"[INIT] ACE Hubs: {len(engine.network.hubs())}")
    print(f"[INIT] Network vulnerability: {engine.network.network_vulnerability:.2f}")

    # Select scenario
    if scenario_name == "salvo":
        threat_pkg = ThreatPackage.scenario_china_salvo(engine.network)
    elif scenario_name == "single":
        threat_pkg = ThreatPackage.scenario_single_strike("GU-ANDERSEN", "DF-26")
    else:
        threat_pkg = ThreatPackage.scenario_china_salvo(engine.network)

    print(f"\n[SCENARIO] {threat_pkg.scenario_name}")
    print(f"[SCENARIO] {threat_pkg.description}")
    print(
        f"[SCENARIO] {len(threat_pkg.threats)} threats, "
        f"{threat_pkg.total_warheads} warheads total"
    )
    print(f"[SCENARIO] Targeted bases: {', '.join(threat_pkg.targeted_bases)}")

    # Run simulation
    print("\n[ASDA] Starting simulation...")
    report = engine.run_full_simulation(threat_pkg)

    # Print cycle log
    print("\n" + "-" * 70)
    print("ASDA CYCLE LOG")
    print("-" * 70)
    for cycle in report.cycles:
        print(f"  [{cycle.timestamp}] {cycle.phase.upper():8s} | {cycle.summary}")

    # Print deployment plan summary
    dp = report.deployment_plan
    print("\n" + "-" * 70)
    print("DEPLOYMENT OPTIMIZATION RESULTS")
    print("-" * 70)
    print(f"  Total transfers:          {dp.get('total_transfers', 0)}")
    print(f"  Vulnerability before:     {dp.get('vulnerability_before', 0):.2f}")
    print(f"  Vulnerability after:      {dp.get('vulnerability_after', 0):.2f}")
    print(
        f"  Vulnerability reduction:  {dp.get('vulnerability_reduction_pct', 0):.1f}%"
    )
    print(f"  Strike retention:         {dp.get('strike_retention_pct', 0):.1f}%")
    print(
        f"  Total transfer distance:  {dp.get('total_transfer_distance_km', 0):.1f} km"
    )
    print(f"  Hubs depleted:            {len(dp.get('hubs_depleted', []))}")
    print(f"  Spokes reinforced:        {len(dp.get('spokes_reinforced', []))}")

    if "recovery" in dp:
        rc = dp["recovery"]
        print(f"\n  Post-strike recovery:")
        print(f"    Recovery transfers:     {rc.get('total_transfers', 0)}")
        print(f"    Vulnerability after:    {rc.get('vulnerability_after', 0):.2f}")

    # Print transfer plan summary
    print("\n" + "-" * 70)
    print("EMERGENCY TRANSFER PLANS")
    print("-" * 70)
    for tp in report.transfer_plans:
        print(f"  {tp['threat_type']} -> {tp['target_base']}")
        print(f"    Response time:    {tp['response_time_min']:.1f} min")
        print(
            f"    Evacuated:        {tp['evacuated']} aircraft (value: {tp['value_saved']})"
        )
        print(
            f"    Stranded:         {tp['stranded']} aircraft (value: {tp['value_lost']})"
        )
        print(f"    Evacuation rate:  {tp['evacuation_rate_pct']:.1f}%")

    # Print damage report
    dr = report.damage_report
    print("\n" + "-" * 70)
    print("DAMAGE ASSESSMENT REPORT")
    print("-" * 70)
    print(f"  Scenario:           {dr.get('scenario', '')}")
    print(f"  Total warheads:      {dr.get('total_warheads', 0)}")
    print(f"  Total aircraft lost: {dr.get('total_aircraft_lost', 0)}")
    print(f"  Total value lost:    {dr.get('total_value_lost', 0)}")
    print(f"  Runways disabled:    {dr.get('runways_disabled', 0)}")
    print(f"  Recovery time:       {dr.get('estimated_recovery_hours', 0):.1f} hours")
    print(f"  Monte Carlo runs:    {dr.get('monte_carlo_runs', 0)}")
    for bh in dr.get("bases_hit", []):
        print(f"\n  Base: {bh['base_name']} ({bh['base_id']})")
        print(f"    Aircraft destroyed:     {bh['aircraft_destroyed']}")
        print(f"    Sheltered survived:      {bh['aircraft_sheltered_survived']}")
        print(f"    Runway destroyed:        {bh['runway_destroyed']}")
        print(f"    Runway repair:           {bh['runway_repair_hours']:.1f}h")
        print(f"    Craters:                 {bh['crater_count']}")
        print(f"    Infrastructure damage:   {bh['infrastructure_destroyed_pct']:.1f}%")

    # Print optimization results
    print("\n" + "-" * 70)
    print("MULTI-OBJECTIVE OPTIMIZATION RESULTS")
    print("-" * 70)
    for i, opt in enumerate(report.optimization_results):
        label = "Initial" if i == 0 else "Post-strike"
        print(f"\n  {label} state:")
        print(f"    Total score: {opt['total_score']:.4f}")
        for obj in opt.get("objectives", []):
            print(
                f"    {obj['name']:30s}: {obj['value']:10.2f} "
                f"(norm: {obj['normalized']:.3f}, w: {obj['weight']})"
            )

    # Generate visualization
    print("\n" + "-" * 70)
    print("GENERATING VISUALIZATION")
    print("-" * 70)
    viz = MapVisualizer(engine.network, engine.fleet)
    viz_path = viz.generate_deployment_map(
        plan=engine.deployer.plan,
        threats=threat_pkg,
        damage_report=engine.damage_assessor.assess_scenario(threat_pkg),
    )
    print(f"  Map saved: {viz_path}")

    # Save JSON report
    report_path = engine.save_report()
    print(f"  Report saved: {report_path}")

    # Final state
    fs = report.final_state
    print("\n" + "=" * 70)
    print("FINAL NETWORK STATE")
    print("=" * 70)
    nw = fs.get("network", {})
    fl = fs.get("fleet", {})
    print(f"  Total bases:        {nw.get('total_bases', 0)}")
    print(
        f"  Total aircraft:     {fl.get('total', 0)} (active: {fl.get('active', 0)}, "
        f"destroyed: {fl.get('destroyed', 0)})"
    )
    print(f"  Network vulnerability: {nw.get('network_vulnerability', 0):.2f}")

    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"\nDeliverables:")
    print(f"  1. Simulation Report: {report_path}")
    print(f"  2. Deployment Map:    {viz_path}")
    print(f"  3. Source Code:       {os.path.join(project_root, '')}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="ACE Deployment Engine - DTC 2026 Level 2"
    )
    parser.add_argument(
        "--scenario",
        choices=["salvo", "single"],
        default="salvo",
        help="Threat scenario to run",
    )
    parser.add_argument(
        "--sim-runs",
        type=int,
        default=100,
        help="Number of Monte Carlo simulations for damage assessment",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    run_simulation(
        scenario_name=args.scenario,
        n_sim=args.sim_runs,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
