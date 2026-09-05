"""PMTEC System Configuration - DTC 2026 Level 3."""

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PROTO_DIR = os.path.join(PROJECT_ROOT, "proto")
GENERATED_DIR = os.path.join(PROTO_DIR, "generated")
BASES_GEOJSON = os.path.join(DATA_DIR, "bases.geojson")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# gRPC server
GRPC_HOST = "localhost"
GRPC_PORT = 50051

# Simulation parameters
SIM_TICK_SECONDS = 1.0  # simulation time step
SIM_REALTIME_RATIO = 1.0  # 1.0 = real-time, 10.0 = 10x speed
SIM_DURATION_SECONDS = 1200  # 20 minutes default scenario
SIM_RANDOM_SEED = 42

# LVC architecture
LVC_LIVE_ENABLED = True  # real-world data feeds
LVC_VIRTUAL_ENABLED = True  # computer-generated forces
LVC_CONSTRUCTIVE_ENABLED = True  # aggregate-level command sim

# SPEAR replay
SPEAR_BUFFER_SIZE = 10000  # max events in replay buffer

# ASDA loop
ASDA_CYCLE_SECONDS = 10

# Track management
TRACK_FUSION_INTERVAL_S = 5
TRACK_MAX_AGE_S = 60
TRACK_MIN_CONFIDENCE = 0.3

# Entity parameters (reuse from Level 2)
AIRCRAFT_SPEED_KMH = {
    "F-35A": 1670,
    "F-22A": 2414,
    "F-15C": 2655,
    "F-15E": 2655,
    "F-16C": 2120,
    "KC-135": 870,
    "KC-46": 870,
    "E-3": 852,
    "RC-135": 980,
}
COMBAT_RADIUS_KM = {
    "F-35A": 1100,
    "F-22A": 850,
    "F-15C": 1600,
    "F-15E": 1600,
    "F-16C": 900,
    "KC-135": 2400,
    "KC-46": 1100,
    "E-3": 1850,
    "RC-135": 4000,
}
AIRCRAFT_VALUE = {
    "F-35A": 100,
    "F-22A": 90,
    "F-15C": 60,
    "F-15E": 70,
    "F-16C": 40,
    "KC-135": 80,
    "KC-46": 85,
    "E-3": 95,
    "RC-135": 85,
}
THREAT_SPEED_KMH = {
    "DF-21D": 6000,
    "DF-26": 8000,
    "DF-17": 7000,
    "KH-101": 800,
    "CJ-10": 800,
}
THREAT_CEP_M = {
    "DF-21D": 50,
    "DF-26": 150,
    "DF-17": 30,
    "KH-101": 20,
    "CJ-10": 30,
}
THREAT_WARHEAD_KG = {
    "DF-21D": 1000,
    "DF-26": 1500,
    "DF-17": 800,
    "KH-101": 450,
    "CJ-10": 500,
}

EARTH_RADIUS_KM = 6371.0

# P1-3: Electronic Warfare (EW) threat parameters
EW_JAMMER_POWER_KW = {
    "KGJ-500": 150,  # Chinese airborne jamming pod
    "KN-200": 80,  # Naval EW system
    "IL-22PP": 200,  # Russian ELINT/jammer aircraft
}
EW_JAM_RANGE_KM = {
    "KGJ-500": 250,
    "KN-200": 150,
    "IL-22PP": 400,
}
EW_BANDS = ["S", "X", "Ku", "Ka"]  # radar bands that can be jammed

# P1-3: Cyber attack threat parameters
CYBER_ATTACK_TYPES = {
    "APT-intrusion": {
        "target": "C2_network",
        "detection_difficulty": 0.8,
        "impact_severity": 0.7,
        "duration_s": 60,
    },
    "GPS-spoofing": {
        "target": "navigation",
        "detection_difficulty": 0.9,
        "impact_severity": 0.5,
        "duration_s": 45,
    },
    "comms-jamming": {
        "target": "datalink",
        "detection_difficulty": 0.6,
        "impact_severity": 0.8,
        "duration_s": 30,
    },
    "supply-chain": {
        "target": "logistics",
        "detection_difficulty": 0.95,
        "impact_severity": 0.9,
        "duration_s": 90,
    },
}

# P1-2: Digital Twin Platform configuration
PLATFORM_REST_PORT = 8080
PLATFORM_PLUGIN_DIR = os.path.join(DATA_DIR, "plugins")
PLATFORM_API_VERSION = "v1"

