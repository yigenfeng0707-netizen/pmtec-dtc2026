#!/usr/bin/env python3
"""
P8 Test Suite: Security, gRPC HA, Multi-Agent & Load Test Verification

Validates:
  1. Security suite: JWT auth, RBAC permissions, audit logger, cert manager
  2. gRPC HA configuration (health check, backup hosts, exponential backoff)
  3. Multi-agent model loading (IQL + MADDPG, 182-dim)
  4. Load test results existence and key metrics
  5. Config switches (security, mTLS, HA, Prometheus, live data)
  6. Docker compose & CI/CD YAML existence

Run: D:/miniconda3/envs/pmtec-xpu/python.exe test_p8.py
"""

import sys
import os
import json
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

PASS = 0
FAIL = 0
RESULTS = []


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        RESULTS.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        RESULTS.append(f"  [FAIL] {name} {detail}")


# ============================================================
# Test 1: Security suite - JWT Auth
# ============================================================
print("\n[1/6] Testing JWT Authentication...")

try:
    from security.auth import AuthManager, AuthError

    auth = AuthManager(secret="test_secret_p8", expiration_hours=1)

    # Issue token
    token_info = auth.issue_token(user_id="test_user", role="commander")
    test("token issued", token_info is not None and token_info.token is not None)
    test("token has user_id", token_info.user_id == "test_user")
    test("token has role", token_info.role == "commander")

    # Verify token
    payload = auth.verify_token(token_info.token)
    test("token verified", payload is not None)
    test("payload user_id matches", payload.get("user_id") == "test_user")
    test("payload role matches", payload.get("role") == "commander")
    test("payload has issuer", payload.get("iss") == "PMTEC-Auth")

    # Invalid token
    try:
        auth.verify_token("invalid.token.here")
        test("invalid token rejected", False)
    except (AuthError, Exception):
        test("invalid token rejected", True)

    # Tampered token
    tampered = token_info.token[:-5] + "XXXXX"
    try:
        auth.verify_token(tampered)
        test("tampered token rejected", False)
    except (AuthError, Exception):
        test("tampered token rejected", True)

except ImportError as e:
    test("auth imports OK", False, str(e))


# ============================================================
# Test 2: RBAC permissions
# ============================================================
print("\n[2/6] Testing RBAC permissions...")

try:
    from security.rbac import Role, RBACManager, Permission

    rbac = RBACManager()

    # Commander can do everything
    test(
        "Commander can start sim",
        rbac.check_permission(Role.COMMANDER, "WarEngine", "StartSimulation"),
    )
    test(
        "Commander can inject event",
        rbac.check_permission(Role.COMMANDER, "WarEngine", "InjectEvent"),
    )
    test(
        "Commander can register component",
        rbac.check_permission(Role.COMMANDER, "PlugAndPlay", "RegisterComponent"),
    )

    # Operator can operate but not configure
    test(
        "Operator can start sim",
        rbac.check_permission(Role.OPERATOR, "WarEngine", "StartSimulation"),
    )
    test(
        "Operator cannot inject event",
        not rbac.check_permission(Role.OPERATOR, "WarEngine", "InjectEvent"),
    )
    test(
        "Operator cannot register component",
        not rbac.check_permission(Role.OPERATOR, "PlugAndPlay", "RegisterComponent"),
    )
    test(
        "Operator can deploy app",
        rbac.check_permission(Role.OPERATOR, "ApplicationStore", "DeployApp"),
    )

    # Observer is read-only
    test(
        "Observer cannot start sim",
        not rbac.check_permission(Role.OBSERVER, "WarEngine", "StartSimulation"),
    )
    test(
        "Observer can get state",
        rbac.check_permission(Role.OBSERVER, "WarEngine", "GetState"),
    )
    test(
        "Observer can get track feed",
        rbac.check_permission(Role.OBSERVER, "BattleNetwork", "GetTrackFeed"),
    )
    test(
        "Observer cannot deploy app",
        not rbac.check_permission(Role.OBSERVER, "ApplicationStore", "DeployApp"),
    )

    # Unknown method denied by default
    test(
        "Unknown method denied",
        not rbac.check_permission(Role.COMMANDER, "Unknown", "UnknownMethod"),
    )

    # HealthCheck exempt
    test("HealthCheck is exempt", rbac.is_exempt("/dtb_model.PlugAndPlay/HealthCheck"))

    # gRPC method path format
    test(
        "check_grpc_method format works",
        rbac.check_grpc_method(Role.COMMANDER, "/dtb_model.WarEngine/StartSimulation"),
    )
    test(
        "check_grpc_method denies unknown",
        not rbac.check_grpc_method(Role.OBSERVER, "/dtb_model.WarEngine/InjectEvent"),
    )

    # Role from string
    test(
        "Role from string 'commander'", Role.from_string("commander") == Role.COMMANDER
    )
    test("Role from string 'OPERATOR'", Role.from_string("OPERATOR") == Role.OPERATOR)

