"""
PMTEC gRPC Server - Implements DTB Model four services.
DTB Model: WarEngine (simulation) + BattleNetwork (tracks) + ApplicationStore (capabilities) + PlugAndPlay (discovery)
ASDA: Full cycle (Act->Sense->Decide->Adapt) executed each simulation cycle.
"""

import sys
import os
import json
import time
import math
import random
import threading
import uuid
from concurrent import futures
from typing import Optional

# Add generated proto path
_GEN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto", "generated"
)
if _GEN_DIR not in sys.path:
    sys.path.insert(0, _GEN_DIR)

import grpc
import dtb_model_pb2 as pb
import dtb_model_pb2_grpc as pb_grpc

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import (
    GRPC_HOST,
    GRPC_PORT,
    SIM_TICK_SECONDS,
    SIM_DURATION_SECONDS,
    SIM_RANDOM_SEED,
    ASDA_CYCLE_SECONDS,
    ASDA_PHASES,
    BASES_GEOJSON,
    OUTPUT_DIR,
    DTB_COMPONENTS,
    AIRCRAFT_SPEED_KMH,
)
import config as pmtec_config
from core.event_bus import EventBus, Event
from core.simulation_clock import SimulationClock
from core.lvc_architecture import LVCArchitecture, haversine
from models.entity import AircraftEntity, MissileEntity, SensorEntity, BattlefieldEntity
from models.track import TrackManager, Track
from models.adversary_agent import AdversaryAgent
from services.spear_replay import SpearReplay

# P0 upgrades: learning manager + realtime push
try:
    from learning import LearningManager

    _learning_available = True
except ImportError:
    _learning_available = False

try:
    from realtime import RealtimeServer

    _realtime_available = True
except ImportError:
    _realtime_available = False

# Deep RL: DQN agent for ASDA decision-making (stable_baselines3 + PyTorch)
try:
    from deep_rl.dqn_agent import DQNAgent
    from deep_rl.multi_agent_dqn import MultiAgentDQN
    from deep_rl.maddpg_agent import MADDPGAgent
    from deep_rl.multi_agent_env import INTERCEPT_AGENT, DISPERSAL_AGENT
    import numpy as np

    _dqn_available = True
except ImportError:
    _dqn_available = False
    DQNAgent = None
    MultiAgentDQN = None
    MADDPGAgent = None

# P1-2: Platform components
try:
    from dt_platform import PluginManager, RestGateway, DTRegistry

    _platform_available = True
except ImportError:
    _platform_available = False

# P2-3: LVC Live real-world data adapters (ADS-B / AIS / Weather)
try:
    from live_data import LiveAdapterManager

    _live_data_available = True
except ImportError:
    _live_data_available = False

# P4-1: SQLite persistence layer
try:
    from persistence import SimulationStateStore

    _persistence_available = True
except ImportError:
    _persistence_available = False

# P7: Security & Authentication (mTLS + JWT + RBAC + Audit)
try:
    from security import (
        AuthManager,
        RBACManager,
        AuditLogger,
        CertificateManager,
        AuthInterceptor,
    )

    _security_available = True
except ImportError:
    _security_available = False


