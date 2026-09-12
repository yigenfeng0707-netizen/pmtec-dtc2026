#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate GeoJSON and Leaflet interactive HTML map for INDOPACOM bases."""

import json
import os

# ============================================================
# Base data: curated from websearch results
# Coordinates are approximate, cross-referenced from multiple sources
# ============================================================

bases = [
    # === JAPAN ===
    {
        "id": "JP-MISAWA",
        "name": "Misawa Air Base",
        "name_cn": "三泽空军基地",
        "country": "Japan",
        "region": "Japan-North",
        "lat": 40.7058,
        "lon": 141.3814,
        "branch": "USAF",
        "unit": "35th Fighter Wing",
        "aircraft": "F-35A (48 planned), P-8A, RC-135",
        "runway_m": 3050,
        "personnel": 3600,
        "facility_code": "FAC 2001",
        "role": "Tactical strike, air superiority, SEAD",
        "vs26_role": "F-35 Effect Simulator source - first virtual training contribution to Guam defense from Japan",
        "scars": True,
        "lvc_layer": "Virtual (simulator source)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network node + Application Store (F-35 sim plug-in)",
        "asda_mapping": "Act (strike launch) + Sense (ISR collection)",
    },
    {
        "id": "JP-YOKOTA",
        "name": "Yokota Air Base",
        "name_cn": "横田空军基地",
        "country": "Japan",
        "region": "Japan-Central",
        "lat": 35.7447,
        "lon": 139.3475,
        "branch": "USAF",
        "unit": "374th Airlift Wing, USFJ HQ",
        "aircraft": "C-130J, KC-135, CV-22, U-2",
        "runway_m": 3050,
        "personnel": 4200,
        "facility_code": "FAC 3013",
        "role": "Command hub, tactical airlift, special operations",
        "vs26_role": "C2 coordination node in Guam-to-Japan-to-Hawaii integration chain",
        "scars": False,
        "lvc_layer": "Live (real-world C2)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (C2 hub) + Plug-and-Play (command modules)",
        "asda_mapping": "Decide (command coordination) + Act (airlift support)",
    },
    {
        "id": "JP-KADENA",
        "name": "Kadena Air Base",
        "name_cn": "嘉手纳空军基地",
        "country": "Japan",
        "region": "Japan-Okinawa",
        "lat": 26.3505,
        "lon": 127.7686,
        "branch": "USAF",
        "unit": "18th Wing",
        "aircraft": "F-15C/D, KC-135, E-3, HH-60",
        "runway_m": 3700,
        "personnel": 15000,
        "facility_code": "FAC 6037",
        "role": "Pacific keystone, forward strike hub, First Island Chain spear",
        "vs26_role": "ACE Hub center - primary forward deployed air power node",
        "scars": False,
        "lvc_layer": "Live (real-world operations)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (primary node) + Application Store (strike packages)",
        "asda_mapping": "Act (strike launch) + Sense (AEW coverage) + Decide (C2)",
    },
    {
        "id": "JP-FUTENMA",
        "name": "MCAS Futenma",
        "name_cn": "普天间航空站",
        "country": "Japan",
        "region": "Japan-Okinawa",
        "lat": 26.2783,
        "lon": 127.7658,
        "branch": "USMC",
        "unit": "1st Marine Aircraft Wing, 3rd MEB",
        "aircraft": "MV-22 (x24), AH-1Z (x12), UH-1Y (x8)",
        "runway_m": 1800,
        "personnel": 2800,
        "facility_code": "FAC 6055",
        "role": "Marine air hub, rapid response, amphibious assault",
        "vs26_role": "Amphibious rapid response capability for ACE dispersal",
        "scars": False,
        "lvc_layer": "Live (real-world operations)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (USMC node) + Plug-and-Play (rotary wing modules)",
        "asda_mapping": "Act (amphibious assault) + Adapt (rapid repositioning)",
    },
    {
        "id": "JP-SASEBO",
        "name": "Sasebo Naval Base",
        "name_cn": "佐世保海军基地",
        "country": "Japan",
        "region": "Japan-South",
        "lat": 33.1611,
        "lon": 129.7225,
        "branch": "USN",
        "unit": "CTF-76, 11th Amphibious Squadron",
        "aircraft": "Amphibious assault ships, DDGs",
        "runway_m": 0,
        "personnel": 4500,
        "facility_code": "FAC 4145",
        "role": "Amphibious operations core, Seventh Fleet support",
        "vs26_role": "Sea-based ACE dispersal platform",
        "scars": False,
        "lvc_layer": "Live (naval operations)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (naval node) + Plug-and-Play (amphibious modules)",
        "asda_mapping": "Act (amphibious deployment) + Sense (maritime ISR)",
    },
    {
        "id": "JP-YOKOSUKA",
        "name": "Yokosuka Naval Base",
        "name_cn": "横须贺海军基地",
        "country": "Japan",
        "region": "Japan-Central",
        "lat": 35.2906,
        "lon": 139.6672,
        "branch": "USN",
        "unit": "USFJ, 7th Fleet HQ",
        "aircraft": "CVN (Ronald Reagan), CGs, DDGs, SSN",
        "runway_m": 0,
        "personnel": 5500,
        "facility_code": "FAC 3099",
        "role": "7th Fleet HQ, nuclear carrier homeport, Pacific maritime command",
        "vs26_role": "7th Fleet C2 in Guam-to-Japan integration chain",
        "scars": False,
        "lvc_layer": "Live (fleet operations)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (fleet C2) + Plug-and-Play (carrier strike group)",
        "asda_mapping": "Act (power projection) + Decide (fleet command) + Sense (maritime domain)",
    },
    {
        "id": "JP-IWAKUNI",
        "name": "MCAS Iwakuni",
        "name_cn": "岩国海军陆战队航空站",
        "country": "Japan",
        "region": "Japan-South",
        "lat": 34.1442,
        "lon": 132.2347,
        "branch": "USMC",
        "unit": "1st Marine Aircraft Wing",
        "aircraft": "F-35B, MV-22",
        "runway_m": 2440,
        "personnel": 3600,
        "facility_code": "FAC 4100",
        "role": "Marine air operations, F-35B deployment",
        "vs26_role": "F-35B STOVL dispersal node for ACE",
        "scars": False,
        "lvc_layer": "Live (real-world operations)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (USMC air node) + Application Store (F-35B package)",
        "asda_mapping": "Act (strike launch) + Adapt (dispersed STOVL operations)",
    },
    # === GUAM ===
    {
        "id": "GU-ANDERSEN",
        "name": "Andersen AFB",
        "name_cn": "安德森空军基地",
        "country": "Guam",
        "region": "Guam",
        "lat": 13.5839,
        "lon": 144.9167,
        "branch": "USAF",
        "unit": "36th Wing, AMC",
        "aircraft": "B-1B, B-2, B-52 (rotational), F-35, tanker support",
        "runway_m": 3414,
        "personnel": 6363,
        "facility_code": "PGUA",
        "role": "360-degree Guam Defense core, strategic bomber forward base, PMTEC hub",
        "vs26_role": "PMTEC center - 360-degree Guam defense operations, LVC integration hub, SPEAR playback center",
        "scars": False,
        "lvc_layer": "Live+Virtual+Constructive (all three layers)",
        "ace_hub": True,
        "dtb_mapping": "War Engine (PMTEC core) + Battle Network (C2 hub) + Application Store + Plug-and-Play",
        "asda_mapping": "All four: Act+Sense+Decide+Adapt (full ASDA loop center)",
    },
    {
        "id": "GU-APRA",
        "name": "Naval Base Guam",
        "name_cn": "阿普拉海军基地",
        "country": "Guam",
        "region": "Guam",
        "lat": 13.4469,
        "lon": 144.6589,
        "branch": "USN",
        "unit": "Commander, Naval Forces Marianas",
        "aircraft": "SSN, surface combatants",
        "runway_m": 0,
        "personnel": 3000,
        "facility_code": "PGUM",
        "role": "Naval support, submarine maintenance, maritime domain awareness",
        "vs26_role": "Naval component of Guam 360-degree defense",
        "scars": False,
        "lvc_layer": "Live (naval operations)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (naval node) + Plug-and-Play (submarine modules)",
        "asda_mapping": "Act (submarine ops) + Sense (undersea domain)",
    },
    # === SOUTH KOREA ===
    {
        "id": "KR-HUMPHREYS",
        "name": "Camp Humphreys",
        "name_cn": "汉弗莱营",
        "country": "South Korea",
        "region": "Korea",
        "lat": 36.9647,
        "lon": 127.0336,
        "branch": "US Army",
        "unit": "Eighth Army HQ, USFK HQ",
        "aircraft": "AH-64, UH-60, CH-47",
        "runway_m": 2438,
        "personnel": 28500,
        "facility_code": "USAG Humphreys",
        "role": "USFK command hub, largest overseas US base",
        "vs26_role": "Ground force C2 node in INDOPACOM integration chain",
        "scars": False,
        "lvc_layer": "Live (real-world C2)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (ground C2 hub) + Plug-and-Play (army modules)",
        "asda_mapping": "Decide (ground command) + Act (ground deployment)",
    },
    {
        "id": "KR-OSAN",
        "name": "Osan Air Base",
        "name_cn": "乌山空军基地",
        "country": "South Korea",
        "region": "Korea",
        "lat": 37.0906,
        "lon": 127.0336,
        "branch": "USAF",
        "unit": "7th Air Force, 51st Fighter Wing",
        "aircraft": "F-16, A-10, U-2",
        "runway_m": 2743,
        "personnel": 6752,
        "facility_code": "K-55",
        "role": "Northeast Asia air sentinel, Korea defense",
        "vs26_role": "Forward air defense node for Korea theater",
        "scars": False,
        "lvc_layer": "Live (real-world operations)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (air defense node) + Application Store (fighter packages)",
        "asda_mapping": "Act (air defense) + Sense (airspace monitoring)",
    },
    {
        "id": "KR-KUNSAN",
        "name": "Kunsan Air Base",
        "name_cn": "群山空军基地",
        "country": "South Korea",
        "region": "Korea",
        "lat": 35.9014,
        "lon": 126.6156,
        "branch": "USAF",
        "unit": "8th Fighter Wing",
        "aircraft": "F-16",
        "runway_m": 2743,
        "personnel": 2650,
        "facility_code": "Kunsan AB",
        "role": "Korea west coast air defense, mutual support with Osan",
        "vs26_role": "ACE dispersal node for Korea peninsula",
        "scars": False,
        "lvc_layer": "Live (real-world operations)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (support node) + Application Store (fighter package)",
        "asda_mapping": "Act (air defense) + Adapt (dispersed operations)",
    },
    # === HAWAII ===
    {
        "id": "HI-PHICKAM",
        "name": "Joint Base Pearl Harbor-Hickam",
        "name_cn": "珍珠港-希卡姆联合基地",
        "country": "USA",
        "region": "Hawaii",
        "lat": 21.3694,
        "lon": -157.9622,
        "branch": "USN/USAF",
        "unit": "USPACOM HQ, PACFLT, PACAF HQ",
        "aircraft": "Multi-domain fleet and air assets",
        "runway_m": 3769,
        "personnel": 44545,
        "facility_code": "JBPHH",
        "role": "USINDOPACOM HQ, Pacific Fleet HQ, Pacific Air Force HQ",
        "vs26_role": "Rear C2 hub - Guam-to-Hawaii integration chain endpoint, USPACOM J7 PMTEC management",
        "scars": False,
        "lvc_layer": "Live (strategic C2) + Constructive (PMTEC management)",
        "ace_hub": True,
        "dtb_mapping": "War Engine (strategic C2) + Battle Network (regional hub)",
        "asda_mapping": "Decide (strategic command) + Adapt (theater-level adjustment)",
    },
    {
        "id": "HI-SCHOFIELD",
        "name": "Schofield Barracks",
        "name_cn": "薛菲尔德兵营",
        "country": "USA",
        "region": "Hawaii",
        "lat": 21.4950,
        "lon": -158.0636,
        "branch": "US Army",
        "unit": "25th Infantry Division",
        "aircraft": "N/A",
        "runway_m": 0,
        "personnel": 16000,
        "facility_code": "Schofield",
        "role": "Pacific ground force staging, rapid deployment",
        "vs26_role": "Ground force deployment staging for Pacific operations",
        "scars": False,
        "lvc_layer": "Live (ground force staging)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (army staging) + Plug-and-Play (ground force modules)",
        "asda_mapping": "Act (ground deployment) + Adapt (force reconstitution)",
    },
    # === ALASKA ===
    {
        "id": "AK-JBER",
        "name": "Joint Base Elmendorf-Richardson",
        "name_cn": "埃尔门多夫-理查森联合基地",
        "country": "USA",
        "region": "Alaska",
        "lat": 61.2647,
        "lon": -149.7275,
        "branch": "USAF/US Army",
        "unit": "3rd Wing, 4th Brigade (Airborne)",
        "aircraft": "F-22, C-17, E-3",
        "runway_m": 3048,
        "personnel": 32000,
        "facility_code": "JBER",
        "role": "Arctic military readiness, northern air defense, strategic bomber base",
        "vs26_role": "Northern flank defense, Arctic domain awareness",
        "scars": False,
        "lvc_layer": "Live (Arctic operations)",
        "ace_hub": True,
        "dtb_mapping": "Battle Network (northern node) + Application Store (F-22 package)",
        "asda_mapping": "Sense (Arctic ISR) + Act (air defense) + Decide (regional C2)",
    },
    {
        "id": "AK-EIELSON",
        "name": "Eielson AFB",
        "name_cn": "艾尔森空军基地",
        "country": "USA",
        "region": "Alaska",
        "lat": 64.6431,
        "lon": -147.6106,
        "branch": "USAF",
        "unit": "354th Fighter Wing",
        "aircraft": "F-35A, F-16 (aggressor)",
        "runway_m": 4420,
        "personnel": 3000,
        "facility_code": "Eielson",
        "role": "Arctic air power, aggressor training, F-35 deployment",
        "vs26_role": "F-35 deployment node for Arctic domain, Red Flag training",
        "scars": False,
        "lvc_layer": "Live (training operations) + Virtual (aggressor sim)",
        "ace_hub": False,
        "dtb_mapping": "Application Store (F-35 package) + Plug-and-Play (training modules)",
        "asda_mapping": "Act (air training) + Adapt (tactics development)",
    },
    # === AUSTRALIA ===
    {
        "id": "AU-DARWIN",
        "name": "RAAF Base Darwin",
        "name_cn": "达尔文皇家空军基地",
        "country": "Australia",
        "region": "Australia",
        "lat": -12.4153,
        "lon": 130.8769,
        "branch": "RAAF/USMC",
        "unit": "MRF-D (Marine Rotational Force Darwin)",
        "aircraft": "F-35, F/A-18, KC-30A, MV-22",
        "runway_m": 2744,
        "personnel": 2000,
        "facility_code": "Darwin",
        "role": "Southern ACE dispersal point, second island chain southern terminus",
        "vs26_role": "Southern ACE dispersal node, MRF-D rotational deployment",
        "scars": False,
        "lvc_layer": "Live (rotational deployment)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (southern node) + Plug-and-Play (USMC rotational modules)",
        "asda_mapping": "Act (southern deployment) + Adapt (rotational presence)",
    },
    {
        "id": "AU-TINDAL",
        "name": "RAAF Base Tindal",
        "name_cn": "廷达尔皇家空军基地",
        "country": "Australia",
        "region": "Australia",
        "lat": -14.5236,
        "lon": 132.3789,
        "branch": "RAAF",
        "unit": "No. 75 Squadron RAAF",
        "aircraft": "F/A-18, KC-30A",
        "runway_m": 2744,
        "personnel": 1000,
        "facility_code": "Tindal",
        "role": "Northern Australia air defense, US force posture initiative",
        "vs26_role": "Support node for USFPI enhanced logistics sustainment",
        "scars": False,
        "lvc_layer": "Live (air defense)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (support node) + Plug-and-Play (RAAF modules)",
        "asda_mapping": "Act (air defense) + Sense (northern approach monitoring)",
    },
    # === PHILIPPINES (EDCA) ===
    {
        "id": "PH-CAMILO",
        "name": "NB Camilo Osias",
        "name_cn": "卡米洛·奥西亚斯海军基地",
        "country": "Philippines",
        "region": "Philippines",
        "lat": 18.5667,
        "lon": 121.1833,
        "branch": "USN/USMC",
        "unit": "EDCA facility",
        "aircraft": "Rotational deployment",
        "runway_m": 0,
        "personnel": 0,
        "facility_code": "Camilo Osias",
        "role": "Northern Luzon forward point, Taiwan Strait monitoring",
        "vs26_role": "ACE forward dispersal node facing Taiwan Strait",
        "scars": False,
        "lvc_layer": "Live (rotational deployment)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (forward node) + Plug-and-Play (rotational modules)",
        "asda_mapping": "Sense (Taiwan Strait ISR) + Act (forward deployment)",
    },
    {
        "id": "PH-LALLO",
        "name": "Lal-lo Airport",
        "name_cn": "拉尔洛机场",
        "country": "Philippines",
        "region": "Philippines",
        "lat": 18.2000,
        "lon": 121.4000,
        "branch": "USAF/USMC",
        "unit": "EDCA facility",
        "aircraft": "Rotational deployment",
        "runway_m": 1500,
        "personnel": 0,
        "facility_code": "Lal-lo",
        "role": "Northern Luzon dispersal airfield",
        "vs26_role": "ACE dispersal airfield for Northern Luzon",
        "scars": False,
        "lvc_layer": "Live (rotational deployment)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (dispersal node) + Plug-and-Play (expeditionary modules)",
        "asda_mapping": "Act (dispersed operations) + Adapt (agile repositioning)",
    },
    {
        "id": "PH-BALABAC",
        "name": "Balabac Island",
        "name_cn": "巴拉巴克岛",
        "country": "Philippines",
        "region": "Philippines",
        "lat": 8.0333,
        "lon": 117.0500,
        "branch": "USMC",
        "unit": "EDCA facility",
        "aircraft": "Rotational deployment",
        "runway_m": 0,
        "personnel": 0,
        "facility_code": "Balabac",
        "role": "Southwest Pacific approach monitoring, South China Sea gateway",
        "vs26_role": "South China Sea monitoring node",
        "scars": False,
        "lvc_layer": "Live (rotational deployment)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (maritime node) + Plug-and-Play (ISR modules)",
        "asda_mapping": "Sense (SCS ISR) + Act (maritime presence)",
    },
    # === TINIAN ===
    {
        "id": "CNMI-TINIAN",
        "name": "Tinian North Field",
        "name_cn": "天宁岛北机场",
        "country": "CNMI",
        "region": "Mariana Islands",
        "lat": 15.0833,
        "lon": 145.6167,
        "branch": "USAF",
        "unit": "ACE dispersal site",
        "aircraft": "Rotational/expeditionary",
        "runway_m": 2611,
        "personnel": 0,
        "facility_code": "Tinian",
        "role": "ACE distributed dispersal node, Second Island Chain depth",
        "vs26_role": "ACE distributed dispersal node - Second Island Chain depth support for Guam defense",
        "scars": False,
        "lvc_layer": "Constructive (planned dispersal site)",
        "ace_hub": False,
        "dtb_mapping": "Battle Network (depth node) + Plug-and-Play (expeditionary modules)",
        "asda_mapping": "Adapt (dispersed operations) + Act (depth deployment)",
    },
]

