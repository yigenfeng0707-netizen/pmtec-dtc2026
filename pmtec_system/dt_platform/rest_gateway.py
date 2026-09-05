"""REST API Gateway - P1-2: HTTP interface for the PMTEC digital twin.

Provides a RESTful HTTP layer over the gRPC services, enabling:
- Web-based access to simulation state and control
- Standardized API for external integrations
- Swagger-style endpoint documentation
- CORS support for browser-based dashboards

Endpoints:
  GET  /api/v1/state          - Current simulation state
  POST /api/v1/sim/start      - Start simulation
  POST /api/v1/sim/stop       - Stop simulation
  GET  /api/v1/spear/report   - SPEAR replay report
  GET  /api/v1/bases          - List all bases
  GET  /api/v1/entities       - List active entities
  GET  /api/v1/tracks         - List active tracks
  GET  /api/v1/plugins        - List registered plugins
  GET  /api/v1/dt/instances   - List digital twin instances
  POST /api/v1/dt/register    - Register a new DT instance
  GET  /api/v1/health         - Platform health check
"""

import json
import time
import threading
import logging
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("pmtec.rest")


class RestGateway:
    """REST API gateway wrapping PMTEC gRPC services.

    Uses Python stdlib http.server - no external dependencies.
    Designed for lightweight deployment on Windows + Intel Arc.
    """

    def __init__(
        self, engine=None, plugin_manager=None, dt_registry=None, port: int = 8080
    ):
        self.engine = engine
        self.plugin_manager = plugin_manager
        self.dt_registry = dt_registry
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def attach_engine(self, engine):
        self.engine = engine

    def attach_plugins(self, pm):
        self.plugin_manager = pm

    def attach_registry(self, reg):
        self.dt_registry = reg

    def start(self):
        """Start the REST API server in a background thread."""
        if self._server:
            return True

        gateway = self

        class RequestHandler(BaseHTTPRequestHandler):
            def _send_json(self, code: int, data):
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):
                self._send_json(200, {"status": "ok"})

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                qs = parse_qs(parsed.query)

                if path == "/api/v1/health":
                    self._send_json(
                        200,
                        {
                            "status": "healthy",
                            "version": "PMTEC-v2.0",
                            "uptime_s": int(time.time()),
                            "services": [
                                "WarEngine",
                                "BattleNetwork",
                                "ApplicationStore",
                                "PlugAndPlay",
                            ],
                        },
                    )
                elif path == "/api/v1/state":
                    if gateway.engine:
                        self._send_json(200, gateway.engine.get_state_dict())
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/spear/report":
                    if gateway.engine:
                        report = gateway.engine.spear.generate_report()
                        self._send_json(200, report)
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/bases":
                    if gateway.engine:
                        self._send_json(200, gateway.engine._bases)
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/entities":
                    if gateway.engine:
                        active = [
                            e.to_dict()
                            for e in gateway.engine._entities
                            if e.status == "active"
                        ]
                        self._send_json(200, {"count": len(active), "entities": active})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/tracks":
                    if gateway.engine:
                        tracks = [
                            t.to_dict() for t in gateway.engine.track_mgr.active_tracks
                        ]
                        self._send_json(200, {"count": len(tracks), "tracks": tracks})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/plugins":
                    if gateway.plugin_manager:
                        self._send_json(200, gateway.plugin_manager.list_plugins())
                    else:
                        self._send_json(200, [])
                elif path == "/api/v1/dt/instances":
                    if gateway.dt_registry:
                        self._send_json(200, gateway.dt_registry.list_instances())
                    else:
                        self._send_json(200, [])
                elif path == "/api/v1/threat-summary":
                    if gateway.plugin_manager:
                        mt = gateway.plugin_manager.get_plugin("builtin-multi-threat")
                        if mt:
                            summary = mt.call("get_threat_summary")
                            self._send_json(200, summary or {})
                        else:
                            self._send_json(200, {})
                    else:
                        self._send_json(200, {})
                elif path == "/" or path == "/api":
                    self._send_json(
                        200,
                        {
                            "name": "PMTEC Digital Twin Platform",
                            "version": "2.0",
                            "endpoints": [
                                "GET /api/v1/health",
                                "GET /api/v1/state",
                                "POST /api/v1/sim/start",
                                "POST /api/v1/sim/stop",
                                "GET /api/v1/spear/report",
                                "GET /api/v1/bases",
                                "GET /api/v1/entities",
                                "GET /api/v1/tracks",
                                "GET /api/v1/plugins",
                                "GET /api/v1/dt/instances",
                                "POST /api/v1/dt/register",
                                "GET /api/v1/threat-summary",
                            ],
                        },
                    )
                else:
                    self._send_json(404, {"error": "Not found", "path": path})

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                try:
                    payload = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON"})
                    return

                if path == "/api/v1/sim/start":
                    if gateway.engine:
                        scenario = payload.get("scenario", "PMTEC-Pacific")
                        duration = payload.get("duration", 1200)
                        seed = payload.get("seed", 42)
                        ok, msg = gateway.engine.start_simulation(
                            scenario, duration, seed
                        )
                        self._send_json(
                            200 if ok else 400, {"success": ok, "message": msg}
                        )
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/sim/stop":
                    if gateway.engine:
                        ok, msg = gateway.engine.stop_simulation()
                        self._send_json(200, {"success": ok, "message": msg})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/dt/register":
                    if gateway.dt_registry:
                        instance = gateway.dt_registry.register(payload)
                        self._send_json(201, instance)
                    else:
                        self._send_json(503, {"error": "Registry not attached"})
                else:
                    self._send_json(404, {"error": "Not found", "path": path})

            def log_message(self, format, *args):
                logger.debug(f"REST {self.address_string()} - {format % args}")

        self._server = HTTPServer(("0.0.0.0", self.port), RequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"REST API server started on port {self.port}")
        return True

    def stop(self):
        """Stop the REST API server."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("REST API server stopped")
