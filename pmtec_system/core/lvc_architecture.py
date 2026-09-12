"""
LVC Architecture - Live/Virtual/Constructive layer management for PMTEC.
DTB Model: War Engine (LVC coordination) + Plug-and-Play (layer composition)
"""

import math
from dataclasses import dataclass, field

from config import EARTH_RADIUS_KM


@dataclass
class LVCLayer:
    layer_name: str  # "Live", "Virtual", "Constructive"
    enabled: bool = True
    entity_count: int = 0
    entities: list = field(default_factory=list)
    description: str = ""

    def add_entity(self, entity):
        self.entities.append(entity)
        self.entity_count = len(self.entities)

    def remove_entity(self, entity_id: str):
        self.entities = [e for e in self.entities if getattr(e, "id", "") != entity_id]
        self.entity_count = len(self.entities)

    def get_entities(self, entity_type: str = None) -> list:
        if entity_type:
            return [
                e for e in self.entities if getattr(e, "entity_type", "") == entity_type
            ]
        return self.entities

    def to_dict(self) -> dict:
        return {
            "layer": self.layer_name,
            "enabled": self.enabled,
            "entity_count": self.entity_count,
            "description": self.description,
        }


class KalmanTrack:
    """P3-2: Kalman-filtered track for multi-source sensor fusion.

    State vector: [lat, lon, v_lat, v_lon] (position + velocity in degrees).
    Constant-velocity model with process noise for maneuvering targets.
    Supports measurement update from multiple sensor sources.
    """

    # Class-level counter for unique track IDs
    _next_id = 1

    def __init__(
        self, lat: float, lon: float, source: str = "", confidence: float = 0.5
    ):
        self.track_id = f"KT-{KalmanTrack._next_id:04d}"
        KalmanTrack._next_id += 1

        # State: [lat, lon, v_lat, v_lon]
        self.x = [lat, lon, 0.0, 0.0]

        # Covariance matrix (4x4) - start with high uncertainty in velocity
        self.P = [
            [0.01, 0.0, 0.0, 0.0],
            [0.0, 0.01, 0.0, 0.0],
            [0.0, 0.0, 0.1, 0.0],
            [0.0, 0.0, 0.0, 0.1],
        ]

        # State transition matrix (constant velocity, dt=1)
        self.F = [
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

        # Measurement matrix (observe position only)
        self.H = [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ]

        # Process noise covariance (maneuvering target)
        q = 0.0005  # ~50m positional noise per step
        self.Q = [
            [q, 0.0, q, 0.0],
            [0.0, q, 0.0, q],
            [q, 0.0, q * 2, 0.0],
            [0.0, q, 0.0, q * 2],
        ]

        # Measurement noise covariance (~0.01 deg ~1.1km)
        self.R = [
            [0.01, 0.0],
            [0.0, 0.01],
        ]

        self.sources: set = {source} if source else set()
        self.source_count: int = 1
        self.confidence: float = confidence
        self.hits: int = 1
        self.misses: int = 0
        self.last_update: float = 0.0
        self.created_at: float = 0.0
        self.classification: str = ""
        self.heading: float = 0.0
        self.speed: float = 0.0
        self.alt_m: float = 0.0
        self.status: str = "tentative"  # tentative -> confirmed -> deleted

    def predict(self, dt: float = 1.0):
        """Prediction step: x = F*x, P = F*P*F' + Q."""
        # Update F for dt
        self.F = [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
        # x = F * x
        new_x = [sum(self.F[i][j] * self.x[j] for j in range(4)) for i in range(4)]
        self.x = new_x
        # P = F * P * F' + Q
        FP = _mat_mul(self.F, self.P)
        _mat_transpose(FP)
        new_P = _mat_add(_mat_mul(FP, _mat_transpose(self.F)), self.Q)
        self.P = new_P
        # Increment misses (will be reset on update)
        self.misses += 1

    def update(
        self,
        lat: float,
        lon: float,
        source: str = "",
        confidence: float = 0.5,
        heading: float = 0.0,
        speed: float = 0.0,
        alt_m: float = 0.0,
        classification: str = "",
    ):
        """Measurement update step: Kalman gain + state correction."""
        # z = measurement
        z = [lat, lon]
        # y = z - H*x (innovation)
        Hx = [sum(self.H[i][j] * self.x[j] for j in range(4)) for i in range(2)]
        y = [z[i] - Hx[i] for i in range(2)]

        # S = H*P*H' + R (innovation covariance)
        HP = _mat_mul(self.H, self.P)
        S = _mat_add(_mat_mul(HP, _mat_transpose(self.H)), self.R)

        # K = P*H'*S^-1 (Kalman gain)
        PHt = _mat_mul(self.P, _mat_transpose(self.H))
        S_inv = _mat_inv_2x2(S)
        K = _mat_mul(PHt, S_inv)

        # x = x + K*y
        Ky = [sum(K[i][j] * y[j] for j in range(2)) for i in range(4)]
        self.x = [self.x[i] + Ky[i] for i in range(4)]

        # P = (I - K*H)*P
        KH = _mat_mul(K, self.H)
        I = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        IKH = [[I[i][j] - KH[i][j] for j in range(4)] for i in range(4)]
        self.P = _mat_mul(IKH, self.P)

        # Track bookkeeping
        self.misses = 0
        self.hits += 1
        if source:
            self.sources.add(source)
            self.source_count = len(self.sources)
        # Weighted confidence: blend filter confidence with measurement confidence
        self.confidence = min(1.0, self.confidence * 0.7 + confidence * 0.3 + 0.05)
        self.last_update = 0.0
        self.heading = heading if heading else self.heading
        self.speed = speed if speed else self.speed
        self.alt_m = alt_m if alt_m else self.alt_m
        if classification:
            self.classification = classification

        # Promote to confirmed after 3 hits
        if self.hits >= 3 and self.status == "tentative":
            self.status = "confirmed"

    @property
    def lat(self) -> float:
        return self.x[0]

    @property
    def lon(self) -> float:
        return self.x[1]

    @property
    def v_lat(self) -> float:
        return self.x[2]

    @property
    def v_lon(self) -> float:
        return self.x[3]

    def innovation(self, lat: float, lon: float) -> list:
        """Compute innovation (measurement residual) y = z - H*x."""
        Hx = [sum(self.H[i][j] * self.x[j] for j in range(4)) for i in range(2)]
        return [lat - Hx[0], lon - Hx[1]]

    def innovation_covariance(self) -> list:
        """Compute S = H*P*H' + R (2x2)."""
        HP = _mat_mul(self.H, self.P)
        return _mat_add(_mat_mul(HP, _mat_transpose(self.H)), self.R)

    def update_jpda(self, weighted_innovation: list):
        """P5-1: JPDA update using a pre-computed weighted innovation.

        Instead of a single measurement, JPDA provides a weighted combination
        of innovations from all gated measurements. The Kalman gain is computed
        normally, then applied to the weighted innovation.
        """
        # S = H*P*H' + R (innovation covariance)
        S = self.innovation_covariance()
        # K = P*H'*S^-1 (Kalman gain)
        PHt = _mat_mul(self.P, _mat_transpose(self.H))
        S_inv = _mat_inv_2x2(S)
        K = _mat_mul(PHt, S_inv)

        # x = x + K * weighted_innovation
        Ky = [sum(K[i][j] * weighted_innovation[j] for j in range(2)) for i in range(4)]
        self.x = [self.x[i] + Ky[i] for i in range(4)]

        # P = (I - K*H)*P  (use JPDA covariance scaling for P update)
        KH = _mat_mul(K, self.H)
        I = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        IKH = [[I[i][j] - KH[i][j] for j in range(4)] for i in range(4)]
        self.P = _mat_mul(IKH, self.P)

    def update_jpda_meta(self, observations: list):
        """Update track metadata (source, heading, speed) from the set of
        associated observations. Picks the highest-confidence observation
        for metadata."""
        if not observations:
            self.misses += 1
            return
        # Pick best observation for metadata
        best = max(observations, key=lambda o: o.get("confidence", 0.5))
        self.misses = 0
        self.hits += 1
        src = best.get("source", "")
        if src:
            self.sources.add(src)
            self.source_count = len(self.sources)
        self.confidence = min(
            1.0, self.confidence * 0.7 + best.get("confidence", 0.5) * 0.3 + 0.05
        )
        self.heading = best.get("heading", 0.0) or self.heading
        self.speed = best.get("speed", 0.0) or self.speed
        self.alt_m = best.get("alt_m", 0.0) or self.alt_m
        if best.get("classification", ""):
            self.classification = best["classification"]
        if self.hits >= 3 and self.status == "tentative":
            self.status = "confirmed"

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "v_lat": round(self.x[2], 5),
            "v_lon": round(self.x[3], 5),
            "heading": round(self.heading, 1),
            "speed": round(self.speed, 0),
            "alt_m": round(self.alt_m, 0),
            "confidence": round(self.confidence, 3),
            "source_count": self.source_count,
            "sources": list(self.sources),
            "hits": self.hits,
            "misses": self.misses,
            "status": self.status,
            "classification": self.classification,
        }


# --- Minimal matrix operations (4x4 and 2x2) ---


def _mat_mul(A, B):
    """Matrix multiply."""
    rows_A = len(A)
    cols_A = len(A[0])
    cols_B = len(B[0])
    result = [[0.0] * cols_B for _ in range(rows_A)]
    for i in range(rows_A):
        for j in range(cols_B):
            s = 0.0
            for k in range(cols_A):
                s += A[i][k] * B[k][j]
            result[i][j] = s
    return result


def _mat_transpose(A):
    """Transpose matrix."""
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]


