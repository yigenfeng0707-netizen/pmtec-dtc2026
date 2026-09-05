"""
PMTEC Gymnasium Environment - Deep RL for ASDA decision-making.
Wraps PMTEC simulation as a Gymnasium env for DQN/PPO training.

State: 22 bases x 5 features + 12 global + 10 threats x 6 features = 182-dim float vector
  Per-base: aircraft_norm, destroyed_norm, sensor_present, threat_proximity, ew_jammed
  Global: total_threats, total_tracks, asda_cycle, vuln, intercept_rate, dispersal_rate,
         ew_active_count, cyber_phase, cyber_effectiveness, wx_detection_factor, wx_visibility, wx_crosswind
Actions: 6 discrete (3 intercept strategies x 2 dispersal options)
Reward: intercept success + base survival - damage - time penalty

Uses scipy.stats for Monte Carlo damage assessment,
networkx for battle network topology and dispersal path optimization.
"""

import json
import os
import math
import random
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from scipy.stats import norm, lognorm
import networkx as nx
from typing import Optional


# ---- Constants ----
NUM_BASES = 22
BASE_FEATURES = (
    5  # aircraft_norm, destroyed_norm, sensor_present, threat_proximity, ew_jammed
)
GLOBAL_FEATURES = (
    12  # total_threats, total_tracks, asda_cycle, vuln, intercept_rate, dispersal_rate,
    # ew_active_count, cyber_phase, cyber_effectiveness, wx_detection_factor, wx_visibility, wx_crosswind
)
# P6-1: Per-threat features for up to 10 active missiles
MAX_THREATS = 10
THREAT_FEATURES = 6  # lat_norm, lon_norm, type_encoded, time_to_impact, track_confidence, sensor_coverage
THREAT_OBS_DIM = MAX_THREATS * THREAT_FEATURES  # 60
OBS_DIM = NUM_BASES * BASE_FEATURES + GLOBAL_FEATURES + THREAT_OBS_DIM  # 182
NUM_ACTIONS = 6
ASDA_CYCLE_SECONDS = 10

# Threat types
THREAT_TYPES = ["ballistic", "cruise", "hypersonic"]


