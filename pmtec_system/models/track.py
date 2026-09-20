"""Track Management - sensor fusion and track lifecycle for PMTEC."""

import time
import uuid
from dataclasses import dataclass, field

from config import TRACK_MAX_AGE_S, TRACK_MIN_CONFIDENCE


@dataclass
class Track:
    track_id: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float = 0.0
    heading_deg: float = 0.0
    speed_kmh: float = 0.0
    confidence: float = 0.5
    classification: str = "unknown"
    sources: list = field(default_factory=list)
    first_detected: float = 0.0
    last_updated: float = 0.0
    update_count: int = 0

    def __post_init__(self):
        if not self.track_id:
            self.track_id = f"TRK-{uuid.uuid4().hex[:6]}"
        now = time.time()
        if self.first_detected == 0:
            self.first_detected = now
        if self.last_updated == 0:
            self.last_updated = now

    @property
    def age_seconds(self) -> float:
        return time.time() - self.last_updated

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > TRACK_MAX_AGE_S

    def update(
        self,
        lat: float,
        lon: float,
        alt_m: float = 0,
        heading: float = 0,
        speed: float = 0,
        confidence: float = 0.5,
        source: str = "",
    ):
        """Update track with new observation."""
        # Weighted average (favor new data)
        w = 0.6
        self.lat = self.lat * (1 - w) + lat * w
        self.lon = self.lon * (1 - w) + lon * w
        self.alt_m = self.alt_m * (1 - w) + alt_m * w
        self.heading_deg = heading if heading else self.heading_deg
        self.speed_kmh = speed if speed else self.speed_kmh
        self.confidence = max(self.confidence, confidence)
        self.last_updated = time.time()
        self.update_count += 1
        if source and source not in self.sources:
            self.sources.append(source)

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "alt_m": round(self.alt_m, 0),
            "heading": round(self.heading_deg, 1),
            "speed_kmh": round(self.speed_kmh, 0),
            "confidence": round(self.confidence, 2),
            "classification": self.classification,
            "sources": self.sources,
            "age_s": round(self.age_seconds, 1),
            "updates": self.update_count,
        }


class TrackManager:
    """Manages the fused track picture from multiple sensor sources."""

    def __init__(self):
        self.tracks: dict[str, Track] = {}
        self.raw_observations: list = []

    def add_observation(
        self,
        lat: float,
        lon: float,
        alt_m: float = 0,
        heading: float = 0,
        speed: float = 0,
        confidence: float = 0.5,
        classification: str = "unknown",
        source: str = "",
    ):
        """Add a raw sensor observation for fusion."""
        self.raw_observations.append(
            {
                "lat": lat,
                "lon": lon,
                "alt_m": alt_m,
                "heading": heading,
                "speed": speed,
                "confidence": confidence,
                "classification": classification,
                "source": source,
                "time": time.time(),
            }
        )

    def fuse(self) -> dict[str, Track]:
        """Fuse raw observations into tracks using proximity association."""
        import math

        # Try to associate with existing tracks
        for obs in self.raw_observations:
            associated = False
            for track in self.tracks.values():
                if track.is_stale:
                    continue
                # Distance to track
                dlat = (track.lat - obs["lat"]) * 111  # ~km per degree
                dlon = (
                    (track.lon - obs["lon"]) * 111 * math.cos(math.radians(obs["lat"]))
                )
                dist = math.sqrt(dlat**2 + dlon**2)
                if dist < 10.0:  # within 10km - same track
                    track.update(
                        obs["lat"],
                        obs["lon"],
                        obs["alt_m"],
                        obs["heading"],
                        obs["speed"],
                        obs["confidence"],
                        obs["source"],
                    )
                    if obs["classification"] != "unknown":
                        track.classification = obs["classification"]
                    associated = True
                    break
            if not associated and obs["confidence"] >= TRACK_MIN_CONFIDENCE:
                # Create new track
                new_track = Track(
                    lat=obs["lat"],
                    lon=obs["lon"],
                    alt_m=obs["alt_m"],
                    heading_deg=obs["heading"],
                    speed_kmh=obs["speed"],
                    confidence=obs["confidence"],
                    classification=obs["classification"],
                    sources=[obs["source"]] if obs["source"] else [],
                )
                self.tracks[new_track.track_id] = new_track

        self.raw_observations.clear()

        # Remove stale tracks
        stale = [tid for tid, t in self.tracks.items() if t.is_stale]
        for tid in stale:
            del self.tracks[tid]

        return self.tracks

    @property
    def active_tracks(self) -> list[Track]:
        # P13.3-fix: 原子快照，防止与仿真主线程 update() 增删 tracks 的竞态
        return [t for t in list(self.tracks.values()) if not t.is_stale]

    def status(self) -> dict:
        return {
            "total_tracks": len(self.tracks),
            "active_tracks": len(self.active_tracks),
            "pending_observations": len(self.raw_observations),
            "tracks": [t.to_dict() for t in self.active_tracks],
        }