def _mat_add(A, B):
    """Add two matrices."""
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


def _mat_inv_2x2(M):
    """Inverse of 2x2 matrix."""
    a, b = M[0][0], M[0][1]
    c, d = M[1][0], M[1][1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        return [[1.0, 0.0], [0.0, 1.0]]
    return [[d / det, -b / det], [-c / det, a / det]]


class LVCArchitecture:
    """
    PMTEC LVC (Live-Virtual-Constructive) Architecture Manager.

    - Live: Real-world entities (actual bases, sensor feeds, real tracks)
    - Virtual: Simulated entities (CGF - computer-generated forces)
    - Constructive: Aggregate-level command simulation (ASDA decisions)
    """

    def __init__(self):
        self.live = LVCLayer(
            layer_name="Live",
            description="Real-world data feeds: base positions, sensor networks, actual track data",
        )
        self.virtual = LVCLayer(
            layer_name="Virtual",
            description="Computer-generated forces: simulated aircraft, missiles, with physics models",
        )
        self.constructive = LVCLayer(
            layer_name="Constructive",
            description="Aggregate command-level simulation: ASDA decisions, ACE deployment algorithms",
        )
        self._fusion_buffer: list = []
        # P3-2: Persistent Kalman-filtered tracks
        self._kalman_tracks: dict[str, KalmanTrack] = {}
        self._fusion_cycle: int = 0

    @property
    def layers(self) -> list[LVCLayer]:
        return [self.live, self.virtual, self.constructive]

    def total_entities(self) -> int:
        return sum(l.entity_count for l in self.layers if l.enabled)

    def all_entities(self) -> list:
        result = []
        for layer in self.layers:
            if layer.enabled:
                result.extend(layer.entities)
        return result

    def get_layer(self, name: str) -> LVCLayer | None:
        for layer in self.layers:
            if layer.layer_name.lower() == name.lower():
                return layer
        return None

    def inject_track(self, track_data: dict, source_layer: str = "Virtual"):
        """Inject a sensor track into the fusion buffer."""
        track_data["source_layer"] = source_layer
        self._fusion_buffer.append(track_data)

    def fuse_tracks(self) -> list:
        """P5-1: Fuse tracks using JPDA (Joint Probabilistic Data Association).

        Replaces nearest-neighbor with full probabilistic association:
        1. Predict all existing Kalman tracks forward
        2. Build gated cost matrix between tracks and observations
        3. Compute joint association probabilities via Gaussian likelihood
        4. Update each track with weighted innovation from all gated measurements
        5. Create new tracks for unmatched observations
        6. Delete stale tracks
        7. Return confirmed/active tracks as fused output
        """
        self._fusion_cycle += 1
        observations = list(self._fusion_buffer)
        self._fusion_buffer.clear()

        if not observations and not self._kalman_tracks:
            return []

        # Step 1: Predict all existing tracks forward
        for track in self._kalman_tracks.values():
            track.predict(dt=1.0)

        # If no existing tracks, create from all observations (cold start)
        if not self._kalman_tracks:
            for obs in observations:
                new_track = KalmanTrack(
                    lat=obs.get("lat", 0),
                    lon=obs.get("lon", 0),
                    source=obs.get("source", ""),
                    confidence=obs.get("confidence", 0.5),
                )
                new_track.heading = obs.get("heading", 0.0)
                new_track.speed = obs.get("speed", 0.0)
                new_track.alt_m = obs.get("alt_m", 0.0)
                new_track.classification = obs.get("classification", "")
                self._kalman_tracks[new_track.track_id] = new_track
        else:
            # Step 2-4: JPDA association and update
            self._jpda_update(observations)

        # Step 5: Delete stale tracks (missed > 5 cycles)
        stale_ids = [
            tid
            for tid, t in self._kalman_tracks.items()
            if t.misses > 5 or t.status == "deleted"
        ]
        for tid in stale_ids:
            del self._kalman_tracks[tid]

        # Step 6: Return active tracks as fused output
        fused = [
            t.to_dict()
            for t in self._kalman_tracks.values()
            if t.status in ("tentative", "confirmed")
        ]
        return fused

    def _jpda_update(self, observations: list):
        """P5-1: JPDA core algorithm.

        For each track, compute association probabilities with all gated
        observations, then update with weighted innovation.

        JPDA computes:
        - beta_0 (probability of no association) per track
        - beta_j (probability of association with measurement j) per track
        - Weighted innovation = sum(beta_j * innovation_j)
        """
        active_tracks = [
            (tid, t) for tid, t in self._kalman_tracks.items() if t.status != "deleted"
        ]
        if not active_tracks:
            return

        GATE_KM = 15.0  # Association gate in km
        GATE_KM * GATE_KM

        # Build gated association: for each track, which observations are within gate?
        # association_map[track_idx] = [(obs_idx, innovation, inv_cov, likelihood), ...]
        association_map = {}  # track_idx -> list of (obs_idx, innovation, S_inv, likelihood)

        for t_idx, (tid, track) in enumerate(active_tracks):
            gated = []
            for o_idx, obs in enumerate(observations):
                obs_lat = obs.get("lat", 0)
                obs_lon = obs.get("lon", 0)
                dist = haversine(obs_lat, obs_lon, track.lat, track.lon)

                if dist < GATE_KM:
                    innov = track.innovation(obs_lat, obs_lon)
                    S = track.innovation_covariance()
                    S_inv = _mat_inv_2x2(S)

                    # Gaussian likelihood: N(innov; 0, S)
                    # det(S) for 2x2
                    det_S = S[0][0] * S[1][1] - S[0][1] * S[1][0]
                    det_S = max(det_S, 1e-12)
                    # Mahalanobis distance squared
                    mahal_sq = (
                        innov[0] * innov[0] * S_inv[0][0]
                        + 2 * innov[0] * innov[1] * S_inv[0][1]
                        + innov[1] * innov[1] * S_inv[1][1]
                    )
                    # likelihood = exp(-0.5 * mahal_sq) / sqrt(2*pi * det_S)
                    # Use log-likelihood for numerical stability
                    log_lik = -0.5 * mahal_sq - 0.5 * math.log(2 * math.pi * det_S)
                    likelihood = math.exp(
                        max(log_lik, -500)
                    )  # clamp to avoid underflow
                    gated.append((o_idx, innov, S_inv, likelihood, obs))

            association_map[t_idx] = gated

        # Compute association probabilities per track
        # For each track: beta_j = likelihood_j / (sum_likelihoods + clutter_term)
        # clutter_term accounts for "no association" (new target / false alarm)
        CLUTTER_PRIOR = 0.1  # 10% prior probability of no association

        new_obs_indices = set(range(len(observations)))  # Start with all as "new"

        for t_idx, (tid, track) in enumerate(active_tracks):
            gated = association_map.get(t_idx, [])
            if not gated:
                # No gated observations -> just increment misses (already done in predict)
                continue

            # Mark these observations as potentially associated (not all new)
            for item in gated:
                new_obs_indices.discard(item[0])

            # Compute association probabilities
            total_lik = sum(item[3] for item in gated) + CLUTTER_PRIOR

            # Weighted innovation
            weighted_innov = [0.0, 0.0]
            associated_obs = []
            for o_idx, innov, S_inv, likelihood, obs in gated:
                beta = likelihood / total_lik
                weighted_innov[0] += beta * innov[0]
                weighted_innov[1] += beta * innov[1]
                if beta > 0.1:  # Only include obs with significant probability
                    associated_obs.append(obs)

            # Apply JPDA Kalman update
            track.update_jpda(weighted_innov)
            track.update_jpda_meta(associated_obs)

        # Create new tracks for unmatched observations
        for o_idx in new_obs_indices:
            obs = observations[o_idx]
            new_track = KalmanTrack(
                lat=obs.get("lat", 0),
                lon=obs.get("lon", 0),
                source=obs.get("source", ""),
                confidence=obs.get("confidence", 0.5),
            )
            new_track.heading = obs.get("heading", 0.0)
            new_track.speed = obs.get("speed", 0.0)
            new_track.alt_m = obs.get("alt_m", 0.0)
            new_track.classification = obs.get("classification", "")
            self._kalman_tracks[new_track.track_id] = new_track

    def status(self) -> dict:
        return {
            "total_entities": self.total_entities(),
            "layers": [l.to_dict() for l in self.layers],
            "fusion_buffer_size": len(self._fusion_buffer),
            "kalman_tracks": len(self._kalman_tracks),
            "fusion_cycle": self._fusion_cycle,
            "association_algorithm": "JPDA",
        }


def haversine(lat1, lon1, lat2, lon2) -> float:
    """Distance in km between two coordinates."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c
