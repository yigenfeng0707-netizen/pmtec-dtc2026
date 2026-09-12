"""
PMTEC gRPC Client Connectors (P2-2).

Provides typed gRPC client wrappers for cross-process communication
between the four distributed DTB services. Each connector lazily opens
a gRPC channel to the target service and caches it for reuse.

P7-v2: Added HA (High Availability) support with multi-backend failover,
exponential backoff reconnection, and gRPC health check polling.

Usage:
  from distributed.grpc_clients import ServiceClient

  client = ServiceClient()
  state = client.war_engine.get_state()
  tracks = client.battle_network.get_tracks(min_lat=0, max_lat=90, min_lon=0, max_lon=180)
  health = client.plug_and_play.health_check()
"""

import logging
import os
import sys
import threading
import time

# Add proto generated path
_GEN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proto", "generated"
)
if _GEN_DIR not in sys.path:
    sys.path.insert(0, _GEN_DIR)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import dtb_model_pb2 as pb
import dtb_model_pb2_grpc as pb_grpc
import grpc

from config import (
    DISTRIBUTED_HOST,
    DISTRIBUTED_PORTS,
    GRPC_HOST,
    GRPC_PORT,
)

# HA config (P7-v2) - safe import with defaults
try:
    from config import (
        GRPC_HA_BACKUP_HOSTS as _HA_BACKUP_HOSTS,
    )
    from config import (
        GRPC_HA_ENABLED as _HA_ENABLED,
    )
    from config import (
        GRPC_HEALTH_CHECK_INTERVAL_S as _HC_INTERVAL,
    )
    from config import (
        GRPC_RECONNECT_INITIAL_MS as _RC_INIT_MS,
    )
    from config import (
        GRPC_RECONNECT_MAX_ATTEMPTS as _RC_MAX_ATTEMPTS,
    )
    from config import (
        GRPC_RECONNECT_MAX_MS as _RC_MAX_MS,
    )
    from config import (
        GRPC_RECONNECT_MULTIPLIER as _RC_MULT,
    )
except ImportError:
    _HA_ENABLED = False
    _HA_BACKUP_HOSTS = []
    _HC_INTERVAL = 10
    _RC_INIT_MS = 1000
    _RC_MAX_MS = 30000
    _RC_MULT = 2.0
    _RC_MAX_ATTEMPTS = 5

logger = logging.getLogger("pmtec.distributed")


# ---------------------------------------------------------------------------
# P7-v2: HA Channel Manager - multi-backend failover + reconnection
# ---------------------------------------------------------------------------