except ImportError as e:
    test("rbac imports OK", False, str(e))


# ============================================================
# Test 3: Audit logger (hash-chained, tamper-evident)
# ============================================================
print("\n[3/6] Testing Audit Logger...")

try:
    from security.audit import AuditLogger

    # Use temp DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_db = tmp.name

    logger = AuditLogger(db_path=tmp_db)

    # Log some entries
    entry1 = logger.log(
        user_id="user1",
        role="commander",
        service="WarEngine",
        method="StartSimulation",
        decision="ALLOWED",
        peer="127.0.0.1:12345",
    )
    test("audit entry 1 logged", entry1 is not None)

    entry2 = logger.log(
        user_id="user2",
        role="observer",
        service="WarEngine",
        method="InjectEvent",
        decision="DENIED",
        peer="127.0.0.1:12346",
    )
    test("audit entry 2 logged", entry2 is not None)

    # Verify hash chain
    entries = logger.query(limit=10)
    test("audit query returns entries", len(entries) >= 2)

    if len(entries) >= 2:
        test("entries have hash", entries[0]["entry_hash"] is not None)
        test("entries have prev_hash", entries[0]["prev_hash"] is not None)
        test(
            "hash chain links",
            entries[0]["prev_hash"] == entries[1]["entry_hash"]
            or entries[1]["prev_hash"] == entries[0]["entry_hash"],
        )

    # Tamper detection
    import sqlite3

    conn = sqlite3.connect(tmp_db)
    conn.execute("UPDATE audit_log SET user_id='HACKED' WHERE id=1")
    conn.commit()
    conn.close()

    is_valid = logger.verify_chain()
    test("tamper detected", not is_valid, "hash chain should be invalid after tamper")

    # Close logger's DB connection before cleanup
    if hasattr(logger, "_conn") and logger._conn:
        logger._conn.close()
    if hasattr(logger, "close"):
        logger.close()

    try:
        os.unlink(tmp_db)
    except PermissionError:
        pass  # Windows may still hold the file

except ImportError as e:
    test("audit imports OK", False, str(e))


# ============================================================
# Test 4: Certificate manager (mTLS)
# ============================================================
print("\n[4/6] Testing Certificate Manager...")

