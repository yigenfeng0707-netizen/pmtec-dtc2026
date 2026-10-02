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
  GET  /api/v1/analysis       - Last cached AI situational analysis (P13)
  POST /api/v1/analysis       - Trigger fresh AI situational analysis (P13)
  GET  /api/v1/health         - Platform health check
  POST /api/v1/auth/login     - Web 展示层登录（PMTEC_WEB_USERS 启用时生效）
  GET  /api/v1/auth/check     - 会话校验（兼作 nginx auth_request 门禁端点）
  POST /api/v1/auth/logout    - 退出并清除会话 Cookie
"""

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("pmtec.rest")

# 网关进程启动时刻（/api/v1/health uptime 基准）
_GATEWAY_BOOT_AT = time.time()

# Web 展示层认证：部署侧经环境变量 PMTEC_WEB_USERS 启用，缺省关闭（既有测试/本地开发零影响）。
# 条目格式 "用户名:sha256(密码)hex:角色"，逗号分隔；角色 ∈ {observer, operator, commander}。
WEB_AUTH_COOKIE = "pmtec_token"
WEB_AUTH_PUBLIC_PATHS = {
    "/",
    "/api",
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/check",
}
WEB_ROLE_RANK = {"observer": 0, "operator": 1, "commander": 2}
# 评委(operator)可触发 AI 参谋官分析；其余 POST（仿真启停 / 实例注册）仅指挥员(commander)
WEB_POST_MIN_ROLE = {"/api/v1/analysis": "operator"}


def parse_web_users(raw: str) -> dict:
    """解析 PMTEC_WEB_USERS → {用户名: (sha256摘要, 角色)}；格式非法条目跳过。"""
    users = {}
    for entry in (raw or "").split(","):
        parts = entry.strip().split(":")
        if len(parts) != 3:
            continue
        username, digest, role = parts
        if not username or len(digest) != 64 or role not in WEB_ROLE_RANK:
            continue
        users[username] = (digest.lower(), role)
    return users


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
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._web_users = parse_web_users(os.environ.get("PMTEC_WEB_USERS", ""))
        self._auth_manager = None

    # ---------------- Web 展示层认证（P7 安全模块端到端落地） ----------------

    @property
    def auth_enabled(self) -> bool:
        return bool(self._web_users)

    def _get_auth_manager(self):
        if self._auth_manager is None:
            from security.auth import AuthManager

            self._auth_manager = AuthManager(
                secret=os.environ.get("PMTEC_JWT_SECRET") or None
            )
        return self._auth_manager

    def login_user(self, username: str, password: str):
        """校验 PMTEC_WEB_USERS 凭据，成功返回 TokenInfo，失败返回 None。"""
        entry = self._web_users.get(username or "")
        if not entry or not password:
            return None
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(digest, entry[0]):
            return None
        return self._get_auth_manager().issue_token(username, entry[1])

    def verify_request(self, headers) -> dict | None:
        """从 Authorization 头或 Cookie 提取并校验 JWT，返回 payload 或 None。"""
        token = headers.get("Authorization") or ""
        if not token.strip():
            for part in (headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == WEB_AUTH_COOKIE:
                    token = value
                    break
        if not token.strip():
            return None
        from security.auth import AuthError

        try:
            return self._get_auth_manager().verify_token(token)
        except AuthError:
            return None

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
            def _send_json(self, code: int, data, extra_headers=None):
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers", "Content-Type, Authorization"
                )
                for name, value in extra_headers or []:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _auth_cookie(self, token: str, max_age: int) -> str:
                return (
                    f"{WEB_AUTH_COOKIE}={token}; HttpOnly; SameSite=Strict; "
                    f"Path=/; Max-Age={max_age}"
                )

            def _web_auth_gate(self, path: str, method: str) -> bool:
                """认证门禁：未启用直接放行；返回 False 表示已应答（401/403）。"""
                if not gateway.auth_enabled:
                    return True
                if path in WEB_AUTH_PUBLIC_PATHS:
                    return True
                payload = gateway.verify_request(self.headers)
                if payload is None:
                    self._send_json(
                        401,
                        {
                            "error": "Unauthorized",
                            "hint": "POST /api/v1/auth/login",
                        },
                    )
                    return False
                if method == "POST":
                    required = WEB_POST_MIN_ROLE.get(path, "commander")
                    role = payload.get("role", "observer")
                    if WEB_ROLE_RANK.get(role, -1) < WEB_ROLE_RANK[required]:
                        self._send_json(
                            403,
                            {
                                "error": "Forbidden",
                                "role": role,
                                "required_role": required,
                                "user_id": payload.get("user_id"),
                            },
                        )
                        return False
                return True

            def do_OPTIONS(self):
                self._send_json(200, {"status": "ok"})

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                parse_qs(parsed.query)

                if not self._web_auth_gate(path, "GET"):
                    return

                if path == "/api/v1/auth/check":
                    payload = gateway.verify_request(self.headers)
                    if payload is None:
                        self._send_json(401, {"error": "Unauthorized"})
                    else:
                        self._send_json(
                            200,
                            {
                                "user_id": payload.get("user_id"),
                                "role": payload.get("role"),
                                "exp": payload.get("exp"),
                            },
                        )
                elif path == "/api/v1/health":
                    self._send_json(
                        200,
                        {
                            "status": "healthy",
                            "version": "PMTEC-v2.0",
                            "uptime_s": int(time.time() - _GATEWAY_BOOT_AT),
                            "auth_enabled": gateway.auth_enabled,
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
                # ---------------- P13: LLM AI situational analysis ----------------
                elif path == "/api/v1/analysis/download":
                    cached = (
                        getattr(gateway.engine, "_ai_analysis", None)
                        if gateway.engine
                        else None
                    )
                    docx_path = (cached or {}).get("docx_path")
                    if docx_path and os.path.exists(docx_path):
                        with open(docx_path, "rb") as f:
                            body = f.read()
                        self.send_response(200)
                        self.send_header(
                            "Content-Type",
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document",
                        )
                        self.send_header(
                            "Content-Disposition",
                            'attachment; filename="PMTEC_AI_situation_analysis.docx"',
                        )
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    else:
                        self._send_json(404, {"error": "docx not generated yet"})
                elif path == "/api/v1/analysis":
                    if gateway.engine:
                        cached = getattr(gateway.engine, "_ai_analysis", None)
                        if cached:
                            self._send_json(200, cached)
                        else:
                            self._send_json(
                                200,
                                {
                                    "status": "not_generated",
                                    "hint": "POST /api/v1/analysis to generate now",
                                },
                            )
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/dt/instances":
                    if gateway.dt_registry:
                        self._send_json(200, gateway.dt_registry.list_instances())
                    else:
                        self._send_json(200, [])
                elif path == "/api/v1/dt/sync":
                    # P13: digital twin sync layer status
                    if gateway.engine and getattr(
                        gateway.engine, "twin_sync", None
                    ):
                        self._send_json(
                            200,
                            {
                                "summary": gateway.engine.twin_sync.summary(),
                                "top_twins": gateway.engine.twin_sync.top_twins(
                                    limit=8
                                ),
                            },
                        )
                    else:
                        self._send_json(200, {"summary": None, "top_twins": []})
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
                # ---------------- P12-6: Maven 接口补全四大服务 ----------------
                # dtb-war-engine (com.dtc2026.dtb.war : 50051)
                elif path == "/api/v1/war/ew-threats":
                    if gateway.engine:
                        ew = [
                            e.to_dict()
                            for e in gateway.engine._entities
                            if "ew" in getattr(e, "entity_type", "").lower()
                        ]
                        self._send_json(200, {"count": len(ew), "threats": ew})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/war/cyber-threats":
                    if gateway.engine:
                        cyb = [
                            e.to_dict()
                            for e in gateway.engine._entities
                            if "cyber" in getattr(e, "entity_type", "").lower()
                        ]
                        self._send_json(200, {"count": len(cyb), "threats": cyb})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                # dtb-battle-network (com.dtc2026.dtb.battle : 50052)
                elif path == "/api/v1/network/lvc-status":
                    if gateway.engine:
                        lvc = getattr(gateway.engine, "lvc", None)
                        layers = {}
                        if lvc:
                            for name in ("live", "virtual", "constructive"):
                                layer = getattr(lvc, name, None)
                                if layer is not None and hasattr(layer, "to_dict"):
                                    layers[name] = layer.to_dict()
                        self._send_json(200, {"lvc": layers})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                elif path == "/api/v1/political/access":
                    # P10: 政治准入态势（盟友站点三态 + 升级度 + MRF-D）
                    if gateway.engine and getattr(gateway.engine, "political", None):
                        self._send_json(200, gateway.engine.political.snapshot())
                    else:
                        self._send_json(200, {"political_access": None})
                elif path == "/api/v1/c2/chain":
                    # P11: INDOPACOM 指挥链态势（组织架构 + 消息流）
                    if gateway.engine and getattr(gateway.engine, "c2", None):
                        c2 = gateway.engine.c2
                        self._send_json(
                            200,
                            {
                                "nodes": sorted(c2.nodes.keys()),
                                "messages": len(getattr(c2, "messages", [])),
                            },
                        )
                    else:
                        self._send_json(200, {"c2": None})
                # dtb-application-store (com.dtc2026.dtb.app : 50053)
                elif path == "/api/v1/app/dqn/status":
                    if gateway.engine and getattr(gateway.engine, "dqn", None):
                        self._send_json(200, gateway.engine.dqn.get_statistics())
                    else:
                        self._send_json(200, {"active": False})
                # dtb-plug-and-play (com.dtc2026.dtb.pnp : 50054)
                elif path == "/api/v1/pnp/health":
                    self._send_json(
                        200,
                        {
                            "service": "PlugAndPlay",
                            "healthy": True,
                            "plugins": (
                                len(gateway.plugin_manager.list_plugins())
                                if gateway.plugin_manager
                                else 0
                            ),
                        },
                    )
                elif path == "/api/v1/maven/services":
                    # 四大服务 Maven 契约总览（映射 deploy_config.maven_modules）
                    self._send_json(
                        200,
                        {
                            "contract": "com.dtc2026.dtb",
                            "services": [
                                {
                                    "module": "dtb-war-engine",
                                    "package": "com.dtc2026.dtb.war",
                                    "grpc_port": 50051,
                                    "rest": [
                                        "/api/v1/state",
                                        "/api/v1/war/ew-threats",
                                        "/api/v1/war/cyber-threats",
                                        "/api/v1/spear/report",
                                    ],
                                },
                                {
                                    "module": "dtb-battle-network",
                                    "package": "com.dtc2026.dtb.battle",
                                    "grpc_port": 50052,
                                    "rest": [
                                        "/api/v1/entities",
                                        "/api/v1/tracks",
                                        "/api/v1/network/lvc-status",
                                    ],
                                },
                                {
                                    "module": "dtb-application-store",
                                    "package": "com.dtc2026.dtb.app",
                                    "grpc_port": 50053,
                                    "rest": [
                                        "/api/v1/app/dqn/status",
                                        "/api/v1/threat-summary",
                                    ],
                                },
                                {
                                    "module": "dtb-plug-and-play",
                                    "package": "com.dtc2026.dtb.pnp",
                                    "grpc_port": 50054,
                                    "rest": [
                                        "/api/v1/plugins",
                                        "/api/v1/pnp/health",
                                        "/api/v1/dt/instances",
                                    ],
                                },
                                {
                                    "module": "dtb-political-c2 (P10/P11)",
                                    "package": "com.dtc2026.dtb.c2",
                                    "grpc_port": None,
                                    "rest": [
                                        "/api/v1/political/access",
                                        "/api/v1/c2/chain",
                                    ],
                                },
                            ],
                        },
                    )
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
                                "GET /api/v1/war/ew-threats",
                                "GET /api/v1/war/cyber-threats",
                                "GET /api/v1/network/lvc-status",
                                "GET /api/v1/app/dqn/status",
                                "GET /api/v1/pnp/health",
                                "GET /api/v1/political/access",
                                "GET /api/v1/c2/chain",
                                "GET /api/v1/maven/services",
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

                if not self._web_auth_gate(path, "POST"):
                    return

                if path == "/api/v1/auth/login":
                    info = gateway.login_user(
                        str(payload.get("username", "")),
                        str(payload.get("password", "")),
                    )
                    if info is None:
                        self._send_json(401, {"error": "Invalid credentials"})
                        return
                    self._send_json(
                        200,
                        {
                            "user_id": info.user_id,
                            "role": info.role,
                            "expires_at": info.expires_at,
                            "token": info.token,
                        },
                        extra_headers=[
                            ("Set-Cookie", self._auth_cookie(info.token, 86400))
                        ],
                    )
                elif path == "/api/v1/auth/logout":
                    self._send_json(
                        200,
                        {"status": "logged_out"},
                        extra_headers=[
                            (
                                "Set-Cookie",
                                f"{WEB_AUTH_COOKIE}=; HttpOnly; SameSite=Strict; "
                                "Path=/; Max-Age=0",
                            )
                        ],
                    )
                elif path == "/api/v1/sim/start":
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
                # ---------------- P13: LLM AI situational analysis ----------------
                elif path == "/api/v1/analysis":
                    if gateway.engine:
                        try:
                            from services.llm_analyst import LLMAnalyst

                            analyst = LLMAnalyst()
                            if not analyst.enabled:
                                self._send_json(
                                    503, {"error": "LLM analyst disabled (no API key)"}
                                )
                                return
                            result = analyst.generate_report_files(
                                gateway.engine.get_state_dict(),
                                gateway.engine.spear.generate_report(),
                                gateway.engine.spear.events[-500:],
                            )
                            if result:
                                cached = {
                                    "status": "generated",
                                    "model": analyst.model,
                                    "generated_at": time.strftime(
                                        "%Y-%m-%d %H:%M:%S"
                                    ),
                                    "md_path": result["md_path"],
                                    "html_path": result["html_path"],
                                    "docx_path": result.get("docx_path"),
                                    "markdown": result["markdown"],
                                    "usage": analyst.last_usage,
                                }
                                gateway.engine._ai_analysis = cached
                                self._send_json(200, cached)
                            else:
                                self._send_json(
                                    502, {"error": "LLM API call failed"}
                                )
                        except Exception as exc:
                            self._send_json(500, {"error": str(exc)})
                    else:
                        self._send_json(503, {"error": "Engine not attached"})
                else:
                    self._send_json(404, {"error": "Not found", "path": path})

            def log_message(self, format, *args):
                logger.debug(f"REST {self.address_string()} - {format % args}")

        # P13-fix: ThreadingHTTPServer so long LLM calls (POST /analysis)
        # don't block other concurrent requests.
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), RequestHandler)
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