class PMTECEngine:
    """Core PMTEC simulation engine - drives the ASDA loop."""

    def __init__(self):
        self.clock = SimulationClock(SIM_TICK_SECONDS)
        self.event_bus = EventBus()
        self.lvc = LVCArchitecture()
        self.track_mgr = TrackManager()
        self.spear = SpearReplay()
        self.asda_phase_idx = 0
        self.asda_cycle_count = 0
        self.scenario_name = ""
        self.duration = SIM_DURATION_SECONDS
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._bases: list[dict] = []
        self._entities: list[BattlefieldEntity] = []
        self._sensors: list[SensorEntity] = []
        self._missiles: list[MissileEntity] = []
        self._missile_stats = {"intercepted": 0, "impacted": 0, "total_launched": 0}
        self._app_store: dict[str, dict] = {}
        self._components: dict[str, dict] = {}
        self._start_time: float = 0
        self._init_app_store()
        self._init_components()
        random.seed(SIM_RANDOM_SEED)

        # P0-3: Learning manager for ASDA Adapt
        self.learning = None
        if _learning_available:
            self.learning = LearningManager()
            print(
                "[Engine] Learning manager initialized (UCB1 + Q-learning + Sensor opt)"
            )

        # P0-1: Realtime WebSocket push server
        self.realtime = None
        if _realtime_available:
            self.realtime = RealtimeServer()

        # Deep RL: DQN agent for ASDA decisions
        self.dqn = None
        if _dqn_available:
            self.dqn = DQNAgent()
            loaded = self.dqn.load()
            if loaded:
                print("[Engine] DQN model loaded (deep RL active)")
            else:
                print("[Engine] DQN not trained yet (run train_dqn.py to enable)")

        # P5-2: Multi-Agent MADDPG (preferred) or P4-4 IQL (fallback)
        self.ma_dqn = None
        if _dqn_available and MADDPGAgent is not None:
            maddpg = MADDPGAgent()
            if maddpg.load():
                self.ma_dqn = maddpg
                print("[Engine] Multi-Agent MADDPG models loaded (Actor-Critic)")
            else:
                print("[Engine] MADDPG not trained yet, trying IQL")
        if self.ma_dqn is None and _dqn_available and MultiAgentDQN is not None:
            self.ma_dqn = MultiAgentDQN()
            ma_loaded = self.ma_dqn.load()
            if ma_loaded:
                print(
                    "[Engine] Multi-Agent IQL models loaded (intercept + dispersal agents)"
                )
            else:
                print(
                    "[Engine] Multi-Agent IQL not trained yet (run train_multi_agent.py)"
                )
                self.ma_dqn = None

        # P1-2: Platform components (plugin manager, REST gateway, DT registry)
        self.plugin_manager = None
        self.rest_gateway = None
        self.dt_registry = None
        if _platform_available:
            self.plugin_manager = PluginManager()
            self.plugin_manager.load_all(self)
            self.dt_registry = DTRegistry()
            self.dt_registry.register(
                {
                    "name": "PMTEC-Pacific-Main",
                    "scenario": "PMTEC-Pacific",
                    "tags": ["primary", "indopacom"],
                }
            )
            self.dt_registry.attach_engine(
                self.dt_registry.get_default().instance_id, self
            )
            self.rest_gateway = RestGateway(
                engine=self,
                plugin_manager=self.plugin_manager,
                dt_registry=self.dt_registry,
            )
            print(
                "[Engine] Platform initialized: PluginManager + RestGateway + DTRegistry"
            )

        # Track intercept outcomes for learning
        self._intercept_results: list[dict] = []
        self._dispersal_actions: list[dict] = []

        # P3-4: Rule-driven adversary agent (replaces random missile launch)
        self.adversary = AdversaryAgent(
            aggression_level=0.3,
            seed=SIM_RANDOM_SEED,
            max_concurrent_threats=8,
        )
        print(
            "[Engine] AdversaryAgent initialized (rule-driven hostile decision-making)"
        )

        # P2-3: LVC Live real-world data adapters
        # P7-v2: use_real_api now config-driven (LIVE_DATA_USE_REAL_API)
        self.live_data = None
        self._live_injection_stats: dict = {}
        if _live_data_available:
            self.live_data = LiveAdapterManager()  # reads config for use_real_api
            mode = (
                "real API + fallback"
                if self.live_data.adsb.use_real_api
                else "simulation"
            )
            print(
                f"[Engine] LVC Live data adapters initialized (ADS-B + AIS + Weather) [{mode}]"
            )

        # P4-1: SQLite persistence layer
        self.store = None
        if _persistence_available:
            self.store = SimulationStateStore()
            print(
                "[Engine] Persistence layer initialized (SQLite snapshots + tracks + events)"
            )

    def _init_app_store(self):
        """Initialize the DTB Application Store with capability modules."""
        apps = [
            (
                "app-f35-strike",
                "F-35A Strike Package",
                "v2.1",
                "strike",
                "Stealth strike mission planning with sensor fusion and threat avoidance",
            ),
            (
                "app-iamd-defense",
                "IAMD Integrated Air Defense",
                "v3.0",
                "defense",
                "Multi-layer air defense: PAC-3, THAAD, Aegis coordination via C2BMC",
            ),
            (
                "app-isr-collection",
                "ISR Sensor Collection",
                "v1.8",
                "isr",
                "Multi-INT sensor tasking: SIGINT, GEOINT, MASINT fusion and tipper-cueing",
            ),
            (
                "app-ace-dispersal",
                "ACE Agile Combat Employment",
                "v2.5",
                "logistics",
                "Distributed aircraft dispersal algorithm with risk-weighted basing",
            ),
            (
                "app-spear-replay",
                "SPEAR Replay Analysis",
                "v1.2",
                "analysis",
                "Post-action review with event timeline reconstruction and ASDA metrics",
            ),
            (
                "app-jad-ai",
                "JAD-AI Joint All-Domain AI",
                "v0.9-beta",
                "decision",
                "AI-assisted decision support across all domains with human-on-the-loop",
            ),
        ]
        for app_id, name, ver, cat, desc in apps:
            self._app_store[app_id] = {
                "app_id": app_id,
                "name": name,
                "version": ver,
                "category": cat,
                "description": desc,
            }

    def _init_components(self):
        """Initialize Plug-and-Play registered components."""
        components = [
            (
                "comp-sim-core",
                "simulation_engine",
                "pmtec://sim:50051",
                {"framework": "PMTEC", "lvc": "all"},
            ),
            (
                "comp-track-fusion",
                "track_manager",
                "pmtec//track:50051",
                {"fusion": "kinematic", "sources": "multi"},
            ),
            (
                "comm-grpc-bridge",
                "grpc_interface",
                "pmtec//grpc:50051",
                {"proto": "dtb_model.proto", "services": "4"},
            ),
            (
                "comp-asda-loop",
                "decision_engine",
                "pmtec//asda:50051",
                {"cycle_s": str(ASDA_CYCLE_SECONDS), "phases": "4"},
            ),
        ]
        for comp_id, comp_type, endpoint, meta in components:
            self._components[comp_id] = {
                "component_id": comp_id,
                "component_type": comp_type,
                "endpoint": endpoint,
                "metadata": meta,
            }

    def load_bases(self, geojson_path: str = None):
        """Load base data from GeoJSON (Level 1 data)."""
        import re

        path = geojson_path or BASES_GEOJSON
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._bases = []
        # Match aircraft designations: F-35A, KC-135, B-1B, CV-22, F/A-18, etc.
        ac_pattern = re.compile(r"\b([A-Z]{1,3}[-/]\d+[A-Z]?)\b")
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [0, 0])
            # Parse aircraft string to list of types
            aircraft_str = props.get("aircraft", "")
            found = ac_pattern.findall(aircraft_str) if aircraft_str else []
            # Normalize common types: F-35 -> F-35A, F-16 -> F-16C, F-22 -> F-22A
            normalize = {
                "F-35": "F-35A",
                "F-35B": "F-35A",
                "F-16": "F-16C",
                "F-22": "F-22A",
                "F-15": "F-15C",
            }
            aircraft_types = list(set(normalize.get(t, t) for t in found))
            base = {
                "id": props.get("id", props.get("name", "")),
                "name": props.get("name", ""),
                "lat": coords[1] if len(coords) >= 2 else props.get("lat", 0),
                "lon": coords[0] if len(coords) >= 2 else props.get("lon", 0),
                "region": props.get("region", ""),
                "military_branch": props.get("branch", ""),
                "is_ace_hub": props.get("ace_hub", False),
                "aircraft_types": aircraft_types,
                "sensor_types": ["AN/TPS-80"],
            }
            self._bases.append(base)
        return len(self._bases)

    def setup_scenario(self, scenario_name: str = "PMTEC-Pacific"):
        """Initialize the battlefield with entities from base data."""
        self.scenario_name = scenario_name
        if not self._bases:
            self.load_bases()

        # Create Live layer: sensors at each base
        for base in self._bases:
            for sensor_type in base.get("sensor_types", ["AN/TPS-80"]):
                sensor = SensorEntity(
                    sensor_type=sensor_type,
                    lat=base["lat"],
                    lon=base["lon"],
                    base_id=base["id"],
                    detection_range_km=400,
                )
                self.lvc.live.add_entity(sensor)
                self._sensors.append(sensor)

        # Create Virtual layer: aircraft at ACE hubs
        ace_hubs = [b for b in self._bases if b.get("is_ace_hub")]
        for base in ace_hubs:
            for ac_type in base.get("aircraft_types", ["F-35A"]):
                count = 4 if ac_type.startswith("F-3") else 2
                for i in range(count):
                    ac = AircraftEntity(
                        ac_type=ac_type,
                        base_id=base["id"],
                        lat=base["lat"] + random.uniform(-0.05, 0.05),
                        lon=base["lon"] + random.uniform(-0.05, 0.05),
                        callsign=f"{base['id'][:4].upper()}{ac_type[:3]}{i + 1:02d}",
                    )
                    ac.assign_mission("patrol")
                    self.lvc.virtual.add_entity(ac)
                    self._entities.append(ac)

        # Create Constructive layer: high-level command entities
        cmd_entity = BattlefieldEntity(
            id="CMD-INDOPACOM",
            entity_type="command",
            subtype="JOC",
            lat=21.35,
            lon=-157.96,  # INDOPACOM HQ Honolulu
            affiliation="friendly",
            status="active",
        )
        self.lvc.constructive.add_entity(cmd_entity)
        self._entities.append(cmd_entity)

        # Record initial state
        self.spear.record_snapshot(self.get_state_dict())

    def start_simulation(self, scenario_name: str, duration: int, seed: int):
        """Start the PMTEC simulation."""
        if self._running:
            return False, "Simulation already running"

        random.seed(seed)
        self.duration = duration or SIM_DURATION_SECONDS
        self.setup_scenario(scenario_name)

        self._running = True
        self._stop_flag.clear()
        self.clock.start()
        self._start_time = time.time()

        # Start simulation thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        self._emit_event(
            "sim_start",
            "system",
            "PMTEC simulation started",
            {
                "scenario": scenario_name,
                "duration": duration,
                "seed": seed,
                "asda_phase": "Act",
                "lvc_layer": "Constructive",
            },
        )
        return True, f"Simulation started: {scenario_name}"

    def stop_simulation(self):
        """Stop the simulation."""
        if not self._running:
            return False, "Simulation not running"
        self._stop_flag.set()
        self._running = False
        self.clock.stop()
        if self._thread:
            self._thread.join(timeout=5)
        self._emit_event(
            "sim_stop",
            "system",
            "PMTEC simulation stopped",
            {
                "total_cycles": self.clock.current.cycle_count,
                "asda_phase": "Adapt",
                "lvc_layer": "Constructive",
            },
        )
        return True, "Simulation stopped"

    def _run_loop(self):
        """Main simulation loop - executes ASDA cycle."""
        tick_count = 0
        while (
            not self._stop_flag.is_set()
            and self.clock.current.sim_seconds < self.duration
        ):
            self.clock.tick()
            tick_count += 1

            # ASDA cycle every ASDA_CYCLE_SECONDS
            if tick_count % int(ASDA_CYCLE_SECONDS / SIM_TICK_SECONDS) == 0:
                self._execute_asda_cycle()

            # Update entities every tick
            self._update_entities(SIM_TICK_SECONDS)

            # Update tracks every 5 ticks
            if tick_count % 5 == 0:
                self._update_tracks()

            # Record snapshot every 10 ticks
            if tick_count % 10 == 0:
                self.spear.record_snapshot(self.get_state_dict())

            # Record metrics
            self.spear.record_metric("active_entities", len(self._active_entities()))
            self.spear.record_metric("active_tracks", len(self.track_mgr.active_tracks))
            self.spear.record_metric("network_vuln", self._calc_network_vulnerability())

            # Sleep for real-time pacing
            time.sleep(0.01)  # fast simulation

        self._running = False

    def _execute_asda_cycle(self):
        """Execute one ASDA (Act-Sense-Decide-Adapt) cycle."""
        phase = ASDA_PHASES[self.asda_phase_idx]
        self.asda_phase_idx = (self.asda_phase_idx + 1) % len(ASDA_PHASES)
        self.asda_cycle_count += 1

        if phase == "Act":
            self._asda_act()
            # P1-2: Plugin hook - inject EW/cyber threats
            if self.plugin_manager:
                self.plugin_manager.call_hook("pre_asda_act", self)
        elif phase == "Sense":
            self._asda_sense()
            # P1-2: Plugin hook - apply EW effects to sensors
            if self.plugin_manager:
                self.plugin_manager.call_hook("post_asda_sense", self)
        elif phase == "Decide":
            self._asda_decide()
        elif phase == "Adapt":
            self._asda_adapt()
            # P1-2: Plugin hook - apply cyber effects, collect stats
            if self.plugin_manager:
                self.plugin_manager.call_hook("post_asda_adapt", self)

        self._emit_event(
            "asda_cycle",
            "ASDA-Engine",
            f"ASDA cycle {self.asda_cycle_count}: {phase} phase",
            {
                "cycle": self.asda_cycle_count,
                "phase": phase,
                "lvc_layer": "Constructive",
            },
        )

    def _asda_act(self):
        """Act phase: execute current orders, missile launches, deployments."""
        # P3-4: Rule-driven adversary agent replaces random missile launch
        decision = self.adversary.decide_attack(
            bases=self._bases,
            entities=self._entities,
            missiles=self._missiles,
            sensors=self._sensors,
            asda_cycle=self.asda_cycle_count,
        )

        if decision["should_attack"]:
            target_base = decision["target_base"]
            missile_type = decision["missile_type"]
            launch_lat = decision["launch_lat"]
            launch_lon = decision["launch_lon"]

            missile = MissileEntity(
                missile_type,
                launch_lat,
                launch_lon,
                target_base["lat"],
                target_base["lon"],
            )
            self.lvc.virtual.add_entity(missile)
            self._missiles.append(missile)
            self._entities.append(missile)
            self._missile_stats["total_launched"] += 1
            self._emit_event(
                "missile_launch",
                "hostile",
                f"{missile_type} launched toward {target_base['name']} "
                f"({decision['reasoning']})",
                {
                    "missile_type": missile_type,
                    "target": target_base["id"],
                    "target_name": target_base["name"],
                    "lvc_layer": "Virtual",
                    "adversary_decision": True,
                    "reasoning": decision["reasoning"],
                },
            )

            # Coordinated EW attack: deploy jammer to suppress target sensors
            if decision["coordinated_ew"]:
                from models.entity import EWThreatEntity

                ew_type = "KGJ-500"  # airborne jamming pod
                ew = EWThreatEntity(
                    ew_type,
                    launch_lat + 1.0,
                    launch_lon + 1.0,
                    target_base["lat"],
                    target_base["lon"],
                )
                self.lvc.virtual.add_entity(ew)
                self._entities.append(ew)
                self._emit_event(
                    "ew_jam",
                    "hostile",
                    f"{ew_type} EW jammer deployed against {target_base['name']} sensors",
                    {
                        "ew_type": ew_type,
                        "target": target_base["id"],
                        "lvc_layer": "Virtual",
                        "coordinated_with": missile.id,
                    },
                )

            # Coordinated Cyber attack: disrupt C2 at hub before kinetic strike
            if decision["coordinated_cyber"]:
                from models.entity import CyberThreatEntity

                cyber_type = "gps_spoof"  # GPS spoofing attack
                cyber = CyberThreatEntity(
                    cyber_type,
                    target_base_id=target_base["id"],
                )
                self.lvc.virtual.add_entity(cyber)
                self._entities.append(cyber)
                self._emit_event(
                    "cyber_attack",
                    "hostile",
                    f"{cyber_type} cyber attack launched against {target_base['name']} C2",
                    {
                        "attack_type": cyber_type,
                        "target": target_base["id"],
                        "lvc_layer": "Constructive",
                        "coordinated_with": missile.id,
                    },
                )

        # ACE dispersal: move some aircraft to alternate bases
        # P0-3: Use Q-learning to select dispersal target
        if random.random() < 0.2 and len(self._bases) > 1:
            aircraft = [
                e
                for e in self._entities
                if isinstance(e, AircraftEntity)
                and e.status == "active"
                and e.mission == "patrol"
            ]
            if aircraft:
                ac = random.choice(aircraft)
                alt_bases = [b for b in self._bases if b["id"] != ac.base_id]
                # P0-3: Q-learning selects dispersal target
                if self.learning and alt_bases:
                    threat_dir = "west"  # simplified
                    target_id = self.learning.select_dispersal_target(
                        ac.base_id, [b["id"] for b in alt_bases], threat_dir
                    )
                    alt_base = next(
                        (b for b in alt_bases if b["id"] == target_id), alt_bases[0]
                    )
                else:
                    alt_base = random.choice(alt_bases)

                ac.assign_mission("transfer", alt_base["lat"], alt_base["lon"])
                self._dispersal_actions.append(
                    {
                        "from_base": ac.base_id,
                        "target_base": alt_base["id"],
                        "threat_dir": "west",
                        "ac_type": ac.subtype,
                    }
                )
                self._emit_event(
                    "transfer",
                    ac.id,
                    f"{ac.subtype} transferring from {ac.base_id} to {alt_base['id']}",
                    {
                        "from": ac.base_id,
                        "to": alt_base["id"],
                        "ac_type": ac.subtype,
                        "lvc_layer": "Virtual",
                    },
                )

    def _asda_sense(self):
        """Sense phase: run all sensors, collect tracks + inject live data."""
        # P2-3: Inject real-world sensor data (ADS-B/AIS/Weather) into LVC Live
        wx_detection_factor = 1.0
        if self.live_data:
            self._live_injection_stats = self.live_data.inject_into_lvc(self.lvc)
            wx_impact = self.live_data.get_weather_impact()
            wx_detection_factor = wx_impact.get("detection_range_factor", 1.0)
            self._emit_event(
                "live_data_inject",
                "LVC-Live",
                f"Live data injected: {self._live_injection_stats.get('total_injected', 0)} entities",
                {
                    **self._live_injection_stats,
                    "wx_detection_factor": wx_detection_factor,
                    "lvc_layer": "Live",
                },
            )

        # P3-1: Apply weather impact to sensor detection range (closed loop)
        for sensor in self._sensors:
            if sensor.status == "active":
                sensor.set_range_factor(wx_detection_factor)

        all_entities = self.lvc.all_entities()
        for sensor in self._sensors:
            if sensor.status == "active":
                detections = sensor.scan(all_entities)
                for det in detections:
                    self.track_mgr.add_observation(
                        lat=det["lat"],
                        lon=det["lon"],
                        alt_m=det["alt_m"],
                        heading=det["heading_deg"],
                        speed=det["speed_kmh"],
                        confidence=det["confidence"],
                        classification=det["classification"],
                        source=det["source"],
                    )
                    # P3-2: Also inject into LVC fusion buffer for Kalman filtering
                    self.lvc.inject_track(
                        {
                            "lat": det["lat"],
                            "lon": det["lon"],
                            "alt_m": det["alt_m"],
                            "heading": det["heading_deg"],
                            "speed": det["speed_kmh"],
                            "confidence": det["confidence"],
                            "classification": det["classification"],
                            "source": det["source"],
                        },
                        source_layer="Live",
                    )
                    self._emit_event(
                        "detect",
                        sensor.id,
                        f"Sensor detected track at ({det['lat']:.2f}, {det['lon']:.2f})",
                        {
                            "confidence": det["confidence"],
                            "classification": det["classification"],
                            "lvc_layer": "Live",
                        },
                    )

        # P3-2: Run Kalman track fusion (predict -> associate -> update -> lifecycle)
        kalman_fused = self.lvc.fuse_tracks()
        if kalman_fused:
            self._emit_event(
                "kalman_fuse",
                "LVC-Fusion",
                f"Kalman fusion: {len(kalman_fused)} tracks (cycle {self.lvc._fusion_cycle})",
                {
                    "kalman_tracks": len(kalman_fused),
                    "fusion_cycle": self.lvc._fusion_cycle,
                    "lvc_layer": "Constructive",
                },
            )

    def _build_dqn_observation(self) -> "np.ndarray":
        """Build 182-dim observation vector for DQN from current engine state.

        Layout (P6-1 expanded): 22 bases x 5 feats + 12 global + 10 threats x 6 feats = 182
          Per-base: aircraft_norm, destroyed_norm, sensor_present, threat_proximity, ew_jammed
          Global: total_threats, total_tracks, asda_cycle, vuln, intercept_rate,
                  dispersal_rate, ew_active_count, cyber_phase, cyber_effectiveness,
                  wx_detection_factor, wx_visibility, wx_crosswind
          Per-threat: lat_norm, lon_norm, type_encoded, time_to_impact, track_confidence, sensor_coverage
        """
        import numpy as np
        from models.entity import EWThreatEntity, CyberThreatEntity

        NUM_BASES = 22
        BASE_FEATS = 5
        GLOBAL_FEATS = 12
        MAX_THREATS = 10
        THREAT_FEATS = 6
        obs = np.zeros(
            NUM_BASES * BASE_FEATS + GLOBAL_FEATS + MAX_THREATS * THREAT_FEATS,
            dtype=np.float32,
        )
        for i, b in enumerate(self._bases[:NUM_BASES]):
            ac = sum(
                1
                for e in self._entities
                if isinstance(e, AircraftEntity)
                and e.base_id == b["id"]
                and e.status == "active"
            )
            dst = sum(
                1
                for e in self._entities
                if isinstance(e, AircraftEntity)
                and e.base_id == b["id"]
                and e.status == "destroyed"
            )
            sen = (
                1.0
                if any(
                    s.base_id == b["id"] and s.status == "active" for s in self._sensors
                )
                else 0.0
            )
            threats = sum(
                1 for m in self._missiles if m.status == "active" and m.lat is not None
            )
            # EW jamming intensity for this base (check if base sensors are jammed)
            ew_jammed = 0.0
            for e in self._entities:
                if isinstance(e, EWThreatEntity) and e.status == "active":
                    # Check if this EW threat jams any sensor at this base
                    base_sensors = [
                        s
                        for s in self._sensors
                        if s.base_id == b["id"] and s.status == "active"
                    ]
                    for s in base_sensors:
                        dist = e.distance_to(s.lat, s.lon)
                        if dist <= e.jam_range_km:
                            ew_jammed = max(ew_jammed, e.effectiveness)
            obs[i * BASE_FEATS + 0] = min(ac / 10.0, 1.0)
            obs[i * BASE_FEATS + 1] = min(dst / 10.0, 1.0)
            obs[i * BASE_FEATS + 2] = sen
            obs[i * BASE_FEATS + 3] = min(threats / 5.0, 1.0)
            obs[i * BASE_FEATS + 4] = ew_jammed

        off = NUM_BASES * BASE_FEATS
        active_msl = sum(1 for m in self._missiles if m.status == "active")
        # P3-2: Use Kalman-fused track count (primary) + TrackManager (fallback)
        kalman_n = (
            len(self.lvc._kalman_tracks) if hasattr(self.lvc, "_kalman_tracks") else 0
        )
        tm_n = len(self.track_mgr.fuse())
        n_tracks = max(kalman_n, tm_n)
        vuln = self._calc_network_vulnerability()
        ir = 0.0
        if self._intercept_results:
            ir = len([r for r in self._intercept_results if r.get("strategy")]) / max(
                len(self._intercept_results), 1
            )
        dr = len(self._dispersal_actions) / max(len(self._entities), 1)

        # EW/Cyber/Weather global features
        ew_active = sum(
            1
            for e in self._entities
            if isinstance(e, EWThreatEntity) and e.status == "active"
        )
        cyber_threats = [
            e
            for e in self._entities
            if isinstance(e, CyberThreatEntity) and e.status == "active"
        ]
        # Cyber phase is string: map to 0-1 (infiltration=0, persistence=0.33, impact=0.67, remediated=1.0)
        _phase_map = {
            "infiltration": 0.0,
            "persistence": 0.33,
            "impact": 0.67,
            "remediated": 1.0,
        }
        cyber_phase = (
            sum(
                _phase_map.get(getattr(e, "phase", "infiltration"), 0.0)
                for e in cyber_threats
            )
            / max(len(cyber_threats), 1)
            if cyber_threats
            else 0.0
        )
        cyber_eff = (
            sum(getattr(e, "effectiveness", 0.0) for e in cyber_threats)
            / max(len(cyber_threats), 1)
            if cyber_threats
            else 0.0
        )
        # Weather from live_data adapter
        wx_det = 1.0
        wx_vis = 1.0
        wx_wind = 0.0
        if self.live_data:
            wx_impact = self.live_data.get_weather_impact()
            wx_det = wx_impact.get("detection_range_factor", 1.0)
            wx_vis = wx_impact.get("visibility_factor", 1.0)
            wx_wind = wx_impact.get("crosswind_component", 0.0)

        obs[off + 0] = min(active_msl / 20.0, 1.0)
        obs[off + 1] = min(n_tracks / 20.0, 1.0)
        obs[off + 2] = min(self.asda_cycle_count / 30.0, 1.0)
        obs[off + 3] = vuln
        obs[off + 4] = ir
        obs[off + 5] = min(dr, 1.0)
        obs[off + 6] = min(ew_active / 5.0, 1.0)
        obs[off + 7] = cyber_phase
        obs[off + 8] = cyber_eff
        obs[off + 9] = wx_det / 1.5  # normalize to [0,1]
        obs[off + 10] = wx_vis
        obs[off + 11] = wx_wind

        # P6-1: Per-threat features (up to 10 active missiles x 6 features)
        threat_off = NUM_BASES * BASE_FEATS + GLOBAL_FEATS
        type_enc = {"ballistic": 0.0, "cruise": 0.5, "hypersonic": 1.0}
        active_missiles = [m for m in self._missiles if m.status == "active"]
        # Get track confidences from TrackManager
        tm_tracks = self.track_mgr.fuse()
        for i, m in enumerate(active_missiles[:MAX_THREATS]):
            base_idx = threat_off + i * THREAT_FEATS
            # Normalized lat/lon (range 20-50 lat, 100-140 lon)
            obs[base_idx + 0] = (getattr(m, "lat", 35.0) - 20.0) / 30.0
            obs[base_idx + 1] = (getattr(m, "lon", 120.0) - 100.0) / 40.0
            obs[base_idx + 2] = type_enc.get(getattr(m, "subtype", "ballistic"), 0.0)
            # Time to impact: estimate from distance and speed
            try:
                dist_km = m.distance_to(m.target_lat, m.target_lon)
                tti = dist_km / max(m.speed_kmh / 3600.0, 1.0)
            except Exception:
                tti = 120.0
            obs[base_idx + 3] = min(tti / 300.0, 1.0)
            # Track confidence for this missile
            track_conf = 0.0
            for tid, trk in tm_tracks.items():
                if tid == m.id or (
                    hasattr(trk, "missile_id") and trk.missile_id == m.id
                ):
                    track_conf = getattr(trk, "confidence", 0.5)
                    break
            obs[base_idx + 4] = track_conf
            # Sensor coverage for nearest base to missile target
            try:
                nearest_base = min(
                    self._bases,
                    key=lambda b: (
                        abs(b.get("lat", 0) - m.target_lat)
                        + abs(b.get("lon", 0) - m.target_lon)
                    ),
                )
                sensor_cov = (
                    sum(
                        1
                        for s in self._sensors
                        if s.base_id == nearest_base["id"] and s.status == "active"
                    )
                    / 5.0
                )
            except Exception:
                sensor_cov = 0.0
            obs[base_idx + 5] = min(sensor_cov, 1.0)

        return obs

    def _asda_decide(self):
        """Decide phase: evaluate threats, decide countermeasures.
        Deep RL (DQN) overrides UCB1 when a trained model is available."""
        tracks = self.track_mgr.fuse()
        hostile_tracks = [
            t
            for t in tracks.values()
            if t.classification in ("missile", "aircraft") and t.confidence > 0.5
        ]

        # Deep RL: Multi-agent IQL or single DQN selects action from observation
        dqn_action = None
        if self.ma_dqn and self.ma_dqn.is_trained():
            # P5-2: MADDPG or P4-4: IQL - two agents cooperate
            algo_name = self.ma_dqn.get_statistics().get("algorithm", "MultiAgent")[:20]
            obs = self._build_dqn_observation()
            ma_actions = self.ma_dqn.predict(obs)
            intercept_idx = ma_actions.get(INTERCEPT_AGENT, 0)
            dispersal_idx = ma_actions.get(DISPERSAL_AGENT, 0)
            strategy_map = {0: "direct", 1: "predictive", 2: "saturation"}
            intercept_strategy = strategy_map.get(intercept_idx, "direct")
            should_disperse = dispersal_idx > 0
            dispersal_level = ["hold", "light", "heavy"][dispersal_idx]
            self._emit_event(
                "ma_dqn_decision",
                algo_name,
                f"Multi-Agent {algo_name.split('(')[0].strip()}: intercept={intercept_strategy} + dispersal={dispersal_level}",
                {
                    "intercept_action": intercept_idx,
                    "dispersal_action": dispersal_idx,
                    "intercept_strategy": intercept_strategy,
                    "should_disperse": should_disperse,
                    "dispersal_level": dispersal_level,
                    "asda_phase": "Decide",
                    "lvc_layer": "Constructive",
                },
            )
            # Execute multi-agent directed dispersal
            if should_disperse and self._bases and self._entities:
                self._do_dqn_dispersal(heavy=(dispersal_idx == 2))
        elif self.dqn and self.dqn.is_trained():
            obs = self._build_dqn_observation()
            dqn_action = self.dqn.predict(obs, deterministic=True)
            # Decode: action // 2 = intercept strategy (0=direct,1=predictive,2=saturation)
            # action % 2 = should_disperse (0=no, 1=yes)
            strategy_map = {0: "direct", 1: "predictive", 2: "saturation"}
            intercept_strategy = strategy_map.get(dqn_action // 2, "direct")
            should_disperse = dqn_action % 2 == 1
            self._emit_event(
                "dqn_decision",
                "DQN-Agent",
                f"Deep RL action={dqn_action}: {intercept_strategy} intercept + dispersal={should_disperse}",
                {
                    "dqn_action": dqn_action,
                    "intercept_strategy": intercept_strategy,
                    "should_disperse": should_disperse,
                    "asda_phase": "Decide",
                    "lvc_layer": "Constructive",
                },
            )
            # Execute DQN-directed dispersal
            if should_disperse and self._bases and self._entities:
                self._do_dqn_dispersal()
        elif self.learning:
            # Fallback: UCB1
            intercept_strategy = self.learning.select_intercept_strategy()
        else:
            intercept_strategy = "direct"

        # P6-fix: Map missile subtypes to threat categories for intercept probability
        _SUBTYPE_TO_THREAT = {
            "DF-17": "hypersonic",
            "DF-26": "ballistic",
            "DF-21D": "ballistic",
            "KH-101": "cruise",
            "CJ-10": "cruise",
        }
        _BASE_PROBS = {
            "direct": {"ballistic": 0.75, "cruise": 0.90, "hypersonic": 0.72},
            "predictive": {"ballistic": 0.85, "cruise": 0.80, "hypersonic": 0.75},
            "saturation": {"ballistic": 0.80, "cruise": 0.80, "hypersonic": 0.85},
        }
        _TYPE_MATCH = {
            "direct": {"ballistic": 0.95, "cruise": 1.0, "hypersonic": 0.90},
            "predictive": {"ballistic": 1.0, "cruise": 0.95, "hypersonic": 0.92},
            "saturation": {"ballistic": 0.90, "cruise": 0.90, "hypersonic": 1.0},
        }

        for track in hostile_tracks:
            # Decide: intercept or evade
            if track.classification == "missile":
                self._emit_event(
                    "intercept_decision",
                    "ASDA-Engine",
                    f"Decide: {intercept_strategy} intercept hostile track {track.track_id}",
                    {
                        "track_id": track.track_id,
                        "confidence": track.confidence,
                        "asda_phase": "Decide",
                        "lvc_layer": "Constructive",
                        "intercept_strategy": intercept_strategy,
                    },
                )
                # Record intercept attempt for learning
                self._intercept_results.append(
                    {
                        "strategy": intercept_strategy,
                        "track_id": track.track_id,
                        "cycle": self.asda_cycle_count,
                    }
                )
                # P6-fix: Execute intercept with probability model
                missile = next(
                    (
                        m
                        for m in self._missiles
                        if m.id == track.track_id and m.status == "active"
                    ),
                    None,
                )
                if missile:
                    threat_type = _SUBTYPE_TO_THREAT.get(missile.subtype, "ballistic")
                    p = _BASE_PROBS.get(intercept_strategy, {}).get(threat_type, 0.5)
                    p *= _TYPE_MATCH.get(intercept_strategy, {}).get(threat_type, 0.8)
                    p *= 0.7 + 0.3 * track.confidence
                    # Time window bonus: more time remaining = higher intercept probability
                    time_remaining = (
                        max(0.0, missile.impact_time - missile.timestamp)
                        if missile.impact_time > 0
                        else 60.0
                    )
                    time_factor = 1.0 + 0.5 * min(1.0, time_remaining / 120.0)
                    p = min(0.95, p * time_factor)
                    if random.random() < p:
                        missile.status = "destroyed"
                        missile.impact_time = 0
                        self._missile_stats["intercepted"] += 1
                        self._emit_event(
                            "intercept_success",
                            "ASDA-Engine",
                            f"Intercept SUCCESS: {missile.subtype} {missile.id} destroyed ({intercept_strategy})",
                            {
                                "missile_id": missile.id,
                                "missile_type": missile.subtype,
                                "threat_type": threat_type,
                                "intercept_strategy": intercept_strategy,
                                "probability": round(p, 3),
                                "asda_phase": "Decide",
                                "lvc_layer": "Constructive",
                            },
                        )
                    else:
                        self._emit_event(
                            "intercept_fail",
                            "ASDA-Engine",
                            f"Intercept MISS: {missile.subtype} {missile.id} ({intercept_strategy}, p={p:.1%})",
                            {
                                "missile_id": missile.id,
                                "missile_type": missile.subtype,
                                "intercept_strategy": intercept_strategy,
                                "probability": round(p, 3),
                            },
                        )
            else:
                self._emit_event(
                    "evade_decision",
                    "ASDA-Engine",
                    f"Decide: evade hostile aircraft {track.track_id}",
                    {
                        "track_id": track.track_id,
                        "asda_phase": "Decide",
                        "lvc_layer": "Constructive",
                    },
                )

        # P6-fix: Also intercept missiles directly from self._missiles
        # (track_mgr may not classify missiles correctly via sensor fusion)
        track_intercepted_ids = {r["track_id"] for r in self._intercept_results}
        for missile in self._missiles:
            if missile.status != "active" or missile.id in track_intercepted_ids:
                continue
            threat_type = _SUBTYPE_TO_THREAT.get(missile.subtype, "ballistic")
            p = _BASE_PROBS.get(intercept_strategy, {}).get(threat_type, 0.5)
            p *= _TYPE_MATCH.get(intercept_strategy, {}).get(threat_type, 0.8)
            # Sensor confidence: use distance-based proxy
            nearest_sensor_dist = min(
                (
                    s.distance_to(missile.lat, missile.lon)
                    for s in self._sensors
                    if s.status == "active"
                ),
                default=999.0,
            )
            sensor_conf = max(0.5, 1.0 - nearest_sensor_dist / 400.0 * 0.5)
            p *= 0.7 + 0.3 * sensor_conf
            time_remaining = (
                max(0.0, missile.impact_time - missile.timestamp)
                if missile.impact_time > 0
                else 60.0
            )
            time_factor = 1.0 + 0.5 * min(1.0, time_remaining / 120.0)
            p = min(0.95, p * time_factor)
            if random.random() < p:
                missile.status = "destroyed"
                missile.impact_time = 0
                self._missile_stats["intercepted"] += 1
                self._emit_event(
                    "intercept_success",
                    "ASDA-Engine",
                    f"Intercept SUCCESS: {missile.subtype} {missile.id} destroyed ({intercept_strategy})",
                    {
                        "missile_id": missile.id,
                        "missile_type": missile.subtype,
                        "threat_type": threat_type,
                        "intercept_strategy": intercept_strategy,
                        "probability": round(p, 3),
                        "asda_phase": "Decide",
                        "lvc_layer": "Constructive",
                    },
                )
            else:
                self._emit_event(
                    "intercept_fail",
                    "ASDA-Engine",
                    f"Intercept MISS: {missile.subtype} {missile.id} ({intercept_strategy}, p={p:.1%})",
                    {
                        "missile_id": missile.id,
                        "missile_type": missile.subtype,
                        "intercept_strategy": intercept_strategy,
                        "probability": round(p, 3),
                    },
                )

    def _do_dqn_dispersal(self, heavy: bool = False):
        """Execute DQN-directed dispersal: move patrol aircraft to safest alternate base.

        P4-4: Supports variable dispersal fraction (15% light / 30% heavy).
        """
        fraction = 0.30 if heavy else 0.15
        patrol_ac = [
            e
            for e in self._entities
            if isinstance(e, AircraftEntity)
            and e.status == "active"
            and e.mission == "patrol"
        ]
        n_transfer = max(1, int(len(patrol_ac) * fraction))
        if n_transfer == 0 or len(self._bases) < 2:
            return

        # Pick aircraft from most threatened bases
        def base_threats(bid):
            return sum(
                1 for m in self._missiles if m.status == "active" and m.lat is not None
            )

        patrol_ac.sort(key=lambda a: base_threats(a.base_id), reverse=True)
        for ac in patrol_ac[:n_transfer]:
            src = ac.base_id
            candidates = [b for b in self._bases if b["id"] != src]

            # Safest = fewest threats targeting it + most aircraft already there
            def safety(b):
                threats = sum(1 for m in self._missiles if m.status == "active")
                ac_count = sum(
                    1
                    for e in self._entities
                    if isinstance(e, AircraftEntity)
                    and e.base_id == b["id"]
                    and e.status == "active"
                )
                return threats - ac_count

            safest = min(candidates, key=safety)
            ac.assign_mission("transfer", safest["lat"], safest["lon"])
            self._dispersal_actions.append(
                {
                    "from_base": src,
                    "target_base": safest["id"],
                    "threat_dir": "dqn",
                    "ac_type": ac.subtype,
                }
            )
            self._emit_event(
                "dqn_dispersal",
                "DQN-Agent",
                f"Deep RL dispersal: {ac.subtype} {src} -> {safest['id']}",
                {
                    "from": src,
                    "to": safest["id"],
                    "ac_type": ac.subtype,
                    "lvc_layer": "Virtual",
                },
            )

    def _asda_adapt(self):
        """Adapt phase: apply decisions, update deployments, learn.
        P0-3: Records intercept/dispersal outcomes to learning manager,
        updates strategy parameters for next cycle."""
        # Check missile impacts and record intercept outcomes
        intercept_success_count = 0
        intercept_attempt_count = len(self._intercept_results)

        for missile in self._missiles:
            if missile.status == "destroyed" and missile.impact_time > 0:
                # Assess damage at impact site
                impact_base = min(
                    self._bases,
                    key=lambda b: haversine(
                        b["lat"], b["lon"], missile.lat, missile.lon
                    ),
                )
                dist = haversine(
                    impact_base["lat"], impact_base["lon"], missile.lat, missile.lon
                )
                if dist < 5.0:  # hit the base
                    # Monte Carlo damage assessment (simplified)
                    hit_prob = min(0.8, 1.0 - (missile.cep / 1000) / max(dist, 0.1))
                    if random.random() < hit_prob:
                        # Damage nearby aircraft
                        nearby_ac = [
                            e
                            for e in self._entities
                            if isinstance(e, AircraftEntity)
                            and e.distance_to(missile.lat, missile.lon) < 5
                            and e.status == "active"
                        ]
                        for ac in nearby_ac[:2]:  # max 2 damaged
                            ac.status = "destroyed"
                            self._emit_event(
                                "damage",
                                missile.id,
                                f"{ac.subtype} {ac.id} destroyed at {impact_base['name']}",
                                {
                                    "base": impact_base["id"],
                                    "ac_type": ac.subtype,
                                    "missile_type": missile.subtype,
                                    "lvc_layer": "Virtual",
                                },
                            )
                missile.impact_time = 0  # mark as processed

        # P0-3: Record intercept outcomes for UCB1 learning
        # An intercept is "successful" if the missile was destroyed before impact
        # or if no damage occurred at the target base
        for result in self._intercept_results:
            track_id = result["track_id"]
            strategy = result["strategy"]
            # Find the corresponding missile
            missile = next(
                (
                    m
                    for m in self._missiles
                    if m.id == track_id or m.status == "destroyed"
                ),
                None,
            )
            if missile:
                # Missile destroyed before reaching target = successful intercept
                # Check if missile was destroyed before impact (impact_time == 0 and not processed)
                success = missile.status == "destroyed"
            else:
                success = True  # No missile found = threat neutralized

            if self.learning:
                self.learning.record_intercept_result(strategy, success)
            if success:
                intercept_success_count += 1

        self._intercept_results.clear()

        # P3-4: Record attack outcomes for adversary adaptive learning
        for missile in self._missiles:
            if missile.status == "destroyed":
                # Determine if missile was intercepted (defense) or hit (attack success)
                hit = missile.impact_time > 0
                intercepted = missile.impact_time == 0
                self.adversary.record_outcome(
                    attack_id=missile.id, hit=hit, intercepted=intercepted
                )

        # P0-3: Record dispersal outcomes for Q-learning
        for action in self._dispersal_actions:
            if self.learning:
                # Calculate loss rate: fraction of aircraft at target base destroyed
                target_base_id = action.get("target_base", "")
                ac_at_target = [
                    e
                    for e in self._entities
                    if isinstance(e, AircraftEntity) and e.base_id == target_base_id
                ]
                destroyed_at_target = [
                    e for e in ac_at_target if e.status == "destroyed"
                ]
                loss_rate = len(destroyed_at_target) / max(len(ac_at_target), 1)

                self.learning.record_dispersal_result(
                    current_base=action.get("from_base", ""),
                    target_base=target_base_id,
                    threat_dir=action.get("threat_dir", "unknown"),
                    loss_rate=loss_rate,
                    next_base=target_base_id,
                    next_available=[b["id"] for b in self._bases],
                )

        self._dispersal_actions.clear()

        # P0-3: Record sensor coverage
        if self.learning and self._sensors and self._bases:
            base_coverage = {}
            for base in self._bases:
                sensors_at_base = [s for s in self._sensors if s.base_id == base["id"]]
                if sensors_at_base:
                    threats_near = [
                        e
                        for e in self._entities
                        if e.affiliation == "hostile" and e.status == "active"
                    ]
                    if threats_near:
                        detected = 0
                        for s in sensors_at_base:
                            for threat in threats_near:
                                if (
                                    s.distance_to(threat.lat, threat.lon)
                                    <= s.detection_range_km
                                ):
                                    detected += 1
                                    break
                        base_coverage[base["id"]] = detected / max(len(threats_near), 1)
                    else:
                        base_coverage[base["id"]] = 1.0
                else:
                    base_coverage[base["id"]] = 0.0

            self.learning.record_sensor_coverage(base_coverage)

        # P0-3: End learning cycle
        if self.learning:
            cycle_data = {
                "cycle": self.asda_cycle_count,
                "intercept_attempts": intercept_attempt_count,
                "intercept_successes": intercept_success_count,
                "active_entities": len(self._active_entities()),
                "sim_seconds": self.clock.current.sim_seconds,
            }
            self.learning.end_cycle(cycle_data)

        # Recover: transfer aircraft back from alternate bases
        landed = [
            e
            for e in self._entities
            if isinstance(e, AircraftEntity) and e.status == "landed"
        ]
        for ac in landed:
            if random.random() < 0.3:
                home_base = next(
                    (b for b in self._bases if b["id"] == ac.base_id), None
                )
                if home_base:
                    ac.status = "active"
                    ac.assign_mission("transfer", home_base["lat"], home_base["lon"])
                    self._emit_event(
                        "recover",
                        ac.id,
                        f"{ac.subtype} recovering to {ac.base_id}",
                        {
                            "ac_type": ac.subtype,
                            "to": ac.base_id,
                            "lvc_layer": "Virtual",
                        },
                    )

        # P0-1: Push real-time update after Adapt phase
        if self.realtime:
            state = self.get_state_dict()
            recent_events = self.spear.events[-20:]
            self.realtime.push_state(state, recent_events)

        # P4-1: Persist simulation state to SQLite
        if self.store:
            state = self.get_state_dict()
            kalman_status = {}
            if hasattr(self.lvc, "status"):
                kalman_status = self.lvc.status()
            adversary_stats = self.adversary.get_stats() if self.adversary else {}
            weather = {}
            if self.live_data:
                weather = self.live_data.get_weather_impact()
            self.store.save_snapshot(
                state=state,
                cycle=self.asda_cycle_count,
                kalman_info=kalman_status,
                adversary_stats=adversary_stats,
                weather=weather,
            )
            # Persist Kalman tracks
            kalman_tracks = []
            if hasattr(self.lvc, "fuse_tracks"):
                kalman_tracks = self.lvc.fuse_tracks()
            if kalman_tracks:
                self.store.save_kalman_tracks(self.asda_cycle_count, kalman_tracks)
            # Persist new SPEAR events from this cycle
            cycle_events = [
                e
                for e in self.spear.events
                if e.get("cycle") == self.asda_cycle_count
                or e.get("data", {}).get("asda_cycle") == self.asda_cycle_count
            ]
            if not cycle_events:
                # Fallback: persist last 5 events if cycle tagging didn't work
                cycle_events = self.spear.events[-5:]
            self.store.save_events(self.asda_cycle_count, cycle_events)

    def _update_entities(self, dt: float):
        """Update all entity positions."""
        from models.entity import EWThreatEntity, CyberThreatEntity

        for entity in self._entities:
            if isinstance(entity, AircraftEntity):
                entity.update(dt)
            elif isinstance(entity, MissileEntity):
                entity.update(dt)
            elif isinstance(entity, (EWThreatEntity, CyberThreatEntity)):
                entity.update(dt)

        # Clean up destroyed missiles from all lists (but keep stats)
        active_missiles = [m for m in self._missiles if m.status == "active"]
        destroyed = [m for m in self._missiles if m.status != "active"]
        for m in destroyed:
            # Track impacted missiles (not intercepted: impact_time > 0)
            if m.impact_time > 0:
                self._missile_stats["impacted"] += 1
            self.lvc.virtual.remove_entity(m.id)
        self._missiles = active_missiles
        # Also clean up destroyed/neutralized entities from entities list
        self._entities = [
            e
            for e in self._entities
            if e.status not in ("destroyed", "neutralized")
            or isinstance(e, AircraftEntity)
        ]

    def _update_tracks(self):
        """Fuse and update track picture."""
        self.track_mgr.fuse()

    def _calc_network_vulnerability(self) -> float:
        """Calculate network vulnerability score (0=secure, 1=critical)."""
        active = len(self._active_entities())
        destroyed = len([e for e in self._entities if e.status == "destroyed"])
        if active + destroyed == 0:
            return 0.0
        return min(1.0, destroyed / max(active + destroyed, 1) * 2)

    def _active_entities(self) -> list:
        return [e for e in self._entities if e.status == "active"]

    def _emit_event(
        self, event_type: str, source: str, description: str, data: dict = None
    ):
        """Emit and record a simulation event."""
        evt = Event(
            event_type=event_type,
            timestamp=time.time(),
            source=source,
            data=data or {},
        )
        self.event_bus.publish(evt)
        evt_dict = evt.to_dict()
        evt_dict["description"] = description
        self.spear.record_event(evt_dict)

    def get_state_dict(self) -> dict:
        """Get current system state as dictionary."""
        # P4-3: Include Kalman tracks for 3D confidence heatmap
        kalman_tracks = []
        if self.lvc and hasattr(self.lvc, "_kalman_tracks"):
            kalman_tracks = [
                t.to_dict()
                for t in self.lvc._kalman_tracks.values()
                if t.status in ("tentative", "confirmed")
            ]
        # P4-3: Include weather impact for overlay
        weather = {}
        if self.live_data:
            weather = self.live_data.get_weather_impact()
        return {
            "sim_time": str(self.clock.current),
            "sim_seconds": self.clock.current.sim_seconds,
            "total_entities": len(self._entities),
            "active_tracks": len(self.track_mgr.active_tracks),
            "asda_cycle": self.asda_cycle_count,
            "asda_phase": ASDA_PHASES[(self.asda_phase_idx - 1) % 4]
            if self.asda_cycle_count > 0
            else "idle",
            "network_vulnerability": round(self._calc_network_vulnerability(), 3),
            "entities": [e.to_dict() for e in self._entities if e.status == "active"],
            "tracks": [t.to_dict() for t in self.track_mgr.active_tracks],
            "kalman_tracks": kalman_tracks,
            "weather": weather,
            "live_data_stats": self._live_injection_stats if self.live_data else {},
            "lvc_live_entities": self.lvc.live.entity_count if self.lvc else 0,
            "adversary_stats": self.adversary.get_stats(),
            "ma_dqn_stats": self.ma_dqn.get_statistics() if self.ma_dqn else {},
            "persistence": self.store.get_summary() if self.store else {},
            # P6-fix: threat/intercept statistics (persistent counters)
            "threat_stats": {
                "total_missiles": self._missile_stats["total_launched"],
                "intercepted": self._missile_stats["intercepted"],
                "impacted": self._missile_stats["impacted"],
                "active": sum(1 for m in self._missiles if m.status == "active"),
                "intercept_rate": (
                    self._missile_stats["intercepted"]
                    / max(self._missile_stats["total_launched"], 1)
                ),
            },
            "dqn_agent": {
                "active": self.dqn is not None and self.dqn.is_trained(),
                "model_name": "pmtec_dqn_p6"
                if (self.dqn and self.dqn.is_trained())
                else "none",
            },
        }

    # ---- gRPC service implementations ----

    def get_state_proto(self, at_time: int = 0) -> pb.SystemState:
        """Convert state to protobuf message."""
        state = self.get_state_dict()
        msg = pb.SystemState(
            sim_time=int(state["sim_seconds"]),
            total_entities=state["total_entities"],
            active_tracks=state["active_tracks"],
            asda_cycle=state["asda_cycle"],
            asda_phase=state["asda_phase"],
            network_vulnerability=state["network_vulnerability"],
            strike_capability=len(
                [
                    e
                    for e in self._entities
                    if isinstance(e, AircraftEntity) and e.status == "active"
                ]
            ),
        )
        for e_dict in state["entities"]:
            msg.entities.add(
                id=e_dict["id"],
                type=e_dict["type"],
                subtype=e_dict["subtype"],
                lat=e_dict["lat"],
                lon=e_dict["lon"],
                alt_m=e_dict["alt_m"],
                heading_deg=e_dict["heading"],
                speed_kmh=e_dict["speed_kmh"],
                affiliation=e_dict["affiliation"],
                base_id=e_dict["base_id"],
                status=e_dict["status"],
            )
        for t_dict in state["tracks"]:
            msg.tracks.add(
                track_id=t_dict["track_id"],
                lat=t_dict["lat"],
                lon=t_dict["lon"],
                alt_m=t_dict["alt_m"],
                heading_deg=t_dict["heading"],
                speed_kmh=t_dict["speed_kmh"],
                confidence=t_dict["confidence"],
                classification=t_dict["classification"],
            )
        # Recent events (last 10)
        for evt in self.spear.events[-10:]:
            sim_evt = msg.recent_events.add(
                event_id=evt.get("event_id", ""),
                event_type=evt.get("event_type", ""),
                timestamp=int(evt.get("timestamp", 0)),
                actor=evt.get("source", ""),
                description=evt.get("description", ""),
            )
            for k, v in evt.get("data", {}).items():
                if isinstance(v, (str, int, float)):
                    sim_evt.params[str(k)] = str(v)
        return msg


class WarEngineServicer(pb_grpc.WarEngineServicer):
    """DTB WarEngine service - simulation control."""

    def __init__(self, engine: PMTECEngine):
        self.engine = engine

    def StartSimulation(self, request, context):
        success, msg = self.engine.start_simulation(
            request.scenario_name, request.duration_seconds, request.seed
        )
        return pb.Ack(success=success, message=msg)

    def StopSimulation(self, request, context):
        success, msg = self.engine.stop_simulation()
        return pb.Ack(success=success, message=msg)

    def GetState(self, request, context):
        return self.engine.get_state_proto(request.at_time)

    def InjectEvent(self, request, context):
        self.engine._emit_event(
            request.event_type, request.actor, request.description, dict(request.params)
        )
        return pb.Ack(success=True, message=f"Event {request.event_id} injected")

    def GetSpearReport(self, request, context):
        report = self.engine.spear.generate_report(request.start_time, request.end_time)
        msg = pb.SpearReport(
            total_duration=int(report["total_duration_s"]),
            total_events=int(report["total_events"]),
            total_tracks=int(len(self.engine.track_mgr.tracks)),
            summary=report["summary"],
        )
        for evt in report.get("timeline", []):
            msg.timeline.add(
                event_id=str(evt.get("event_id", "")),
                event_type=str(evt.get("event_type", "")),
                timestamp=int(float(evt.get("timestamp", 0))),
                actor=str(evt.get("source", "")),
                description=str(evt.get("description", "")),
            )
        return msg

    # ---- P2: EW/Cyber threat RPCs ----

    def GetEWThreats(self, request, context):
        """Get electronic warfare threats."""
        from models.entity import EWThreatEntity

        msg = pb.EWThreatList()
        for entity in self.engine._entities:
            if not isinstance(entity, EWThreatEntity):
                continue
            if (
                request.target_base_id
                and entity.target_base_id != request.target_base_id
            ):
                continue
            if request.active_only and entity.status != "active":
                continue
            t = msg.threats.add(
                threat_id=entity.id,
                ew_type=entity.subtype,
                lat=entity.lat or 0.0,
                lon=entity.lon or 0.0,
                alt_m=entity.alt_m or 0.0,
                power_kw=entity.power_kw,
                jam_range_km=entity.jam_range_km,
                effectiveness=entity.effectiveness,
                target_base_id=getattr(entity, "target_base_id", ""),
                status=entity.status,
            )
            t.jammed_bands.extend(entity.jammed_bands)
        return msg

    def GetCyberThreats(self, request, context):
        """Get cyber threats."""
        from models.entity import CyberThreatEntity

        msg = pb.CyberThreatList()
        for entity in self.engine._entities:
            if not isinstance(entity, CyberThreatEntity):
                continue
            if (
                request.target_base_id
                and entity.target_base_id != request.target_base_id
            ):
                continue
            if request.detected_only and not entity.detected:
                continue
            msg.threats.add(
                threat_id=entity.id,
                attack_type=entity.subtype,
                target_base_id=entity.target_base_id or "",
                target_system=entity.target_system or "",
                phase=entity.phase,
                detection_difficulty=entity.detection_difficulty,
                impact_severity=entity.impact_severity,
                effectiveness=entity.effectiveness,
                detected=entity.detected,
                impact_score=entity.impact_score,
                status=entity.status,
            )
        return msg

    def GetThreatSummary(self, request, context):
        """Get summary of all active threats."""
        from models.entity import EWThreatEntity, CyberThreatEntity

        ew_active = sum(
            1
            for e in self.engine._entities
            if isinstance(e, EWThreatEntity) and e.status == "active"
        )
        cyber_active = sum(
            1
            for e in self.engine._entities
            if isinstance(e, CyberThreatEntity) and e.status == "active"
        )
        cyber_detected = sum(
            1
            for e in self.engine._entities
            if isinstance(e, CyberThreatEntity) and e.detected
        )
        kinetic_active = sum(1 for m in self.engine._missiles if m.status == "active")
        return pb.ThreatSummary(
            ew_active=ew_active,
            cyber_active=cyber_active,
            cyber_detected=cyber_detected,
            kinetic_active=kinetic_active,
        )


class BattleNetworkServicer(pb_grpc.BattleNetworkServicer):
    """DTB BattleNetwork service - track and entity management."""

    def __init__(self, engine: PMTECEngine):
        self.engine = engine

    def GetTrackFeed(self, request, context):
        """Stream track updates to subscribers."""
        last_count = 0
        while self.engine._running or context.is_active():
            tracks = self.engine.track_mgr.active_tracks
            if len(tracks) != last_count:
                update = pb.TrackUpdate(timestamp=int(time.time()))
                for t in tracks:
                    if (
                        request.min_lat <= t.lat <= request.max_lat
                        and request.min_lon <= t.lon <= request.max_lon
                    ):
                        if (
                            not request.classification_filter
                            or t.classification == request.classification_filter
                        ):
                            update.tracks.add(
                                track_id=t.track_id,
                                lat=t.lat,
                                lon=t.lon,
                                alt_m=t.alt_m,
                                heading_deg=t.heading_deg,
                                speed_kmh=t.speed_kmh,
                                confidence=t.confidence,
                                classification=t.classification,
                            )
                yield update
                last_count = len(tracks)
            time.sleep(1)

    def GetEntityStatus(self, request, context):
        """Get status of a specific entity."""
        for entity in self.engine._entities:
            if request.entity_id and entity.id != request.entity_id:
                continue
            if request.type_filter and entity.entity_type != request.type_filter:
                continue
            return pb.EntityStatus(
                entity=pb.Entity(
                    id=entity.id,
                    type=entity.entity_type,
                    subtype=entity.subtype,
                    lat=entity.lat,
                    lon=entity.lon,
                    alt_m=entity.alt_m,
                    heading_deg=entity.heading_deg,
                    speed_kmh=entity.speed_kmh,
                    affiliation=entity.affiliation,
                    base_id=entity.base_id,
                    status=entity.status,
                ),
                health="operational" if entity.status == "active" else entity.status,
                fuel_pct=getattr(entity, "fuel_pct", 1.0),
                ammo_count=getattr(entity, "ammo_count", 0),
            )
        return pb.EntityStatus()

    def GetNetworkState(self, request, context):
        """Get DTB BattleNetwork state."""
        active = len(self.engine._active_entities())
        total = len(self.engine._entities)
        degraded = total - active
        node_statuses = []
        for base in self.engine._bases[:10]:
            ac_count = len(
                [
                    e
                    for e in self.engine._entities
                    if isinstance(e, AircraftEntity) and e.base_id == base["id"]
                ]
            )
            node_statuses.append(
                f"{base['id']}: {ac_count} aircraft, {'active' if ac_count > 0 else 'empty'}"
            )
        return pb.NetworkState(
            total_nodes=len(self.engine._bases),
            active_nodes=len(
                [
                    b
                    for b in self.engine._bases
                    if any(
                        e.base_id == b["id"] and e.status == "active"
                        for e in self.engine._entities
                    )
                ]
            ),
            degraded_nodes=degraded,
            avg_latency_ms=round(random.uniform(15, 50), 1),
            node_status=node_statuses,
        )

    # ---- P2: LVC Live data RPCs ----

    def GetLiveFeed(self, request, context):
        """Stream live sensor data updates (AIS/ADS-B/weather)."""
        lvc = self.engine.lvc
        live_entities = lvc.live.entities if lvc else {}
        while self.engine._running or context.is_active():
            update = pb.LiveFeedUpdate(
                feed_source=request.feed_type or "all",
                timestamp=int(time.time()),
            )
            for entity in live_entities.values():
                if hasattr(entity, "lat") and entity.lat is not None:
                    if (
                        request.min_lat <= entity.lat <= request.max_lat
                        and request.min_lon <= entity.lon <= request.max_lon
                    ):
                        update.contacts.add(
                            sensor_id=getattr(entity, "id", ""),
                            sensor_type=getattr(entity, "entity_type", "sensor"),
                            lat=entity.lat,
                            lon=entity.lon,
                            alt_m=getattr(entity, "alt_m", 0.0),
                            heading_deg=getattr(entity, "heading_deg", 0.0),
                            speed_kmh=getattr(entity, "speed_kmh", 0.0),
                            callsign=getattr(entity, "callsign", ""),
                            affiliation=getattr(entity, "affiliation", "unknown"),
                            confidence=getattr(entity, "confidence", 0.8),
                            timestamp=int(time.time()),
                        )
            yield update
            time.sleep(2)

    def GetLVCStatus(self, request, context):
        """Get LVC (Live/Virtual/Constructive) layer status."""
        lvc = self.engine.lvc
        msg = pb.LVCStatus()
        for layer_name, layer in [
            ("Live", lvc.live),
            ("Virtual", lvc.virtual),
            ("Constructive", lvc.constructive),
        ]:
            count = len(layer.entities) if layer else 0
            msg.layers.add(
                layer_name=layer_name,
                enabled=True,
                entity_count=count,
                description=f"{layer_name} layer: {count} entities",
            )
        msg.total_entities = len(self.engine._entities)
        return msg


class ApplicationStoreServicer(pb_grpc.ApplicationStoreServicer):
    """DTB ApplicationStore service - capability management."""

    def __init__(self, engine: PMTECEngine):
        self.engine = engine

    def ListApps(self, request, context):
        msg = pb.AppList()
        for app_id, app in self.engine._app_store.items():
            if request.category and app["category"] != request.category:
                continue
            msg.apps.add(
                app_id=app["app_id"],
                name=app["name"],
                version=app["version"],
                category=app["category"],
                description=app["description"],
            )
        return msg

    def DeployApp(self, request, context):
        app = self.engine._app_store.get(request.app_id)
        if not app:
            return pb.DeployResult(
                success=False, message=f"App {request.app_id} not found"
            )
        deploy_id = f"DEP-{uuid.uuid4().hex[:8]}"
        self.engine._emit_event(
            "deploy",
            "ApplicationStore",
            f"App {app['name']} deployed to {request.target_base} x{request.count}",
            {
                "app_id": request.app_id,
                "base": request.target_base,
                "count": request.count,
                "lvc_layer": "Constructive",
            },
        )
        return pb.DeployResult(
            success=True,
            message=f"{app['name']} v{app['version']} deployed to {request.target_base}",
            deployment_id=deploy_id,
        )

    def QueryCapability(self, request, context):
        base = next((b for b in self.engine._bases if b["id"] == request.base_id), None)
        if not base:
            return pb.CapabilityReport(base_id=request.base_id)
        ac_list = [
            e
            for e in self.engine._entities
            if isinstance(e, AircraftEntity)
            and e.base_id == base["id"]
            and e.status == "active"
        ]
        strike = sum(
            1
            for a in ac_list
            if a.subtype.startswith("F-3") or a.subtype.startswith("F-15")
        )
        defense = len([s for s in self.engine._sensors if s.base_id == base["id"]])
        isr = len([a for a in ac_list if a.subtype in ("RC-135", "E-3")])
        logistics = len([a for a in ac_list if a.subtype.startswith("KC-")])
        return pb.CapabilityReport(
            base_id=base["id"],
            strike_capability=strike,
            defense_capability=defense,
            isr_capability=isr,
            logistics_capability=logistics,
        )

    # ---- P2: DQN inference RPCs ----

    def DQNInfer(self, request, context):
        """Run DQN inference on observation vector."""
        if not self.engine.dqn or not self.engine.dqn.is_trained():
            return pb.DQNInferenceResult(action=0, device="none")

        import numpy as np

        obs = np.array(request.observation, dtype=np.float32)
        action = self.engine.dqn.predict(obs, deterministic=request.deterministic)
        # Try to get Q-values if model is available
        q_values = []
        try:
            model = self.engine.dqn.model
            obs_tensor = model.policy.obs_to_tensor(obs)[0]
            q_vals = model.policy.q_net(obs_tensor)
            q_values = q_vals.detach().cpu().numpy().flatten().tolist()
        except Exception:
            pass

        device = "cpu"
        try:
            import torch

            device = str(model.policy.q_net.device)
        except Exception:
            pass

        return pb.DQNInferenceResult(
            action=int(action),
            q_values=q_values,
            device=device,
        )

    def GetDQNStatus(self, request, context):
        """Get DQN training status."""
        dqn = self.engine.dqn
        if not dqn:
            return pb.DQNTrainingStatus(is_trained=False)

        is_trained = dqn.is_trained()
        training_runs = getattr(dqn, "training_runs", 0)
        total_timesteps = getattr(dqn, "total_timesteps", 0)
        device = "cpu"
        policy_arch = ""
        obs_dim = 0
        action_space = 0
        try:
            model = dqn.model
            if model:
                import torch

                device = str(model.policy.q_net.device)
                policy_arch = str(model.policy.net_arch)
                obs_dim = model.observation_space.shape[0]
                action_space = model.action_space.n
        except Exception:
            pass

        return pb.DQNTrainingStatus(
            is_trained=is_trained,
            training_runs=training_runs,
            total_timesteps=total_timesteps,
            device=device,
            policy_arch=policy_arch,
            observation_dim=obs_dim,
            action_space_size=action_space,
        )


class PlugAndPlayServicer(pb_grpc.PlugAndPlayServicer):
    """DTB PlugAndPlay service - component registration and discovery."""

    def __init__(self, engine: PMTECEngine):
        self.engine = engine

    def RegisterComponent(self, request, context):
        comp_id = request.component_id or f"comp-{uuid.uuid4().hex[:8]}"
        self.engine._components[comp_id] = {
            "component_id": comp_id,
            "component_type": request.component_type,
            "endpoint": request.endpoint,
            "metadata": dict(request.metadata),
        }
        return pb.RegResult(
            success=True,
            component_id=comp_id,
            message=f"Component {comp_id} registered as {request.component_type}",
        )

    def DiscoverServices(self, request, context):
        msg = pb.ServiceList()
        for comp_id, comp in self.engine._components.items():
            if request.service_type and comp["component_type"] != request.service_type:
                continue
            msg.services.add(
                service_id=comp_id,
                service_type=comp["component_type"],
                endpoint=comp["endpoint"],
                healthy=True,
            )
        return msg

    def HealthCheck(self, request, context):
        uptime = time.time() - self.engine._start_time if self.engine._start_time else 0
        return pb.HealthStatus(
            healthy=True,
            version="PMTEC-v1.0",
            uptime_seconds=int(uptime),
            cpu_usage=round(random.uniform(10, 40), 1),
            active_connections=len(self.engine._components),
        )

    # ---- P2: Platform management RPCs ----

    def ListPlugins(self, request, context):
        """List registered plugins."""
        msg = pb.PluginList()
        pm = self.engine.plugin_manager
        if not pm:
            return msg
        # Use list_plugins() which returns list of dicts, fall back to _plugins
        plugin_list = pm.list_plugins() if hasattr(pm, "list_plugins") else []
        for pinfo in plugin_list:
            if (
                request.plugin_type
                and pinfo.get("plugin_type", "") != request.plugin_type
            ):
                continue
            if request.active_only and not pinfo.get("active", True):
                continue
            msg.plugins.add(
                plugin_id=pinfo.get("plugin_id", ""),
                name=pinfo.get("name", ""),
                version=pinfo.get("version", "1.0"),
                author=pinfo.get("author", "unknown"),
                description=pinfo.get("description", ""),
                plugin_type=pinfo.get("plugin_type", "generic"),
                active=pinfo.get("active", True),
                call_count=pinfo.get("call_count", 0),
                error_count=pinfo.get("error_count", 0),
            )
        return msg

    def ListDTInstances(self, request, context):
        """List registered Digital Twin instances."""
        msg = pb.DTInstanceList()
        dtr = self.engine.dt_registry
        if not dtr:
            return msg
        for inst in dtr.list_instances():
            dti = msg.instances.add(
                instance_id=inst.get("instance_id", ""),
                name=inst.get("name", ""),
                scenario=inst.get("scenario", ""),
                status=inst.get("status", ""),
                created_at=int(inst.get("created_at", 0)),
            )
            for k, v in inst.get("metadata", {}).items():
                dti.metadata[str(k)] = str(v)
            dti.tags.extend(inst.get("tags", []))
        return msg

    def RegisterDTInstance(self, request, context):
        """Register a new Digital Twin instance."""
        dtr = self.engine.dt_registry
        if not dtr:
            return pb.DTInstanceInfo()
        inst = dtr.register(
            {
                "name": request.name,
                "scenario": request.scenario,
                "tags": list(request.tags),
                "metadata": dict(request.metadata),
            }
        )
        return pb.DTInstanceInfo(
            instance_id=inst.get("instance_id", ""),
            name=inst.get("name", ""),
            scenario=inst.get("scenario", ""),
            status=inst.get("status", ""),
            created_at=int(inst.get("created_at", 0)),
        )


class PMTECServer:
    """PMTEC gRPC Server - hosts all DTB Model services with P7 security.

    P7-v2: Adds gRPC Health Check Protocol for HA support.
    """

    def __init__(
        self,
        host: str = GRPC_HOST,
        port: int = GRPC_PORT,
        security_enabled: bool = None,
        mtls_enabled: bool = None,
    ):
        self.host = host
        self.port = port
        self.engine = PMTECEngine()
        self._server: Optional[grpc.Server] = None
        self._health_servicer: Optional["health.HealthServicer"] = None
        self._health_watcher: Optional[threading.Thread] = None
        self._tracing: Optional["TracingManager"] = None

        # P7: Security initialization
        sec_cfg = getattr(pmtec_config, "SECURITY_ENABLED", True)
        mtls_cfg = getattr(pmtec_config, "MTLS_ENABLED", True)
        self._security_enabled = (
            security_enabled if security_enabled is not None else sec_cfg
        )
        self._mtls_enabled = mtls_enabled if mtls_enabled is not None else mtls_cfg
        self._auth = None
        self._rbac = None
        self._audit = None
        self._cert_mgr = None
        self._interceptor = None

        if self._security_enabled and _security_available:
            jwt_hours = getattr(pmtec_config, "JWT_EXPIRATION_HOURS", 24)
            jwt_secret = getattr(pmtec_config, "JWT_SECRET", None)
            self._auth = AuthManager(secret=jwt_secret, expiration_hours=jwt_hours)
            self._rbac = RBACManager()
            audit_path = getattr(pmtec_config, "AUDIT_DB_PATH", None)
            self._audit = AuditLogger(audit_path)
            self._interceptor = AuthInterceptor(self._auth, self._rbac, self._audit)
        elif self._security_enabled and not _security_available:
            print("[WARN] Security requested but security package not available")

        if self._mtls_enabled and _security_available:
            cert_dir = getattr(pmtec_config, "CERT_DIR", None)
            self._cert_mgr = CertificateManager(cert_dir)

        # P8-v2: Distributed tracing (graceful no-op if not installed)
        try:
            from tracing import TracingManager

            self._tracing = TracingManager()
        except ImportError:
            self._tracing = None

    def issue_token(self, user_id: str, role: str):
        """Issue a JWT token for a user. Used by clients to authenticate."""
        if self._auth:
            return self._auth.issue_token(user_id, role)
        return None

    def authenticate(self, user_id: str, password: str, role: str):
        """Authenticate a user and return a token."""
        if self._auth:
            return self._auth.authenticate(user_id, password, role)
        return None

    def get_client_credentials(self):
        """Get mTLS client credentials for connecting to this server."""
        if self._cert_mgr:
            return self._cert_mgr.get_client_channel_credentials()
        return None

    def get_audit_logger(self):
        """Access the audit logger for querying operation history."""
        return self._audit

    def get_cert_info(self) -> dict:
        """Return certificate status information."""
        if self._cert_mgr:
            return self._cert_mgr.get_cert_info()
        return {}

    def start(self):
        """Start the gRPC server with all DTB services, security, and health check.

        P7-v2: Added gRPC Health Check Protocol for HA support.
        """
        interceptors = []
        if self._interceptor:
            interceptors.append(self._interceptor)

        # P8-v2: Initialize distributed tracing
        tracing_interceptor = None
        if self._tracing:
            self._tracing.setup()
            tracing_interceptor = self._tracing.create_grpc_server_interceptor()
            if tracing_interceptor:
                interceptors.append(tracing_interceptor)

        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=pmtec_config.GRPC_MAX_WORKERS),
            interceptors=interceptors,
            options=[
                ("grpc.max_concurrent_rpcs", pmtec_config.GRPC_MAX_CONCURRENT_RPCS),
                ("grpc.max_receive_message_length", 16 * 1024 * 1024),
                ("grpc.max_send_message_length", 16 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.keepalive_permit_without_calls", 1),
            ],
        )
        pb_grpc.add_WarEngineServicer_to_server(
            WarEngineServicer(self.engine), self._server
        )
        pb_grpc.add_BattleNetworkServicer_to_server(
            BattleNetworkServicer(self.engine), self._server
        )
        pb_grpc.add_ApplicationStoreServicer_to_server(
            ApplicationStoreServicer(self.engine), self._server
        )
        pb_grpc.add_PlugAndPlayServicer_to_server(
            PlugAndPlayServicer(self.engine), self._server
        )

        # P7-v2: gRPC Health Check Protocol
        try:
            from grpc_health.v1 import health, health_pb2, health_pb2_grpc

            self._health_servicer = health.HealthServicer()
            health_pb2_grpc.add_HealthServicer_to_server(
                self._health_servicer, self._server
            )
            # Set all services to SERVING
            for svc in (
                "",
                "pmtec.WarEngine",
                "pmtec.BattleNetwork",
                "pmtec.ApplicationStore",
                "pmtec.PlugAndPlay",
            ):
                self._health_servicer.set(svc, health_pb2.HealthCheckResponse.SERVING)
            print("[Server] gRPC Health Check Protocol enabled (HA-ready)")
        except ImportError:
            print("[WARN] grpcio-health-checking not installed; health check disabled")

        if self._cert_mgr:
            creds = self._cert_mgr.load_server_credentials()
            self._server.add_secure_port(f"{self.host}:{self.port}", creds)
        else:
            self._server.add_insecure_port(f"{self.host}:{self.port}")

        self._server.start()
        return True

    def set_unhealthy(self, service: str = ""):
        """Mark a service as NOT_SERVING (for graceful shutdown / HA failover)."""
        if self._health_servicer:
            try:
                from grpc_health.v1 import health_pb2

                self._health_servicer.set(
                    service, health_pb2.HealthCheckResponse.NOT_SERVING
                )
            except ImportError:
                pass

    def stop(self):
        if self._server:
            self.engine.stop_simulation()
            self._server.stop(grace=2)
        return True

    def wait_for_termination(self):
        if self._server:
            self._server.wait_for_termination()

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"