# ============================================================
# Generate GeoJSON
# ============================================================

features = []
for b in bases:
    props = {k: v for k, v in b.items() if k not in ("lat", "lon")}
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
        "properties": props,
    }
    features.append(feature)

geojson = {
    "type": "FeatureCollection",
    "name": "INDOPACOM Military Bases",
    "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
    "features": features,
}

geojson_path = os.path.join("D:/APPs/数字孪生挑战赛", "indopacom_bases.geojson")
with open(geojson_path, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=2)

print(f"GeoJSON saved: {geojson_path} ({len(features)} features)")

# ============================================================
# Generate Leaflet Interactive HTML Map
# ============================================================

# Color mapping by branch
branch_colors = {
    "USAF": "#4FC3F7",
    "USN": "#42A5F5",
    "USMC": "#8D6E63",
    "US Army": "#66BB6A",
    "USN/USAF": "#26C6DA",
    "USAF/US Army": "#66BB6A",
    "RAAF/USMC": "#FFA726",
    "RAAF": "#FFCA28",
    "USN/USMC": "#8D6E63",
    "USAF/USMC": "#789262",
}

# Region grouping
regions = {
    "Japan-North": {"name": "Japan (North)", "color": "#1565C0"},
    "Japan-Central": {"name": "Japan (Central)", "color": "#1976D2"},
    "Japan-Okinawa": {"name": "Japan (Okinawa)", "color": "#1E88E5"},
    "Japan-South": {"name": "Japan (South)", "color": "#2196F3"},
    "Guam": {"name": "Guam", "color": "#D32F2F"},
    "Korea": {"name": "South Korea", "color": "#388E3C"},
    "Hawaii": {"name": "Hawaii", "color": "#7B1FA2"},
    "Alaska": {"name": "Alaska", "color": "#00838F"},
    "Australia": {"name": "Australia", "color": "#F57C00"},
    "Philippines": {"name": "Philippines", "color": "#5D4037"},
    "Mariana Islands": {"name": "Mariana Islands", "color": "#C62828"},
}


