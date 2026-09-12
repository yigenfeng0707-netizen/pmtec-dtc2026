#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P9.6 地图与工程更新
- 读取 indopacom_bases_v2.geojson（67 实体：CRS Table A-1 66 站点 + Tinian）
- 生成 Leaflet 交互地图 INDOPACOM-Bases-Map.html：
  Tier 分层渲染（4 级符号）+ 军种/准入双模式着色切换 + FY2024 数据弹窗
- 重新生成 QGIS 工程 INDOPACOM-Bases.qgs（指向 v2 数据，按 Tier 分级符号）
"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = "D:/APPs/数字孪生挑战赛"
GEOJSON_V2 = f"{BASE_DIR}/indopacom_bases_v2.geojson"
MAP_HTML = f"{BASE_DIR}/INDOPACOM-Bases-Map.html"
QGS_FILE = f"{BASE_DIR}/INDOPACOM-Bases.qgs"

# ============================================================
# 军种着色（P9.6：按军种着色切换）
# ============================================================
SERVICE_COLORS = {
    "US Army": "#66BB6A",
    "USN": "#1E88E5",
    "USAF": "#4FC3F7",
    "USMC": "#EF5350",
    "USSF": "#AB47BC",
    "USN/USAF": "#26C6DA",
    "USAF/US Army": "#26C6DA",
    "US Army/USAF": "#26C6DA",
    "RAAF": "#FFA726",
    "RAAF/USMC": "#FFA726",
    "PAF/US (EDCA)": "#FFA726",
    "PA/US (EDCA)": "#FFA726",
    "Australian Army/US": "#FFA726",
}
DEFAULT_COLOR = "#B0BEC5"

ACCESS_COLORS = {
    "sovereign": "#66BB6A",      # 美国主权
    "territory": "#FFB74D",       # 美国领地/海外领土
    "host_nation": "#FF7043",     # 盟友东道国（准入不确定性）
}

TIER_INFO = {
    1: ("Tier 1 战略核心", "Strategic Core"),
    2: ("Tier 2 主要作战基地", "Main Operating Base"),
    3: ("Tier 3 专用功能站点", "Specialized Site"),
    4: ("Tier 4 准入/轮换", "Access & Rotational"),
}

with open(GEOJSON_V2, encoding="utf-8") as f:
    gj = json.load(f)
features = gj["features"]


def fmt_prv(v):
    if v is None:
        return "—"
    return f"${v:,.0f}M"


