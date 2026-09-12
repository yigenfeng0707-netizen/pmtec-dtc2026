"""Digital Twin Plugin Manager - P1-2: Platform extensibility.

Provides a plugin architecture for the PMTEC digital twin platform.
Plugins can register capabilities, extend the ASDA loop, or provide
new visualization modules without modifying core code.

Design:
- Plugin Interface: register() / init(engine) / shutdown()
- Hot-load from data/plugins/ directory (Python modules)
- Sandbox: plugins run in restricted namespace
- Lifecycle: discover -> load -> init -> [active] -> shutdown
"""

import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger("pmtec.plugin")


@dataclass
class PluginManifest:
    """Plugin metadata descriptor."""

    plugin_id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    plugin_type: str = "capability"  # capability, visualization, threat_model, learning
    dependencies: list = field(default_factory=list)
    entry_point: str = "create_plugin"  # factory function name

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "type": self.plugin_type,
            "dependencies": self.dependencies,
        }


class PluginInstance:
    """Wrapper for a loaded plugin instance."""

    def __init__(self, manifest: PluginManifest, instance: object):
        self.manifest = manifest
        self.instance = instance
        self.loaded_at = time.time()
        self.active = True
        self.call_count = 0
        self.error_count = 0

    def call(self, method_name: str, *args, **kwargs):
        """Safely call a method on the plugin instance."""
        self.call_count += 1
        try:
            method = getattr(self.instance, method_name, None)
            if method is None:
                return None
            return method(*args, **kwargs)
        except Exception as e:
            self.error_count += 1
            logger.warning(f"Plugin {self.manifest.plugin_id}.{method_name} error: {e}")
            return None