# Generate popup HTML for each base
def make_popup(b):
    html = f"""<div style="min-width:320px;font-size:12px;line-height:1.6">
<h3 style="margin:0 0 4px 0;color:#1565C0">{b["name"]}</h3>
<div style="color:#666;margin-bottom:6px">{b["name_cn"]} | {b["country"]} | {b["branch"]}</div>
<table style="border-collapse:collapse;width:100%">
<tr><td style="color:#999;padding:2px 6px">Unit</td><td style="padding:2px 6px">{b["unit"]}</td></tr>
<tr><td style="color:#999;padding:2px 6px">Aircraft</td><td style="padding:2px 6px">{b["aircraft"]}</td></tr>
<tr><td style="color:#999;padding:2px 6px">Runway</td><td style="padding:2px 6px">{b["runway_m"]} m</td></tr>
<tr><td style="color:#999;padding:2px 6px">Personnel</td><td style="padding:2px 6px">{b["personnel"]:,}</td></tr>
<tr><td style="color:#999;padding:2px 6px">Facility Code</td><td style="padding:2px 6px">{b["facility_code"]}</td></tr>
<tr><td style="color:#999;padding:2px 6px">Role</td><td style="padding:2px 6px">{b["role"]}</td></tr>
<tr><td style="color:#E65100;padding:2px 6px;font-weight:bold">VS26 Role</td><td style="padding:2px 6px">{b["vs26_role"]}</td></tr>
<tr><td style="color:#999;padding:2px 6px">LVC Layer</td><td style="padding:2px 6px">{b["lvc_layer"]}</td></tr>
<tr><td style="color:#999;padding:2px 6px">ACE Hub</td><td style="padding:2px 6px">{"Yes" if b["ace_hub"] else "No"}</td></tr>
<tr><td style="color:#999;padding:2px 6px">SCARS</td><td style="padding:2px 6px">{"Yes" if b["scars"] else "No"}</td></tr>
<tr><td style="color:#1565C0;padding:2px 6px;font-weight:bold">DTB Model</td><td style="padding:2px 6px">{b["dtb_mapping"]}</td></tr>
<tr><td style="color:#C62828;padding:2px 6px;font-weight:bold">ASDA Loop</td><td style="padding:2px 6px">{b["asda_mapping"]}</td></tr>
</table>
</div>"""
    return html.replace("\n", "")


