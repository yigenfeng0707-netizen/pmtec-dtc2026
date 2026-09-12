#!/usr/bin/env python3
"""
P12-3: Real-time tactical map v2 — 67-entity layered live situation display.

Generates output/pmtec_realtime_map_v2.html, a self-contained Leaflet client that:
  - embeds the full 67-entity authoritative base database (CRS R47589 + FY2024)
  - renders Tier layers (1 core hub / 2 depth / 3 forward / 4 ally & EDCA)
    with per-branch coloring and an EDCA overlay
  - connects to the PMTEC RealtimeServer WebSocket (ws://localhost:8765)
  - supports P12-3 controls: pause / resume / replay (step-back) / live

Usage:
  python visualization/realtime_map_v2.py
  # then serve or open the file; start the sim (python main.py) and watch live
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(PROJECT_ROOT, "data", "bases_v2.geojson")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "pmtec_realtime_map_v2.html")

BRANCH_COLORS = {
    "usaf": "#58a6ff",
    "usn": "#79c0ff",
    "usmc": "#d29922",
    "army": "#3fb950",
    "ussf": "#bc8cff",
    "joint": "#e3b341",
    "sof": "#f85149",
    "other": "#8b949e",
}

TIER_META = {
    1: ("Tier-1 核心枢纽", "#ff7b72"),
    2: ("Tier-2 主要作战/纵深", "#ffa657"),
    3: ("Tier-3 前沿节点", "#d2a8ff"),
    4: ("Tier-4 盟友/EDCA/以远", "#7ee787"),
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PMTEC v2 实时态势图 — 67 实体分层 (P12-3)</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  html, body {{ margin: 0; height: 100%; font-family: 'Segoe UI','Microsoft YaHei',sans-serif; background: #0d1117; color: #c9d1d9; }}
  body {{ display: flex; flex-direction: column; overflow: hidden; }}
  #map {{ flex: 1; min-height: 0; }}
  #head {{ flex: none; background: #161b22; border-bottom: 1px solid #30363d; }}
  .hrow {{ display: flex; align-items: center; gap: 10px; padding: 5px 12px; flex-wrap: wrap; }}
  .hrow + .hrow {{ border-top: 1px solid #21262d; }}
  #brand {{ font-size: 13.5px; font-weight: 700; color: #58a6ff; letter-spacing: .5px; }}
  #ws {{ font-size: 12px; color: #f85149; }}
  #ws.ok {{ color: #3fb950; }}
  .kpi {{ background: #0d1117; border: 1px solid #30363d; border-radius: 7px;
    padding: 3px 10px; font-size: 11px; color: #8b949e; display: flex;
    align-items: baseline; gap: 5px; }}
  .kpi b {{ font-size: 15px; color: #3fb950; font-family: Consolas,monospace; }}
  .kpi.warn {{ border-color: #f0883e; }}
  .kpi.warn b {{ color: #f0883e; }}
  .btn {{ background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px;
    padding: 3px 9px; cursor: pointer; font-size: 12px; }}
  .btn:hover {{ border-color: #58a6ff; }}
  .btn.active {{ background: #1f6feb; color: #fff; }}
  .grp {{ display: flex; align-items: center; gap: 4px; }}
  .grplabel {{ font-size: 10.5px; color: #6e7681; margin-right: 2px; }}
  .spacer {{ flex: 1; }}
  #clock {{ font-family: Consolas,monospace; color: #79c0ff; font-size: 13px; }}
  .legend {{ background: #161b22e6; padding: 8px 12px; border-radius: 8px; font-size: 12px; line-height: 1.8; box-shadow: 0 1px 6px #0008; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }}
  .layer-chip {{ margin-right: 4px; }}
  @media (max-width: 760px) {{
    .hrow {{ gap: 6px; padding: 4px 8px; }}
    .kpi {{ padding: 2px 7px; }}
  }}
</style>
</head>
<body>
<div id="head">
  <div class="hrow">
    <span id="brand">PMTEC 实时态势 · 67 实体</span>
    <span id="ws">● 未连接</span>
    <span class="spacer"></span>
    <span id="clock">T+00:00:00</span>
  </div>
  <div class="hrow">
    <span class="kpi">实体 <b id="ent">-</b></span>
    <span class="kpi">航迹 <b id="trk">-</b></span>
    <span class="kpi">周期 <b id="cyc">-</b></span>
    <span class="kpi" id="vulnbox">脆弱度 <b id="vuln">-</b></span>
    <span class="spacer"></span>
    <span class="grp">
      <span class="grplabel">回放</span>
      <button class="btn" id="b-pause" title="暂停推送">⏸</button>
      <button class="btn" id="b-resume" title="恢复推送">▶</button>
      <button class="btn" id="b-back" title="回溯 5 周期">⏪5</button>
      <button class="btn" id="b-live" title="回到实时">⏭ 实时</button>
    </span>
    <span class="grp">
      <span class="grplabel">图层</span>
      <span id="tierToggles" class="grp"></span>
    </span>
  </div>
</div>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const BASES = {bases_json};
const TIERS = {tiers_json};
const BRANCH_COLORS = {branches_json};

const map = L.map('map', {{preferCanvas: true}}).setView([18, 145], 3);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution: 'Esri, HERE, Garmin, (c) OpenStreetMap contributors', maxZoom: 16}}).addTo(map);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{attribution: '', maxZoom: 16}}).addTo(map);

// ---- 分层渲染：Tier 图层组 + 军种着色 ----
const tierGroups = {{}}, branchGroups = {{}};
for (const t of Object.keys(TIERS)) tierGroups[t] = L.layerGroup().addTo(map);
const edcaGroup = L.layerGroup();

for (const b of BASES) {{
  const color = BRANCH_COLORS[b.branch] || BRANCH_COLORS.other;
  const marker = L.circleMarker([b.lat, b.lon], {{
    radius: b.tier === 1 ? 7 : b.tier === 2 ? 5.5 : 4.5,
    color: color, weight: 2, fillColor: TIERS[b.tier] ? TIERS[b.tier][1] : '#555',
    fillOpacity: 0.75,
  }});
  marker.bindPopup(
    `<b>${{b.name}}</b> (${{b.id}})<br>军种: ${{b.branch}} | 国家: ${{b.country}}<br>` +
    `Tier-${{b.tier}} ${{TIERS[b.tier] ? TIERS[b.tier][0] : ''}} | ACE Hub: ${{b.ace_hub ? '是' : '否'}}<br>` +
    `PRV 四分位: ${{b.prv_q || 'n/a'}} | 人员: ${{(b.personnel || 0).toLocaleString()}}`
  );
  marker.bindTooltip(b.id, {{direction: 'top'}});
  if (tierGroups[b.tier]) tierGroups[b.tier].addLayer(marker);
  if (b.edca) edcaGroup.addLayer(
    L.circleMarker([b.lat, b.lon], {{radius: 11, color: '#7ee787', weight: 1, fill: false, dashArray: '4 3'}})
  );
}}
edcaGroup.addTo(map);

// Tier 开关
const toggles = document.getElementById('tierToggles');
for (const t of Object.keys(TIERS)) {{
  const chip = document.createElement('button');
  chip.className = 'btn layer-chip active';
  chip.textContent = `T${{t}}`;
  chip.onclick = () => {{
    if (map.hasLayer(tierGroups[t])) {{ map.removeLayer(tierGroups[t]); chip.classList.remove('active'); }}
    else {{ tierGroups[t].addTo(map); chip.classList.add('active'); }}
  }};
  toggles.appendChild(chip);
}}
const edcaChip = document.createElement('button');
edcaChip.className = 'btn layer-chip active';
edcaChip.textContent = 'EDCA';
edcaChip.onclick = () => {{
  if (map.hasLayer(edcaGroup)) {{ map.removeLayer(edcaGroup); edcaChip.classList.remove('active'); }}
  else {{ edcaGroup.addTo(map); edcaChip.classList.add('active'); }}
}};
toggles.appendChild(edcaChip);

L.control.layers(null, tierGroups, {{collapsed: true}}).addTo(map);
L.control.legend ? null : null;
const legend = L.control({{position: 'bottomleft'}});
legend.onAdd = () => {{
  const div = L.DomUtil.create('div', 'legend');
  div.innerHTML = Object.entries(TIERS).map(([t, [label, c]]) =>
    `<span><span class="dot" style="background:${{c}}"></span>${{label}}</span>`).join('<br>') +
    '<br>' + Object.entries(BRANCH_COLORS).map(([b, c]) =>
    `<span><span class="dot" style="border-color:${{c}};background:transparent;border:2px solid ${{c}};width:8px;height:8px"></span>${{b.toUpperCase()}}</span>`).join(' ');
  return div;
}};
legend.addTo(map);

// ---- P12-3 WebSocket 实时通道 ----
const WS_URL = "ws://" + (location.hostname || "localhost") + ":8765";
let ws = null, paused = false;
const markerCache = new Map();

function connect() {{
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {{ const el = document.getElementById('ws'); el.textContent = '● 已连接 ' + WS_URL; el.className = 'ok'; }};
  ws.onclose = () => {{ const el = document.getElementById('ws'); el.textContent = '● 断开，2s 重连'; el.className = ''; setTimeout(connect, 2000); }};
  ws.onmessage = (ev) => {{
    const msg = JSON.parse(ev.data);
    if (msg.type === 'full' || msg.type === 'replay' || msg.type === 'delta') render(msg);
  }};
}}
function sendCmd(obj) {{ if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }}

function render(msg) {{
  document.getElementById('cyc').textContent = msg.asda_cycle ?? '-';
  document.getElementById('clock').textContent = msg.sim_time ?? '-';
  const vpct = msg.network_vulnerability != null ? (msg.network_vulnerability * 100).toFixed(1) + '%' : '-';
  document.getElementById('vuln').textContent = vpct;
  document.getElementById('vulnbox').className =
    'kpi' + (msg.network_vulnerability > .15 ? ' warn' : '');
  const ents = msg.entities;
  if (ents) {{
    const list = typeof ents === 'object' && !Array.isArray(ents) ? Object.values(ents) : ents;
    document.getElementById('ent').textContent = list.length;
    for (const e of list) {{
      if (!e.lat || !e.lon) continue;
      let m = markerCache.get(e.id);
      const isHostile = (e.kind || e.type || '').toLowerCase().includes('missile') || e.hostile;
      if (!m) {{
        m = L.circleMarker([e.lat, e.lon], {{
          radius: isHostile ? 5 : 4,
          color: isHostile ? '#f85149' : '#58a6ff', weight: 1.5,
          fillOpacity: 0.9, fillColor: isHostile ? '#f85149' : '#58a6ff',
        }}).addTo(map).bindTooltip(e.id);
        markerCache.set(e.id, m);
      }} else {{
        m.setLatLng([e.lat, e.lon]);
      }}
      if (e.status === 'destroyed') {{ m.setStyle({{color: '#6e7681', fillOpacity: 0.3}}); }}
    }}
  }}
  if (msg.total_tracks != null) document.getElementById('trk').textContent = msg.total_tracks;
  if (msg.type === 'replay') document.getElementById('cyc').textContent =
    (msg.asda_cycle ?? '-') + ' (回溯)';
}}

document.getElementById('b-pause').onclick = () => {{ paused = true; sendCmd({{cmd: 'pause'}}); }};
document.getElementById('b-resume').onclick = () => {{ paused = false; sendCmd({{cmd: 'resume'}}); }};
document.getElementById('b-back').onclick = () => {{
  const cur = parseInt(document.getElementById('cyc').textContent) || 0;
  sendCmd({{cmd: 'replay', cycle: Math.max(0, cur - 5)}});
}};
document.getElementById('b-live').onclick = () => {{ paused = false; sendCmd({{cmd: 'live'}}); }};

connect();
</script>
</body>
</html>"""


