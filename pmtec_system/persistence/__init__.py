"""
P4-1 Persistence Layer - SQLite-based simulation state persistence.

Provides:
  - SimulationStateStore: snapshots, events, Kalman tracks, DQN metrics
  - Checkpoint/restore for simulation resume
  - Query API for historical analysis
"""

from persistence.state_store import SimulationStateStore

__all__ = ["SimulationStateStore"]
