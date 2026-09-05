"""Digital Twin Registry - P1-2: Instance lifecycle management.

Manages multiple digital twin instances, each representing a distinct
operational scenario or simulated environment. Enables the platform
to host parallel simulations, A/B testing, and scenario comparison.

DT Instance Lifecycle:
  registered -> initialized -> running -> paused -> stopped -> archived

Each instance carries:
- Unique ID and metadata
- Reference to its PMTEC engine (or None for remote)
- Scenario configuration
- Runtime statistics
- SPEAR replay data snapshot
"""

import time
import json
import uuid
import logging
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("pmtec.registry")


class DTStatus(str, Enum):
    REGISTERED = "registered"
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"


@dataclass
class DTInstance:
    """A digital twin instance representing one simulation environment."""

    instance_id: str
    name: str
    scenario: str = "PMTEC-Pacific"
    status: DTStatus = DTStatus.REGISTERED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    engine_ref: Optional[object] = None  # Reference to PMTECEngine if local
    metadata: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "scenario": self.scenario,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "stats": self.stats,
            "tags": self.tags,
        }


class DTRegistry:
    """Registry for managing digital twin instances.

    Features:
    - Register/unregister DT instances
    - Track lifecycle status transitions
    - Aggregate statistics across all instances
    - Support tagging and filtering
    """

    def __init__(self):
        self._instances: dict[str, DTInstance] = {}
        self._default_instance: Optional[str] = None

    def register(self, config: dict = None) -> dict:
        """Register a new digital twin instance.

        Args:
            config: Dict with 'name', 'scenario', 'tags', 'metadata'
        Returns:
            Instance dict
        """
        config = config or {}
        instance_id = config.get("instance_id") or f"DT-{uuid.uuid4().hex[:8]}"
        instance = DTInstance(
            instance_id=instance_id,
            name=config.get("name", f"DT-{instance_id[-4:]}"),
            scenario=config.get("scenario", "PMTEC-Pacific"),
            metadata=config.get("metadata", {}),
            tags=config.get("tags", []),
        )
        self._instances[instance_id] = instance

        if self._default_instance is None:
            self._default_instance = instance_id

        logger.info(f"DT instance registered: {instance_id} ({instance.name})")
        return instance.to_dict()

    def unregister(self, instance_id: str) -> bool:
        """Remove a DT instance from the registry."""
        if instance_id in self._instances:
            del self._instances[instance_id]
            if self._default_instance == instance_id:
                self._default_instance = (
                    next(iter(self._instances), None) if self._instances else None
                )
            return True
        return False

    def get(self, instance_id: str) -> Optional[DTInstance]:
        return self._instances.get(instance_id)

    def update_status(self, instance_id: str, status: DTStatus) -> bool:
        """Transition a DT instance to a new status."""
        inst = self._instances.get(instance_id)
        if inst is None:
            return False
        inst.status = status
        inst.updated_at = time.time()
        logger.info(f"DT {instance_id} -> {status.value}")
        return True

    def attach_engine(self, instance_id: str, engine) -> bool:
        """Attach a PMTEC engine to a DT instance."""
        inst = self._instances.get(instance_id)
        if inst is None:
            return False
        inst.engine_ref = engine
        inst.updated_at = time.time()
        return True

    def update_stats(self, instance_id: str, stats: dict) -> bool:
        """Update runtime statistics for a DT instance."""
        inst = self._instances.get(instance_id)
        if inst is None:
            return False
        inst.stats.update(stats)
        inst.updated_at = time.time()
        return True

    def list_instances(self, tag: str = None, status: DTStatus = None) -> list[dict]:
        """List all DT instances, optionally filtered by tag or status."""
        results = []
        for inst in self._instances.values():
            if tag and tag not in inst.tags:
                continue
            if status and inst.status != status:
                continue
            results.append(inst.to_dict())
        return results

    def get_default(self) -> Optional[DTInstance]:
        """Get the default DT instance."""
        if self._default_instance:
            return self._instances.get(self._default_instance)
        return None

    def aggregate_stats(self) -> dict:
        """Aggregate statistics across all instances."""
        total = len(self._instances)
        by_status = {}
        for inst in self._instances.values():
            s = inst.status.value
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_instances": total,
            "by_status": by_status,
            "default_instance": self._default_instance,
            "tags": list(
                set(t for inst in self._instances.values() for t in inst.tags)
            ),
        }

    def export_registry(self) -> dict:
        """Export full registry state for persistence."""
        return {
            "instances": [inst.to_dict() for inst in self._instances.values()],
            "default": self._default_instance,
            "aggregated": self.aggregate_stats(),
        }