def load_bases() -> list:
    """Load the 67-entity v2 database into compact client-side records."""
    with open(DATA_PATH, encoding="utf-8") as f:
        gj = json.load(f)
    bases = []
    for ft in gj["features"]:
        p = ft["properties"]
        lon, lat = ft["geometry"]["coordinates"][:2]
        bases.append(
            {
                "id": p.get("id", ""),
                "name": p.get("name", ""),
                "branch": (p.get("branch", "") or "").lower().replace(" ", "_"),
                "country": p.get("country", ""),
                "tier": p.get("tier", 2),
                "ace_hub": bool(p.get("ace_hub", False)),
                "prv_q": p.get("fy24_prv_quartile"),
                "personnel": p.get("personnel", 0),
                "edca": "PH" in (p.get("id", "") or "") and "PH-" == p.get("id", "")[:3],
                "lat": lat,
                "lon": lon,
            }
        )
    return bases


def generate(output_path: str = OUTPUT_PATH) -> str:
    bases = load_bases()
    tiers_json = json.dumps({str(k): list(v) for k, v in TIER_META.items()},
                            ensure_ascii=False)
    html = HTML_TEMPLATE.format(
        bases_json=json.dumps(bases, ensure_ascii=False),
        tiers_json=tiers_json,
        branches_json=json.dumps(BRANCH_COLORS),
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[P12-3] Real-time map v2 generated: {output_path} ({len(bases)} bases)")
    return output_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else OUTPUT_PATH
    generate(out)