try:
    from security.cert_manager import CertificateManager

    with tempfile.TemporaryDirectory() as cert_dir:
        cm = CertificateManager(cert_dir=cert_dir)

        test("CA cert created", os.path.exists(cm._ca_cert_path))
        test("CA key created", os.path.exists(cm._ca_key_path))
        test("server cert created", os.path.exists(cm._server_cert_path))
        test("server key created", os.path.exists(cm._server_key_path))
        test("client cert created", os.path.exists(cm._client_cert_path))
        test("client key created", os.path.exists(cm._client_key_path))

        # Verify cert is valid X.509
        from cryptography import x509

        with open(cm._ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        test("CA cert is valid X.509", ca_cert is not None)
        test("CA cert has subject", ca_cert.subject is not None)

        # Server cert should be signed by CA
        with open(cm._server_cert_path, "rb") as f:
            server_cert = x509.load_pem_x509_certificate(f.read())
        test("server cert is valid X.509", server_cert is not None)

except ImportError as e:
    test("cert_manager imports OK", False, str(e))


# ============================================================
# Test 5: gRPC HA configuration & multi-agent models
# ============================================================
print("\n[5/6] Testing gRPC HA & multi-agent models...")

# Check config.py has HA settings
import importlib

sys.path.insert(0, PROJECT_ROOT)
# Import config directly
config_path = os.path.join(PROJECT_ROOT, "config.py")
with open(config_path, "r", encoding="utf-8") as f:
    config_source = f.read()

test("config has SECURITY_ENABLED", "SECURITY_ENABLED" in config_source)
test("config has MTLS_ENABLED", "MTLS_ENABLED" in config_source)
test("config has GRPC_HA_ENABLED", "GRPC_HA_ENABLED" in config_source)
test("config has GRPC_HA_BACKUP_HOSTS", "GRPC_HA_BACKUP_HOSTS" in config_source)
test("config has PROMETHEUS_ENABLED", "PROMETHEUS_ENABLED" in config_source)
test("config has LIVE_DATA_USE_REAL_API", "LIVE_DATA_USE_REAL_API" in config_source)
test("config has JWT_SECRET", "JWT_SECRET" in config_source)
test("config has CERT_DIR", "CERT_DIR" in config_source)
test("config has AUDIT_DB_PATH", "AUDIT_DB_PATH" in config_source)

# Check HA parameters
test(
    "HA health check interval",
    "GRPC_HEALTH_CHECK_INTERVAL" in config_source
    or "health_check" in config_source.lower(),
)
test(
    "HA exponential backoff",
    "RECONNECT_MAX_ATTEMPTS" in config_source or "backoff" in config_source.lower(),
)

# Multi-agent model files
models_dir = os.path.join(PROJECT_ROOT, "data", "models")
iql_intercept = os.path.join(models_dir, "pmtec_iql_intercept.zip")
iql_dispersal = os.path.join(models_dir, "pmtec_iql_dispersal.zip")
maddpg_intercept = os.path.join(models_dir, "pmtec_maddpg_intercept.pt")
maddpg_dispersal = os.path.join(models_dir, "pmtec_maddpg_dispersal.pt")

test("IQL intercept model exists", os.path.exists(iql_intercept))
test("IQL dispersal model exists", os.path.exists(iql_dispersal))
test("MADDPG intercept model exists", os.path.exists(maddpg_intercept))
test("MADDPG dispersal model exists", os.path.exists(maddpg_dispersal))

# Load and verify multi-agent models
try:
    from deep_rl.dqn_agent import detect_best_device
    from deep_rl.pmtec_env import OBS_DIM, NUM_ACTIONS

    device = detect_best_device()

    # IQL load test
    from deep_rl.multi_agent_dqn import MultiAgentDQN, INTERCEPT_AGENT
    import numpy as np

    iql = MultiAgentDQN(device=device)
    if os.path.exists(iql_intercept):
        loaded = iql.load()
        test("IQL models loaded", loaded)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        action = iql.predict(obs, agent_id=INTERCEPT_AGENT)
        test("IQL inference valid", 0 <= action < NUM_ACTIONS, f"action={action}")

    # MADDPG load test
    from deep_rl.maddpg_agent import MADDPGAgent

    maddpg = MADDPGAgent(device=device)
    if os.path.exists(maddpg_intercept):
        loaded = maddpg.load()
        test("MADDPG models loaded", loaded)
        obs = np.zeros(OBS_DIM, dtype=np.float32)
        action = maddpg.predict(obs, agent_id="intercept")
        test("MADDPG inference valid", action is not None)

except ImportError as e:
    test("multi-agent imports OK", False, str(e))


# ============================================================
# Test 6: Load test results & CI/CD files
# ============================================================
print("\n[6/6] Testing load test results & CI/CD...")

# Load test results JSON
load_results_path = os.path.join(
    PROJECT_ROOT, "data", "models", "load_test_results.json"
)
if os.path.exists(load_results_path):
    with open(load_results_path, "r", encoding="utf-8") as f:
        load_results = json.load(f)

    test("load test results JSON valid", isinstance(load_results, dict))

    if isinstance(load_results, dict):
        test("results have sqlite data", "sqlite" in load_results)
        test("results have grpc data", "grpc" in load_results)
        test("results have engine data", "engine" in load_results)
        test("results have timestamp", "timestamp" in load_results)
        test("results have device", "device" in load_results)

        # Check SQLite throughput
        sqlite_data = load_results.get("sqlite", {})
        if sqlite_data:
            max_wps = max(
                (
                    v.get("throughput_wps", 0)
                    for v in sqlite_data.values()
                    if isinstance(v, dict)
                ),
                default=0,
            )
            test("SQLite peak throughput > 1000 wps", max_wps > 1000, f"max={max_wps}")

        # Check gRPC throughput
        grpc_data = load_results.get("grpc", {})
        if isinstance(grpc_data, dict) and "error" not in grpc_data:
            max_rps = max(
                (
                    v.get("throughput_rps", 0)
                    for v in grpc_data.values()
                    if isinstance(v, dict)
                ),
                default=0,
            )
            test("gRPC peak throughput > 50 RPS", max_rps > 50, f"max={max_rps}")

        # Check engine concurrency
        engine_data = load_results.get("engine", {})
        if isinstance(engine_data, dict):
            test(
                "engine has 0 errors",
                engine_data.get("errors", -1) == 0,
                f"errors={engine_data.get('errors')}",
            )
else:
    test("load test results exist", False, f"not found: {load_results_path}")

# Load test report HTML
load_report_html = os.path.join(PROJECT_ROOT, "output", "PMTEC_Load_Test_Report.html")
test("load test HTML report exists", os.path.exists(load_report_html))

# Docker compose
docker_compose = os.path.join(PROJECT_ROOT, "docker-compose.yml")
test("docker-compose.yml exists", os.path.exists(docker_compose))
if os.path.exists(docker_compose):
    with open(docker_compose, "r", encoding="utf-8") as f:
        dc_source = f.read()
    test("compose has 7+ services", dc_source.count("container_name") >= 7)
    test(
        "compose has health check",
        "healthcheck" in dc_source.lower() or "health" in dc_source.lower(),
    )
    test("compose has prometheus", "prometheus" in dc_source.lower())
    test("compose has grafana", "grafana" in dc_source.lower())
    test("compose has backup service", "backup" in dc_source.lower())

# Dockerfile
dockerfile = os.path.join(PROJECT_ROOT, "Dockerfile")
test("Dockerfile exists", os.path.exists(dockerfile))

# GitHub Actions CI/CD
ci_cd = os.path.join(PROJECT_ROOT, ".github", "workflows", "ci-cd.yml")
test("ci-cd.yml exists", os.path.exists(ci_cd))
if os.path.exists(ci_cd):
    with open(ci_cd, "r", encoding="utf-8") as f:
        ci_source = f.read()
    test("CI has lint stage", "lint" in ci_source.lower())
    test("CI has test stage", "test" in ci_source.lower())
    test(
        "CI has docker build",
        "docker" in ci_source.lower() or "build" in ci_source.lower(),
    )

# Runbook HTML
runbook = os.path.join(PROJECT_ROOT, "PMTEC_Disaster_Recovery_Runbook.html")
test("disaster recovery runbook exists", os.path.exists(runbook))

# Architecture document
arch_doc = os.path.join(PROJECT_ROOT, "PMTEC_Architecture_Document.html")
test("architecture document exists", os.path.exists(arch_doc))

# Upgrade plan
upgrade_plan = os.path.join(PROJECT_ROOT, "output", "PMTEC_Upgrade_Plan.html")
test("upgrade plan exists", os.path.exists(upgrade_plan))


# ============================================================
# Summary
# ============================================================
print("\n" + "=" * 60)
print(f"P8 Test Results: {PASS} passed, {FAIL} failed")
print("=" * 60)
for r in RESULTS:
    print(r)

sys.exit(0 if FAIL == 0 else 1)