# P2-2: Distributed deployment - each service on its own port
# P4-2: Docker support - PMTEC_HOST env var overrides for containers
DISTRIBUTED_PORTS = {
    "WarEngine": 50051,
    "BattleNetwork": 50052,
    "ApplicationStore": 50053,
    "PlugAndPlay": 50054,
}
DISTRIBUTED_HOST = os.environ.get("PMTEC_HOST", "localhost")

# DTB Model mapping
DTB_COMPONENTS = {
    "WarEngine": "PMTEC simulation core - drives LVC time-space coordination",
    "BattleNetwork": "gRPC track distribution + entity status broadcast",
    "ApplicationStore": "Capability modules (F-35 strike, IAMD defense, ISR collection)",
    "PlugAndPlay": "Dynamic component registration via gRPC service discovery",
}

ASDA_PHASES = ["Act", "Sense", "Decide", "Adapt"]

# P1-3: Threat classification taxonomy
THREAT_TAXONOMY = {
    "kinetic": ["DF-21D", "DF-26", "DF-17", "KH-101", "CJ-10"],
    "electronic": list(EW_JAMMER_POWER_KW.keys()),
    "cyber": list(CYBER_ATTACK_TYPES.keys()),
}

# ============================================================
# P7: Security & Authentication Configuration
# ============================================================
SECURITY_ENABLED = os.environ.get("PMTEC_SECURITY", "1") == "1"
MTLS_ENABLED = os.environ.get("PMTEC_MTLS", "1") == "1"
JWT_EXPIRATION_HOURS = int(os.environ.get("PMTEC_JWT_HOURS", "24"))
JWT_SECRET = os.environ.get("PMTEC_JWT_SECRET")  # auto-generated if None
CERT_DIR = os.path.join(DATA_DIR, "certs")
AUDIT_DB_PATH = os.path.join(DATA_DIR, "persistence", "audit_log.db")

# ============================================================
# P8-v2: gRPC Thread Pool Configuration
# ============================================================
GRPC_MAX_WORKERS = int(os.environ.get("PMTEC_GRPC_WORKERS", "64"))
GRPC_MAX_CONCURRENT_RPCS = int(os.environ.get("PMTEC_GRPC_MAX_CONCURRENT", "128"))

# ============================================================
# P7-v2: gRPC High Availability Configuration
# ============================================================
GRPC_HA_ENABLED = os.environ.get("PMTEC_HA", "1") == "1"
GRPC_HA_BACKUP_HOSTS = [
    h.strip() for h in os.environ.get("PMTEC_HA_BACKUPS", "").split(",") if h.strip()
]  # e.g. "backup1:50051,backup2:50051"
GRPC_HEALTH_CHECK_INTERVAL_S = int(os.environ.get("PMTEC_HEALTH_INTERVAL", "10"))
GRPC_RECONNECT_INITIAL_MS = int(os.environ.get("PMTEC_RECONNECT_INITIAL_MS", "1000"))
GRPC_RECONNECT_MAX_MS = int(os.environ.get("PMTEC_RECONNECT_MAX_MS", "30000"))
GRPC_RECONNECT_MULTIPLIER = float(os.environ.get("PMTEC_RECONNECT_MULTIPLIER", "2.0"))
GRPC_RECONNECT_MAX_ATTEMPTS = int(os.environ.get("PMTEC_RECONNECT_MAX_ATTEMPTS", "5"))

# ============================================================
# P7-v2: Observability Configuration
# ============================================================
PROMETHEUS_ENABLED = os.environ.get("PMTEC_PROMETHEUS", "1") == "1"
PROMETHEUS_PORT = int(os.environ.get("PMTEC_PROM_PORT", "9090"))
PROMETHEUS_METRICS_PATH = "/metrics"

# ============================================================
# P7-v2: Live Data API Configuration
# ============================================================
LIVE_DATA_USE_REAL_API = os.environ.get("PMTEC_LIVE_REAL_API", "0") == "1"
LIVE_DATA_OPENSKY_URL = "https://opensky-network.org/api/states/all"
LIVE_DATA_OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
LIVE_DATA_TIMEOUT_S = int(os.environ.get("PMTEC_LIVE_TIMEOUT", "10"))
LIVE_DATA_RETRY_ATTEMPTS = int(os.environ.get("PMTEC_LIVE_RETRIES", "3"))
