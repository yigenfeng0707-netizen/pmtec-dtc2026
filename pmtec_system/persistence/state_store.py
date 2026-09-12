"""
SimulationStateStore - SQLite persistence for PMTEC digital battlefield.

Tables:
  1. sim_snapshots   - periodic state snapshots (one per ASDA cycle)
  2. kalman_tracks    - Kalman-fused track history (position/velocity/confidence)
  3. spear_events     - SPEAR replay event log (all simulation events)
  4. dqn_metrics      - DQN training/eval metrics (reward, loss, epsilon)
  5. checkpoints      - full simulation checkpoints for resume

Features:
  - Auto-create tables on init
  - Batch insert for performance
  - Query API for historical analysis
  - Checkpoint save/restore for simulation resume
  - Thread-safe (one connection per thread)
"""

import json
import os
import sqlite3
import threading
import time


class SimulationStateStore:
    """SQLite-backed persistence for simulation state, tracks, events, and metrics."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sim_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle INTEGER NOT NULL,
        sim_seconds REAL NOT NULL,
        asda_phase TEXT NOT NULL,
        total_entities INTEGER,
        active_tracks INTEGER,
        active_missiles INTEGER,
        network_vulnerability REAL,
        lvc_live_entities INTEGER,
        adversary_attacks INTEGER,
        adversary_hit_rate REAL,
        weather_det_factor REAL,
        kalman_track_count INTEGER,
        fusion_cycle INTEGER,
        state_json TEXT,
        created_at REAL DEFAULT (strftime('%s','now'))
    );

    CREATE TABLE IF NOT EXISTS kalman_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle INTEGER NOT NULL,
        track_id TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        v_lat REAL,
        v_lon REAL,
        status TEXT,
        confidence REAL,
        source TEXT,
        hits INTEGER,
        misses INTEGER,
        created_at REAL DEFAULT (strftime('%s','now'))
    );

    CREATE TABLE IF NOT EXISTS spear_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle INTEGER,
        event_type TEXT NOT NULL,
        source TEXT,
        description TEXT,
        timestamp REAL,
        data_json TEXT,
        lvc_layer TEXT,
        created_at REAL DEFAULT (strftime('%s','now'))
    );

    CREATE TABLE IF NOT EXISTS dqn_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        step INTEGER NOT NULL,
        episode INTEGER,
        reward REAL,
        loss REAL,
        epsilon REAL,
        learning_rate REAL,
        obs_dim INTEGER,
        device TEXT,
        created_at REAL DEFAULT (strftime('%s','now'))
    );

    CREATE TABLE IF NOT EXISTS checkpoints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checkpoint_name TEXT NOT NULL,
        cycle INTEGER NOT NULL,
        sim_seconds REAL NOT NULL,
        state_json TEXT NOT NULL,
        created_at REAL DEFAULT (strftime('%s','now'))
    );

    CREATE INDEX IF NOT EXISTS idx_snap_cycle ON sim_snapshots(cycle);
    CREATE INDEX IF NOT EXISTS idx_tracks_cycle ON kalman_tracks(cycle);
    CREATE INDEX IF NOT EXISTS idx_events_type ON spear_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_events_cycle ON spear_events(cycle);
    CREATE INDEX IF NOT EXISTS idx_dqn_step ON dqn_metrics(step);
    """

    def __init__(self, db_path: str | None = None):
        """Initialize the store. db_path=None uses default path in data/."""
        if db_path is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "persistence",
            )
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "pmtec_state.db")
        self._db_path = db_path
        self._local = threading.local()
        # Create tables (in main thread)
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()
        print(f"[Persistence] SQLite store initialized: {db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def close(self):
        """Close the connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn

    # ---- Snapshot persistence ----

    def save_snapshot(
        self,
        state: dict,
        cycle: int,
        kalman_info: dict = None,
        adversary_stats: dict = None,
        weather: dict = None,
    ):
        """Save a simulation state snapshot for one ASDA cycle."""
        conn = self._get_conn()
        kalman_info = kalman_info or {}
        adversary_stats = adversary_stats or {}
        weather = weather or {}
        conn.execute(
            """
            INSERT INTO sim_snapshots
                (cycle, sim_seconds, asda_phase, total_entities, active_tracks,
                 active_missiles, network_vulnerability, lvc_live_entities,
                 adversary_attacks, adversary_hit_rate, weather_det_factor,
                 kalman_track_count, fusion_cycle, state_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cycle,
                state.get("sim_seconds", 0.0),
                state.get("asda_phase", "unknown"),
                state.get("total_entities", 0),
                state.get("active_tracks", 0),
                sum(
                    1
                    for e in state.get("entities", [])
                    if e.get("classification") == "missile"
                    or e.get("type") == "missile"
                ),
                state.get("network_vulnerability", 0.0),
                state.get("lvc_live_entities", 0),
                adversary_stats.get("total_attacks", 0),
                adversary_stats.get("hit_rate", 0.0),
                weather.get("detection_range_factor", 1.0),
                kalman_info.get("kalman_tracks", 0),
                kalman_info.get("fusion_cycle", 0),
                json.dumps(state, ensure_ascii=False),
            ),
        )
        conn.commit()

    def get_snapshots(self, limit: int = 100) -> list:
        """Get recent snapshots."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sim_snapshots ORDER BY cycle DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = [
            d[0]
            for d in conn.execute("SELECT * FROM sim_snapshots LIMIT 0").description
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Kalman track persistence ----

    def save_kalman_tracks(self, cycle: int, tracks: list):
        """Save Kalman-fused tracks for a cycle."""
        if not tracks:
            return
        conn = self._get_conn()
        rows = []
        for t in tracks:
            rows.append(
                (
                    cycle,
                    t.get("track_id", t.get("id", "unknown")),
                    t.get("lat", 0.0),
                    t.get("lon", 0.0),
                    t.get("v_lat", 0.0),
                    t.get("v_lon", 0.0),
                    t.get("status", "unknown"),
                    t.get("confidence", 0.0),
                    t.get("source", ""),
                    t.get("hits", 0),
                    t.get("misses", 0),
                )
            )
        conn.executemany(
            """
            INSERT INTO kalman_tracks
                (cycle, track_id, lat, lon, v_lat, v_lon, status, confidence, source, hits, misses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    def get_kalman_tracks(self, cycle: int) -> list:
        """Get Kalman tracks for a specific cycle."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM kalman_tracks WHERE cycle = ?", (cycle,)
        ).fetchall()
        cols = [
            d[0]
            for d in conn.execute("SELECT * FROM kalman_tracks LIMIT 0").description
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ---- SPEAR event persistence ----

    def save_events(self, cycle: int, events: list):
        """Save SPEAR events (batch insert)."""
        if not events:
            return
        conn = self._get_conn()
        rows = []
        for evt in events:
            data = evt.get("data", {})
            if isinstance(data, dict):
                data_str = json.dumps(data, ensure_ascii=False)
            else:
                data_str = str(data)
            rows.append(
                (
                    cycle,
                    evt.get("event_type", "unknown"),
                    evt.get("source", ""),
                    evt.get("description", ""),
                    evt.get("timestamp", time.time()),
                    data_str,
                    data.get("lvc_layer", "") if isinstance(data, dict) else "",
                )
            )
        conn.executemany(
            """
            INSERT INTO spear_events
                (cycle, event_type, source, description, timestamp, data_json, lvc_layer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    def get_events(self, event_type: str = None, limit: int = 100) -> list:
        """Query events by type or get recent."""
        conn = self._get_conn()
        if event_type:
            rows = conn.execute(
                "SELECT * FROM spear_events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                (event_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM spear_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        cols = [
            d[0] for d in conn.execute("SELECT * FROM spear_events LIMIT 0").description
        ]
        return [dict(zip(cols, row)) for row in rows]

    def get_event_stats(self) -> dict:
        """Get event type counts."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM spear_events GROUP BY event_type ORDER BY cnt DESC"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ---- DQN metrics persistence ----

    def save_dqn_metrics(
        self,
        step: int,
        reward: float,
        loss: float = None,
        epsilon: float = None,
        learning_rate: float = None,
        obs_dim: int = None,
        device: str = None,
        episode: int = None,
    ):
        """Save DQN training metrics."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO dqn_metrics
                (step, episode, reward, loss, epsilon, learning_rate, obs_dim, device)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (step, episode, reward, loss, epsilon, learning_rate, obs_dim, device),
        )
        conn.commit()

    def get_dqn_metrics(self, limit: int = 100) -> list:
        """Get recent DQN metrics."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM dqn_metrics ORDER BY step DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = [
            d[0] for d in conn.execute("SELECT * FROM dqn_metrics LIMIT 0").description
        ]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Checkpoint / restore ----

    def save_checkpoint(self, name: str, cycle: int, sim_seconds: float, state: dict):
        """Save a full simulation checkpoint for resume."""
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO checkpoints (checkpoint_name, cycle, sim_seconds, state_json)
            VALUES (?, ?, ?, ?)
            """,
            (name, cycle, sim_seconds, json.dumps(state, ensure_ascii=False)),
        )
        conn.commit()

    def load_checkpoint(self, name: str) -> dict | None:
        """Load the latest checkpoint by name."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT cycle, sim_seconds, state_json FROM checkpoints WHERE checkpoint_name = ? ORDER BY id DESC LIMIT 1",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return {
            "cycle": row[0],
            "sim_seconds": row[1],
            "state": json.loads(row[2]),
        }

    def list_checkpoints(self) -> list:
        """List all checkpoints."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, checkpoint_name, cycle, sim_seconds, created_at FROM checkpoints ORDER BY id DESC"
        ).fetchall()
        cols = ["id", "name", "cycle", "sim_seconds", "created_at"]
        return [dict(zip(cols, row)) for row in rows]

    # ---- Analytics ----

    def get_summary(self) -> dict:
        """Get a summary of persisted data."""
        conn = self._get_conn()
        snap_count = conn.execute("SELECT COUNT(*) FROM sim_snapshots").fetchone()[0]
        track_count = conn.execute("SELECT COUNT(*) FROM kalman_tracks").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM spear_events").fetchone()[0]
        dqn_count = conn.execute("SELECT COUNT(*) FROM dqn_metrics").fetchone()[0]
        ckpt_count = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        last_snap = conn.execute(
            "SELECT cycle, sim_seconds FROM sim_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "snapshots": snap_count,
            "kalman_tracks": track_count,
            "events": event_count,
            "dqn_metrics": dqn_count,
            "checkpoints": ckpt_count,
            "last_cycle": last_snap[0] if last_snap else 0,
            "last_sim_seconds": last_snap[1] if last_snap else 0.0,
        }