def make_popup(p):
    """FY2024 + CRS 富信息弹窗。"""
    prv = fmt_prv(p.get("fy24_prv_musd"))
    quart = p.get("fy24_prv_quartile") or "—"
    acres = p.get("fy24_total_acres")
    acres_s = f"{acres:,.0f}" if acres is not None else "—"
    owned = p.get("fy24_bldgs_owned")
    leased = p.get("fy24_bldgs_leased")
    bldgs = "—" if owned is None else f"{owned:,}" + (f" (+{leased:,} 租用)" if leased else "")
    access = p.get("access_uncertainty")
    access_cn = {"sovereign": "美国主权", "territory": "美国领地", "host_nation": "盟友东道国"}.get(access, "—")
    crs_no = p.get("crs_no")
    crs_s = f"#{crs_no}" if crs_no else "CNMI 保留"
    tier = p.get("tier")
    t_cn, t_en = TIER_INFO.get(tier, ("?", "?"))
    personnel = p.get("personnel")
    per_s = f"{personnel:,}" if personnel else "轮换/分遣"
    runway = p.get("runway_m")
    rw_s = f"{runway:,} m" if runway else "—"

    rows = [
        ("CRS 编号", crs_s),
        ("军种", p.get("branch", "—")),
        ("单位", p.get("unit", "—")),
        ("人员", per_s),
        ("跑道", rw_s),
        ("国家/区域", f'{p.get("country", "—")} / {p.get("region", "—")}'),
        ("FY2024 PRV", prv),
        ("PRV 分位", str(quart)),
        ("占地(英亩)", acres_s),
        ("建筑物", bldgs),
        ("BSR 匹配", str(p.get("fy24_bsr_status", "—"))),
        ("准入属性", access_cn),
        ("分级", f"{tier} — {t_cn}"),
        ("职能", p.get("role", "—")),
        ("VS26 角色", p.get("vs26_role", "—")),
        ("LVC 层", p.get("lvc_layer", "—")),
        ("DTB 映射", p.get("dtb_mapping", "—")),
        ("ASDA 映射", p.get("asda_mapping", "—")),
    ]
    trs = "".join(
        f'<tr><td style="color:#8fa3b8;padding:2px 6px;white-space:nowrap">{k}</td>'
        f'<td style="padding:2px 6px">{v}</td></tr>'
        for k, v in rows
    )
    return (
        f'<div style="min-width:380px;font-size:12px;line-height:1.55">'
        f'<h3 style="margin:0 0 2px 0;color:#ffb347">{p.get("name","")}</h3>'
        f'<div style="color:#8fa3b8;margin-bottom:6px">{p.get("name_cn","")} | '
        f'<span style="color:#4FC3F7">{t_en}</span></div>'
        f'<table style="border-collapse:collapse;width:100%">{trs}</table>'
        f'<div style="margin-top:6px;color:#5d7285;font-size:10px">数据源：CRS R47589 Table A-1 + '
        f'DoD FY2024 Base Structure Report</div></div>'
    )


# ---- 站点 JS 数据 ----
js_sites = []
for feat in features:
    p = feat["properties"]
    coords = feat["geometry"]["coordinates"]
    branch = p.get("branch", "")
    svc_color = SERVICE_COLORS.get(branch, DEFAULT_COLOR)
    access = p.get("access_uncertainty", "sovereign")
    acc_color = ACCESS_COLORS.get(access, DEFAULT_COLOR)
    js_sites.append({
        "lat": coords[1],
        "lon": coords[0],
        "name": p.get("name", ""),
        "name_cn": p.get("name_cn", ""),
        "tier": p.get("tier", 2),
        "branch": branch,
        "region": p.get("region", ""),
        "country": p.get("country", ""),
        "svc_color": svc_color,
        "acc_color": acc_color,
        "ace_hub": bool(p.get("ace_hub")),
        "ally": access == "host_nation",
        "sovereign": access in ("sovereign", "territory"),
        "edca": "EDCA" in branch or p.get("country") == "Philippines",
        "fy24": p.get("fy24_bsr_status") == "matched",
        "popup": make_popup(p),
    })

js_data = json.dumps(js_sites, ensure_ascii=False)

n = len(js_sites)
t1 = sum(1 for s in js_sites if s["tier"] == 1)
t2 = sum(1 for s in js_sites if s["tier"] == 2)
t3 = sum(1 for s in js_sites if s["tier"] == 3)
t4 = sum(1 for s in js_sites if s["tier"] == 4)
n_ally = sum(1 for s in js_sites if s["ally"])
n_hub = sum(1 for s in js_sites if s["ace_hub"])
n_fy24 = sum(1 for s in js_sites if s["fy24"])

# ---- 国家分组图例 ----
from collections import Counter, OrderedDict
country_order = ["USA", "Guam", "CNMI", "USA (Wake Island)", "Marshall Islands",
                 "Japan", "South Korea", "Philippines", "Australia", "Singapore",
                 "British Indian Ocean Territory"]