class _HAChannelManager:
    """Manages a set of gRPC channels with failover and automatic reconnection.

    - Maintains a primary channel and optional backup channels.
    - On RPC failure, switches to the next healthy backend.
    - Uses exponential backoff for reconnection attempts.
    - Polls gRPC Health Check protocol when available.
    """

    def __init__(self, primary: str, backups: list | None = None):
        self._primary = primary
        self._backups = list(backups) if backups else []
        self._all_endpoints = [primary] + self._backups
        self._active_idx = 0
        self._channels: dict[str, grpc.Channel] = {}
        self._channel_states: dict[
            str, str
        ] = {}  # "IDLE" | "CONNECTING" | "READY" | "TRANSIENT_FAILURE"
        self._reconnect_attempts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._health_thread: threading.Thread | None = None
        self._health_stop = threading.Event()

        # Create all channels upfront
        for ep in self._all_endpoints:
            self._channels[ep] = self._create_channel(ep)
            self._channel_states[ep] = "IDLE"
            self._reconnect_attempts[ep] = 0

        # Start health polling if HA enabled
        if _HA_ENABLED and len(self._all_endpoints) > 1:
            self._start_health_polling()

    def _create_channel(self, endpoint: str) -> grpc.Channel:
        """Create a gRPC channel with HA-aware options."""
        return grpc.insecure_channel(
            endpoint,
            options=[
                ("grpc.max_send_message_length", 50 * 1024 * 1024),
                ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                ("grpc.keepalive_time_ms", 30000),
                ("grpc.keepalive_timeout_ms", 10000),
                ("grpc.enable_retries", 1),
                (
                    "grpc.service_config",
                    '{"retryPolicy": {"maxAttempts": %d, "initialBackoff": "%.1fs", '
                    '"maxBackoff": "%.1fs", "backoffMultiplier": %.1f, "retryableStatusCodes": [14, 13]}}'
                    % (
                        _RC_MAX_ATTEMPTS + 1,
                        _RC_INIT_MS / 1000.0,
                        _RC_MAX_MS / 1000.0,
                        _RC_MULT,
                    ),
                ),
            ],
        )

    def _start_health_polling(self):
        """Start background thread polling gRPC health checks."""
        self._health_thread = threading.Thread(
            target=self._health_loop, daemon=True, name="pmtec-ha-health"
        )
        self._health_thread.start()
        logger.info(f"[HA] Health polling started (interval={_HC_INTERVAL}s)")

    def _health_loop(self):
        """Periodically check health of all backends."""
        try:
            from grpc_health.v1 import health_pb2, health_pb2_grpc
        except ImportError:
            logger.warning(
                "[HA] grpcio-health-checking not installed; health polling disabled"
            )
            return

        while not self._health_stop.is_set():
            for ep in self._all_endpoints:
                if self._health_stop.is_set():
                    break
                try:
                    ch = self._channels.get(ep)
                    if ch is None:
                        continue
                    stub = health_pb2_grpc.HealthStub(ch)
                    check_fn = getattr(stub, "Check", None)
                    if check_fn is None:
                        continue
                    resp = check_fn(
                        health_pb2.HealthCheckRequest(service=""),
                        timeout=5,
                    )
                    state = resp.status  # 1=SERVING, 0=NOT_SERVING, 2=UNKNOWN
                    with self._lock:
                        if state == health_pb2.HealthCheckResponse.SERVING:
                            self._channel_states[ep] = "READY"
                            self._reconnect_attempts[ep] = 0
                        else:
                            self._channel_states[ep] = "TRANSIENT_FAILURE"
                except Exception:
                    with self._lock:
                        self._channel_states[ep] = "TRANSIENT_FAILURE"
            self._health_stop.wait(_HC_INTERVAL)

    def get_active_channel(self) -> grpc.Channel:
        """Return the current active channel, failing over if needed."""
        with self._lock:
            # Try current active
            ep = self._all_endpoints[self._active_idx]
            if self._channel_states.get(ep) == "READY":
                return self._channels[ep]

            # Try to find a READY backend
            for i, alt_ep in enumerate(self._all_endpoints):
                if self._channel_states.get(alt_ep) == "READY":
                    self._active_idx = i
                    logger.info(f"[HA] Failover: {ep} -> {alt_ep}")
                    return self._channels[alt_ep]

            # No READY backend - return current (will trigger gRPC retry)
            return self._channels[ep]

    def report_failure(self, endpoint: str = None):
        """Report that a backend failed; trigger reconnection logic."""
        ep = endpoint or self._all_endpoints[self._active_idx]
        with self._lock:
            self._channel_states[ep] = "TRANSIENT_FAILURE"
            self._reconnect_attempts[ep] = self._reconnect_attempts.get(ep, 0) + 1
            attempts = self._reconnect_attempts[ep]

        backoff = (
            min(
                _RC_INIT_MS * (_RC_MULT ** (attempts - 1)),
                _RC_MAX_MS,
            )
            / 1000.0
        )
        logger.warning(f"[HA] {ep} failed (attempt {attempts}), backoff {backoff:.1f}s")
        # Try to reconnect in background
        threading.Thread(target=self._reconnect, args=(ep,), daemon=True).start()

    def _reconnect(self, endpoint: str):
        """Attempt to reconnect to a failed backend."""
        backoff = (
            min(
                _RC_INIT_MS
                * (_RC_MULT ** (self._reconnect_attempts.get(endpoint, 0) - 1)),
                _RC_MAX_MS,
            )
            / 1000.0
        )
        time.sleep(backoff)

        # Recreate channel
        with self._lock:
            old = self._channels.get(endpoint)
            if old:
                try:
                    old.close()
                except Exception:
                    pass
            self._channels[endpoint] = self._create_channel(endpoint)
            self._channel_states[endpoint] = "CONNECTING"

        # Wait for channel to be ready (with timeout)
        try:
            grpc.channel_ready_future(self._channels[endpoint]).result(timeout=10)
            with self._lock:
                self._channel_states[endpoint] = "READY"
                self._reconnect_attempts[endpoint] = 0
            logger.info(f"[HA] {endpoint} reconnected successfully")
        except Exception as e:
            with self._lock:
                self._channel_states[endpoint] = "TRANSIENT_FAILURE"
            logger.warning(f"[HA] {endpoint} reconnect failed: {e}")

    def close_all(self):
        self._health_stop.set()
        if self._health_thread:
            self._health_thread.join(timeout=5)
        for ch in self._channels.values():
            try:
                ch.close()
            except Exception:
                pass
        self._channels.clear()

    def get_status(self) -> dict:
        """Return HA status for observability."""
        with self._lock:
            return {
                "primary": self._primary,
                "active": self._all_endpoints[self._active_idx],
                "backups": self._backups,
                "endpoints": {
                    ep: {
                        "state": self._channel_states.get(ep, "UNKNOWN"),
                        "reconnect_attempts": self._reconnect_attempts.get(ep, 0),
                    }
                    for ep in self._all_endpoints
                },
            }


