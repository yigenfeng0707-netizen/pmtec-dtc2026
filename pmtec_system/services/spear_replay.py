"""
SPEAR Replay System - Simulation Playback, Evaluation, Analysis & Review.
DTB Model: WarEngine service (GetSpearReport) + Application Store (analysis apps).
ASDA: Adapt phase (lessons learned feed back into next Act phase).
"""

import json
import time
from collections import defaultdict


class SpearReplay:
    """Records and replays simulation events for post-action analysis."""

    def __init__(self, buffer_size: int = 10000, snapshot_buffer_size: int = 240):
        self.buffer_size = buffer_size
        # 快照与事件分开限长：一条快照内嵌全量实体/航迹 dict（约 0.4MB），
        # 沿用 10000 条事件上限意味着 3-5GB 内存——2026-10-02 曾把 2GB ECS
        # 整机挤到僵死。240 条 ≈ 100MB，回放窗口仍覆盖数十分钟推演。
        self.snapshot_buffer_size = snapshot_buffer_size
        self.events: list[dict] = []
        self.snapshots: list[dict] = []
        self.metrics: dict = defaultdict(list)

    def record_event(self, event: dict):
        """Record a simulation event."""
        self.events.append(event)
        if len(self.events) > self.buffer_size:
            self.events = self.events[-self.buffer_size :]

    def record_snapshot(self, snapshot: dict):
        """Record a system state snapshot."""
        self.snapshots.append(snapshot)
        if len(self.snapshots) > self.snapshot_buffer_size:
            self.snapshots = self.snapshots[-self.snapshot_buffer_size :]

    def record_metric(self, name: str, value: float):
        """Record a time-series metric."""
        self.metrics[name].append(
            {
                "time": time.time(),
                "value": value,
            }
        )
        if len(self.metrics[name]) > self.buffer_size:
            self.metrics[name] = self.metrics[name][-self.buffer_size :]

    def get_timeline(self, start_time: float = 0, end_time: float = 0) -> list[dict]:
        """Get events within time range."""
        result = self.events
        if start_time > 0:
            result = [e for e in result if e.get("timestamp", 0) >= start_time]
        if end_time > 0:
            result = [e for e in result if e.get("timestamp", 0) <= end_time]
        return result

    def generate_report(self, start_time: float = 0, end_time: float = 0) -> dict:
        """Generate a comprehensive SPEAR analysis report."""
        timeline = self.get_timeline(start_time, end_time)

        # Event type distribution
        event_types = defaultdict(int)
        for e in timeline:
            event_types[e.get("event_type", "unknown")] += 1

        # ASDA phase analysis
        asda_phases = {"Act": 0, "Sense": 0, "Decide": 0, "Adapt": 0}
        for e in timeline:
            phase = e.get("data", {}).get("asda_phase", "")
            if phase in asda_phases:
                asda_phases[phase] += 1

        # Damage assessment
        destroyed = [e for e in timeline if e.get("event_type") == "damage"]
        transfers = [e for e in timeline if e.get("event_type") == "transfer"]
        detections = [e for e in timeline if e.get("event_type") == "detect"]
        deployments = [e for e in timeline if e.get("event_type") == "deploy"]

        # Timeline metrics
        total_duration = 0
        if timeline:
            times = [e.get("timestamp", 0) for e in timeline]
            total_duration = max(times) - min(times) if len(times) > 1 else 0

        report = {
            "total_duration_s": round(total_duration, 1),
            "total_events": len(timeline),
            "event_distribution": dict(event_types),
            "asda_phase_activity": asda_phases,
            "damage_events": len(destroyed),
            "transfer_events": len(transfers),
            "detection_events": len(detections),
            "deployment_events": len(deployments),
            "snapshots_recorded": len(self.snapshots),
            "metrics_tracked": list(self.metrics.keys()),
            "summary": self._generate_summary(timeline, event_types, asda_phases),
            "timeline": timeline[-50:],  # last 50 events
        }
        return report

    def _generate_summary(self, timeline, event_types, asda_phases) -> str:
        parts = []
        parts.append(f"SPEAR Replay: {len(timeline)} events recorded over simulation.")

        # ASDA balance
        total_asda = sum(asda_phases.values())
        if total_asda > 0:
            for phase, count in asda_phases.items():
                pct = count / total_asda * 100
                parts.append(f"  {phase}: {count} events ({pct:.0f}%)")

        # Key findings
        if event_types.get("damage", 0) > 0:
            parts.append(
                f"  Damage events: {event_types['damage']} - review IAMD effectiveness."
            )
        if event_types.get("transfer", 0) > 0:
            parts.append(
                f"  Transfer events: {event_types['transfer']} - ACE dispersal executed."
            )
        if event_types.get("detect", 0) > 0:
            parts.append(
                f"  Detection events: {event_types['detect']} - sensor fusion active."
            )

        # LVC layer analysis
        live_count = sum(
            1 for e in timeline if e.get("data", {}).get("lvc_layer") == "Live"
        )
        virt_count = sum(
            1 for e in timeline if e.get("data", {}).get("lvc_layer") == "Virtual"
        )
        cons_count = sum(
            1 for e in timeline if e.get("data", {}).get("lvc_layer") == "Constructive"
        )
        parts.append(
            f"  LVC: Live={live_count}, Virtual={virt_count}, Constructive={cons_count}"
        )

        return "\n".join(parts)

    def export_json(self, filepath: str):
        """Export full replay data to JSON."""
        data = {
            "events": self.events,
            "snapshots": self.snapshots[-100:],
            "metrics": {k: v[-100:] for k, v in self.metrics.items()},
            "report": self.generate_report(),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath
