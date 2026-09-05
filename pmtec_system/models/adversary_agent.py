"""
Adversary Agent - Rule-driven hostile force decision-making.

Replaces random missile launch (random.random() < 0.30) with situational-aware
targeting based on:
  - Base value assessment (hub status, aircraft count, sensor coverage)
  - Defensive gap identification (bases with fewer defenses)
  - Adaptive timing (recon -> escalation -> sustained pressure)
  - Multi-domain coordination (kinetic + EW + Cyber)
  - Learning from attack history (success rate feedback)
"""

import random
import math
from typing import Optional


class AdversaryAgent:
    """Rule-driven adversary agent for hostile force decision-making.

    Decides attack timing, target selection, missile type, and
    coordinated EW/Cyber support based on real-time battlefield assessment.
    """

    # Missile types with characteristics
    MISSILE_TYPES = {
        "DF-17": {
            "speed": 7000,
            "cep": 30,
            "warhead": 800,
            "role": "hypersonic_precise",
        },
        "DF-21D": {"speed": 6000, "cep": 50, "warhead": 1000, "role": "general"},
        "DF-26": {"speed": 8000, "cep": 150, "warhead": 1500, "role": "heavy_hub"},
    }

    def __init__(
        self,
        aggression_level: float = 0.5,
        seed: int = 42,
        max_concurrent_threats: int = 8,
    ):
        self.baseline_aggression = aggression_level
        self._rng = random.Random(seed)
        self._max_concurrent = max_concurrent_threats
        self._attack_history: list[dict] = []
        self._attack_count = 0  # Total attacks decided (even if outcome unknown)
        self._cycles_since_last_attack = 0

    def decide_attack(
        self,
        bases: list,
        entities: list,
        missiles: list,
        sensors: list,
        asda_cycle: int,
    ) -> dict:
        """Decide whether and where to launch an attack this ASDA cycle.

        Returns dict with keys:
          should_attack: bool
          target_base: dict or None
          missile_type: str or None
          launch_lat: float or None
          launch_lon: float or None
          coordinated_ew: bool (launch EW jammer to suppress sensors at target?)
          coordinated_cyber: bool (launch cyber attack on target C2?)
          reasoning: str
        """
        # --- 1. Assess concurrent threat saturation ---
        active_missiles = sum(1 for m in missiles if m.status == "active")
        if active_missiles >= self._max_concurrent:
            return self._no_attack("Threat saturation: too many concurrent missiles")

        # --- 2. Adaptive aggression based on attack history ---
        recent = self._attack_history[-5:]
        if recent:
            success_rate = sum(1 for a in recent if a.get("hit", False)) / len(recent)
            # Increase aggression if successful, decrease if not
            adapted_aggression = self.baseline_aggression * (0.6 + 0.8 * success_rate)
        else:
            adapted_aggression = self.baseline_aggression

        # --- 3. Timing: minimal recon phase (cycles 0-1) ramps up quickly ---
        if asda_cycle < 1:
            # First cycle: low but non-zero attack probability
            cycle_factor = 0.5
        elif asda_cycle < 5:
            # Rapid escalation phase
            cycle_factor = 0.7 + 0.06 * (asda_cycle - 1)
        else:
            # Sustained pressure
            cycle_factor = 1.0

        # Cooldown: shorter cooldown for more frequent attacks
        cooldown = max(0.5, 1.0 - self._cycles_since_last_attack * 0.08)

        attack_prob = adapted_aggression * cycle_factor * cooldown

        if self._rng.random() > attack_prob:
            self._cycles_since_last_attack += 1
            return self._no_attack(
                f"Attack probability {attack_prob:.2f} not met (cycle={asda_cycle})"
            )

        # --- 4. Assess each base ---
        assessments = []
        for b in bases:
            ac_count = sum(
                1
                for e in entities
                if hasattr(e, "base_id")
                and e.base_id == b["id"]
                and e.status == "active"
                and e.affiliation == "friendly"
                and not hasattr(e, "detection_range_km")  # exclude sensors
            )
            # Count sensors protecting this base
            sensor_count = sum(
                1 for s in sensors if s.base_id == b["id"] and s.status == "active"
            )
            # Count active missiles already targeting this base
            threats_on_base = sum(
                1
                for m in missiles
                if m.status == "active"
                and hasattr(m, "target_lat")
                and abs(m.target_lat - b["lat"]) < 1.0
                and abs(m.target_lon - b["lon"]) < 1.0
            )
            is_hub = b.get("is_hub", b.get("is_ace_hub", False))

            # Value: hubs worth 2x, more aircraft = higher value target
            value = (2.0 if is_hub else 1.0) + ac_count * 0.15
            # Vulnerability: fewer aircraft + fewer sensors = more vulnerable
            vuln = 1.0 - min(ac_count / 12.0, 0.4) - min(sensor_count / 4.0, 0.3)
            vuln = max(0.1, vuln)
            # Threat pressure: already targeted bases get lower priority (avoid overkill)
            pressure = min(threats_on_base / 3.0, 1.0)

            # Priority = value * vulnerability * (1 - pressure * 0.7)
            priority = value * vuln * (1.0 - pressure * 0.7)

            assessments.append(
                {
                    "base": b,
                    "aircraft": ac_count,
                    "sensors": sensor_count,
                    "is_hub": is_hub,
                    "value": round(value, 2),
                    "vulnerability": round(vuln, 2),
                    "threat_pressure": round(pressure, 2),
                    "priority": round(priority, 3),
                }
            )

        if not assessments:
            return self._no_attack("No bases to target")

        # --- 5. Select target (weighted random from top-3) ---
        assessments.sort(key=lambda x: x["priority"], reverse=True)
        top_n = min(3, len(assessments))
        candidates = assessments[:top_n]

        # Weighted selection by priority
        weights = [c["priority"] for c in candidates]
        total_w = sum(weights)
        if total_w <= 0:
            target_assessment = candidates[0]
        else:
            r = self._rng.uniform(0, total_w)
            cum = 0.0
            target_assessment = candidates[0]
            for c in candidates:
                cum += c["priority"]
                if r <= cum:
                    target_assessment = c
                    break

        target = target_assessment["base"]

        # --- 6. Select missile type based on target characteristics ---
        if target_assessment["is_hub"] and target_assessment["aircraft"] > 5:
            missile_type = "DF-26"  # Heavy warhead for high-value hubs
        elif target_assessment["sensors"] > 2:
            missile_type = "DF-17"  # Hypersonic, precise CEP for sensor-dense bases
        elif target_assessment["aircraft"] <= 3:
            missile_type = "DF-17"  # Quick precision strike on weak bases
        else:
            missile_type = "DF-21D"  # General purpose

        # --- 7. Launch position: based on missile speed for 60-120s time-to-impact ---
        missile_speed = self.MISSILE_TYPES.get(missile_type, {}).get("speed", 6000)
        # Target 60-120 seconds flight time -> distance = speed * time / 3600
        tti_seconds = self._rng.uniform(60, 120)
        launch_dist_km = missile_speed * tti_seconds / 3600.0
        launch_dist_km = min(launch_dist_km, 120.0)  # Cap at 120 km (sensor range)
        # Convert km to degrees (approx: 1 deg lat ~111 km)
        deg_offset = launch_dist_km / 111.0
        # Random bearing for realistic seaward approach
        bearing_rad = self._rng.uniform(0, 2 * math.pi)
        launch_lat = target["lat"] + deg_offset * math.cos(bearing_rad)
        launch_lon = target["lon"] + deg_offset * math.sin(bearing_rad) / max(
            math.cos(math.radians(target["lat"])), 0.5
        )

        # --- 8. Coordinated multi-domain attacks ---
        # EW: launch jammer if target has multiple sensors (suppress defenses)
        coordinated_ew = target_assessment["sensors"] >= 2 and self._rng.random() < 0.4
        # Cyber: attack C2 if hub (disrupt coordination before kinetic strike)
        coordinated_cyber = target_assessment["is_hub"] and self._rng.random() < 0.35

        reasoning = (
            f"Target {target['id']} ({target['name']}): "
            f"value={target_assessment['value']}, "
            f"vuln={target_assessment['vulnerability']}, "
            f"priority={target_assessment['priority']}. "
            f"Missile={missile_type}. "
            f"EW_support={coordinated_ew}, Cyber_support={coordinated_cyber}"
        )

        self._cycles_since_last_attack = 0
        self._attack_count += 1
        return {
            "should_attack": True,
            "target_base": target,
            "missile_type": missile_type,
            "launch_lat": launch_lat,
            "launch_lon": launch_lon,
            "coordinated_ew": coordinated_ew,
            "coordinated_cyber": coordinated_cyber,
            "reasoning": reasoning,
        }

    def record_outcome(self, attack_id: str, hit: bool, intercepted: bool):
        """Record attack outcome for adaptive learning."""
        self._attack_history.append(
            {"attack_id": attack_id, "hit": hit, "intercepted": intercepted}
        )
        # Keep only last 20 entries
        if len(self._attack_history) > 20:
            self._attack_history = self._attack_history[-20:]

    def get_stats(self) -> dict:
        """Get adversary statistics."""
        total = self._attack_count
        recorded = len(self._attack_history)
        hits = sum(1 for a in self._attack_history if a["hit"])
        intercepted = sum(1 for a in self._attack_history if a["intercepted"])
        return {
            "total_attacks": total,
            "outcomes_recorded": recorded,
            "hits": hits,
            "intercepted": intercepted,
            "hit_rate": hits / max(recorded, 1),
            "intercept_rate": intercepted / max(recorded, 1),
            "cycles_since_last_attack": self._cycles_since_last_attack,
            "current_aggression": self.baseline_aggression,
        }

    def _no_attack(self, reason: str) -> dict:
        return {
            "should_attack": False,
            "target_base": None,
            "missile_type": None,
            "launch_lat": None,
            "launch_lon": None,
            "coordinated_ew": False,
            "coordinated_cyber": False,
            "reasoning": reason,
        }