class _GrpcChannelPool:
    """Lazily creates and caches gRPC channels per service.

    P7-v2: When GRPC_HA_ENABLED is True, uses _HAChannelManager for
    multi-backend failover with health checking and automatic reconnection.
    """

    def __init__(self):
        self._channels: dict[str, grpc.Channel] = {}
        self._ha_managers: dict[str, _HAChannelManager] = {}

    def get(self, host: str, port: int) -> grpc.Channel:
        key = f"{host}:{port}"
        if key not in self._channels:
            if _HA_ENABLED and _HA_BACKUP_HOSTS:
                # HA mode: create manager with primary + backups
                backups = [f"{h}:{port}" for h in _HA_BACKUP_HOSTS if h != host]
                mgr = _HAChannelManager(primary=key, backups=backups)
                self._ha_managers[key] = mgr
                self._channels[key] = mgr.get_active_channel()
            else:
                # Non-HA mode: simple channel (original behavior)
                self._channels[key] = grpc.insecure_channel(
                    f"{host}:{port}",
                    options=[
                        ("grpc.max_send_message_length", 50 * 1024 * 1024),
                        ("grpc.max_receive_message_length", 50 * 1024 * 1024),
                        ("grpc.keepalive_time_ms", 30000),
                        ("grpc.keepalive_timeout_ms", 10000),
                    ],
                )
        return self._channels[key]

    def close_all(self):
        for mgr in self._ha_managers.values():
            mgr.close_all()
        self._ha_managers.clear()
        for ch in self._channels.values():
            try:
                ch.close()
            except Exception:
                pass
        self._channels.clear()

    def get_ha_status(self) -> dict:
        """Return HA status for all managed endpoints (P7-v2)."""
        return {key: mgr.get_status() for key, mgr in self._ha_managers.items()}


_channel_pool = _GrpcChannelPool()