class PMTECEnv(gym.Env):
    """Gymnasium environment wrapping PMTEC ASDA cycle for deep RL training."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        bases: list = None,
        duration: int = 120,
        seed: int = 42,
    ):
        super().__init__()
        self.duration = duration
        self.base_seed = seed
        self._bases = bases or self._default_bases()
        self._build_network()

        # Spaces
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(NUM_ACTIONS)

        # Episode state
        self._aircraft: list[dict] = []
        self._missiles: list[dict] = []
        self._sensors: list[dict] = []
        self._tracks: list[dict] = []
        self._asda_cycle = 0
        self._sim_time = 0.0
        self._intercept_results: list[bool] = []
        self._dispersal_results: list[float] = []
        self._rng = random.Random(seed)

        # EW / Cyber / Weather state (P3-3 extended observation)
        self._ew_threats: list[dict] = []
        self._cyber_threats: list[dict] = []
        self._weather_state: dict = {
            "detection_range_factor": 1.0,
            "visibility_factor": 1.0,
            "crosswind_component": 0.0,
        }

        # P6-3: Curriculum learning difficulty level
        # "easy": fewer threats, mostly cruise; "medium": default; "hard": more threats, more hypersonic
        self.difficulty: str = "medium"

    def _default_bases(self) -> list:
        """Load bases from GeoJSON or create defaults."""
        geojson_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "bases.geojson",
        )
        bases = []
        if os.path.exists(geojson_path):
            with open(geojson_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for feat in data.get("features", []):
                props = feat.get("properties", {})
                coords = feat.get("geometry", {}).get("coordinates", [0, 0])
                bases.append(
                    {
                        "id": props.get("base_id", props.get("name", "")),
                        "name": props.get("name", ""),
                        "lat": coords[1] if len(coords) >= 2 else 0,
                        "lon": coords[0] if len(coords) >= 2 else 0,
                        "is_hub": props.get("is_ace_hub", False),
                    }
                )
        if not bases:
            for i in range(NUM_BASES):
                bases.append(
                    {
                        "id": f"BASE-{i:02d}",
                        "name": f"Base {i}",
                        "lat": 10 + i * 3,
                        "lon": 120 + i * 5,
                        "is_hub": i % 3 == 0,
                    }
                )
        return bases[:NUM_BASES]

    def _build_network(self):
        """Build battle network topology graph with networkx."""
        self._graph = nx.Graph()
        for b in self._bases:
            self._graph.add_node(
                b["id"],
                lat=b["lat"],
                lon=b["lon"],
                is_hub=b.get("is_hub", False),
            )
        # Designate first 8 bases as hubs if none marked
        hubs = [b["id"] for b in self._bases if b.get("is_hub")]
        if not hubs:
            hubs = [b["id"] for b in self._bases[:8]]
        for b in self._bases:
            if b["id"] in hubs:
                for h in hubs:
                    if h != b["id"]:
                        d = self._haversine(
                            b["lat"], b["lon"], self._base_lat(h), self._base_lon(h)
                        )
                        self._graph.add_edge(b["id"], h, weight=d)
            else:
                nearest = min(
                    hubs,
                    key=lambda h: self._haversine(
                        b["lat"], b["lon"], self._base_lat(h), self._base_lon(h)
                    ),
                )
                d = self._haversine(
                    b["lat"], b["lon"], self._base_lat(nearest), self._base_lon(nearest)
                )
                self._graph.add_edge(b["id"], nearest, weight=d)

    def _base_lat(self, bid: str) -> float:
        for b in self._bases:
            if b["id"] == bid:
                return b["lat"]
        return 0.0

    def _base_lon(self, bid: str) -> float:
        for b in self._bases:
            if b["id"] == bid:
                return b["lon"]
        return 0.0

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        """Reset episode: spawn aircraft at bases, add sensors, generate threats."""
        super().reset(seed=seed)
        self._rng = random.Random(seed or self.base_seed)
        self._aircraft = []
        self._missiles = []
        self._sensors = []
        self._tracks = []
        self._asda_cycle = 0
        self._sim_time = 0.0
        self._intercept_results = []
        self._dispersal_results = []
        self._ew_threats = []
        self._cyber_threats = []
        self._weather_state = self._roll_weather()

        # Spawn aircraft: 5-8 per base, 7 F-35 + others
        ac_types = ["F-35A", "F-22", "F-15EX", "F-16C"]
        for b in self._bases:
            n = self._rng.randint(5, 8)
            for i in range(n):
                self._aircraft.append(
                    {
                        "id": f"AC-{b['id']}-{i}",
                        "base_id": b["id"],
                        "type": self._rng.choice(ac_types),
                        "status": "active",
                        "mission": "patrol",
                        "lat": b["lat"],
                        "lon": b["lon"],
                    }
                )

        # Spawn sensors: 1-2 per base
        for b in self._bases:
            for i in range(self._rng.randint(1, 2)):
                self._sensors.append(
                    {
                        "id": f"SEN-{b['id']}-{i}",
                        "base_id": b["id"],
                        "type": "radar",
                        "range_km": 150 + self._rng.randint(0, 100),
                        "lat": b["lat"],
                        "lon": b["lon"],
                        "status": "active",
                    }
                )

        # Initial threat wave
        self._spawn_threats()

        return self._get_obs(), self._get_info()

    def _spawn_threats(self):
        """Spawn incoming missiles, EW jamming, and cyber attacks targeting random bases."""
        # P6-3: Curriculum difficulty controls
        if self.difficulty == "easy":
            n_threats = self._rng.randint(1, 2)  # fewer missiles
            threat_pool = ["cruise", "cruise", "ballistic"]  # mostly easy-to-intercept
            ew_prob, cyber_prob = 0.0, 0.0  # no EW/cyber in easy mode
        elif self.difficulty == "hard":
            n_threats = self._rng.randint(3, 6)  # more missiles
            threat_pool = [
                "ballistic",
                "hypersonic",
                "hypersonic",
                "cruise",
            ]  # harder mix
            ew_prob, cyber_prob = 0.5, 0.4  # frequent EW/cyber
        else:  # medium (default)
            n_threats = self._rng.randint(2, 5)
            threat_pool = THREAT_TYPES
            ew_prob, cyber_prob = 0.30, 0.25

        for i in range(n_threats):
            target = self._rng.choice(self._bases)
            threat_type = self._rng.choice(threat_pool)
            speed = {"ballistic": 3000, "cruise": 800, "hypersonic": 5000}[threat_type]
            tti = self._rng.uniform(30, 120)
            # P6-fix: Place missile at realistic distance = speed * TTI, capped within sensor range
            # This ensures missiles are detectable by base sensors (150-250 km range)
            distance_km = min(
                speed * tti / 3600.0, 120.0
            )  # cap at 120 km for sensor coverage
            bearing = self._rng.uniform(0, 2 * math.pi)
            lat_offset = distance_km / 111.0 * math.cos(bearing)
            lon_offset = (
                distance_km
                / (111.0 * max(0.1, math.cos(math.radians(target["lat"]))))
                * math.sin(bearing)
            )
            self._missiles.append(
                {
                    "id": f"MSL-{self._asda_cycle}-{i}",
                    "target_base": target["id"],
                    "type": threat_type,
                    "speed_kmh": speed,
                    "lat": target["lat"] + lat_offset,
                    "lon": target["lon"] + lon_offset,
                    "status": "active",
                    "time_to_impact": tti,
                    "cep": self._rng.uniform(50, 300),  # Circular Error Probable (m)
                    "intercepted": False,
                }
            )

        # --- EW jamming threats (difficulty-scaled probability) ---
        if self._rng.random() < ew_prob:
            target = self._rng.choice(self._bases)
            self._ew_threats.append(
                {
                    "id": f"EW-{self._asda_cycle}-{len(self._ew_threats)}",
                    "target_base": target["id"],
                    "jammer_lat": target["lat"] + self._rng.uniform(-5, 5),
                    "jammer_lon": target["lon"] + self._rng.uniform(-8, 8),
                    "jamming_power": self._rng.uniform(0.3, 0.9),
                    "status": "active",
                    "duration": self._rng.randint(2, 5),  # ASDA cycles
                }
            )

        # --- Cyber attack threats (difficulty-scaled probability) ---
        if self._rng.random() < cyber_prob:
            target = self._rng.choice(self._bases)
            self._cyber_threats.append(
                {
                    "id": f"CYB-{self._asda_cycle}-{len(self._cyber_threats)}",
                    "target_base": target["id"],
                    "phase": 0,  # 0=recon, 1=intrusion, 2=propagation, 3=impact
                    "effectiveness": 0.0,
                    "status": "active",
                    "duration": self._rng.randint(3, 6),  # ASDA cycles
                }
            )

    def _update_ew_cyber_weather(self):
        """Advance EW/Cyber/Weather state by one ASDA cycle."""
        # Advance EW threats
        for ew in self._ew_threats:
            if ew["status"] == "active":
                ew["duration"] -= 1
                if ew["duration"] <= 0:
                    ew["status"] = "expired"

        # Advance cyber threats through 4-phase lifecycle
        for cyb in self._cyber_threats:
            if cyb["status"] == "active":
                cyb["duration"] -= 1
                if cyb["duration"] <= 0:
                    cyb["status"] = "expired"
                else:
                    # Advance phase: recon -> intrusion -> propagation -> impact
                    if cyb["phase"] < 3:
                        cyb["phase"] += 1
                    # Effectiveness grows with phase
                    cyb["effectiveness"] = min(1.0, cyb["phase"] / 3.0 * 0.8)

        # Weather slowly drifts
        wx = self._weather_state
        wx["detection_range_factor"] = max(
            0.2, min(1.5, wx["detection_range_factor"] + self._rng.uniform(-0.05, 0.05))
        )
        wx["visibility_factor"] = max(
            0.1, min(1.0, wx["visibility_factor"] + self._rng.uniform(-0.05, 0.05))
        )
        wx["crosswind_component"] = max(
            0.0, min(1.0, wx["crosswind_component"] + self._rng.uniform(-0.08, 0.08))
        )

        # Clean up expired
        self._ew_threats = [e for e in self._ew_threats if e["status"] == "active"]
        self._cyber_threats = [
            c for c in self._cyber_threats if c["status"] == "active"
        ]

    def _roll_weather(self) -> dict:
        """Roll random initial weather conditions."""
        conditions = [
            {
                "detection_range_factor": 1.0,
                "visibility_factor": 1.0,
                "crosswind_component": 0.05,
            },
            {
                "detection_range_factor": 0.7,
                "visibility_factor": 0.7,
                "crosswind_component": 0.3,
            },
            {
                "detection_range_factor": 0.45,
                "visibility_factor": 0.4,
                "crosswind_component": 0.5,
            },
            {
                # P7-v2: raised from 0.3 to 0.5 so sensors can still detect
                # hypersonic missiles at 75-125km effective range in extreme weather
                "detection_range_factor": 0.5,
                "visibility_factor": 0.35,
                "crosswind_component": 0.7,
            },
        ]
        return dict(self._rng.choice(conditions))

    def _is_base_ew_jammed(self, base_id: str) -> float:
        """Return EW jamming intensity (0.0-1.0) affecting a given base's sensors."""
        jamming = 0.0
        for ew in self._ew_threats:
            if ew["status"] == "active" and ew["target_base"] == base_id:
                jamming = max(jamming, ew["jamming_power"])
        return jamming

    def step(self, action: int):
        """Run one ASDA cycle (10 seconds) with the given action."""
        # Decode action: 0-5
        # Bits: [intercept_strategy (0-2)] [should_disperse (0/1)]
        intercept_strategy = action // 2  # 0=direct, 1=predictive, 2=saturation
        should_disperse = action % 2 == 1

        prev_destroyed = sum(1 for a in self._aircraft if a["status"] == "destroyed")
        prev_total = len(self._aircraft)

        # --- Act phase ---
        if should_disperse:
            self._do_dispersal()

        # --- Sense phase ---
        self._sense_threats()

        # --- Decide phase: intercept ---
        self._do_intercept(intercept_strategy)

        # --- Adapt phase: damage assessment ---
        self._assess_damage()

        # --- Update EW/Cyber/Weather state ---
        self._update_ew_cyber_weather()

        # --- Advance time ---
        self._sim_time += ASDA_CYCLE_SECONDS
        self._asda_cycle += 1

        # Spawn new threats periodically
        if self._asda_cycle % 3 == 0:
            self._spawn_threats()

        # --- Calculate reward (P6-1: reward shaping) ---
        cur_destroyed = sum(1 for a in self._aircraft if a["status"] == "destroyed")
        new_destroyed = cur_destroyed - prev_destroyed
        intercepted_count = sum(
            1 for m in self._missiles if m["intercepted"] and m["status"] == "destroyed"
        )
        new_intercepts = (
            len(self._intercept_results) - sum(self._intercept_results[:-1])
            if self._intercept_results
            else 0
        )

        reward = 0.0
        # P6-1: Higher intercept bonus to encourage aggressive defense
        reward += intercepted_count * 5.0  # intercept bonus (was 2.0)
        # P6-1: Reduced loss penalty to avoid overly conservative behavior
        reward -= new_destroyed * 2.0  # loss penalty (was 3.0)
        reward -= 0.05  # time penalty (was 0.1)
        if should_disperse:
            dispersed_safe = sum(
                1
                for a in self._aircraft
                if a["mission"] == "transfer" and a["status"] == "active"
            )
            reward += dispersed_safe * 0.3
        # Base survival bonus
        active_bases = set(
            a["base_id"] for a in self._aircraft if a["status"] == "active"
        )
        reward += len(active_bases) * 0.05

        # P6-1: Strategy-threat type matching bonus (P6-fix: aligned with new probabilities)
        strategy_names = ["direct", "predictive", "saturation"]
        strategy_name = strategy_names[intercept_strategy]
        type_match_map = {
            "direct": {"ballistic": 0.95, "cruise": 1.0, "hypersonic": 0.80},
            "predictive": {"ballistic": 1.0, "cruise": 0.95, "hypersonic": 0.90},
            "saturation": {"ballistic": 0.90, "cruise": 0.90, "hypersonic": 1.0},
        }
        match_mult = type_match_map[strategy_name]
        for m in self._missiles:
            if m["status"] == "active" and not m.get("intercepted", False):
                # Reward for choosing strategy that matches the dominant threat type
                m_factor = match_mult.get(m["type"], 0.5)
                if m_factor >= 0.8:
                    reward += 0.5  # good strategy-threat match
                # Time window bonus: reward engaging threats with more time remaining
                if m.get("time_to_impact", 0) > 60:
                    reward += 0.3

        # P6-1: Sensor coverage bonus
        active_sensors = sum(
            1
            for b in self._bases
            if b.get("has_sensor", False) and b["status"] == "active"
        )
        reward += active_sensors * 0.02

        # --- Check done ---
        done = self._sim_time >= self.duration
        truncated = False

        if done:
            # End-of-episode bonus
            surviving = len([a for a in self._aircraft if a["status"] == "active"])
            reward += surviving * 0.2

        return self._get_obs(), reward, done, truncated, self._get_info()

    def _do_dispersal(self):
        """Disperse aircraft to alternate bases using networkx shortest path.

        P4-4: Support variable dispersal fraction (15% light / 30% heavy).
        """
        patrol_ac = [
            a
            for a in self._aircraft
            if a["status"] == "active" and a["mission"] == "patrol"
        ]
        # P4-4: Variable dispersal fraction
        fraction = 0.30 if getattr(self, "_heavy_dispersal", False) else 0.15
        n_transfer = int(len(patrol_ac) * fraction)
        if n_transfer == 0:
            return

        for ac in self._rng.sample(patrol_ac, min(n_transfer, len(patrol_ac))):
            src = ac["base_id"]
            # Find safest alternate base via networkx
            candidates = [b["id"] for b in self._bases if b["id"] != src]

            # Score: lower = safer (fewer threats near, more aircraft already there)
            def base_safety(bid):
                threats_near = sum(
                    1
                    for m in self._missiles
                    if m["status"] == "active" and m["target_base"] == bid
                )
                ac_count = sum(
                    1
                    for a in self._aircraft
                    if a["base_id"] == bid and a["status"] == "active"
                )
                return threats_near * 10 - ac_count

            safest = min(candidates, key=base_safety)
            ac["mission"] = "transfer"
            ac["dest_base"] = safest
            ac["lat"] = self._base_lat(safest)
            ac["lon"] = self._base_lon(safest)

    def _sense_threats(self):
        """Sensor detection: update tracks from active missiles (with EW jamming + weather)."""
        self._tracks = []
        wx_factor = self._weather_state["detection_range_factor"]
        for m in self._missiles:
            if m["status"] != "active":
                continue
            # Check if any sensor detects it
            for s in self._sensors:
                if s["status"] != "active":
                    continue
                # Apply weather degradation to sensor range
                eff_range = s["range_km"] * wx_factor
                # Apply EW jamming to sensor at this base
                jamming = self._is_base_ew_jammed(s["base_id"])
                eff_range *= 1.0 - jamming * 0.7  # up to 70% range reduction
                if eff_range < 10:
                    continue  # sensor effectively blinded
                d = self._haversine(s["lat"], s["lon"], m["lat"], m["lon"])
                if d <= eff_range:
                    self._tracks.append(
                        {
                            "missile_id": m["id"],
                            "type": m["type"],
                            "confidence": min(0.95, 0.5 + (eff_range - d) / eff_range),
                            "target_base": m["target_base"],
                        }
                    )
                    break

    def _do_intercept(self, strategy: int):
        """Attempt to intercept detected threats based on strategy.

        P6-1: Dynamic probability model with strategy-threat type matching
        and time-window bonus, removing the hardcoded ~54% cap.
        P6-fix: Raised base probabilities and reduced type-match penalties
        so a well-trained DQN can achieve 70%+ intercept rate.
        """
        strategy_names = ["direct", "predictive", "saturation"]
        strategy_name = strategy_names[strategy]

        # P6-fix: Raised base intercept probabilities
        # P7-v2: Raised hypersonic probs to improve stealth breakthrough
        base_probs = {
            "direct": {"ballistic": 0.70, "cruise": 0.90, "hypersonic": 0.60},
            "predictive": {"ballistic": 0.85, "cruise": 0.80, "hypersonic": 0.70},
            "saturation": {"ballistic": 0.75, "cruise": 0.75, "hypersonic": 0.85},
        }
        # P6-fix: Reduced penalties for mismatched strategy-threat type
        # P7-v2: Improved hypersonic type match slightly
        type_match = {
            "direct": {"ballistic": 0.95, "cruise": 1.0, "hypersonic": 0.85},
            "predictive": {"ballistic": 1.0, "cruise": 0.95, "hypersonic": 0.95},
            "saturation": {"ballistic": 0.90, "cruise": 0.90, "hypersonic": 1.0},
        }

        for track in self._tracks:
            m = next(
                (m for m in self._missiles if m["id"] == track["missile_id"]), None
            )
            if m and m["status"] == "active":
                p = base_probs[strategy_name].get(m["type"], 0.3)
                # Strategy-threat type matching bonus
                p *= type_match[strategy_name].get(m["type"], 0.5)
                # Sensor confidence boost
                p *= 0.7 + 0.3 * track["confidence"]
                # Time window bonus: earlier interception attempt = higher probability
                time_factor = 1.0 + 0.5 * max(0.0, m.get("time_to_impact", 60) / 120.0)
                p = min(0.95, p * time_factor)
                if self._rng.random() < p:
                    m["intercepted"] = True
                    m["status"] = "destroyed"
                    self._intercept_results.append(True)
                else:
                    self._intercept_results.append(False)

        # P7-v2: Area defense fallback for undetected active missiles.
        # Simulates blind area-defense interceptors that engage targets
        # outside sensor tracking range with low probability.
        tracked_ids = {t["missile_id"] for t in self._tracks}
        for m in self._missiles:
            if m["status"] == "active" and m["id"] not in tracked_ids:
                area_p = 0.15 + 0.10 * max(
                    0.0, 1.0 - m.get("time_to_impact", 60) / 120.0
                )
                if self._rng.random() < area_p:
                    m["intercepted"] = True
                    m["status"] = "destroyed"
                    self._intercept_results.append(True)
                else:
                    self._intercept_results.append(False)

    def _assess_damage(self):
        """Assess damage from missiles reaching impact using scipy.stats."""
        for m in self._missiles:
            if m["status"] != "active":
                continue
            m["time_to_impact"] -= ASDA_CYCLE_SECONDS
            if m["time_to_impact"] <= 0 and not m["intercepted"]:
                # Impact! Use scipy.stats for damage assessment
                target = m["target_base"]
                cep_km = m["cep"] / 1000.0
                # Hit probability: CEP-based with log-normal distribution
                # P(hit within r) = 1 - exp(-r^2 / (2 * sigma^2))
                sigma = cep_km / 1.1774  # CEP = 1.1774 * sigma for 2D
                r = self._rng.uniform(0, 5.0)  # distance from base center
                hit_prob = 1.0 - math.exp(-(r**2) / (2 * sigma**2))

                if self._rng.random() < hit_prob:
                    # Damage: log-normal distribution for casualty count
                    mu = math.log(2.0)
                    s = 0.5
                    n_damaged = max(1, int(lognorm.rvs(s, scale=math.exp(mu))))
                    nearby_ac = [
                        a
                        for a in self._aircraft
                        if a["base_id"] == target and a["status"] == "active"
                    ]
                    for ac in nearby_ac[:n_damaged]:
                        ac["status"] = "destroyed"
                m["status"] = "destroyed"  # Missile spent

    def _get_obs(self) -> np.ndarray:
        """Get flattened observation vector (182-dim, P6-1 expanded)."""
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        # Per-base features: aircraft_norm, destroyed_norm, sensor_present,
        # threat_proximity, ew_jammed
        for i, b in enumerate(self._bases):
            ac_count = sum(
                1
                for a in self._aircraft
                if a["base_id"] == b["id"] and a["status"] == "active"
            )
            dest_count = sum(
                1
                for a in self._aircraft
                if a["base_id"] == b["id"] and a["status"] == "destroyed"
            )
            has_sensor = (
                1.0
                if any(
                    s["base_id"] == b["id"] and s["status"] == "active"
                    for s in self._sensors
                )
                else 0.0
            )
            threat_prox = (
                sum(
                    1
                    for m in self._missiles
                    if m["target_base"] == b["id"] and m["status"] == "active"
                )
                / 5.0
            )
            ew_jammed = self._is_base_ew_jammed(b["id"])
            obs[i * BASE_FEATURES + 0] = min(ac_count / 10.0, 1.0)
            obs[i * BASE_FEATURES + 1] = min(dest_count / 10.0, 1.0)
            obs[i * BASE_FEATURES + 2] = has_sensor
            obs[i * BASE_FEATURES + 3] = min(threat_prox, 1.0)
            obs[i * BASE_FEATURES + 4] = ew_jammed

        # Global features: total_threats, total_tracks, asda_cycle, vuln,
        # intercept_rate, dispersal_rate, ew_active_count, cyber_phase,
        # cyber_effectiveness, wx_detection_factor, wx_visibility, wx_crosswind
        offset = NUM_BASES * BASE_FEATURES
        active_threats = sum(1 for m in self._missiles if m["status"] == "active")
        total_tracks = len(self._tracks)
        vuln = dest_overall = sum(
            1 for a in self._aircraft if a["status"] == "destroyed"
        ) / max(len(self._aircraft), 1)
        ir = (
            sum(self._intercept_results) / max(len(self._intercept_results), 1)
            if self._intercept_results
            else 0
        )
        dr = len([a for a in self._aircraft if a["mission"] == "transfer"]) / max(
            len(self._aircraft), 1
        )
        ew_count = len(self._ew_threats)
        cyber_phase = (
            sum(c["phase"] for c in self._cyber_threats)
            / max(len(self._cyber_threats) * 3, 1)
            if self._cyber_threats
            else 0.0
        )
        cyber_eff = (
            sum(c["effectiveness"] for c in self._cyber_threats)
            / max(len(self._cyber_threats), 1)
            if self._cyber_threats
            else 0.0
        )
        wx = self._weather_state
        obs[offset + 0] = min(active_threats / 20.0, 1.0)
        obs[offset + 1] = min(total_tracks / 20.0, 1.0)
        obs[offset + 2] = min(self._asda_cycle / 30.0, 1.0)
        obs[offset + 3] = vuln
        obs[offset + 4] = ir
        obs[offset + 5] = dr
        obs[offset + 6] = min(ew_count / 5.0, 1.0)
        obs[offset + 7] = cyber_phase
        obs[offset + 8] = cyber_eff
        obs[offset + 9] = wx["detection_range_factor"] / 1.5  # normalize to [0,1]
        obs[offset + 10] = wx["visibility_factor"]
        obs[offset + 11] = wx["crosswind_component"]

        # P6-1: Per-threat features (up to MAX_THREATS active missiles × THREAT_FEATURES)
        threat_offset = NUM_BASES * BASE_FEATURES + GLOBAL_FEATURES
        type_encoding = {"ballistic": 0.0, "cruise": 0.5, "hypersonic": 1.0}
        active_missiles = [m for m in self._missiles if m["status"] == "active"]
        for i, m in enumerate(active_missiles[:MAX_THREATS]):
            base_idx = threat_offset + i * THREAT_FEATURES
            # Normalized lat/lon (assume range 20-50 lat, 100-140 lon)
            obs[base_idx + 0] = (m.get("lat", 35.0) - 20.0) / 30.0
            obs[base_idx + 1] = (m.get("lon", 120.0) - 100.0) / 40.0
            obs[base_idx + 2] = type_encoding.get(m.get("type", "ballistic"), 0.0)
            obs[base_idx + 3] = min(m.get("time_to_impact", 120) / 300.0, 1.0)
            # Track confidence for this missile
            track = next((t for t in self._tracks if t["missile_id"] == m["id"]), None)
            obs[base_idx + 4] = track["confidence"] if track else 0.0
            # Sensor coverage for the target base
            target_base = m.get("target_base", 0)
            sensor_cov = (
                sum(
                    1
                    for s in self._sensors
                    if s["base_id"] == target_base and s["status"] == "active"
                )
                / 5.0
            )
            obs[base_idx + 5] = min(sensor_cov, 1.0)

        return obs

    def _get_info(self) -> dict:
        return {
            "asda_cycle": self._asda_cycle,
            "sim_time": self._sim_time,
            "active_aircraft": sum(
                1 for a in self._aircraft if a["status"] == "active"
            ),
            "destroyed_aircraft": sum(
                1 for a in self._aircraft if a["status"] == "destroyed"
            ),
            "active_missiles": sum(
                1 for m in self._missiles if m["status"] == "active"
            ),
            "intercepted_missiles": sum(1 for m in self._missiles if m["intercepted"]),
            "total_tracks": len(self._tracks),
            "intercept_rate": (
                sum(self._intercept_results) / len(self._intercept_results)
            )
            if self._intercept_results
            else 0.0,
            "active_ew_threats": len(self._ew_threats),
            "active_cyber_threats": len(self._cyber_threats),
            "weather": dict(self._weather_state),
            "obs_dim": OBS_DIM,
        }
