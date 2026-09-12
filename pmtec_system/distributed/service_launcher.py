"""
PMTEC Distributed Service Launcher (P2-2).

Launches each DTB gRPC service as an independent gRPC server on its own
port, with shared engine state for development/testing. In production,
each service would run in its own process or container.

Services can be started individually or all at once via background threads.

Usage:
  # Start all 4 services in background threads
  from distributed.service_launcher import launch_all
  launcher = launch_all()
  launcher.stop_all()

  # Start a single service (blocking)
  from distributed.service_launcher import run_war_engine
  run_war_engine()  # blocks until Ctrl-C

  # CLI: python -m distributed.service_launcher --service war_engine
"""

import logging
import os
import sys
import threading
import time
from concurrent import futures

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_GEN_DIR = os.path.join(_PROJECT_ROOT, "proto", "generated")
if _GEN_DIR not in sys.path:
    sys.path.insert(0, _GEN_DIR)

import dtb_model_pb2_grpc as pb_grpc
import grpc

from config import (
    DISTRIBUTED_HOST,
    DISTRIBUTED_PORTS,
)
from services.grpc_server import (
    ApplicationStoreServicer,
    BattleNetworkServicer,
    PlugAndPlayServicer,
    PMTECEngine,
    WarEngineServicer,
)

logger = logging.getLogger("pmtec.distributed")

# Singleton shared engine for single-process multi-port mode.
# In a real distributed deployment, each service gets its own engine
# and communicates via gRPC clients (see grpc_clients.py).
_shared_engine: PMTECEngine | None = None
_shared_engine_lock = threading.Lock()


def get_shared_engine() -> PMTECEngine:
    """Get or create the singleton shared PMTEC engine."""
    global _shared_engine
    if _shared_engine is None:
        with _shared_engine_lock:
            if _shared_engine is None:
                _shared_engine = PMTECEngine()
                _shared_engine.load_bases()
                logger.info(
                    "Shared PMTEC engine initialized with %d bases",
                    len(_shared_engine._bases),
                )
    return _shared_engine


def _create_server(host: str, port: int) -> grpc.Server:
    """Create a gRPC server bound to host:port with 4-worker pool."""
    return grpc.server(futures.ThreadPoolExecutor(max_workers=4))


class _DistributedService:
    """Wraps a single gRPC service running on its own port."""

    def __init__(self, name: str, host: str, port: int, servicer, servicer_add_fn):
        self.name = name
        self.host = host
        self.port = port
        self._servicer = servicer
        self._add_fn = servicer_add_fn
        self._server: grpc.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self, blocking: bool = False):
        """Start this service. If blocking=True, blocks until interrupted."""
        self._server = _create_server(self.host, self.port)
        self._add_fn(self._servicer, self._server)
        self._server.add_insecure_port(f"{self.host}:{self.port}")
        self._server.start()
        logger.info("%s started on %s:%d", self.name, self.host, self.port)

        if blocking:
            try:
                self._server.wait_for_termination()
            except KeyboardInterrupt:
                logger.info("%s received Ctrl-C, stopping...", self.name)
                self._server.stop(grace=2)
        else:
            # Non-blocking: return immediately, server runs in background
            pass

    def stop(self):
        if self._server:
            self._server.stop(grace=2)
            logger.info("%s stopped", self.name)

    def is_running(self) -> bool:
        return self._server is not None

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class DistributedLauncher:
    """Manages all four distributed PMTEC services.

    In single-process mode, all services share the same PMTECEngine
    instance but listen on separate ports. This enables:
      - Testing service isolation
      - Demonstrating the distributed architecture
      - Cross-service gRPC client calls via grpc_clients.py
    """

    def __init__(self, host: str = None):
        self.host = host or DISTRIBUTED_HOST
        self.engine = get_shared_engine()
        self._services: dict[str, _DistributedService] = {}
        self._started = False

    def _build_services(self):
        """Create service wrappers for all four DTB services."""
        engine = self.engine

        self._services["WarEngine"] = _DistributedService(
            "WarEngine",
            self.host,
            DISTRIBUTED_PORTS["WarEngine"],
            WarEngineServicer(engine),
            pb_grpc.add_WarEngineServicer_to_server,
        )
        self._services["BattleNetwork"] = _DistributedService(
            "BattleNetwork",
            self.host,
            DISTRIBUTED_PORTS["BattleNetwork"],
            BattleNetworkServicer(engine),
            pb_grpc.add_BattleNetworkServicer_to_server,
        )
        self._services["ApplicationStore"] = _DistributedService(
            "ApplicationStore",
            self.host,
            DISTRIBUTED_PORTS["ApplicationStore"],
            ApplicationStoreServicer(engine),
            pb_grpc.add_ApplicationStoreServicer_to_server,
        )
        self._services["PlugAndPlay"] = _DistributedService(
            "PlugAndPlay",
            self.host,
            DISTRIBUTED_PORTS["PlugAndPlay"],
            PlugAndPlayServicer(engine),
            pb_grpc.add_PlugAndPlayServicer_to_server,
        )

    def start_all(self):
        """Start all four services in background (non-blocking)."""
        if self._started:
            logger.warning("Services already started")
            return
        self._build_services()
        for svc in self._services.values():
            svc.start(blocking=False)
        self._started = True
        logger.info("All 4 services started:")
        for name, svc in self._services.items():
            logger.info("  %s -> %s", name, svc.address)

    def stop_all(self):
        """Stop all services."""
        for svc in self._services.values():
            svc.stop()
        self._started = False
        # Stop engine if running
        if self.engine._running:
            self.engine.stop_simulation()
        # Shutdown platform components
        if self.engine.plugin_manager:
            self.engine.plugin_manager.shutdown()
        if self.engine.rest_gateway:
            self.engine.rest_gateway.stop()
        if self.engine.realtime:
            self.engine.realtime.stop()
        logger.info("All services stopped")

    def start_simulation(
        self, scenario: str = "PMTEC-Pacific", duration: int = 300, seed: int = 42
    ):
        """Start the simulation on the shared engine."""
        return self.engine.start_simulation(scenario, duration, seed)

    def stop_simulation(self):
        return self.engine.stop_simulation()

    @property
    def addresses(self) -> dict:
        """Return dict of service_name -> address string."""
        return {name: svc.address for name, svc in self._services.items()}

    def __enter__(self):
        self.start_all()
        return self

    def __exit__(self, *args):
        self.stop_all()


