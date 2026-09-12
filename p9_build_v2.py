#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P9 数据库升级主脚本（P9.2/P9.3/P9.4 合并）
- 载入现有 22 基地（indopacom_bases.geojson）
- 融合 CRS Table A-1 全部 66 站点（45 个新站点全量数据，坐标经 web 双源验证）
- 解析 FY2024 基地结构报告 Excel：PRV / 占地 / 建筑物统计（模糊匹配 + 四分位实时计算）
- Tier 分级（4 级）+ 政治约束字段（准入不确定性进入 ASDA-Adapt 建模）
- 输出 indopacom_bases_v2.geojson（67 实体）
"""

import json
import re
import sys

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = "D:/APPs/数字孪生挑战赛"
GEOJSON_V1 = f"{BASE_DIR}/indopacom_bases.geojson"
GEOJSON_V2 = f"{BASE_DIR}/indopacom_bases_v2.geojson"
EXCEL = (
    "回复：+第八届数字孪生体挑战赛（DTC+2026）赛道二参赛报名+——+根深叶茂团队/"
    "2 美国国防部基地结构报告-FY2024.xlsx"
)

# =====================================================================
# 45 个新站点（CRS Table A-1 编号 / 名称 / 中文名 / 国家 / 区域 / 军种 /
# 坐标 / 单位 / 角色 / DTB映射 / ASDA映射 / LVC / Tier）
# 坐标来源：公开资料交叉验证，4 处经 web 双源修正：
#   Camp Mujuk(浦项 35.9577/129.4252)、Kyogamisaki(35.7658/135.1955)、
#   Camp Melchor Dela Cruz(17.0730/121.8662)、Robertson Barracks(-12.4373/130.9755)
# =====================================================================

NEW_SITES = [
    # ---- Alaska（4）----
    dict(crs_no=1, id="AK-WAINWRIGHT", name="Fort Wainwright", name_cn="温赖特堡",
         country="USA", region="Alaska", service="Army", us_territory=True, dod_operated=True,
         lat=64.8372, lon=-147.7044, unit="1st Stryker Brigade, USARAK",
         role="Arctic ground force readiness, 11th Airborne Division",
         dtb="Battle Network (ground node) + Plug-and-Play (arctic brigade modules)",
         asda="Act (ground deployment) + Adapt (arctic operations)", lvc="Live", tier=2),
    dict(crs_no=2, id="AK-GREELEY", name="Fort Greely", name_cn="格里利堡",
         country="USA", region="Alaska", service="Army", us_territory=True, dod_operated=True,
         lat=63.8739, lon=-145.6900, unit="100th Missile Defense Brigade (GMD)",
         role="Ground-based Midcourse Defense interceptor site, homeland missile defense",
         dtb="Battle Network (BMD sensor-shooter link) + War Engine (GMD interceptor model)",
         asda="Sense (early warning track) + Act (interceptor launch)", lvc="Live", tier=3),
    dict(crs_no=5, id="AK-EARECKSON", name="Eareckson Air Station", name_cn="埃里克森航空站",
         country="USA", region="Alaska", service="Air Force", us_territory=True, dod_operated=True,
         lat=52.7117, lon=174.1275, unit="374th Operations Group detachment (Shemya)",
         role="Cobra Dane AN/FPS-108 radar, westernmost strategic warning node on Aleutians",
         dtb="Battle Network (space domain awareness) + War Engine (radar model)",
         asda="Sense (ballistic missile tracking) ", lvc="Live", tier=3),
    dict(crs_no=6, id="AK-CLEAR", name="Clear Space Force Station", name_cn="克利尔太空军基地",
         country="USA", region="Alaska", service="Space Force", us_territory=True, dod_operated=True,
         lat=64.2928, lon=-149.1156, unit="13th Space Warning Squadron",
         role="Upgraded Early Warning Radar (UEWR), missile warning and space surveillance",
         dtb="Battle Network (space sensor layer) + Plug-and-Play (UEWR module)",
         asda="Sense (missile warning / space surveillance)", lvc="Live", tier=3),
    # ---- Washington（5）----
    dict(crs_no=7, id="WA-JBLM", name="Joint Base Lewis-McChord", name_cn="刘易斯-麦科德联合基地",
         country="USA", region="Washington", service="Joint (Army and Air Force)", us_territory=True, dod_operated=True,
         lat=47.1043, lon=-122.4842, unit="I Corps HQ, 62nd Airlift Wing",
         role="I Corps command hub, West Coast power projection, C-17 airlift",
         dtb="War Engine (corps-level C2) + Battle Network + Application Store (airlift packages)",
         asda="Decide (corps command) + Act (strategic airlift)", lvc="Live", tier=1, ace_hub=True),
    dict(crs_no=8, id="WA-KITSAP", name="Naval Base Kitsap", name_cn="基察普海军基地",
         country="USA", region="Washington", service="Navy", us_territory=True, dod_operated=True,
         lat=47.5660, lon=-122.6326, unit="SSBN Bangor, PSNS & IMF shipyard",
         role="Ohio-class SSBN homeport, nuclear shipyard, Pacific sea-based deterrent",
         dtb="War Engine (SSBN deterrent model) + Battle Network (strategic comms)",
         asda="Act (strategic deterrent patrol) + Sense (undersea domain)", lvc="Live", tier=1, ace_hub=True),
    dict(crs_no=9, id="WA-EVERETT", name="Naval Station Everett", name_cn="埃弗雷特海军基地",
         country="USA", region="Washington", service="Navy", us_territory=True, dod_operated=True,
         lat=47.9689, lon=-122.2186, unit="Carrier Strike Group support",
         role="Northernmost Pacific carrier destroyer support base",
         dtb="Battle Network (fleet logistics) + Plug-and-Play (surface modules)",
         asda="Act (fleet deployment) + Adapt (force reconstitution)", lvc="Live", tier=2),
    dict(crs_no=10, id="WA-WHIDBEY", name="Naval Air Station Whidbey Island", name_cn="惠德比岛海军航空站",
         country="USA", region="Washington", service="Navy", us_territory=True, dod_operated=True,
         lat=48.3522, lon=-122.6578, unit="Electronic Attack Wing (VAQ)",
         role="EA-18G Growler electronic attack, all Pacific Growler home base",
         dtb="Application Store (EW strike package) + Plug-and-Play (Growler module)",
         asda="Act (electronic attack) + Sense (SIGINT) + Adapt (EM spectrum ops)", lvc="Live", tier=2),
    dict(crs_no=11, id="WA-FAIRCHILD", name="Fairchild Air Force Base", name_cn="费尔柴尔德空军基地",
         country="USA", region="Washington", service="Air Force", us_territory=True, dod_operated=True,
         lat=47.6233, lon=-117.6486, unit="92nd Air Refueling Wing",
         role="KC-135 tanker bridge from West Coast to WestPac",
         dtb="Battle Network (tanker bridge) + Plug-and-Play (refueling module)",
         asda="Act (air refueling support) + Adapt (reach extension)", lvc="Live", tier=2),
    # ---- California（9）----
    dict(crs_no=12, id="CA-VENTURA", name="Naval Base Ventura County", name_cn="文图拉县海军基地",
         country="USA", region="California", service="Navy", us_territory=True, dod_operated=True,
         lat=34.1192, lon=-119.1189, unit="Point Mugu sea range, Port Hueneme",
         role="Missile test range, SM-6/SM-3 flight test launch to Kwajalein, Seabee base",
         dtb="War Engine (live-fire test range) + Battle Network (range instrumentation)",
         asda="Act (test launch) + Sense (range tracking)", lvc="Live+Constructive (test models)", tier=2),
    dict(crs_no=13, id="CA-CORONADO", name="Naval Base Coronado", name_cn="科罗纳多海军基地",
         country="USA", region="California", service="Navy", us_territory=True, dod_operated=True,
         lat=32.6833, lon=-117.1667, unit="Naval Special Warfare Command, Naval Surface Force",
         role="NSWC SEAL home base, surface fleet berthing, amphibious ready",
         dtb="Battle Network (SOCAL hub) + Application Store (SOF packages)",
         asda="Act (special operations) + Decide (SOF C2)", lvc="Live", tier=2),
    dict(crs_no=14, id="CA-SANDIEGO", name="Naval Base San Diego", name_cn="圣迭戈海军基地",
         country="USA", region="California", service="Navy", us_territory=True, dod_operated=True,
         lat=32.6758, lon=-117.1214, unit="Naval Surface Force Pacific",
         role="Largest surface fleet base on West Coast, ~50 ships homeport",
         dtb="Battle Network (fleet hub) + Plug-and-Play (surface action group)",
         asda="Act (fleet sorties) + Adapt (surge deployment)", lvc="Live", tier=2),
    dict(crs_no=15, id="CA-POINTLOMA", name="Naval Base Point Loma", name_cn="洛马角海军基地",
         country="USA", region="California", service="Navy", us_territory=True, dod_operated=True,
         lat=32.6839, lon=-117.1378, unit="Submarine Squadron 11, SPAWAR",
         role="SSN homeport, submarine torpedo test, space and naval warfare systems",
         dtb="Battle Network (undersea + C2 systems) + Plug-and-Play (submarine modules)",
         asda="Sense (undersea ISR) + Act (submarine ops)", lvc="Live", tier=2),
    dict(crs_no=16, id="CA-MIRAMAR", name="Marine Corps Air Station Miramar", name_cn="米拉玛航空站",
         country="USA", region="California", service="Marine Corps", us_territory=True, dod_operated=True,
         lat=32.8733, lon=-117.1439, unit="3rd Marine Aircraft Wing",
         role="F-35C VMFA-314, KC-130J, 3rd MAW West Coast air combat power",
         dtb="Application Store (F-35C strike package) + Plug-and-Play (MAW modules)",
         asda="Act (strike launch) + Adapt (regeneration)", lvc="Live", tier=1, ace_hub=True),
    dict(crs_no=17, id="CA-PENDLETON", name="Marine Corps Base Camp Pendleton", name_cn="彭德尔顿营",
         country="USA", region="California", service="Marine Corps", us_territory=True, dod_operated=True,
         lat=33.3164, lon=-117.3486, unit="1st Marine Division, I MEF",
         role="1st MARDIV amphibious training, WESTPAC force generation",
         dtb="War Engine (MEF C2) + Battle Network + Plug-and-Play (MEB modules)",
         asda="Decide (MEF command) + Act (amphibious assault)", lvc="Live", tier=1, ace_hub=True),
    dict(crs_no=18, id="CA-BEALE", name="Beale Air Force Base", name_cn="比尔空军基地",
         country="USA", region="California", service="Air Force", us_territory=True, dod_operated=True,
         lat=39.1339, lon=-121.4353, unit="9th Reconnaissance Wing",
         role="U-2, RQ-4 Global Hawk ISR collection, theater-wide intelligence",
         dtb="Battle Network (ISR feed) + Application Store (ISR packages)",
         asda="Sense (strategic ISR) + Adapt (sensor tasking)", lvc="Live+Virtual (ISR sim)", tier=2),
    dict(crs_no=19, id="CA-TRAVIS", name="Travis Air Force Base", name_cn="特拉维斯空军基地",
         country="USA", region="California", service="Air Force", us_territory=True, dod_operated=True,
         lat=38.2667, lon=-121.9247, unit="60th Air Mobility Wing",
         role="C-5M, C-17, KC-10 West Coast air mobility hub, Pacific logistics bridge",
         dtb="Battle Network (airlift bridge) + Plug-and-Play (mobility modules)",
         asda="Act (strategic airlift) + Adapt (surge logistics)", lvc="Live", tier=1, ace_hub=True),
    dict(crs_no=20, id="CA-VANDENBERG", name="Vandenberg Space Force Base", name_cn="范登堡太空军基地",
         country="USA", region="California", service="Space Force", us_territory=True, dod_operated=True,
         lat=34.7394, lon=-120.5728, unit="Space Launch Delta 30",
         role="Polar-orbit satellite launch, ICBM test, space domain resiliency",
         dtb="Battle Network (space domain layer) + War Engine (launch operations)",
         asda="Act (space launch) + Sense (space domain awareness)", lvc="Live", tier=1, ace_hub=True),
    # ---- Hawaii（4）----
    dict(crs_no=22, id="HI-SHAFTER", name="Fort Shafter", name_cn="谢夫特堡",
         country="USA", region="Hawaii", service="Army", us_territory=True, dod_operated=True,
         lat=21.3419, lon=-157.8606, unit="US Army Pacific HQ",
         role="USARPAC command hub for all Pacific Army operations",
         dtb="Battle Network (army theater C2) + Plug-and-Play (theater army modules)",
         asda="Decide (theater army command) + Adapt (posture adjustment)", lvc="Live", tier=2),
    dict(crs_no=23, id="HI-WHEELER", name="Wheeler Army Airfield", name_cn="惠勒陆军机场",
         country="USA", region="Hawaii", service="Army", us_territory=True, dod_operated=True,
         lat=21.4856, lon=-158.0397, unit="25th Combat Aviation Brigade",
         role="25th Infantry Division aviation, Hawaii army air component",
         dtb="Battle Network (army aviation node) + Plug-and-Play (CAB modules)",
         asda="Act (aviation support) + Sense (local air picture)", lvc="Live", tier=2),
    dict(crs_no=25, id="HI-PMRF", name="Pacific Missile Range Facility Barking Sands", name_cn="太平洋导弹靶场",
         country="USA", region="Hawaii", service="Navy", us_territory=True, dod_operated=True,
         lat=22.0283, lon=-159.7864, unit="PMRF range operations",
         role="World's largest instrumented multi-domain missile test range, Aegis BMD live-fire",
         dtb="War Engine (live-fire range model) + Battle Network (range instrumentation)",
         asda="Sense (range tracking) + Act (test launch) + Adapt (weapon iteration)", lvc="Live+Constructive", tier=3),
    dict(crs_no=26, id="HI-MCBH", name="Marine Corps Base Hawaii", name_cn="夏威夷海军陆战队基地",
         country="USA", region="Hawaii", service="Marine Corps", us_territory=True, dod_operated=True,
         lat=21.4469, lon=-157.7639, unit="3rd Marine Regiment (MLR pending), MCB Hawaii",
         role="Kaneohe Bay amphibious base, 3rd MLR Indo-Pacific experimentation",
         dtb="Battle Network (USMC node) + Plug-and-Play (MLR modules)",
         asda="Act (littoral ops) + Sense (littoral ISR)", lvc="Live", tier=2),
    # ---- Wake Island（1）----
    dict(crs_no=27, id="WL-WAKE", name="Wake Island Airfield", name_cn="威克岛机场",
         country="USA (Wake Island)", region="Wake Island", service="Air Force", us_territory=True, dod_operated=True,
         lat=19.2822, lon=166.6481, unit="Detachment, 36th Wing (Andersen)",
         role="Emergency divert airfield, mid-Pacific missile test support node",
         dtb="Battle Network (depth node) + Plug-and-Play (expeditionary module)",
         asda="Act (divert operations) + Adapt ( austere reactivation)", lvc="Constructive (contingency node)", tier=3),
    # ---- Guam（1）----
    dict(crs_no=29, id="GU-BLAZ", name="Marine Corps Base Camp Blaz", name_cn="布拉兹营",
         country="Guam", region="Guam", service="Marine Corps", us_territory=True, dod_operated=True,
         lat=13.5336, lon=144.8181, unit="3rd Marine Litteral Regiment support",
         role="First new Marine base since 1952, 3rd MLR staging for first island chain ops",
         dtb="Battle Network (USMC forward node) + Plug-and-Play (MLR expeditionary modules)",
         asda="Act (littoral deployment) + Adapt (ACE dispersal)", lvc="Live", tier=2),
    # ---- Marshall Islands（1）----
    dict(crs_no=31, id="MH-KWAJALEIN", name="Army Garrison-Kwajalein Atoll", name_cn="夸贾林环礁陆军驻地",
         country="Marshall Islands", region="Marshall Islands", service="Army", us_territory=False, dod_operated=True,
         lat=8.7197, lon=167.7325, unit="USAG-KA, Reagan Test Site",
         role="Ronald Reagan Ballistic Missile Defense Test Site, space surveillance (GEODSS)",
         dtb="War Engine (test range) + Battle Network (space surveillance)",
         asda="Sense (test tracking) + Act (test launches)", lvc="Live+Constructive", tier=3),
    # ---- Japan Mainland（4）----
    dict(crs_no=32, id="JP-ZAMA", name="Camp Zama", name_cn="座间营",
         country="Japan", region="Japan-Central", service="Army", us_territory=False, dod_operated=True,
         lat=35.4872, lon=139.4125, unit="US Army Japan HQ, I Corps (Forward)",
         role="USARJ command hub, I Corps forward CP, JGSDF bilateral coordination",
         dtb="Battle Network (army C2) + Plug-and-Play (forward CP modules)",
         asda="Decide (army command) + Act (ground deployment)", lvc="Live", tier=2),
    dict(crs_no=33, id="JP-SHARIKI", name="Shariki Communications Site", name_cn="尻労通信所",
         country="Japan", region="Japan-North", service="Army", us_territory=False, dod_operated=True,
         lat=40.8578, lon=140.3450, unit="10th Missile Defense Battery",
         role="AN/TPY-2 X-band radar, Japan Sea / DPRK missile early warning",
         dtb="Battle Network (BMD sensor net) + War Engine (radar model)",
         asda="Sense (missile tracking) + Decide (cue interceptors)", lvc="Live", tier=3),
    dict(crs_no=34, id="JP-KYOGAMISAKI", name="Kyogamisaki Communications Site", name_cn="经ヶ岬通信所",
         country="Japan", region="Japan-Central", service="Army", us_territory=False, dod_operated=True,
         lat=35.7658, lon=135.1955, unit="14th Missile Defense Battery",
         role="AN/TPY-2 X-band radar, Japan Sea western approach early warning",
         dtb="Battle Network (BMD sensor net) + War Engine (radar model)",
         asda="Sense (missile tracking) + Decide (cue interceptors)", lvc="Live", tier=3),
    dict(crs_no=37, id="JP-ATSUGI", name="Naval Air Facility Atsugi", name_cn="厚木海军航空设施",
         country="Japan", region="Japan-Central", service="Navy", us_territory=False, dod_operated=True,
         lat=35.4533, lon=139.4506, unit="CVW-5 shore base, CTF-72 patrol",
         role="Carrier Air Wing 5 shore infrastructure, P-8A/MQ-4C support",
         dtb="Battle Network (naval air node) + Plug-and-Play (CVW modules)",
         asda="Act (carrier air ops) + Sense (maritime patrol)", lvc="Live", tier=2),
    # ---- Japan Okinawa（2）----
    dict(crs_no=41, id="JP-OKINAWA", name="Army Garrison Okinawa (Torii Station)", name_cn="托里站",
         country="Japan", region="Japan-Okinawa", service="Army", us_territory=False, dod_operated=True,
         lat=26.3319, lon=127.8628, unit="10th Support Group, 1st SFG (A)",
         role="Army special forces, SIGINT, Okinawa western training areas",
         dtb="Battle Network (army node) + Application Store (SOF packages)",
         asda="Sense (SIGINT) + Act (special operations)", lvc="Live", tier=2),
    dict(crs_no=42, id="JP-BUTLER", name="Marine Corps Base Camp Butler", name_cn="巴特勒营",
         country="Japan", region="Japan-Okinawa", service="Marine Corps", us_territory=False, dod_operated=True,
         lat=26.2964, lon=127.7703, unit="III MEF HQ, MCB Camp Butler (Foster)",
         role="Okinawa Marine umbrella garrison, III MEF command node",
         dtb="Battle Network (MEF C2) + Plug-and-Play (MEF modules)",
         asda="Decide (MEF command) + Act (amphibious readiness)", lvc="Live", tier=2),
    # ---- Korea（4）----
    dict(crs_no=46, id="KR-DAEGU", name="Army Garrison Daegu", name_cn="大邱陆军驻地",
         country="South Korea", region="Korea", service="Army", us_territory=False, dod_operated=True,
         lat=35.8492, lon=128.6033, unit="19th Sustainment Command, USFK logistics",
         role="USFK peninsula logistics hub, camps Henry/George/Walker",
         dtb="Battle Network (logistics C2) + Plug-and-Play (sustainment modules)",
         asda="Act (sustainment) + Adapt (posture rebalance)", lvc="Live", tier=2),
    dict(crs_no=47, id="KR-YONGSAN", name="Army Garrison Yongsan-Casey", name_cn="龙山-凯西营",
         country="South Korea", region="Korea", service="Army", us_territory=False, dod_operated=True,
         lat=37.5322, lon=126.9942, unit="Eighth Army residual, 2ID area (Camp Casey)",
         role="Seoul legacy garrison + Casey corridor, alliance HQ residual functions",
         dtb="Battle Network (army node) + Plug-and-Play (transitional modules)",
         asda="Decide (alliance coordination) + Adapt (camp consolidation)", lvc="Live", tier=2),
    dict(crs_no=48, id="KR-CHINHAE", name="Fleet Activities Chinhae", name_cn="镇海海军基地",
         country="South Korea", region="Korea", service="Navy", us_territory=False, dod_operated=True,
         lat=35.1136, lon=128.6383, unit="CNFK naval element",
         role="ROK Navy coordination, peninsula littoral support",
         dtb="Battle Network (naval coordination node)",
         asda="Decide (naval coordination) + Sense (littoral picture)", lvc="Live", tier=2),
    dict(crs_no=49, id="KR-MUJUK", name="Marine Corps Installations Camp Mujuk", name_cn="无敌营",
         country="South Korea", region="Korea", service="Marine Corps", us_territory=False, dod_operated=True,
         lat=35.9577, lon=129.4252, unit="Marine Corps Installations Pacific",
         role="USMC Korea rotational training base, near 1st ROK Marine Division (Pohang)",
         dtb="Battle Network (USMC training node) + Plug-and-Play (rotational modules)",
         asda="Act (rotational training) + Adapt (bilateral readiness)", lvc="Live", tier=2),
    # ---- Philippines（6）----
    dict(crs_no=52, id="PH-BAUTISTA", name="Antonio Bautista Air Base", name_cn="安东尼奥·包蒂斯塔空军基地",
         country="Philippines", region="Philippines", service="N/A (PAF joint use)", us_territory=False, dod_operated=False,
         lat=9.7408, lon=118.7600, unit="EDCA site (PAF 560th Air Base Group)",
         role="Palawan SCS-facing ISR, nearest EDCA site to Spratlys",
         dtb="Battle Network (forward access node) + Application Store (ISR packages)",
         asda="Sense (SCS ISR) + Adapt (rotational access)", lvc="Live (rotational)", tier=4),
    dict(crs_no=53, id="PH-BASA", name="Basa Air Base", name_cn="巴萨空军基地",
         country="Philippines", region="Philippines", service="N/A (PAF joint use)", us_territory=False, dod_operated=False,
         lat=14.9867, lon=120.5475, unit="EDCA site (PAF 5th Fighter Wing)",
         role="Northern Luzon air hub, PDI-funded expansion, F-16 bilateral ops",
         dtb="Battle Network (air access node) + Plug-and-Play (expeditionary modules)",
         asda="Act (air ops surge) + Adapt (access uncertainty)", lvc="Live (rotational)", tier=4),
    dict(crs_no=54, id="PH-MAGSAYSAY", name="Fort Magsaysay", name_cn="麦格赛赛堡",
         country="Philippines", region="Philippines", service="N/A (PA joint use)", us_territory=False, dod_operated=False,
         lat=15.4142, lon=121.1086, unit="EDCA site (PA 7th ID)",
         role="Largest Philippine army training area, humanitarian staging",
         dtb="Battle Network (training access) + Plug-and-Play (army modules)",
         asda="Act (training) + Adapt (joint readiness)", lvc="Live (rotational)", tier=4),
    dict(crs_no=55, id="PH-LUMBIA", name="Lumbia Airport", name_cn="伦比亚机场",
         country="Philippines", region="Philippines", service="N/A (PAF joint use)", us_territory=False, dod_operated=False,
         lat=8.6122, lon=124.4553, unit="EDCA site (PAF)",
         role="Mindanao logistics, humanitarian assistance staging",
         dtb="Battle Network (south node) + Plug-and-Play (HA modules)",
         asda="Act (logistics) + Adapt (contingency response)", lvc="Live (rotational)", tier=4),
    dict(crs_no=56, id="PH-EBUEN", name="Benito Ebuen Air Base", name_cn="贝尼托·埃布恩空军基地",
         country="Philippines", region="Philippines", service="N/A (PAF joint use)", us_territory=False, dod_operated=False,
         lat=10.3075, lon=123.9792, unit="EDCA site (PAF Mactan)",
         role="Cebu 3300m runway (2nd longest in PH), central PH power projection",
         dtb="Battle Network (central node) + Plug-and-Play (airlift modules)",
         asda="Act (airlift) + Adapt (surge access)", lvc="Live (rotational)", tier=4),
    dict(crs_no=59, id="PH-MELCHOR", name="Camp Melchor Dela Cruz", name_cn="梅尔乔·德拉克鲁斯营",
         country="Philippines", region="Philippines", service="N/A (PA joint use)", us_territory=False, dod_operated=False,
         lat=17.0730, lon=121.8662, unit="EDCA site (PA 5th ID, Gamu Isabela)",
         role="Northern Luzon Cagayan Valley, facing Luzon Strait south",
         dtb="Battle Network (north node) + Plug-and-Play (army modules)",
         asda="Sense (Luzon Strait ISR) + Act (training)", lvc="Live (rotational)", tier=4),
    # ---- Singapore（1）----
    dict(crs_no=61, id="SG-NRCS", name="Navy Region Center Singapore", name_cn="新加坡海军区域中心",
         country="Singapore", region="Singapore", service="Navy", us_territory=False, dod_operated=False,
         lat=1.4517, lon=103.8103, unit="COMLOG Western Pacific",
         role="Combat Logistics Force western Pacific hub, LCS rotation support (Sembawang)",
         dtb="Battle Network (logistics hub) + Plug-and-Play (CLF modules)",
         asda="Act (fleet logistics) + Adapt (rotation support)", lvc="Live", tier=2),
    # ---- Australia（2）----
    dict(crs_no=63, id="AU-ROBERTSON", name="Robertson Barracks", name_cn="罗伯逊兵营",
         country="Australia", region="Australia", service="N/A (Australian Army joint)", us_territory=False, dod_operated=False,
         lat=-12.4373, lon=130.9755, unit="Australian 1st Brigade, MRF-D training",
         role="Australian Army 1st BDE base, US rotational training (Holtze/Darwin)",
         dtb="Battle Network (allied node) + Plug-and-Play (rotational modules)",
         asda="Act (combined training) + Adapt (allied posture)", lvc="Live (rotational)", tier=4),
    dict(crs_no=65, id="AU-HOLT", name="Naval Communication Station Harold E. Holt", name_cn="哈罗德·霍尔特海军通信站",
         country="Australia", region="Australia", service="Navy", us_territory=False, dod_operated=True,
         lat=-21.8164, lon=114.1667, unit="USN/RAAN joint (North West Cape)",
         role="VLF/ULF submarine communications, Indian Ocean undersea command link",
         dtb="Battle Network (strategic comms layer)",
         asda="Sense (undersea comms) + Decide (SSN tasking)", lvc="Live", tier=3),
    # ---- BIOT（1）----
    dict(crs_no=66, id="IO-DIEGOGARCIA", name="Naval Support Facility Diego Garcia", name_cn="迪戈加西亚海军支援设施",
         country="British Indian Ocean Territory", region="Diego Garcia", service="Navy", us_territory=False, dod_operated=True,
         lat=-7.3136, lon=72.4122, unit="NSF Diego Garcia, forward deployed task force support",
         role="Strategic bomber forward node, Indian Ocean submarine base, junction of Indo-Pacific & CENTCOM",
         dtb="War Engine (strategic strike node) + Battle Network + Plug-and-Play (bomber modules)",
         asda="Act (strategic strike) + Adapt (bomber rotation)", lvc="Live", tier=1, ace_hub=True),
]

# 现有 22 基地中与 CRS Table A-1 的映射（用于 crs_no 注入；Tinian 不在 A-1 中）
EXISTING_CRS_MAP = {
    "JP-MISAWA": 40, "JP-YOKOTA": 39, "JP-KADENA": 44, "JP-FUTENMA": 43,
    "JP-SASEBO": 36, "JP-YOKOSUKA": 35, "JP-IWAKUNI": 38,
    "GU-ANDERSEN": 30, "GU-APRA": 28,
    "KR-HUMPHREYS": 45, "KR-OSAN": 50, "KR-KUNSAN": 51,
    "HI-PHICKAM": 24, "HI-SCHOFIELD": 21, "AK-JBER": 3, "AK-EIELSON": 4,
    "AU-DARWIN": 62, "AU-TINDAL": 64,
    "PH-CAMILO": 57, "PH-LALLO": 58, "PH-BALABAC": 60,
    "CNMI-TINIAN": None,
}

# 现有基地 Tier 重划（与 v2 四级体系对齐）
EXISTING_TIER_OVERRIDE = {
    "JP-YOKOTA": 1, "JP-KADENA": 1, "JP-YOKOSUKA": 1, "GU-ANDERSEN": 1,
    "KR-HUMPHREYS": 1, "KR-OSAN": 2, "HI-PHICKAM": 1, "AK-JBER": 1,
    "JP-MISAWA": 2, "JP-FUTENMA": 2, "JP-SASEBO": 2, "JP-IWAKUNI": 2,
    "GU-APRA": 2, "KR-KUNSAN": 2, "HI-SCHOFIELD": 2, "AK-EIELSON": 2,
    "AU-DARWIN": 4, "AU-TINDAL": 4, "CNMI-TINIAN": 3,
    "PH-CAMILO": 4, "PH-LALLO": 4, "PH-BALABAC": 4,
}

TIER_LABELS = {
    1: "Tier 1 战略核心基地 (Strategic Core)",
    2: "Tier 2 主要作战基地 (Main Operating Base)",
    3: "Tier 3 专用功能站点 (Specialized Site)",
    4: "Tier 4 准入/轮换基地 (Access & Rotational)",
}

# CRS 服务名 -> 标准军种缩写
SERVICE_ABBR = {
    "Army": "US Army", "Navy": "USN", "Air Force": "USAF",
    "Marine Corps": "USMC", "Space Force": "USSF",
    "Joint (Army and Air Force)": "US Army/USAF",
    "Joint (Navy and Air Force)": "USN/USAF",
    "N/A (PAF joint use)": "PAF/US (EDCA)",
    "N/A (PA joint use)": "PA/US (EDCA)",
    "N/A (Australian Army joint)": "Australian Army/US",
}

# 不在 FY2024 BSR（联邦主报告）中的实体及原因——显式数据治理标注，杜绝"静默缺数据"
HOST_NATION_FACILITIES = {
    # 菲律宾 EDCA 9 站点：东道国设施，美国仅有准入权，无 US DoD 持有资产
    "PH-BAUTISTA", "PH-BASA", "PH-MAGSAYSAY", "PH-LUMBIA", "PH-EBUEN",
    "PH-MELCHOR", "PH-CAMILO", "PH-LALLO", "PH-BALABAC",
    # 澳大利亚陆军自有兵营，美军仅轮换进驻（MRF-D），无 US DoD 持有资产
    "AU-ROBERTSON",
}
NOT_SEPARATELY_LISTED = {
    # Wheeler AAF 在 FY2024 BSR 中并入 USAG Hawaii（Schofield 综合），无独立行
    "HI-WHEELER",
}


def bsr_status_of(eid: str) -> str:
    """未匹配 BSR 时的显式原因标注。出现 no_match 视为构建失败（硬断言拦截）。"""
    if eid in HOST_NATION_FACILITIES:
        return "host_nation_facility"
    if eid in NOT_SEPARATELY_LISTED:
        return "not_separately_listed"
    return "no_match"

# =====================================================================
# FY2024 Excel 统计融合
# =====================================================================

def norm_name(s: str) -> str:
    """规范化站点名以便匹配。"""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    # 展开缩写
    repl = {
        "afb": "air force base", "sfb": "space force base",
        "mcas": "marine corps air station", "mcb": "marine corps base",
        "nas": "naval air station", "navsta": "naval station",
        "ns": "naval station", "naf": "naval air facility",
        "jrb": "joint reserve base", "jb": "joint base",
        "angs": "air national guard station", "raaf": "royal australian air force",
        "usaf": "air force", "usn": "navy", "usmc": "marine corps",
    }
    tokens = [repl.get(t, t) for t in s.split()]
    return " ".join(tokens)


def load_excel_stats():
    """读取 Federal DoD Main Report，返回 (rows_by_state_site, all_prv_sorted)。"""
    wb = openpyxl.load_workbook(EXCEL, read_only=True)
    ws = wb["Federal DoD Main Report"]
    rows = list(ws.iter_rows(values_only=True))

    header_idx = None
    for i, r in enumerate(rows):
        if r and r[0] == "Country/State":
            header_idx = i
            break
    assert header_idx is not None, "header not found"

    sites = {}          # (state_lower, norm_site) -> dict
    prv_list = []       # (prv, state, site) 全表 PRV 排序
    for r in rows[header_idx + 1:]:
        if not r or r[0] is None or r[1] is None:
            continue
        state = str(r[0]).strip()
        site = str(r[1]).strip()
        try:
            prv = float(r[12]) if r[12] is not None else 0.0
        except (TypeError, ValueError):
            prv = 0.0
        rec = dict(
            state=state, site=site,
            bldgs_owned=int(r[4]) if r[4] not in (None, "") else 0,
            bldgs_leased=int(r[6]) if r[6] not in (None, "") else 0,
            bldgs_other=int(r[8]) if r[8] not in (None, "") else 0,
            total_acres=float(r[11]) if r[11] not in (None, "") else 0.0,
            prv_m=round(prv, 1),
        )
        key = (state.lower(), norm_name(site))
        # 同名站点合并（保留 PRV/面积最大者作为主记录，但累计）
        if key in sites:
            p = sites[key]
            for f in ("bldgs_owned", "bldgs_leased", "bldgs_other"):
                p[f] += rec[f]
            p["total_acres"] = round(p["total_acres"] + rec["total_acres"], 1)
            p["prv_m"] = round(p["prv_m"] + rec["prv_m"], 1)
        else:
            sites[key] = rec
        if prv > 0:
            prv_list.append((prv, state, site))

    prv_list.sort(key=lambda x: -x[0])
    wb.close()
    return sites, prv_list


def compute_quartile_cutoffs(prv_list):
    """按 BSR 定义：PRV 降序累计，每 $578.3B 一档。返回 3 个累计值阈值（单位 $M）。"""
    total_m = 2313230129595.76 / 1e6  # 总 PRV $2.313T -> $M
    q = total_m / 4.0
    cutoffs = []
    cum = 0.0
    target = q
    for prv, _, _ in prv_list:
        cum += prv
        while cum >= target and len(cutoffs) < 3:
            cutoffs.append(prv)
            target += q
    # cutoffs[i] = 第 (i+1) 档的最低 PRV 值
    return cutoffs


def prv_quartile_of(prv_m: float, cutoffs, matched: bool):
    if not matched:
        return None
    if prv_m <= 0:
        return "Land Only"
    if prv_m >= cutoffs[0]:
        return "1st Quartile"
    if prv_m >= cutoffs[1]:
        return "2nd Quartile"
    if prv_m >= cutoffs[2]:
        return "3rd Quartile"
    return "4th Quartile"


# 匹配别名（Excel 站点名 -> 我们的实体名片段）
ALIASES = {
    # (state_lower, norm片段集合) -> 实体 id
    ("alaska", "fort wainwright"): "AK-WAINWRIGHT",
    ("alaska", "fort greely"): "AK-GREELEY",
    ("alaska", "eareckson"): "AK-EARECKSON",
    ("alaska", "clear"): "AK-CLEAR",
    # JBLM 在 FY2024 BSR 中为 "Fort Lewis" 行（McChord 未单列）
    ("washington", "fort lewis"): "WA-JBLM",
    ("washington", "kitsap"): "WA-KITSAP",
    ("washington", "everett"): "WA-EVERETT",
    ("washington", "whidbey"): "WA-WHIDBEY",
    ("washington", "fairchild"): "WA-FAIRCHILD",
    ("california", "ventura"): "CA-VENTURA",
    ("california", "coronado"): "CA-CORONADO",
    ("california", "san diego"): "CA-SANDIEGO",
    ("california", "point loma"): "CA-POINTLOMA",
    ("california", "miramar"): "CA-MIRAMAR",
    ("california", "pendleton"): "CA-PENDLETON",
    ("california", "beale"): "CA-BEALE",
    ("california", "travis"): "CA-TRAVIS",
    ("california", "vandenberg"): "CA-VANDENBERG",
    ("hawaii", "shafter"): "HI-SHAFTER",
    ("hawaii", "wheeler"): "HI-WHEELER",
    # PMRF：FY2024 BSR 站点名为 "PACMISRANFAC Hawaiian Area"（太平洋导弹靶场官方缩写）
    # 及其 Kauai 跟踪站 "Makaha Ridge"
    ("hawaii", "barking sands"): "HI-PMRF",
    ("hawaii", "pacmisranfac"): "HI-PMRF",
    ("hawaii", "makaha ridge"): "HI-PMRF",
    # MCB Hawaii：Kaneohe/Manana/Pearl City/Puuloa 均归 MCBH。
    # 注意 norm_name 会把 "MCB" 展开为 "marine corps base"，别名用展开后片段
    ("hawaii", "marine corps base hawaii"): "HI-MCBH",
    ("wake island", "wake"): "WL-WAKE",
    ("guam", "blaz"): "GU-BLAZ",
    ("guam", "finegayan"): "GU-BLAZ",
    ("marshall islands", "kwajalein"): "MH-KWAJALEIN",
    ("japan", "zama"): "JP-ZAMA",
    ("japan", "shariki"): "JP-SHARIKI",
    ("japan", "kyogamisaki"): "JP-KYOGAMISAKI",
    ("japan", "kyoga"): "JP-KYOGAMISAKI",
    ("japan", "atsugi"): "JP-ATSUGI",
    ("japan", "torii"): "JP-OKINAWA",
    ("japan", "foster"): "JP-BUTLER",
    ("japan", "butler"): "JP-BUTLER",
    ("japan", "kadena"): "JP-KADENA",
    ("japan", "futenma"): "JP-FUTENMA",
    ("japan", "sasebo"): "JP-SASEBO",
    ("japan", "yokosuka"): "JP-YOKOSUKA",
    ("japan", "iwakuni"): "JP-IWAKUNI",
    ("japan", "yokota"): "JP-YOKOTA",
    ("japan", "misawa"): "JP-MISAWA",
    # Excel 中国名为 "Korea, South"（州级小写需完全一致）
    ("korea, south", "daegu"): "KR-DAEGU",
    ("korea, south", "taegu"): "KR-DAEGU",
    ("korea, south", "henry"): "KR-DAEGU",
    ("korea, south", "walker"): "KR-DAEGU",
    ("korea, south", "carroll"): "KR-DAEGU",
    ("korea, south", "casey"): "KR-YONGSAN",
    ("korea, south", "yongsan"): "KR-YONGSAN",
    ("korea, south", "red cloud"): "KR-YONGSAN",
    ("korea, south", "hovey"): "KR-YONGSAN",
    ("korea, south", "stanley"): "KR-YONGSAN",
    ("korea, south", "castle"): "KR-YONGSAN",
    ("korea, south", "chinhae"): "KR-CHINHAE",
    ("korea, south", "jinhae"): "KR-CHINHAE",
    ("korea, south", "mu juk"): "KR-MUJUK",
    ("korea, south", "humphreys"): "KR-HUMPHREYS",
    ("korea, south", "pyongtaek"): "KR-HUMPHREYS",
    # Osan：用完整词组避免误匹配 "Koryosan ASA"（独立站点，含子串 osan）
    ("korea, south", "osan air force base"): "KR-OSAN",
    ("korea, south", "osan ni"): "KR-OSAN",
    ("korea, south", "osan site"): "KR-OSAN",
    ("korea, south", "kunsan"): "KR-KUNSAN",
    ("singapore", "singapore"): "SG-NRCS",
    ("australia", "darwin"): "AU-DARWIN",
    ("australia", "tindal"): "AU-TINDAL",
    ("australia", "robertson"): "AU-ROBERTSON",
    # Harold E. Holt：FY2024 BSR 行为 "NAVCOMMSTA H E Holt Exmouth" 及其
    # 发射/接收天线区（Area A-VLF、Area C-HFR、Exmouth FH Annex）
    ("australia", "holt"): "AU-HOLT",
    ("australia", "area a vlf"): "AU-HOLT",
    ("australia", "area c hfr"): "AU-HOLT",
    ("australia", "exmouth fh"): "AU-HOLT",
    ("diego garcia", "diego garcia"): "IO-DIEGOGARCIA",
    ("northern mariana islands", "tinian"): "CNMI-TINIAN",
    ("northern marianas", "tinian"): "CNMI-TINIAN",
    ("hawaii", "pearl harbor"): "HI-PHICKAM",
    ("hawaii", "hickam"): "HI-PHICKAM",
    ("hawaii", "schofield"): "HI-SCHOFIELD",
    ("alaska", "elmendorf"): "AK-JBER",
    ("alaska", "richardson"): "AK-JBER",
    ("alaska", "eielson"): "AK-EIELSON",
    ("guam", "andersen"): "GU-ANDERSEN",
    ("guam", "naval base guam"): "GU-APRA",
    ("guam", "apra"): "GU-APRA",
    ("guam", "santa ritia"): "GU-APRA",
    ("guam", "santa rita"): "GU-APRA",
    ("northern mariana islands", "saipan"): None,
}


def match_excel(stats_by_key):
    """扫描 Excel 全表，按 (state, 名称片段) 别名映射到实体 id，聚合统计。"""
    result = {}  # id -> merged stats
    for (state_lower, norm_site), rec in stats_by_key.items():
        for (st, frag), eid in ALIASES.items():
            if state_lower == st and frag in norm_site:
                if eid is None:
                    break
                if eid in result:
                    p = result[eid]
                    for f in ("bldgs_owned", "bldgs_leased", "bldgs_other"):
                        p[f] += rec[f]
                    p["total_acres"] = round(p["total_acres"] + rec["total_acres"], 1)
                    p["prv_m"] = round(p["prv_m"] + rec["prv_m"], 1)
                    p["excel_sites"].append(f"{rec['site']} ({rec['state']})")
                else:
                    result[eid] = dict(
                        bldgs_owned=rec["bldgs_owned"], bldgs_leased=rec["bldgs_leased"],
                        bldgs_other=rec["bldgs_other"], total_acres=rec["total_acres"],
                        prv_m=rec["prv_m"], excel_sites=[f"{rec['site']} ({rec['state']})"],
                    )
                break
    return result


# =====================================================================
# 主流程
# =====================================================================

def main():
    # 1. Excel 统计
    print("[1/5] 解析 FY2024 Excel ...")
    stats_by_key, prv_list = load_excel_stats()
    print(f"  Federal DoD Main Report: {len(stats_by_key)} 站点记录, {len(prv_list)} 条正 PRV")
    cutoffs = compute_quartile_cutoffs(prv_list)
    print(f"  PRV 四分位累计阈值: Q1>={cutoffs[0]:.0f}M, Q2>={cutoffs[1]:.0f}M, Q3>={cutoffs[2]:.0f}M")
    excel_match = match_excel(stats_by_key)
    print(f"  匹配到实体: {len(excel_match)}")

    # 2. 现有 22 基地
    print("[2/5] 载入现有 22 基地 ...")
    with open(GEOJSON_V1, "r", encoding="utf-8") as f:
        v1 = json.load(f)
    features = []
    for feat in v1["features"]:
        p = feat["properties"]
        eid = p["id"]
        lon, lat = feat["geometry"]["coordinates"]
        tier = EXISTING_TIER_OVERRIDE.get(eid, 2)
        props = dict(p)  # 保留全部原有字段
        props.update({
            "crs_no": EXISTING_CRS_MAP.get(eid),
            "us_territory": p["country"] in ("USA", "Guam", "CNMI"),
            "dod_operated": p["country"] in ("USA", "Guam", "CNMI", "Japan", "South Korea", "Australia"),
            "tier": tier,
            "tier_label": TIER_LABELS[tier],
            "data_source": "v1 (22-base database, P1-P8)",
        })
        # Excel 统计融合
        m = excel_match.get(eid)
        if m:
            props.update({
                "fy24_total_acres": m["total_acres"],
                "fy24_bldgs_owned": m["bldgs_owned"],
                "fy24_bldgs_leased": m["bldgs_leased"],
                "fy24_bldgs_other": m["bldgs_other"],
                "fy24_prv_musd": m["prv_m"],
                "fy24_prv_quartile": prv_quartile_of(m["prv_m"], cutoffs, matched=True),
                "fy24_bsr_site": "; ".join(m["excel_sites"][:4]),
                "fy24_bsr_status": "matched",
            })
        else:
            props.update({
                "fy24_total_acres": None, "fy24_bldgs_owned": None, "fy24_bldgs_leased": None,
                "fy24_bldgs_other": None, "fy24_prv_musd": None, "fy24_prv_quartile": None,
                "fy24_bsr_site": None,
                "fy24_bsr_status": bsr_status_of(eid),
            })
        # 政治准入不确定性（非美国领土 => 进入 ASDA-Adapt）
        props["access_uncertainty"] = (
            "host_nation" if not props["us_territory"]
            else ("territory" if p["country"] in ("Guam", "CNMI") else "sovereign")
        )
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]},
            "properties": props,
        })

    # 3. 追加 45 个新站点
    print("[3/5] 构造 45 个新站点 ...")
    for s in NEW_SITES:
        tier = s["tier"]
        props = {
            "id": s["id"], "name": s["name"], "name_cn": s["name_cn"],
            "country": s["country"], "region": s["region"],
            "branch": SERVICE_ABBR.get(s["service"], s["service"]),
            "crs_service": s["service"],
            "crs_no": s["crs_no"],
            "unit": s["unit"],
            "aircraft": "N/A", "runway_m": 0, "personnel": 0,
            "facility_code": f"CRS A-1 #{s['crs_no']}",
            "role": s["role"],
            "vs26_role": s["role"],
            "scars": False,
            "lvc_layer": s["lvc"],
            "ace_hub": s.get("ace_hub", False),
            "dtb_mapping": s["dtb"],
            "asda_mapping": s["asda"],
            "us_territory": s["us_territory"],
            "dod_operated": s["dod_operated"],
            "tier": tier,
            "tier_label": TIER_LABELS[tier],
            "access_uncertainty": (
                "host_nation" if not s["us_territory"]
                else ("territory" if s["country"] in ("Guam", "USA (Wake Island)") else "sovereign")
            ),
            "data_source": "CRS Table A-1 + FY2024 BSR + web-verified coords",
        }
        m = excel_match.get(s["id"])
        if m:
            props.update({
                "fy24_total_acres": m["total_acres"],
                "fy24_bldgs_owned": m["bldgs_owned"],
                "fy24_bldgs_leased": m["bldgs_leased"],
                "fy24_bldgs_other": m["bldgs_other"],
                "fy24_prv_musd": m["prv_m"],
                "fy24_prv_quartile": prv_quartile_of(m["prv_m"], cutoffs, matched=True),
                "fy24_bsr_site": "; ".join(m["excel_sites"][:4]),
                "fy24_bsr_status": "matched",
            })
        else:
            props.update({
                "fy24_total_acres": None, "fy24_bldgs_owned": None, "fy24_bldgs_leased": None,
                "fy24_bldgs_other": None, "fy24_prv_musd": None, "fy24_prv_quartile": None,
                "fy24_bsr_site": None,
                "fy24_bsr_status": bsr_status_of(s["id"]),
            })
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                        "coordinates": [round(s["lon"], 4), round(s["lat"], 4)]},
            "properties": props,
        })

    # 4. 一致性校验
    print("[4/5] 校验 ...")
    ids = [f["properties"]["id"] for f in features]
    assert len(ids) == len(set(ids)), "重复 id"
    assert len(features) == 67, f"实体数 {len(features)} != 67"
    crs_covered = {p["crs_no"] for p in (f["properties"] for f in features) if p.get("crs_no")}
    missing = set(range(1, 67)) - crs_covered
    assert not missing, f"CRS A-1 缺失编号: {sorted(missing)}"
    print(f"  实体 67, CRS A-1 编号 66/66 全覆盖, 去重通过")

    # BSR 状态校验：不允许出现未解释的 no_match
    no_match = [f["properties"]["id"] for f in features
                if f["properties"]["fy24_bsr_status"] == "no_match"]
    assert not no_match, f"存在未解释的 BSR no_match 实体: {no_match}"
    matched_n = sum(1 for f in features if f["properties"]["fy24_prv_musd"] is not None)
    status_n = {}
    for f in features:
        st = f["properties"]["fy24_bsr_status"]
        status_n[st] = status_n.get(st, 0) + 1
    print(f"  FY2024 BSR 统计融合: {matched_n}/67 实体 | 状态分布: {status_n}")

    # Tier 分布（用于 metadata 动态计数）
    tier_counts = {}
    for f in features:
        t = f["properties"]["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    # 5. 输出
    print("[5/5] 写入 indopacom_bases_v2.geojson ...")
    v2 = {
        "type": "FeatureCollection",
        "name": "INDOPACOM Military Sites v2 (CRS Table A-1 + FY2024 BSR)",
        "crs": v1["crs"],
        "metadata": {
            "generated": "P9 database upgrade, DTC 2026",
            "entities": 67,
            "sources": [
                "CRS R47589 (2023-06-06) Table A-1: 66 U.S. defense sites in Indo-Pacific",
                "DoD Base Structure Report FY2024 (PRV/acreage/buildings)",
                "Open-source coordinates cross-verified (4 dual-source corrections)",
            ],
            "tier_system": {
                "1": f"Strategic Core ({tier_counts.get(1, 0)})",
                "2": f"Main Operating Base ({tier_counts.get(2, 0)})",
                "3": f"Specialized Site ({tier_counts.get(3, 0)})",
                "4": f"Access & Rotational ({tier_counts.get(4, 0)})",
            },
            "fields_new": [
                "crs_no", "crs_service", "us_territory", "dod_operated",
                "tier", "tier_label", "access_uncertainty",
                "fy24_total_acres", "fy24_bldgs_owned", "fy24_bldgs_leased",
                "fy24_bldgs_other", "fy24_prv_musd", "fy24_prv_quartile",
                "fy24_bsr_site", "fy24_bsr_status",
            ],
            "bsr_status_legend": {
                "matched": "已匹配 FY2024 联邦主报告站点（含 PRV 四分位）",
                "host_nation_facility": "东道国自有设施（菲 EDCA / 澳陆军兵营），无 US DoD 持有资产",
                "not_separately_listed": "FY2024 BSR 未单列（Wheeler AAF 并入 USAG Hawaii）",
            },
        },
        "features": features,
    }
    with open(GEOJSON_V2, "w", encoding="utf-8") as f:
        json.dump(v2, f, ensure_ascii=False, indent=2)
    print(f"  写入完成: {GEOJSON_V2} ({len(json.dumps(v2))//1024} KB)")

    # 汇总
    print()
    print("=== 汇总 ===")
    for t in (1, 2, 3, 4):
        n = sum(1 for f in features if f["properties"]["tier"] == t)
        print(f"  {TIER_LABELS[t]}: {n}")
    qn = {}
    for f in features:
        q = f["properties"]["fy24_prv_quartile"]
        if q:
            qn[q] = qn.get(q, 0) + 1
    print(f"  PRV 四分位分布: {qn}")
    unmatched = [(f["properties"]["id"], f["properties"]["fy24_bsr_status"])
                for f in features if f["properties"]["fy24_prv_musd"] is None]
    print(f"  无 BSR 统计实体（均有显式原因标注）: {unmatched}")


if __name__ == "__main__":
    main()