country_cn = {
    "USA": "美国本土", "Guam": "关岛", "CNMI": "北马里亚纳", "USA (Wake Island)": "威克岛",
    "Marshall Islands": "马绍尔群岛", "Japan": "日本", "South Korea": "韩国",
    "Philippines": "菲律宾 (EDCA)", "Australia": "澳大利亚", "Singapore": "新加坡",
    "British Indian Ocean Territory": "迪戈加西亚",
}
cc = Counter(s["country"] for s in js_sites)
legend_items = "".join(
    f'<div style="display:flex;justify-content:space-between;margin:2px 0">'
    f'<span style="font-size:11px;color:#cfd8e3">{country_cn.get(c, c)}</span>'
    f'<span style="font-size:11px;color:#6f8296">{cc[c]}</span></div>'
    for c in country_order if c in cc
)

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>INDOPACOM Military Sites Map (P9 v2) | DTC 2026</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;overflow:hidden;background:#0a0e14;font-family:"Microsoft YaHei",system-ui,sans-serif;color:#cfd8e3}}
#map{{width:100%;height:100%;position:fixed;inset:0}}
.pane{{position:fixed;background:rgba(10,14,20,.9);border:1px solid rgba(255,255,255,.08);backdrop-filter:blur(14px);border-radius:4px;z-index:1000;box-shadow:0 8px 32px rgba(0,0,0,.6)}}
#title{{left:16px;top:16px;padding:14px 18px;max-width:360px}}
#title h1{{font-size:16px;font-weight:600;letter-spacing:1px;color:#eef3f8;margin-bottom:4px}}
#title h1 b{{color:#ffb347}}
#title .sub{{font-size:10px;letter-spacing:2px;color:#6f8296;text-transform:uppercase;margin-bottom:6px}}
#title .stats{{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0}}
.chip{{font-size:10px;padding:2px 7px;border-radius:9px;background:rgba(79,195,247,.12);border:1px solid rgba(79,195,247,.25);color:#8fd3f4}}
#title .desc{{font-size:11px;color:#93a4b6;line-height:1.6}}
#legend{{left:16px;bottom:16px;padding:12px 16px;max-width:230px;max-height:42vh;overflow-y:auto}}
#legend h3{{font-size:11px;letter-spacing:1.5px;color:#6f8296;margin-bottom:8px}}
#filter{{right:16px;top:16px;padding:12px 14px;width:212px}}
#filter h3{{font-size:11px;letter-spacing:1.5px;color:#6f8296;margin:8px 0 6px}}
.fbtn{{display:block;width:100%;padding:5px 8px;margin:2px 0;font-size:11px;text-align:left;cursor:pointer;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.06);color:#93a4b6;border-radius:2px;transition:.15s}}
.fbtn:hover{{background:rgba(255,255,255,.09);color:#e6eef7}}
.fbtn.active{{background:rgba(255,179,71,.18);border-color:rgba(255,179,71,.3);color:#ffb347}}
.modebtn{{display:inline-block;padding:4px 10px;margin:2px 2px;font-size:11px;cursor:pointer;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:#93a4b6;border-radius:2px}}
.modebtn.active{{background:rgba(102,187,106,.16);border-color:rgba(102,187,106,.35);color:#a5d6a7}}
#counter{{right:16px;bottom:16px;padding:8px 14px;font-size:11px;color:#8fd3f4}}
#counter b{{color:#ffb347;font-size:14px}}
.leaflet-popup-content-wrapper{{background:rgba(10,14,20,.96);color:#cfd8e3;border:1px solid rgba(255,255,255,.1)}}
.leaflet-popup-tip{{background:rgba(10,14,20,.96)}}
</style>
</head>
<body>
<div id="map"></div>
<div class="pane" id="title">
<h1>INDOPACOM <b>Military Sites</b></h1>
<div class="sub">DTC 2026 | Level 1 | P9 权威数据库 v2</div>
<div class="stats">
<span class="chip">{n} 实体 (CRS 66 + Tinian)</span>
<span class="chip">Tier1 {t1}</span><span class="chip">Tier2 {t2}</span>
<span class="chip">Tier3 {t3}</span><span class="chip">Tier4 {t4}</span>
</div>
<div class="desc">基于 CRS R47589 Table A-1 权威清单 + DoD FY2024 基地结构报告。
按 Tier 四级分层渲染；军种/准入双模式着色；FY2024 PRV 价值四分位已融合。
盟友东道国站点（准入不确定性）为 P10 政治建模预留接口。</div>
</div>
<div class="pane" id="legend">
<h3>TIER 分级</h3>
<div style="display:flex;align-items:center;margin:3px 0"><span style="display:inline-block;width:14px;height:14px;border-radius:50%;background:#e65100;border:3px solid #fff;box-shadow:0 0 8px #ff7043"></span><span style="font-size:11px;margin-left:6px">Tier 1 战略核心 ({t1})</span></div>
<div style="display:flex;align-items:center;margin:3px 0"><span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:#4FC3F7;border:2px solid #fff"></span><span style="font-size:11px;margin-left:6px">Tier 2 主要作战基地 ({t2})</span></div>
<div style="display:flex;align-items:center;margin:3px 0"><span style="display:inline-block;width:9px;height:9px;transform:rotate(45deg);background:#9CCC65;border:1px solid #fff"></span><span style="font-size:11px;margin-left:6px">Tier 3 专用功能站点 ({t3})</span></div>
<div style="display:flex;align-items:center;margin:3px 0"><span style="display:inline-block;width:11px;height:11px;border-radius:50%;border:2px dashed #FFA726"></span><span style="font-size:11px;margin-left:6px">Tier 4 准入/轮换 ({t4})</span></div>
<h3>军种着色</h3>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#66BB6A"></span><span style="font-size:10.5px;margin-left:6px">陆军 Army</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#1E88E5"></span><span style="font-size:10.5px;margin-left:6px">海军 Navy</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#4FC3F7"></span><span style="font-size:10.5px;margin-left:6px">空军 Air Force</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#EF5350"></span><span style="font-size:10.5px;margin-left:6px">陆战队 USMC</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#AB47BC"></span><span style="font-size:10.5px;margin-left:6px">太空军 USSF</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#26C6DA"></span><span style="font-size:10.5px;margin-left:6px">联合 Joint</span></div>
<div style="display:flex;align-items:center;margin:2px 0"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#FFA726"></span><span style="font-size:10.5px;margin-left:6px">盟友 Allied</span></div>
<h3>国家/地区 ({len(cc)})</h3>
{legend_items}
</div>
<div class="pane" id="filter">
<h3>着色模式</h3>
<span class="modebtn active" data-mode="service">按军种</span>
<span class="modebtn" data-mode="access">按准入属性</span>
<h3>过滤</h3>
<div class="fbtn active" data-filter="all">全部站点 ({n})</div>
<div class="fbtn" data-filter="t1">Tier 1 战略核心 ({t1})</div>
<div class="fbtn" data-filter="t2">Tier 2 主要作战基地 ({t2})</div>
<div class="fbtn" data-filter="t3">Tier 3 专用功能 ({t3})</div>
<div class="fbtn" data-filter="t4">Tier 4 准入/轮换 ({t4})</div>
<div class="fbtn" data-filter="ace">ACE 枢纽 ({n_hub})</div>
<div class="fbtn" data-filter="ally">盟友东道国站点 ({n_ally})</div>
<div class="fbtn" data-filter="sovereign">美国主权/领地 ({n - n_ally})</div>
<div class="fbtn" data-filter="fy24">FY2024 已匹配 ({n_fy24})</div>
</div>
<div class="pane" id="counter">显示 <b id="cnum">{n}</b> / {n} 站点</div>
<script>
const sites = {js_data};

const map = L.map('map', {{center:[10,150],zoom:3,worldCopyJump:true,minZoom:2,maxZoom:12}});

L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
attribution:'&copy; OpenStreetMap &copy; CARTO',subdomains:'abcd',maxZoom:19
}}).addTo(map);

let colorMode = 'service';
let currentFilter = 'all';
const markers = [];

function markerIcon(s) {{
const c = colorMode === 'service' ? s.svc_color : s.acc_color;
let html;
if (s.tier === 1) {{
  html = '<div style="width:16px;height:16px;border-radius:50%;background:'+c+';border:3px solid #fff;box-shadow:0 0 10px '+c+'"></div>';
}} else if (s.tier === 2) {{
  html = '<div style="width:11px;height:11px;border-radius:50%;background:'+c+';border:2px solid #fff;box-shadow:0 0 5px '+c+'"></div>';
}} else if (s.tier === 3) {{
  html = '<div style="width:10px;height:10px;transform:rotate(45deg);background:'+c+';border:1px solid #fff;margin:1px"></div>';
}} else {{
  html = '<div style="width:11px;height:11px;border-radius:50%;border:2px dashed '+c+'"></div>';
}}
return L.divIcon({{html: html, className: '', iconSize: [18,18], iconAnchor: [9,9]}});
}}

sites.forEach(s => {{
const m = L.marker([s.lat, s.lon], {{icon: markerIcon(s)}}).addTo(map);
m.bindPopup(s.popup, {{maxWidth:420, maxHeight:420}});
markers.push({{marker: m, site: s}});
}});

// Guam-Kadena-Yokota-PearlHarbor 集成链
const chain = [[13.5839,144.9167],[26.3505,127.7686],[35.7447,139.3475],[21.3694,-157.9622]];
L.polyline(chain, {{color:'#ffb347',weight:2,dashArray:'8 6',opacity:.5}}).addTo(map);
// 第二岛链以远纵深链：关岛-威克-夏威夷 / 关岛-迪戈加西亚
L.polyline([[13.5839,144.9167],[19.28,166.62],[21.3694,-157.9622]], {{color:'#4FC3F7',weight:1.5,dashArray:'2 6',opacity:.4}}).addTo(map);
L.polyline([[13.5839,144.9167],[-7.31,72.41]], {{color:'#4FC3F7',weight:1.5,dashArray:'2 6',opacity:.4}}).addTo(map);

function applyFilter() {{
let shown = 0;
markers.forEach(m => {{
const s = m.site;
let show = false;
if (currentFilter === 'all') show = true;
else if (currentFilter === 't1') show = s.tier === 1;
else if (currentFilter === 't2') show = s.tier === 2;
else if (currentFilter === 't3') show = s.tier === 3;
else if (currentFilter === 't4') show = s.tier === 4;
else if (currentFilter === 'ace') show = s.ace_hub;
else if (currentFilter === 'ally') show = s.ally;
else if (currentFilter === 'sovereign') show = s.sovereign;
else if (currentFilter === 'fy24') show = s.fy24;
if (show) {{ map.addLayer(m.marker); shown++; }} else map.removeLayer(m.marker);
}});
document.getElementById('cnum').textContent = shown;
}}

document.querySelectorAll('.fbtn').forEach(btn => {{
btn.addEventListener('click', function() {{
document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
this.classList.add('active');
currentFilter = this.dataset.filter;
applyFilter();
}});
}});

document.querySelectorAll('.modebtn').forEach(btn => {{
btn.addEventListener('click', function() {{
document.querySelectorAll('.modebtn').forEach(b => b.classList.remove('active'));
this.classList.add('active');
colorMode = this.dataset.mode;
markers.forEach(m => m.marker.setIcon(markerIcon(m.site)));
}});
}});

map.on('click', () => {{ /* 点击地图空白处收起弹窗 */ }});
</script>
</body>
</html>"""

with open(MAP_HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Leaflet map saved: {MAP_HTML} ({n} sites)")

# ============================================================
# QGIS 工程（指向 v2 GeoJSON，按 Tier 分级渲染）
# ============================================================

tier_symbols = {
    1: ("230,81,0", "10"),   # 深橙，大符号
    2: ("79,195,247", "7"),
    3: ("156,204,101", "5"),
    4: ("255,167,38", "5"),
}
cats = "\n".join(
    f'          <category render="true" label="{TIER_INFO[t][0]}" value="{t}" symbol="{i}"/>'
    for i, t in enumerate(sorted(tier_symbols))
)
syms = "\n".join(
    f'          <symbol type="marker" name="{i}" alpha="1" clip_to_extent="1"><layer class="SimpleMarker" locked="0" enabled="1"><prop k="color" v="{rgb}"/><prop k="size" v="{sz}"/><prop k="outline_color" v="255,255,255"/><prop k="outline_style" v="{"dash" if t == 4 else "solid"}"/></layer></symbol>'
    for i, (t, (rgb, sz)) in enumerate(sorted(tier_symbols.items()))
)

qgs = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname="INDOPACOM Military Sites v2" version="3.34.0">
  <homePath path=""/>
  <title>INDOPACOM Military Sites P9 v2 - DTC 2026 Level 1</title>
  <autotransaction enabled="0"/>
  <evaluateDefaultValues enabled="0"/>
  <layer-tree-group>
    <layer-tree-layer name="INDOPACOM Sites v2" source="../indopacom_bases_v2.geojson|layername=INDOPACOM Military Bases" provider="ogr" id="indopacom_bases_v2_p9">
      <layer-tree-legend patch-size="0,0" name=""/>
    </layer-tree-layer>
  </layer-tree-group>
  <projectlayers>
    <maplayer name="INDOPACOM Sites v2" type="vector" maxScale="0" minScale="1e+8" geometry="Point" simplifyDrawingTol="1" simplifyMaxScale="1" refreshOnNotifyEnabled="0" autoRefreshEnabled="0" simplifyAlgorithm="0" simplifyLocal="1" styleCategories="AllStyleCategories" refreshOnNotifyMessage="" autoRefreshTime="0" hasScaleBasedVisibility="0" simplifyDrawingHints="1">
      <id>indopacom_bases_v2_p9</id>
      <datasource>./indopacom_bases_v2.geojson|layername=INDOPACOM Military Bases</datasource>
      <keywordList>
        <value></value>
      </keywordList>
      <layername>INDOPACOM Sites v2</layername>
      <srs>
        <spatialrefsys nativeFormat="Wkt">
          <wkt>GEOGCRS["WGS 84",DATUM["World Geodetic System 1984",ELLIPSOID["WGS 84",6378137,298.257223563]],CS[ellipsoidal,2],AXIS["Latitude",north],AXIS["Longitude",east],UNIT["degree",9.86808271708726e-18],ID["EPSG",4326]]</wkt>
          <proj4>+proj=longlat +datum=WGS84 +no_defs</proj4>
          <identifier>EPSG:4326</identifier>
          <description>WGS 84</description>
        </spatialrefsys>
      </srs>
      <provider>ogr</provider>
      <vectorjestimation type="base" inforeground="0" vertical="0"/>
      <renderer-v2 type="categorizedSymbol" attr="tier">
        <categories>
{cats}
        </categories>
        <symbols>
{syms}
        </symbols>
      </renderer-v2>
      <labeling type="simple">
        <settings>
          <text-style fontSize="7" fieldName="name"/>
        </settings>
      </labeling>
    </maplayer>
  </projectlayers>
  <mapcanvas>
    <settings>
      <extent xmin="60" xmax="-60" ymin="-25" ymax="72" maxalone="0"/>
      <rotation>0</rotation>
      <destCRS>EPSG:4326</destCRS>
    </settings>
  </mapcanvas>
</qgis>"""

with open(QGS_FILE, "w", encoding="utf-8") as f:
    f.write(qgs)
print(f"QGIS project saved: {QGS_FILE} (tier-categorized, v2 data)")

print(f"\nSummary: {n} entities | Tier1={t1} Tier2={t2} Tier3={t3} Tier4={t4} | "
      f"ally={n_ally} ace_hub={n_hub} fy24_matched={n_fy24}")