def launch_all(host: str = None) -> DistributedLauncher:
    """Convenience: create, start, and return a DistributedLauncher."""
    launcher = DistributedLauncher(host)
    launcher.start_all()
    return launcher


# ---- Individual service entry points (blocking, for separate processes) ----


def run_war_engine(host: str = None):
    """Run only WarEngine service (blocking)."""
    engine = get_shared_engine()
    svc = _DistributedService(
        "WarEngine",
        host or DISTRIBUTED_HOST,
        DISTRIBUTED_PORTS["WarEngine"],
        WarEngineServicer(engine),
        pb_grpc.add_WarEngineServicer_to_server,
    )
    svc.start(blocking=True)


def run_battle_network(host: str = None):
    """Run only BattleNetwork service (blocking)."""
    engine = get_shared_engine()
    svc = _DistributedService(
        "BattleNetwork",
        host or DISTRIBUTED_HOST,
        DISTRIBUTED_PORTS["BattleNetwork"],
        BattleNetworkServicer(engine),
        pb_grpc.add_BattleNetworkServicer_to_server,
    )
    svc.start(blocking=True)


def run_application_store(host: str = None):
    """Run only ApplicationStore service (blocking)."""
    engine = get_shared_engine()
    svc = _DistributedService(
        "ApplicationStore",
        host or DISTRIBUTED_HOST,
        DISTRIBUTED_PORTS["ApplicationStore"],
        ApplicationStoreServicer(engine),
        pb_grpc.add_ApplicationStoreServicer_to_server,
    )
    svc.start(blocking=True)


def run_plug_and_play(host: str = None):
    """Run only PlugAndPlay service (blocking)."""
    engine = get_shared_engine()
    svc = _DistributedService(
        "PlugAndPlay",
        host or DISTRIBUTED_HOST,
        DISTRIBUTED_PORTS["PlugAndPlay"],
        PlugAndPlayServicer(engine),
        pb_grpc.add_PlugAndPlayServicer_to_server,
    )
    svc.start(blocking=True)


def main():
    """CLI entry point: python -m distributed.service_launcher [--service NAME] [--all]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PMTEC Distributed Service Launcher (P2-2)"
    )
    parser.add_argument(
        "--service",
        choices=["war_engine", "battle_network", "application_store", "plug_and_play"],
        help="Start a single service (blocking mode)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Start all 4 services in background threads, then run simulation",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Simulation duration in seconds (default: 300)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--host",
        default=DISTRIBUTED_HOST,
        help=f"Listen host (default: {DISTRIBUTED_HOST})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.all:
        # Start all services, run simulation, then stop
        launcher = DistributedLauncher(args.host)
        launcher.start_all()
        print()
        print("=" * 60)
        print("PMTEC Distributed Deployment (P2-2)")
        print("=" * 60)
        print("Services:")
        for name, addr in launcher.addresses.items():
            print(f"  {name:20s} -> {addr}")
        print()

        # Start simulation
        launcher.start_simulation("PMTEC-Pacific", args.duration, args.seed)
        print(f"Simulation started: {args.duration}s, seed={args.seed}")
        print()

        # Monitor
        while launcher.engine._running:
            state = launcher.engine.get_state_dict()
            print(
                f"  T+{state['sim_seconds']:6.0f}s | ASDA#{state['asda_cycle']} "
                f"{state['asda_phase']:8s} | Entities: {state['total_entities']:3d} "
                f"| Tracks: {state['active_tracks']:3d}"
            )
            if state["sim_seconds"] >= args.duration:
                break
            time.sleep(2)

        launcher.stop_simulation()
        launcher.stop_all()

        # Print summary
        report = launcher.engine.spear.generate_report()
        print()
        print(f"Total events: {report['total_events']}")
        print(f"ASDA cycles: {launcher.engine.asda_cycle_count}")
        for evt_type, count in sorted(report["event_distribution"].items()):
            print(f"  {evt_type:25s}: {count:4d}")

    elif args.service:
        svc_map = {
            "war_engine": run_war_engine,
            "battle_network": run_battle_network,
            "application_store": run_application_store,
            "plug_and_play": run_plug_and_play,
        }
        svc_map[args.service](args.host)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
