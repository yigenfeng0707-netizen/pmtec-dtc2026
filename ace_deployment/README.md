# ACE Deployment Engine

## DTC 2026 Level 2: ACE Distributed Deployment & Strike Response Algorithm

### Overview

This project implements the ACE (Agile Combat Employment) distributed deployment
optimization and strike response algorithm for the INDOPACOM theater. It is the
Level 2 deliverable for the DTC 2026 Digital Twin Body Challenge (Scene Development Track).

### Architecture

```
ace_deployment/
  config.py              Configuration constants (aircraft, threats, damage params)
  main.py                CLI entry point
  models/
    base.py              Military base model + base network graph
    aircraft.py          Aircraft model + fleet management
    threat.py            Threat model (DF-21D, DF-26, DF-17, KH-101, CJ-10)
  algorithms/
    deployment.py        ACE deployment optimizer (multi-objective greedy + local search)
    transfer.py          Emergency transfer planner (priority-based evacuation)
    damage.py            Damage assessment (Monte Carlo simulation)
    optimization.py      Multi-objective optimization (Pareto analysis)
  engine/
    asda_engine.py       ASDA loop orchestrator (Act-Sense-Decide-Adapt)
  visualization/
    map_viz.py           Interactive Leaflet HTML map generator
  data/
    bases.geojson        Level 1 base data (22 INDOPACOM bases)
```

### DTB Model Mapping

| Component | DTB Layer | Implementation |
|-----------|-----------|----------------|
| Base network | Battle Network | BaseNetwork graph with adjacency matrix |
| Aircraft | Plug-and-Play | Each aircraft is a deployable capability module |
| Deployment optimizer | Application Store | Capability distribution algorithm |
| ASDA engine | War Engine | Simulation driver with cycle control |
| Damage assessor | War Engine | Monte Carlo simulation engine |

### ASDA Loop Mapping

| Phase | Action | Implementation |
|-------|--------|----------------|
| Act | Execute deployment/transfer orders | DeploymentOptimizer + TransferPlanner |
| Sense | Detect threats, assess damage | ThreatPackage + DamageAssessor |
| Decide | Multi-objective optimization | MultiObjectiveOptimizer |
| Adapt | Re-optimize after damage | Post-strike recovery deployment |

### Key Algorithms

1. **ACE Deployment Optimizer** (`deployment.py`)
   - Multi-objective: minimize vulnerability, maximize strike, minimize distance
   - Phase 1: Identify dispersal candidates from hub bases (60% dispersion ratio)
   - Phase 2: Score spoke bases (capacity, defense, shelters, runway, geography)
   - Phase 3: Greedy assignment (high-value aircraft to best-scoring spokes)
   - Phase 4: Local search refinement (pairwise swaps to reduce vulnerability)

2. **Emergency Transfer Planner** (`transfer.py`)
   - Priority-based: F-35 > F-22 > F-15 > F-16 > tankers > ISR
   - Constraint: transfer time < threat alert-to-impact time
   - Nearest feasible destination assignment
   - Feasibility check with time margin calculation

3. **Damage Assessment** (`damage.py`)
   - Monte Carlo simulation (100+ iterations per threat)
   - CEP-based impact point distribution (2D normal)
   - Blast radius damage to aircraft (sheltered vs open parking)
   - Runway cratering model with repair time estimation
   - Infrastructure damage percentage calculation

4. **Multi-Objective Optimizer** (`optimization.py`)
   - 5 objectives: vulnerability, strike, diversity, SPOF risk, defense coverage
   - Shannon entropy for distribution diversity
   - Concentration ratio for single-point-of-failure risk
   - Weighted sum normalization
   - Pareto dominance comparison

### Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Run full simulation (PLA missile salvo scenario)
python main.py --scenario salvo --sim-runs 100

# Run single-strike scenario
python main.py --scenario single --sim-runs 50

# Custom seed for reproducibility
python main.py --seed 12345
```

### Output

The simulation generates:
1. `output/asda_simulation_report.json` - Complete JSON report with all cycles
2. `output/ace_deployment_map.html` - Interactive Leaflet map visualization

### Environment Compatibility

- Python 3.10+
- Windows + Intel Arc GPU compatible (no CUDA dependencies)
- No external GIS software required (all computation in pure Python)
