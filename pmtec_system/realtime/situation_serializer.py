"""
Situation Serializer - incremental diff serialization for WebSocket push.
Only sends changed entities to minimize bandwidth.
"""

import json
import time


class SituationSerializer:
    """Serializes simulation state into incremental WebSocket messages."""

    def __init__(self):
        self._last_snapshot: dict[str, dict] = {}
        self._last_sim_time: float = 0.0
        self._last_cycle: int = 0

    def serialize_full(self, state: dict, events: list = None) -> str:
        """Serialize full state snapshot (initial push)."""
        entities = state.get("entities", [])
        tracks = state.get("tracks", [])
        msg = {
            "type": "full",
            "sim_time": state.get("sim_time", "T+00:00:00"),
            "sim_seconds": state.get("sim_seconds", 0),
            "asda_cycle": state.get("asda_cycle", 0),
            "asda_phase": state.get("asda_phase", "idle"),
            "network_vulnerability": state.get("network_vulnerability", 0),
            "total_entities": state.get("total_entities", 0),
            "total_tracks": len(tracks),
            "entities": {e["id"]: e for e in entities},
            "tracks": tracks,
            "events": events[-20:] if events else [],
            "timestamp": time.time(),
        }
        self._last_snapshot = dict(msg["entities"])
        self._last_sim_time = state.get("sim_seconds", 0)
        self._last_cycle = state.get("asda_cycle", 0)
        return json.dumps(msg, ensure_ascii=False, default=str)

    def serialize_delta(self, state: dict, events: list = None) -> str | None:
        """Serialize only changed entities (incremental push)."""
        entities = state.get("entities", [])
        current_ids = set()
        changed: list[dict] = []
        added: list[dict] = []

        for e in entities:
            eid = e["id"]
            current_ids.add(eid)
            prev = self._last_snapshot.get(eid)
            if prev is None:
                added.append(e)
            else:
                if (
                    abs(e.get("lat", 0) - prev.get("lat", 0)) > 0.001
                    or abs(e.get("lon", 0) - prev.get("lon", 0)) > 0.001
                    or e.get("status") != prev.get("status")
                ):
                    changed.append(e)

        removed_ids = set(self._last_snapshot.keys()) - current_ids

        if (
            not changed
            and not added
            and not removed_ids
            and state.get("asda_cycle", 0) == self._last_cycle
        ):
            return None

        msg = {
            "type": "delta",
            "sim_time": state.get("sim_time", "T+00:00:00"),
            "sim_seconds": state.get("sim_seconds", 0),
            "asda_cycle": state.get("asda_cycle", 0),
            "asda_phase": state.get("asda_phase", "idle"),
            "network_vulnerability": state.get("network_vulnerability", 0),
            "total_entities": state.get("total_entities", 0),
            "total_tracks": len(state.get("tracks", [])),
            "changed": changed,
            "added": added,
            "removed_ids": list(removed_ids),
            "new_tracks": state.get("tracks", [])[-5:],
            "new_events": events[-10:] if events else [],
            "timestamp": time.time(),
        }

        self._last_snapshot = {e["id"]: e for e in entities}
        self._last_sim_time = state.get("sim_seconds", 0)
        self._last_cycle = state.get("asda_cycle", 0)
        return json.dumps(msg, ensure_ascii=False, default=str)

    def reset(self):
        """Reset serializer state for new simulation."""
        self._last_snapshot = {}
        self._last_sim_time = 0.0
        self._last_cycle = 0
