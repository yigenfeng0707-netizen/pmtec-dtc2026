#!/usr/bin/env python3
"""
Distributed Tracing Integration - P8-v2 (ideal)

Implements OpenTelemetry-based distributed tracing for PMTEC gRPC services.
Provides end-to-end request visibility across: gRPC client -> server -> engine -> AI inference.

Architecture:
  - OpenTelemetry SDK instruments gRPC interceptors
  - Spans trace: StartSimulation -> ASDA cycles -> DQN inference -> SQLite write
  - Export to Jaeger (via OTLP) or stdout (for development)

Usage:
    from tracing import TracingManager

    tm = TracingManager(service_name="pmtec-war-engine", endpoint="localhost:4317")
    tm.setup()

    # In gRPC interceptor:
    with tm.tracer.start_as_current_span("dqn_inference") as span:
        span.set_attribute("obs_dim", 182)
        action = agent.predict(obs)

Dependencies (optional, gracefully degrades if not installed):
    pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
"""

import os

# ============================================================
# Configuration
# ============================================================

# Auto-enable tracing when opentelemetry is installed, unless explicitly disabled
# Set PMTEC_TRACING=0 to force-disable even when opentelemetry is available
_OTEL_AVAILABLE = False
try:
    import opentelemetry  # noqa: F401

    _OTEL_AVAILABLE = True
except ImportError:
    pass

TRACING_ENABLED = (
    os.environ.get("PMTEC_TRACING", "1" if _OTEL_AVAILABLE else "0") == "1"
)
TRACING_SERVICE_NAME = os.environ.get("PMTEC_TRACING_SERVICE", "pmtec-war-engine")
TRACING_OTLP_ENDPOINT = os.environ.get("PMTEC_TRACING_ENDPOINT", "localhost:4317")
TRACING_SAMPLE_RATE = float(os.environ.get("PMTEC_TRACING_SAMPLE_RATE", "0.1"))
TRACING_EXPORT_INTERVAL = int(os.environ.get("PMTEC_TRACING_EXPORT_INTERVAL", "5000"))


class TracingManager:
    """Manages OpenTelemetry tracing setup for PMTEC.

    Gracefully degrades: if opentelemetry is not installed, all operations
    become no-ops. This allows the codebase to reference tracing without
    hard dependency.
    """

    def __init__(
        self,
        service_name: str = TRACING_SERVICE_NAME,
        endpoint: str = TRACING_OTLP_ENDPOINT,
        sample_rate: float = TRACING_SAMPLE_RATE,
    ):
        self.service_name = service_name
        self.endpoint = endpoint
        self.sample_rate = sample_rate
        self._tracer = None
        self._provider = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        return TRACING_ENABLED and self._initialized

    @property
    def tracer(self):
        """Return active tracer or a no-op fallback."""
        if self.enabled and self._tracer:
            return self._tracer
        return _NoopTracer()

    def setup(self) -> bool:
        """Initialize OpenTelemetry SDK and exporter.

        Returns True if tracing is active, False if degraded to no-op.
        """
        if not TRACING_ENABLED:
            return False

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )
        except ImportError:
            print("[Tracing] opentelemetry not installed; tracing disabled (no-op)")
            return False

        # Resource identifies this service
        resource = Resource.create(
            {
                "service.name": self.service_name,
                "service.version": "P8-v2",
                "deployment.environment": os.environ.get("PMTEC_ENV", "development"),
            }
        )

        self._provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(self._provider)

        # Console exporter (always on for development)
        console_processor = BatchSpanProcessor(ConsoleSpanExporter())
        self._provider.add_span_processor(console_processor)

        # OTLP exporter (for Jaeger/Collector) - optional
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            otlp_processor = BatchSpanProcessor(
                OTLPSpanExporter(endpoint=self.endpoint, insecure=True)
            )
            self._provider.add_span_processor(otlp_processor)
            print(f"[Tracing] OTLP exporter configured: {self.endpoint}")
        except ImportError:
            print("[Tracing] OTLP exporter not available; using console only")

        self._tracer = trace.get_tracer(self.service_name)
        self._initialized = True
        print(
            f"[Tracing] Enabled: {self.service_name} (sample_rate={self.sample_rate})"
        )
        return True

    def shutdown(self):
        """Shutdown tracing, flush pending spans."""
        if self._provider:
            self._provider.shutdown()
            self._initialized = False

    # ============================================================
    # gRPC Interceptor with Tracing
    # ============================================================

    def create_grpc_server_interceptor(self):
        """Create a gRPC server interceptor that traces incoming requests.

        P12/S fix: previously returned GrpcInstrumentorServer() — an
        OpenTelemetry *instrumentor* (global patcher), not a grpc.
        ServerInterceptor — which made EVERY RPC fail with
        "Error in service handler!" when tracing was enabled.

        Now returns a real grpc.ServerInterceptor that creates one span per
        unary-unary RPC. Defensive by design: tracing failures never break
        RPCs.

        Usage in grpc_server.py:
            tm = TracingManager()
            tm.setup()
            server_interceptor = tm.create_grpc_server_interceptor()
            server = grpc.server(
                executor,
                interceptors=[server_interceptor, ...],
            )
        """
        if not self.enabled:
            return None

        return _TracingServerInterceptor(self.tracer)

    def create_grpc_client_interceptor(self):
        """Create a gRPC client interceptor for outgoing calls."""
        if not self.enabled:
            return None

        from opentelemetry.instrumentation.grpc import (
            GrpcInstrumentorClient,
        )

        return GrpcInstrumentorClient()

    # ============================================================
    # Convenience Span Creators
    # ============================================================

    def trace_asda_cycle(self, cycle_num: int):
        """Create a span for an ASDA simulation cycle."""
        span = self.tracer.start_span(f"asda_cycle_{cycle_num}")
        span.set_attribute("simulation.cycle", cycle_num)
        return span

    def trace_dqn_inference(self, obs_dim: int, action: int = None):
        """Create a span for DQN inference."""
        span = self.tracer.start_span("dqn_inference")
        span.set_attribute("model.obs_dim", obs_dim)
        if action is not None:
            span.set_attribute("model.action", action)
        return span

    def trace_intercept_attempt(self, threat_type: str, success: bool):
        """Create a span for a missile intercept attempt."""
        span = self.tracer.start_span("intercept_attempt")
        span.set_attribute("threat.type", threat_type)
        span.set_attribute("intercept.success", success)
        return span