class WarEngineClient:
    """gRPC client for the WarEngine service."""

    def __init__(self, host: str = None, port: int = None):
        self._host = host or DISTRIBUTED_HOST
        self._port = port or DISTRIBUTED_PORTS["WarEngine"]
        self._stub: pb_grpc.WarEngineStub | None = None

    @property
    def stub(self) -> pb_grpc.WarEngineStub:
        if self._stub is None:
            ch = _channel_pool.get(self._host, self._port)
            self._stub = pb_grpc.WarEngineStub(ch)
        return self._stub

    def start_simulation(self, scenario: str, duration: int, seed: int) -> pb.Ack:
        return self.stub.StartSimulation(
            pb.StartRequest(
                scenario_name=scenario, duration_seconds=duration, seed=seed
            )
        )

    def stop_simulation(self) -> pb.Ack:
        return self.stub.StopSimulation(pb.StopRequest())

    def get_state(self, at_time: int = 0) -> pb.SystemState:
        return self.stub.GetState(pb.StateRequest(at_time=at_time))

    def inject_event(
        self, event_type: str, actor: str, description: str, params: dict = None
    ) -> pb.Ack:
        evt = pb.SimEvent(
            event_id=f"ext-{int(time.time())}",
            event_type=event_type,
            timestamp=int(time.time()),
            actor=actor,
            description=description,
        )
        if params:
            for k, v in params.items():
                evt.params[str(k)] = str(v)
        return self.stub.InjectEvent(evt)

    def get_spear_report(
        self, start: int = 0, end: int = 0, speed: float = 1.0
    ) -> pb.SpearReport:
        return self.stub.GetSpearReport(
            pb.SpearReplayRequest(start_time=start, end_time=end, playback_speed=speed)
        )

    def get_ew_threats(
        self, target_base: str = "", active_only: bool = False
    ) -> pb.EWThreatList:
        return self.stub.GetEWThreats(
            pb.EWThreatQuery(target_base_id=target_base, active_only=active_only)
        )

    def get_cyber_threats(
        self, target_base: str = "", detected_only: bool = False
    ) -> pb.CyberThreatList:
        return self.stub.GetCyberThreats(
            pb.CyberThreatQuery(target_base_id=target_base, detected_only=detected_only)
        )

    def get_threat_summary(self) -> pb.ThreatSummary:
        return self.stub.GetThreatSummary(pb.HealthQuery())


class BattleNetworkClient:
    """gRPC client for the BattleNetwork service."""

    def __init__(self, host: str = None, port: int = None):
        self._host = host or DISTRIBUTED_HOST
        self._port = port or DISTRIBUTED_PORTS["BattleNetwork"]
        self._stub: pb_grpc.BattleNetworkStub | None = None

    @property
    def stub(self) -> pb_grpc.BattleNetworkStub:
        if self._stub is None:
            ch = _channel_pool.get(self._host, self._port)
            self._stub = pb_grpc.BattleNetworkStub(ch)
        return self._stub

    def get_entity_status(
        self, entity_id: str = "", type_filter: str = ""
    ) -> pb.EntityStatus:
        return self.stub.GetEntityStatus(
            pb.EntityQuery(entity_id=entity_id, type_filter=type_filter)
        )

    def get_network_state(self) -> pb.NetworkState:
        return self.stub.GetNetworkState(pb.NetQuery())

    def get_live_feed(
        self,
        feed_type: str = "all",
        min_lat: float = -90,
        max_lat: float = 90,
        min_lon: float = -180,
        max_lon: float = 180,
    ):
        """Returns a streaming iterator of LiveFeedUpdate."""
        return self.stub.GetLiveFeed(
            pb.LiveFeedRequest(
                feed_type=feed_type,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
            )
        )

    def get_lvc_status(self) -> pb.LVCStatus:
        return self.stub.GetLVCStatus(pb.HealthQuery())


