"""Event Bus - pub/sub messaging for PMTEC simulation entities."""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    event_type: str
    timestamp: float
    source: str = ""
    target: str = ""
    data: dict = field(default_factory=dict)
    event_id: str = ""

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"EVT-{int(time.time() * 1000) % 1000000:06d}"

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
            "data": self.data,
        }


class EventBus:
    """In-process pub/sub event bus for simulation entities."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._history: list[Event] = []
        self._max_history = 10000

    def subscribe(self, event_type: str, handler: Callable[[Event], Any]):
        self._subscribers[event_type].append(handler)

    def publish(self, event: Event):
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]
        for handler in self._subscribers.get(event.event_type, []):
            try:
                handler(event)
            except Exception as e:
                print(f"[EventBus] Handler error for {event.event_type}: {e}")
        # Also notify wildcard subscribers
        for handler in self._subscribers.get("*", []):
            try:
                handler(event)
            except Exception:
                pass

    @property
    def history(self) -> list[Event]:
        return self._history

    def get_events(self, event_type: str = None, since_time: float = 0) -> list[Event]:
        result = self._history
        if event_type:
            result = [e for e in result if e.event_type == event_type]
        if since_time > 0:
            result = [e for e in result if e.timestamp >= since_time]
        return result

    def clear(self):
        self._history.clear()