# Generate JS data array
js_bases = []
for b in bases:
    popup = make_popup(b)
    color = branch_colors.get(b["branch"], "#757575")
    js_bases.append(
        {
            "lat": b["lat"],
            "lon": b["lon"],
            "name": b["name"],
            "name_cn": b["name_cn"],
            "region": b["region"],
            "branch": b["branch"],
            "color": color,
            "ace_hub": b["ace_hub"],
            "popup": popup,
        }
    )

js_data = json.dumps(js_bases, ensure_ascii=False)

# Generate region legend
legend_items = ""
for rkey, rinfo in regions.items():
    count = sum(1 for b in bases if b["region"] == rkey)
    if count > 0:
        legend_items += f'<div style="display:flex;align-items:center;margin:3px 0"><span style="display:inline-block;width:14px;height:14px;background:{rinfo["color"]};border-radius:50%;margin-right:6px"></span><span style="font-size:11px;color:#cfd8e3">{rinfo["name"]} ({count})</span></div>'

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>INDOPACOM Military Bases Map | DTC 2026</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#0a0e14;font-family:"Microsoft YaHei",system-ui,sans-serif;color:#cfd8e3}}
#map{{width:100%;height:100%;position:fixed;inset:0}}
.pane{{position:fixed;background:rgba(10,14,20,.88);border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(14px);border-radius:4px;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,.6)}}
#title{{left:16px;top:16px;padding:14px 20px;max-width:340px}}
#title h1{{font-size:16px;font-weight:600;letter-spacing:1px;color:#eef3f8;margin-bottom:4px}}
#title h1 b{{color:#ffb347}}
#title .sub{{font-size:10px;letter-spacing:2px;color:#6f8296;text-transform:uppercase;margin-bottom:8px}}
#title .desc{{font-size:11px;color:#93a4b6;line-height:1.6}}
#legend{{left:16px;bottom:16px;padding:12px 16px;max-width:200px}}
#legend h3{{font-size:11px;letter-spacing:1.5px;color:#6f8296;margin-bottom:8px}}
#filter{{right:16px;top:16px;padding:12px 16px;width:220px}}
#filter h3{{font-size:11px;letter-spacing:1.5px;color:#6f8296;margin-bottom:8px}}
.fbtn{{display:block;width:100%;padding:5px 8px;margin:2px 0;font-size:11px;text-align:left;cursor:pointer;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);color:#93a4b6;border-radius:2px;transition:.15s}}
.fbtn:hover{{background:rgba(255,255,255,.09);color:#e6eef7}}
.fbtn.active{{background:rgba(255,179,71,.18);border-color:rgba(255,179,71,.3);color:#ffb347}}
.leaflet-popup-content-wrapper{{background:rgba(10,14,20,.95);color:#cfd8e3;border:1px solid rgba(255,255,255,.08)}}
.leaflet-popup-tip{{background:rgba(10,14,20,.95)}}
</style>
</head>
<body>
<div id="map"></div>
<div class="pane" id="title">
<h1>INDOPACOM <b>Military Bases</b></h1>
<div class="sub">DTC 2026 | Scene Development Track Level 1</div>
<div class="desc">INDOPACOM辖区{len(bases)}个美军军事基地标绘地图。每个基地含坐标、军种、装备、VS26实战角色、LVC架构定位、DTB Model映射和ASDA闭环映射。体现"智能杀伤网"ASDA闭环理解。</div>
</div>
<div class="pane" id="legend">
<h3>REGION LEGEND</h3>
{legend_items}
</div>
<div class="pane" id="filter">
<h3>FILTERS</h3>
<div class="fbtn active" data-filter="all">All Bases ({len(bases)})</div>
<div class="fbtn" data-filter="ace">ACE Hub Bases</div>
<div class="fbtn" data-filter="usaf">Air Force Bases</div>
<div class="fbtn" data-filter="usn">Navy Bases</div>
<div class="fbtn" data-filter="usmc">Marine Corps</div>
<div class="fbtn" data-filter="lvc">LVC Integration</div>
</div>
<script>
const bases = {js_data};

const map = L.map('map', {{center:[20,135],zoom:4,worldCopyJump:true,minZoom:2,maxZoom:12}});

L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
attribution:'Esri, HERE, Garmin, &copy; OpenStreetMap contributors',maxZoom:16
}}).addTo(map);

const markers = [];
bases.forEach(b => {{
const icon = L.divIcon({{
html: '<div style="width:12px;height:12px;border-radius:50%;background:' + b.color + ';border:2px solid #fff;box-shadow:0 0 6px ' + b.color + '"></div>',
className: '',iconSize:[12,12],iconAnchor:[6,6]
}});
const m = L.marker([b.lat, b.lon], {{icon}}).addTo(map);
m.bindPopup(b.popup, {{maxWidth:360}});
markers.push({{marker:m, data:b}});
}});

// Connect Guam-Japan-Hawaii chain
const chainLatLngs = [
[13.5839,144.9167],  // Guam
[26.3505,127.7686],  // Kadena
[35.7447,139.3475],  // Yokota
[21.3694,-157.9622]  // Pearl Harbor
];
L.polyline(chainLatLngs, {{color:'#ffb347',weight:2,dashArray:'8 6',opacity:.5}}).addTo(map);

// Filter
document.querySelectorAll('.fbtn').forEach(btn => {{
btn.addEventListener('click', function() {{
document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
this.classList.add('active');
const f = this.dataset.filter;
markers.forEach(m => {{
let show = false;
if (f === 'all') show = true;
else if (f === 'ace') show = m.data.ace_hub;
else if (f === 'usaf') show = m.data.branch.includes('USAF');
else if (f === 'usn') show = m.data.branch.includes('USN');
else if (f === 'usmc') show = m.data.branch.includes('USMC');
else if (f === 'lvc') show = m.data.lvc_layer.includes('Virtual') || m.data.lvc_layer.includes('Constructive') || m.data.lvc_layer.includes('all');
if (show) map.addLayer(m.marker); else map.removeLayer(m.marker);
}});
}});
}});
</script>
</body>
</html>"""

html_path = os.path.join("D:/APPs/数字孪生挑战赛", "INDOPACOM-Bases-Map.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"HTML map saved: {html_path}")
print(f"Total bases: {len(bases)}")
print(f"Regions: {len(set(b['region'] for b in bases))}")
print(f"ACE Hub bases: {sum(1 for b in bases if b['ace_hub'])}")