class ApplicationStoreClient:
    """gRPC client for the ApplicationStore service."""

    def __init__(self, host: str = None, port: int = None):
        self._host = host or DISTRIBUTED_HOST
        self._port = port or DISTRIBUTED_PORTS["ApplicationStore"]
        self._stub: pb_grpc.ApplicationStoreStub | None = None

    @property
    def stub(self) -> pb_grpc.ApplicationStoreStub:
        if self._stub is None:
            ch = _channel_pool.get(self._host, self._port)
            self._stub = pb_grpc.ApplicationStoreStub(ch)
        return self._stub

    def list_apps(self, category: str = "") -> pb.AppList:
        return self.stub.ListApps(pb.AppQuery(category=category))

    def deploy_app(
        self, app_id: str, target_base: str, count: int = 1
    ) -> pb.DeployResult:
        return self.stub.DeployApp(
            pb.DeployRequest(app_id=app_id, target_base=target_base, count=count)
        )

    def query_capability(self, base_id: str) -> pb.CapabilityReport:
        return self.stub.QueryCapability(pb.CapabilityQuery(base_id=base_id))

    def dqn_infer(
        self, observation: list, deterministic: bool = True
    ) -> pb.DQNInferenceResult:
        return self.stub.DQNInfer(
            pb.DQNInferenceRequest(observation=observation, deterministic=deterministic)
        )

    def get_dqn_status(self) -> pb.DQNTrainingStatus:
        return self.stub.GetDQNStatus(pb.HealthQuery())


class PlugAndPlayClient:
    """gRPC client for the PlugAndPlay service."""

    def __init__(self, host: str = None, port: int = None):
        self._host = host or DISTRIBUTED_HOST
        self._port = port or DISTRIBUTED_PORTS["PlugAndPlay"]
        self._stub: pb_grpc.PlugAndPlayStub | None = None

    @property
    def stub(self) -> pb_grpc.PlugAndPlayStub:
        if self._stub is None:
            ch = _channel_pool.get(self._host, self._port)
            self._stub = pb_grpc.PlugAndPlayStub(ch)
        return self._stub

    def register_component(
        self, comp_id: str, comp_type: str, endpoint: str, metadata: dict = None
    ) -> pb.RegResult:
        return self.stub.RegisterComponent(
            pb.ComponentInfo(
                component_id=comp_id,
                component_type=comp_type,
                endpoint=endpoint,
                metadata=metadata or {},
            )
        )

    def discover_services(self, service_type: str = "") -> pb.ServiceList:
        return self.stub.DiscoverServices(pb.DiscoveryQuery(service_type=service_type))

    def health_check(self) -> pb.HealthStatus:
        return self.stub.HealthCheck(pb.HealthQuery())

    def list_plugins(
        self, plugin_type: str = "", active_only: bool = False
    ) -> pb.PluginList:
        return self.stub.ListPlugins(
            pb.PluginQuery(plugin_type=plugin_type, active_only=active_only)
        )

    def list_dt_instances(self) -> pb.DTInstanceList:
        return self.stub.ListDTInstances(pb.HealthQuery())

    def register_dt_instance(
        self, name: str, scenario: str, tags: list = None, metadata: dict = None
    ) -> pb.DTInstanceInfo:
        return self.stub.RegisterDTInstance(
            pb.DTRegisterRequest(
                name=name,
                scenario=scenario,
                tags=tags or [],
                metadata=metadata or {},
            )
        )