class _TracingServerInterceptor:
    """P12/S: real gRPC server interceptor creating a span per unary RPC.

    Defensive by design: tracing failures must never break RPCs. If span
    creation itself raises, the handler runs uninstrumented.
    """

    def __init__(self, tracer):
        import grpc

        self._grpc = grpc
        self._tracer = tracer

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None:
            return handler
        # Only unary-unary handlers are wrapped; streaming RPCs pass through
        if handler.request_streaming or handler.response_streaming:
            return handler

        inner = handler.unary_unary
        method = handler_call_details.method or "unknown"
        name = "grpc." + method.rsplit("/", 1)[-1]
        grpc_mod = self._grpc

        def wrapped(request, context):
            cm = None
            try:
                cm = self._tracer.start_as_current_span(name)
                cm.__enter__()
            except Exception:
                cm = None  # tracing unavailable -> run uninstrumented
            try:
                return inner(request, context)
            finally:
                if cm is not None:
                    try:
                        cm.__exit__(None, None, None)
                    except Exception:
                        pass

        return grpc_mod.unary_unary_rpc_method_handler(
            wrapped,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )


class _NoopSpan:
    """No-op span for when tracing is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, key, value):
        pass

    def add_event(self, name, attributes=None):
        pass

    def record_exception(self, exception):
        pass

    def set_status(self, status):
        pass


class _NoopTracer:
    """No-op tracer for when tracing is disabled."""

    def start_span(self, name):
        return _NoopSpan()

    def start_as_current_span(self, name):
        return _NoopSpan()


# ============================================================
# Integration Guide (printed when run as script)
# ============================================================

INTEGRATION_GUIDE = """
============================================================
PMTEC Distributed Tracing Integration Guide
============================================================

1. INSTALL DEPENDENCIES
   pip install opentelemetry-api opentelemetry-sdk \\
       opentelemetry-exporter-otlp \\
       opentelemetry-instrumentation-grpc

2. START JAEGER (Docker)
   docker run -d --name jaeger \\
     -p 4317:4317 -p 16686:16686 \\
     jaegertracing/all-in-one:latest

3. ENABLE TRACING
   export PMTEC_TRACING=1
   export PMTEC_TRACING_ENDPOINT=localhost:4317
   export PMTEC_TRACING_SAMPLE_RATE=0.1

4. ADD TO docker-compose.yml
   jaeger:
     image: jaegertracing/all-in-one:latest
     ports:
       - "4317:4317"  # OTLP gRPC
       - "16686:16686"  # UI
     networks: [pmtec-net]

5. INSTRUMENT CODE
   from tracing import TracingManager

   tm = TracingManager(service_name="pmtec-war-engine")
   tm.setup()

   # In gRPC server:
   interceptor = tm.create_grpc_server_interceptor()
   # Add to grpc.server(interceptors=[interceptor])

   # In business logic:
   with tm.tracer.start_as_current_span("asda_cycle") as span:
       span.set_attribute("cycle", cycle_num)
       # ... ASDA logic ...

6. VIEW TRACES
   Open http://localhost:16686
   Select service: pmtec-war-engine

TRACE FLOW:
  gRPC Client -> [client interceptor] ->
  gRPC Server -> [server interceptor] ->
  PMTECEngine.start_simulation ->
    ASDA Cycle -> [span]
      Act -> [span]
      Sense -> [span]
      Decide -> [span]
        DQN Inference -> [span]
        IQL/MADDPG -> [span]
      Adapt -> [span]
        SQLite Write -> [span]

============================================================
"""


if __name__ == "__main__":
    print(INTEGRATION_GUIDE)

    # Demo: show tracing works (or degrades gracefully)
    tm = TracingManager(service_name="pmtec-demo")
    if tm.setup():
        print("\n[Demo] Tracing active! Creating test spans...")
        with tm.tracer.start_as_current_span("demo_span") as span:
            span.set_attribute("test", True)
            with tm.tracer.start_as_current_span("child_span") as child:
                child.set_attribute("nested", True)
        print("[Demo] Spans exported. Check Jaeger UI.")
    else:
        print("\n[Demo] Tracing not active (degraded to no-op).")
        print("[Demo] Set PMTEC_TRACING=1 and install opentelemetry to enable.")
