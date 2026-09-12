"""
ACE Deployment Engine - Configuration
DTC 2026 Level 2: ACE Distributed Deployment & Strike Response Algorithm
"""

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
# P9: v2 权威数据库（67 实体；CRS 66 + Tinian）；旧 22 基地版保留为 bases.geojson
BASES_GEOJSON = os.path.join(DATA_DIR, "bases_v2.geojson")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

EARTH_RADIUS_KM = 6371.0

# Aircraft performance data (open-source estimates)
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
    "P-8": 909,
    "MQ-9": 482,
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
    "P-8": 2200,
    "MQ-9": 1850,
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
    "P-8": 50,
    "MQ-9": 30,
}
PARKING_SPOTS = {
    "F-35A": 1,
    "F-22A": 1,
    "F-15C": 1,
    "F-15E": 1,
    "F-16C": 1,
    "KC-135": 2,
    "KC-46": 2,
    "E-3": 2,
    "RC-135": 2,
    "P-8": 1,
    "MQ-9": 1,
}

# Threat types (open-source defense estimates)
THREAT_SPEED_KMH = {
    "DF-21D": 6000,
    "DF-26": 8000,
    "DF-17": 7000,
    "KH-101": 800,
    "CJ-10": 800,
    "H-6N": 900,
}
THREAT_CEP_M = {
    "DF-21D": 50,
    "DF-26": 150,
    "DF-17": 30,
    "KH-101": 20,
    "CJ-10": 30,
    "H-6N": 100,
}
THREAT_WARHEAD_KG = {
    "DF-21D": 1000,
    "DF-26": 1500,
    "DF-17": 800,
    "KH-101": 450,
    "CJ-10": 500,
    "H-6N": 2000,
}
THREAT_RANGE_KM = {
    "DF-21D": 1500,
    "DF-26": 4000,
    "DF-17": 2500,
    "KH-101": 5500,
    "CJ-10": 2000,
    "H-6N": 600,
}

# Damage model
RUNWAY_CRATER_RADIUS_PER_500KG = 15  # meters
SHELTER_SURVIVAL_PROB = 0.85
OPEN_SURVIVAL_PROB = 0.15
BLAST_RADIUS_500KG_M = 150  # effective blast radius

# ASDA parameters
ASDA_CYCLE_SECONDS = 30
ALERT_TO_IMPACT_MINUTES = {
    "DF-21D": 15,
    "DF-26": 10,
    "DF-17": 8,
    "KH-101": 120,
    "CJ-10": 90,
    "H-6N": 45,
}

# ACE parameters
ACE_HUB_DISPERSION_RATIO = 0.6
MIN_SPOKE_CAPACITY = 4
MAX_SPOKE_FILL_RATIO = 0.75

# Default squadron composition
DEFAULT_SQUADRON_F35 = {"F-35A": 24}
DEFAULT_SQUADRON_F22 = {"F-22A": 20}
DEFAULT_SQUADRON_F15 = {"F-15C": 18}
DEFAULT_SQUADRON_F16 = {"F-16C": 18}
DEFAULT_TANKER_SQUADRON = {"KC-135": 12}
DEFAULT_AEW_SQUADRON = {"E-3": 4}

# DTB Model mapping
DTB_MAPPING = {
    "deployment": "Battle Network + Plug-and-Play",
    "transfer": "Battle Network (node reconfiguration)",
    "damage": "War Engine (simulation state update)",
    "threat": "Battle Network (sensor feed)",
    "recovery": "Application Store (capability reload)",
}

# ASDA mapping
ASDA_MAPPING = {
    "Act": "Execute deployment/transfer orders",
    "Sense": "Detect threats via sensor network (radar/satellite/ELINT)",
    "Decide": "Multi-objective optimization for resource allocation",
    "Adapt": "Adjust strategy based on damage assessment and threat evolution",
}