class ServiceClient:
    """Unified client for all four PMTEC DTB services.

    Provides convenient access to all services from a single object,
    with lazy channel creation and shared channel pool.
    """

    def __init__(self, host: str = None, ports: dict = None):
        self._host = host or DISTRIBUTED_HOST
        self._ports = ports or DISTRIBUTED_PORTS
        self.war_engine = WarEngineClient(self._host, self._ports["WarEngine"])
        self.battle_network = BattleNetworkClient(
            self._host, self._ports["BattleNetwork"]
        )
        self.application_store = ApplicationStoreClient(
            self._host, self._ports["ApplicationStore"]
        )
        self.plug_and_play = PlugAndPlayClient(self._host, self._ports["PlugAndPlay"])

    def health_check_all(self) -> dict:
        """Check health of all services. Returns dict of service_name -> healthy."""
        results = {}
        for name, client in [
            ("WarEngine", self.war_engine),
            ("BattleNetwork", self.battle_network),
            ("ApplicationStore", self.application_store),
            ("PlugAndPlay", self.plug_and_play),
        ]:
            try:
                if name == "PlugAndPlay":
                    hs = client.health_check()
                    results[name] = hs.healthy
                elif name == "WarEngine":
                    # WarEngine has no health check; use GetState as liveness probe
                    client.get_state()
                    results[name] = True
                elif name == "BattleNetwork":
                    client.get_network_state()
                    results[name] = True
                elif name == "ApplicationStore":
                    client.list_apps()
                    results[name] = True
            except Exception as e:
                logger.warning(f"{name} health check failed: {e}")
                results[name] = False
        return results

    def close(self):
        _channel_pool.close_all()


# Legacy monolithic-mode client (single port 50051)
class MonolithicClient:
    """Client for monolithic PMTEC deployment (all services on port 50051)."""

    def __init__(self, host: str = None, port: int = None):
        self._host = host or GRPC_HOST
        self._port = port or GRPC_PORT
        # In monolithic mode, all 4 stubs use the same channel
        ch = _channel_pool.get(self._host, self._port)
        self._we_stub = pb_grpc.WarEngineStub(ch)
        self._bn_stub = pb_grpc.BattleNetworkStub(ch)
        self._as_stub = pb_grpc.ApplicationStoreStub(ch)
        self._pp_stub = pb_grpc.PlugAndPlayStub(ch)

    @property
    def war_engine(self):
        return _WarEngineStubWrapper(self._we_stub)

    @property
    def battle_network(self):
        return _BattleNetworkStubWrapper(self._bn_stub)

    @property
    def application_store(self):
        return _AppStoreStubWrapper(self._as_stub)

    @property
    def plug_and_play(self):
        return _PlugAndPlayStubWrapper(self._pp_stub)

    def close(self):
        _channel_pool.close_all()


class _WarEngineStubWrapper:
    def __init__(self, stub):
        self._stub = stub

    def get_state(self, at_time: int = 0) -> pb.SystemState:
        return self._stub.GetState(pb.StateRequest(at_time=at_time))

    def start_simulation(self, scenario: str, duration: int, seed: int) -> pb.Ack:
        return self._stub.StartSimulation(
            pb.StartRequest(
                scenario_name=scenario, duration_seconds=duration, seed=seed
            )
        )

    def stop_simulation(self) -> pb.Ack:
        return self._stub.StopSimulation(pb.StopRequest())


class _BattleNetworkStubWrapper:
    def __init__(self, stub):
        self._stub = stub

    def get_network_state(self) -> pb.NetworkState:
        return self._stub.GetNetworkState(pb.NetQuery())

    def get_lvc_status(self) -> pb.LVCStatus:
        return self._stub.GetLVCStatus(pb.HealthQuery())


class _AppStoreStubWrapper:
    def __init__(self, stub):
        self._stub = stub

    def list_apps(self, category: str = "") -> pb.AppList:
        return self._stub.ListApps(pb.AppQuery(category=category))

    def get_dqn_status(self) -> pb.DQNTrainingStatus:
        return self._stub.GetDQNStatus(pb.HealthQuery())


class _PlugAndPlayStubWrapper:
    def __init__(self, stub):
        self._stub = stub

    def health_check(self) -> pb.HealthStatus:
        return self._stub.HealthCheck(pb.HealthQuery())

    def list_plugins(self) -> pb.PluginList:
        return self._stub.ListPlugins(pb.PluginQuery())

    def list_dt_instances(self) -> pb.DTInstanceList:
        return self._stub.ListDTInstances(pb.HealthQuery())