class PluginManager:
    """Manages plugin discovery, loading, and lifecycle for the PMTEC platform.

    Usage:
        pm = PluginManager()
        pm.discover()  # scan plugin directory
        pm.load_all(engine)  # initialize all plugins with engine context
        pm.list_plugins()  # list loaded plugins
        pm.call_hook("pre_asda_act", engine)  # invoke hook on all plugins
    """

    BUILTIN_PLUGINS = [
        {
            "plugin_id": "builtin-multi-threat",
            "name": "Multi-Threat Extension",
            "version": "1.0.0",
            "author": "PMTEC Core",
            "description": "Electronic warfare and cyber attack threat models",
            "plugin_type": "threat_model",
            "dependencies": [],
            "entry_point": "_create_multi_threat",
        },
        {
            "plugin_id": "builtin-platform-stats",
            "name": "Platform Statistics",
            "version": "1.0.0",
            "author": "PMTEC Core",
            "description": "Aggregated platform statistics and health metrics",
            "plugin_type": "capability",
            "dependencies": [],
            "entry_point": "_create_stats",
        },
    ]

    def __init__(self, plugin_dir: str = None):
        self.plugin_dir = plugin_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "plugins",
        )
        self._plugins: dict[str, PluginInstance] = {}
        self._hooks: dict[str, list[str]] = {}  # hook_name -> [plugin_id, ...]
        self._engine = None

        # Register builtin plugins
        self._register_builtins()

    def _register_builtins(self):
        """Register builtin plugins that ship with the platform."""
        for bp in self.BUILTIN_PLUGINS:
            manifest = PluginManifest(**bp)
            factory = getattr(self, manifest.entry_point, None)
            if factory:
                instance = factory()
                self._plugins[manifest.plugin_id] = PluginInstance(manifest, instance)

    def _create_multi_threat(self):
        """Builtin: multi-threat extension plugin."""

        class MultiThreatPlugin:
            def __init__(self):
                self.name = "multi-threat"
                self.ew_threats = []
                self.cyber_threats = []

            def pre_asda_act(self, engine):
                """Hook: inject EW and cyber threats during Act phase."""
                import random

                # 15% chance of EW threat per cycle
                if random.random() < 0.15 and engine._bases:
                    target = random.choice(engine._bases)
                    from models.entity import EWThreatEntity

                    ew = EWThreatEntity(
                        ew_type="KGJ-500",
                        launch_lat=target["lat"] + random.uniform(-3, -1),
                        launch_lon=target["lon"] + random.uniform(-3, -1),
                        target_lat=target["lat"],
                        target_lon=target["lon"],
                    )
                    engine._entities.append(ew)
                    engine.lvc.virtual.add_entity(ew)
                    self.ew_threats.append(ew)
                    engine._emit_event(
                        "ew_jam_start",
                        "hostile",
                        f"EW jammer KGJ-500 targeting {target['name']}",
                        {
                            "target": target["id"],
                            "jam_range": ew.jam_range_km,
                            "lvc_layer": "Virtual",
                        },
                    )

                # 10% chance of cyber attack per cycle
                if random.random() < 0.10 and engine._bases:
                    target = random.choice(engine._bases)
                    from models.entity import CyberThreatEntity

                    attack_types = ["APT-intrusion", "GPS-spoofing", "comms-jamming"]
                    cyber = CyberThreatEntity(
                        attack_type=random.choice(attack_types),
                        target_base_id=target["id"],
                    )
                    engine._entities.append(cyber)
                    self.cyber_threats.append(cyber)
                    engine._emit_event(
                        "cyber_attack",
                        "hostile",
                        f"Cyber attack {cyber.subtype} on {target['name']}",
                        {
                            "target": target["id"],
                            "target_system": cyber.target_system,
                            "lvc_layer": "Constructive",
                        },
                    )

            def post_asda_sense(self, engine):
                """Hook: apply EW effects to sensor confidence."""
                from models.entity import EWThreatEntity

                ew_entities = [
                    e
                    for e in engine._entities
                    if isinstance(e, EWThreatEntity) and e.status == "active"
                ]
                for ew in ew_entities:
                    jammed_ids = ew.get_jammed_sensors(engine._sensors)
                    for sid in jammed_ids:
                        sensor = next((s for s in engine._sensors if s.id == sid), None)
                        if sensor:
                            # Reduce detection confidence
                            sensor.detection_confidence = max(
                                0.1,
                                sensor.detection_confidence
                                * (1.0 - ew.effectiveness * 0.7),
                            )

            def post_asda_adapt(self, engine):
                """Hook: apply cyber attack effects to network vulnerability."""
                from models.entity import CyberThreatEntity

                cyber_entities = [
                    e
                    for e in engine._entities
                    if isinstance(e, CyberThreatEntity) and e.status == "active"
                ]
                for cyb in cyber_entities:
                    if cyb.detected:
                        engine._emit_event(
                            "cyber_detected",
                            "ASDA-Adapt",
                            f"Cyber threat {cyb.subtype} detected at {cyb.target_base_id}",
                            {
                                "attack_type": cyb.subtype,
                                "target": cyb.target_base_id,
                                "lvc_layer": "Constructive",
                            },
                        )

            def get_threat_summary(self) -> dict:
                return {
                    "ew_active": len(
                        [e for e in self.ew_threats if e.status == "active"]
                    ),
                    "cyber_active": len(
                        [e for e in self.cyber_threats if e.status == "active"]
                    ),
                    "cyber_detected": len(
                        [e for e in self.cyber_threats if e.detected]
                    ),
                }

        return MultiThreatPlugin()

    def _create_stats(self):
        """Builtin: platform statistics plugin."""

        class StatsPlugin:
            def __init__(self):
                self.name = "platform-stats"
                self._stats = {}

            def post_asda_adapt(self, engine):
                self._stats["total_plugins"] = (
                    len(engine._components) if hasattr(engine, "_components") else 0
                )
                self._stats["active_entities"] = len(
                    [e for e in engine._entities if e.status == "active"]
                )
                self._stats["asda_cycle"] = engine.asda_cycle_count

            def get_stats(self) -> dict:
                return dict(self._stats)

        return StatsPlugin()

    def discover(self):
        """Scan the plugin directory for external plugins."""
        if not os.path.isdir(self.plugin_dir):
            return []
        found = []
        for entry in os.listdir(self.plugin_dir):
            if entry.endswith(".py") and not entry.startswith("_"):
                mod_name = entry[:-3]
                found.append(mod_name)
        return found

    def load_all(self, engine):
        """Initialize all plugins with the engine context."""
        self._engine = engine
        for pid, pi in self._plugins.items():
            try:
                init_fn = getattr(pi.instance, "init", None)
                if init_fn:
                    init_fn(engine)
                logger.info(f"Plugin loaded: {pid} ({pi.manifest.name})")
            except Exception as e:
                logger.error(f"Failed to init plugin {pid}: {e}")
                pi.active = False

    def call_hook(self, hook_name: str, *args, **kwargs):
        """Invoke a named hook on all active plugins."""
        results = []
        for pid, pi in self._plugins.items():
            if not pi.active:
                continue
            result = pi.call(hook_name, *args, **kwargs)
            if result is not None:
                results.append({"plugin": pid, "result": result})
        return results

    def list_plugins(self) -> list[dict]:
        """List all registered plugins with status."""
        return [
            {
                **pi.manifest.to_dict(),
                "active": pi.active,
                "calls": pi.call_count,
                "errors": pi.error_count,
                "uptime_s": round(time.time() - pi.loaded_at, 0),
            }
            for pi in self._plugins.values()
        ]

    def get_plugin(self, plugin_id: str) -> PluginInstance | None:
        return self._plugins.get(plugin_id)

    def shutdown(self):
        """Shutdown all plugins."""
        for pid, pi in self._plugins.items():
            try:
                pi.call("shutdown")
            except Exception:
                pass
            pi.active = False
        logger.info("All plugins shut down")
