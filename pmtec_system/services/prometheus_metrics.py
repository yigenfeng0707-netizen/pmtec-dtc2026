"""
PMTEC Prometheus Metrics Exporter (P2-a).

Provides comprehensive observability for the PMTEC Digital Battlefield
system via Prometheus-compatible metrics. Exports simulation, interception,
DQN, gRPC, live data, and persistence metrics.

Usage:
    from services.prometheus_metrics import MetricsExporter

    exporter = MetricsExporter()
    exporter.start_http_server(port=9090)  # /metrics endpoint

    # During simulation:
    exporter.update_from_engine(engine)
    exporter.record_grpc_request("WarEngine", "GetState", duration=0.005)

Metrics are exposed at http://host:9090/metrics in Prometheus text format.
"""

import logging
import os
import sys
import threading

logger = logging.getLogger("pmtec.metrics")

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
        start_http_server,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed; metrics export disabled")

# Config
try:
    from config import PROMETHEUS_ENABLED, PROMETHEUS_METRICS_PATH, PROMETHEUS_PORT
except ImportError:
    PROMETHEUS_ENABLED = True
    PROMETHEUS_PORT = 9090
    PROMETHEUS_METRICS_PATH = "/metrics"


class MetricsExporter:
    """Prometheus metrics exporter for PMTEC system.

    Defines and exposes all system metrics. Can be embedded in the
    gRPC server or run as a standalone metrics endpoint.

    Metric categories:
        - pmtec_sim_*: Simulation state (entities, threats, time)
        - pmtec_intercept_*: Interception statistics
        - pmtec_dqn_*: DQN inference and training
        - pmtec_grpc_*: gRPC server metrics
        - pmtec_live_*: Live data adapter metrics
        - pmtec_persistence_*: SQLite persistence metrics
        - pmtec_security_*: Security/auth metrics
    """

    def __init__(self, enabled: bool = None):
        self.enabled = enabled if enabled is not None else PROMETHEUS_ENABLED
        self._http_thread: threading.Thread | None = None
        self._http_running = False

        if not self.enabled or not _PROMETHEUS_AVAILABLE:
            logger.info("Prometheus metrics disabled")
            return

        # --- System info ---
        self.info = Info(
            "pmtec",
            "PMTEC Digital Battlefield system information",
        )
        self.info.info(
            {
                "version": "P7-v2",
                "system": "PMTEC-DTC2026",
                "architecture": "ASDA-cycle",
            }
        )

        # --- Simulation metrics ---
        self.sim_entities_total = Gauge(
            "pmtec_sim_entities_total",
            "Total entities in simulation",
            ["entity_type"],  # aircraft, vessel, missile, base, radar
        )
        self.sim_active_threats = Gauge(
            "pmtec_sim_active_threats",
            "Active hostile threats in current simulation",
        )
        self.sim_asda_cycles = Gauge(
            "pmtec_sim_asda_cycles_total",
            "Total ASDA (Act-Sense-Decide-Adapt) cycles completed",
        )
        self.sim_elapsed_seconds = Gauge(
            "pmtec_sim_elapsed_seconds",
            "Simulation elapsed time in seconds",
        )
        self.sim_events_total = Counter(
            "pmtec_sim_events_total",
            "Total simulation events generated",
            ["event_type"],  # launch, intercept, detect, destroy, etc.
        )

        # --- Interception metrics ---
        self.intercept_total = Counter(
            "pmtec_intercept_total",
            "Total missile/threat interceptions attempted",
            ["threat_type"],  # ballistic, cruise, hypersonic
        )
        self.intercept_success = Counter(
            "pmtec_intercept_success_total",
            "Successful interceptions",
            ["threat_type"],
        )
        self.intercept_miss = Counter(
            "pmtec_intercept_miss_total",
            "Failed interceptions (miss)",
            ["threat_type"],
        )
        self.intercept_rate = Gauge(
            "pmtec_intercept_rate",
            "Current interception success rate (0.0-1.0)",
        )
        self.intercept_response_time = Histogram(
            "pmtec_intercept_response_time_seconds",
            "Time from threat detection to interception attempt (seconds)",
            ["threat_type"],
            buckets=(1, 5, 10, 20, 30, 60, 120, 300),
        )

        # --- DQN metrics ---
        self.dqn_inference_total = Counter(
            "pmtec_dqn_inference_total",
            "Total DQN inference calls",
        )
        self.dqn_inference_latency = Histogram(
            "pmtec_dqn_inference_latency_seconds",
            "DQN inference latency (seconds)",
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
        )
        self.dqn_training_steps = Gauge(
            "pmtec_dqn_training_steps_total",
            "Total DQN training steps completed",
        )
        self.dqn_avg_reward = Gauge(
            "pmtec_dqn_avg_reward",
            "Average reward (rolling) from DQN training",
        )
        self.dqn_model_loaded = Gauge(
            "pmtec_dqn_model_loaded",
            "1 if DQN model is loaded, 0 otherwise",
        )

        # --- Multi-agent metrics ---
        self.multiagent_agents_active = Gauge(
            "pmtec_multiagent_agents_active",
            "Number of active multi-agent actors",
        )
        self.multiagent_avg_reward = Gauge(
            "pmtec_multiagent_avg_reward",
            "Average reward from multi-agent training (IQL/MADDPG)",
        )

        # --- gRPC metrics ---
        self.grpc_requests_total = Counter(
            "pmtec_grpc_requests_total",
            "Total gRPC requests received",
            ["service", "method"],
        )
        self.grpc_errors_total = Counter(
            "pmtec_grpc_errors_total",
            "Total gRPC request errors",
            ["service", "method"],
        )
        self.grpc_response_time = Histogram(
            "pmtec_grpc_response_time_seconds",
            "gRPC response time (seconds)",
            ["service", "method"],
            buckets=(0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
        )
        self.grpc_active_connections = Gauge(
            "pmtec_grpc_active_connections",
            "Active gRPC connections",
        )
        self.grpc_health_status = Gauge(
            "pmtec_grpc_health_status",
            "gRPC health check status (1=SERVING, 0=NOT_SERVING)",
            ["service"],
        )

        # --- HA metrics ---
        self.ha_active_backend = Gauge(
            "pmtec_ha_active_backend",
            "Index of active backend (0=primary, 1+=backup)",
        )
        self.ha_failover_count = Counter(
            "pmtec_ha_failover_total",
            "Total HA failover events",
        )
        self.ha_backend_state = Gauge(
            "pmtec_ha_backend_state",
            "Backend state (0=TRANSIENT_FAILURE, 1=READY, 2=CONNECTING)",
            ["endpoint"],
        )

        # --- Live data metrics ---
        self.live_contacts_total = Gauge(
            "pmtec_live_contacts_total",
            "Current live data contacts",
            ["source"],  # adsb, ais, weather
        )
        self.live_api_fetches = Counter(
            "pmtec_live_api_fetches_total",
            "Total live data API fetch attempts",
            ["source"],
        )
        self.live_api_failures = Counter(
            "pmtec_live_api_failures_total",
            "Total live data API failures",
            ["source"],
        )
        self.live_real_vs_sim = Gauge(
            "pmtec_live_real_vs_sim",
            "1 if using real API data, 0 if simulation",
            ["source"],
        )

        # --- Persistence metrics ---
        self.persistence_snapshots = Gauge(
            "pmtec_persistence_snapshots_total",
            "Total SQLite snapshots saved",
        )
        self.persistence_db_size_bytes = Gauge(
            "pmtec_persistence_db_size_bytes",
            "SQLite database file size in bytes",
        )
        self.persistence_tracks = Gauge(
            "pmtec_persistence_tracks_total",
            "Total tracks stored in SQLite",
        )

        # --- Security metrics ---
        self.security_auth_attempts = Counter(
            "pmtec_security_auth_attempts_total",
            "Total authentication attempts",
            ["result"],  # success, failure
        )
        self.security_rbac_denied = Counter(
            "pmtec_security_rbac_denied_total",
            "Total RBAC permission denials",
            ["role", "resource"],
        )
        self.security_audit_entries = Counter(
            "pmtec_security_audit_entries_total",
            "Total audit log entries written",
        )

        logger.info(
            "Prometheus metrics exporter initialized (%d metrics)",
            len(REGISTRY._names_to_collectors),
        )

        # P7-v2: Register as singleton to prevent duplicate registration
        global _exporter
        if _exporter is None:
            _exporter = self

    # -- Export methods --

    def update_from_engine(self, engine) -> None:
        """Update all simulation-related metrics from PMTECEngine state.

        Call this periodically (e.g., every ASDA cycle) to refresh metrics.
        """
        if not self.enabled:
            return

        try:
            state = engine.get_state_dict()
        except Exception:
            return

        # Simulation metrics
        entities = state.get("entities", [])
        type_counts: dict[str, int] = {}
        for e in entities:
            etype = e.get("entity_type", e.get("type", "unknown"))
            type_counts[etype] = type_counts.get(etype, 0) + 1
        for etype, count in type_counts.items():
            self.sim_entities_total.labels(entity_type=etype).set(count)

        threats = [e for e in entities if e.get("affiliation") == "hostile"]
        self.sim_active_threats.set(len(threats))

        self.sim_asda_cycles.set(state.get("asda_cycle", 0))
        self.sim_elapsed_seconds.set(state.get("elapsed_sec", 0))

        events = state.get("events", [])
        event_types: dict[str, int] = {}
        for ev in events:
            etype = ev.get("event_type", "unknown")
            event_types[etype] = event_types.get(etype, 0) + 1
        for etype, count in event_types.items():
            self.sim_events_total.labels(event_type=etype).inc(count)

        # Interception metrics
        stats = state.get("interception_stats", {})
        total = stats.get("total_missiles", 0)
        intercepted = stats.get("intercepted", 0)
        stats.get("missed", 0)
        rate = (intercepted / total) if total > 0 else 0.0

        self.intercept_rate.set(rate)
        # Note: Counters are cumulative; only inc the delta
        # For gauges we can set directly

        # DQN metrics
        dqn_info = state.get("dqn_info", {})
        self.dqn_model_loaded.set(1 if dqn_info.get("loaded") else 0)
        self.dqn_training_steps.set(dqn_info.get("training_steps", 0))
        self.dqn_avg_reward.set(dqn_info.get("avg_reward", 0.0))

        # Multi-agent metrics
        ma_info = state.get("multi_agent_info", {})
        self.multiagent_agents_active.set(ma_info.get("agents_active", 0))
        self.multiagent_avg_reward.set(ma_info.get("avg_reward", 0.0))

        # Live data metrics
        live_stats = (
            engine._live_injection_stats
            if hasattr(engine, "_live_injection_stats")
            else {}
        )
        if isinstance(live_stats, dict):
            self.live_contacts_total.labels(source="adsb").set(
                live_stats.get("adsb_contacts", 0)
            )
            self.live_contacts_total.labels(source="ais").set(
                live_stats.get("ais_vessels", 0)
            )
            self.live_contacts_total.labels(source="weather").set(
                live_stats.get("weather_stations", 0)
            )

        # Persistence metrics
        if engine.store:
            persist_stats = (
                engine.store.get_stats() if hasattr(engine.store, "get_stats") else {}
            )
            self.persistence_snapshots.set(persist_stats.get("snapshots", 0))
            self.persistence_tracks.set(persist_stats.get("tracks", 0))
            db_path = getattr(engine.store, "db_path", None)
            if db_path and os.path.exists(db_path):
                self.persistence_db_size_bytes.set(os.path.getsize(db_path))

    def record_grpc_request(
        self, service: str, method: str, duration: float = 0.0, error: bool = False
    ):
        """Record a gRPC request."""
        if not self.enabled:
            return
        self.grpc_requests_total.labels(service=service, method=method).inc()
        if duration > 0:
            self.grpc_response_time.labels(service=service, method=method).observe(
                duration
            )
        if error:
            self.grpc_errors_total.labels(service=service, method=method).inc()

    def record_interception(
        self, threat_type: str, success: bool, response_time: float = 0.0
    ):
        """Record an interception attempt."""
        if not self.enabled:
            return
        self.intercept_total.labels(threat_type=threat_type).inc()
        if success:
            self.intercept_success.labels(threat_type=threat_type).inc()
        else:
            self.intercept_miss.labels(threat_type=threat_type).inc()
        if response_time > 0:
            self.intercept_response_time.labels(threat_type=threat_type).observe(
                response_time
            )

    def record_dqn_inference(self, latency: float = 0.0):
        """Record a DQN inference call."""
        if not self.enabled:
            return
        self.dqn_inference_total.inc()
        if latency > 0:
            self.dqn_inference_latency.observe(latency)

    def record_live_fetch(self, source: str, success: bool, is_real: bool):
        """Record a live data fetch."""
        if not self.enabled:
            return
        self.live_api_fetches.labels(source=source).inc()
        if not success:
            self.live_api_failures.labels(source=source).inc()
        self.live_real_vs_sim.labels(source=source).set(1 if is_real else 0)

    def record_ha_failover(self, active_idx: int = 0):
        """Record an HA failover event."""
        if not self.enabled:
            return
        self.ha_active_backend.set(active_idx)
        self.ha_failover_count.inc()

    def record_security_event(
        self,
        auth_success: bool = True,
        rbac_denied: str = None,
        audit_entry: bool = False,
    ):
        """Record security-related events."""
        if not self.enabled:
            return
        self.security_auth_attempts.labels(
            result="success" if auth_success else "failure"
        ).inc()
        if rbac_denied:
            role, resource = (
                rbac_denied.split(":", 1)
                if ":" in rbac_denied
                else ("unknown", "unknown")
            )
            self.security_rbac_denied.labels(role=role, resource=resource).inc()
        if audit_entry:
            self.security_audit_entries.inc()

    def update_ha_status(self, ha_status: dict):
        """Update HA backend states from channel pool status."""
        if not self.enabled or not ha_status:
            return
        state_map = {"READY": 1, "CONNECTING": 2, "TRANSIENT_FAILURE": 0, "IDLE": 0}
        for ep_key, ep_info in ha_status.items():
            endpoints = ep_info.get("endpoints", {})
            for endpoint, ep_state in endpoints.items():
                state = ep_state.get("state", "UNKNOWN")
                self.ha_backend_state.labels(endpoint=endpoint).set(
                    state_map.get(state, 0)
                )

    # -- HTTP server --

    def start_http_server(self, port: int = None, addr: str = "0.0.0.0") -> bool:
        """Start Prometheus HTTP metrics endpoint.

        Metrics will be available at http://host:port/metrics
        """
        if not self.enabled or not _PROMETHEUS_AVAILABLE:
            return False

        port = port or PROMETHEUS_PORT

        if self._http_running:
            logger.warning("Metrics HTTP server already running on port %d", port)
            return True

        try:
            start_http_server(port, addr=addr)
            self._http_running = True
            logger.info(
                "Prometheus metrics endpoint started on http://%s:%d%s",
                addr,
                port,
                PROMETHEUS_METRICS_PATH,
            )
            print(
                f"[Metrics] Prometheus endpoint: http://{addr}:{port}{PROMETHEUS_METRICS_PATH}"
            )
            return True
        except OSError as e:
            logger.error("Failed to start metrics HTTP server: %s", e)
            print(f"[WARN] Metrics HTTP server failed (port {port} in use?): {e}")
            return False

    def generate_metrics(self) -> tuple[bytes, str]:
        """Generate metrics in Prometheus text format.

        Returns (content_bytes, content_type) for embedding in HTTP responses.
        """
        if not _PROMETHEUS_AVAILABLE:
            return b"", "text/plain"
        return generate_latest(), CONTENT_TYPE_LATEST

    @property
    def is_running(self) -> bool:
        return self._http_running


# Singleton instance for global access
_exporter: MetricsExporter | None = None


def get_metrics_exporter() -> MetricsExporter:
    """Get or create the singleton MetricsExporter instance.

    Returns the existing instance if one was already created (either
    via direct instantiation or this function). This prevents
    DuplicateTimeseries errors from the global Prometheus registry.
    """
    global _exporter
    if _exporter is None:
        _exporter = MetricsExporter()
    return _exporter
