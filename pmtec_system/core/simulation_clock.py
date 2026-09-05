"""Simulation Clock - manages PMTEC simulation time."""

import time
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class SimTime:
    """A point in simulation time."""

    sim_seconds: float = 0.0
    real_seconds: float = 0.0
    cycle_count: int = 0

    def __repr__(self):
        h = int(self.sim_seconds // 3600)
        m = int((self.sim_seconds % 3600) // 60)
        s = int(self.sim_seconds % 60)
        return f"T+{h:02d}:{m:02d}:{s:02d}"


class SimulationClock:
    """Manages simulation time with configurable real-time ratio."""

    def __init__(self, tick_seconds: float = 1.0, realtime_ratio: float = 1.0):
        self.tick_seconds = tick_seconds
        self.realtime_ratio = realtime_ratio
        self.current = SimTime()
        self._running = False
        self._callbacks: list[Callable] = []
        self._tick_callbacks: list[Callable] = []
        self._real_start: float = 0.0

    def start(self):
        self._running = True
        self._real_start = time.time()

    def stop(self):
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def tick(self):
        """Advance simulation by one tick."""
        self.current.sim_seconds += self.tick_seconds
        self.current.real_seconds = time.time() - self._real_start
        self.current.cycle_count += 1
        # Notify tick callbacks
        for cb in self._tick_callbacks:
            try:
                cb(self.current)
            except Exception as e:
                print(f"[Clock] Tick callback error: {e}")

    def on_tick(self, callback: Callable):
        self._tick_callbacks.append(callback)

    def get_state(self) -> dict:
        return {
            "sim_time": str(self.current),
            "sim_seconds": self.current.sim_seconds,
            "real_seconds": round(self.current.real_seconds, 1),
            "cycle": self.current.cycle_count,
            "running": self._running,
            "ratio": self.realtime_ratio,
        }

    def elapsed_minutes(self) -> float:
        return self.current.sim_seconds / 60.0
