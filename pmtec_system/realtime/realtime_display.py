"""
Real-time Display HTML Generator - WebSocket client + Leaflet dynamic updates.
Generates a single-file HTML with WebSocket connection, entity position
interpolation, and time-axis pause/replay controls.
"""

import json
import os

from config import OUTPUT_DIR


class RealtimeDisplay:
    """Generates real-time tactical display HTML with WebSocket client."""

    # ws_host 是嵌入 HTML 的回退直拨地址（非监听地址）：本地开发 / SSH 隧道场景
    # 浏览器拨 ws://localhost:8765；公网部署时页面优先同源 /ws（nginx 反代），
    # 拨号失败自动轮换回退；监听侧见 websocket_server.py
    def __init__(self, ws_host: str = "localhost", ws_port: int = 8765):
        self.ws_host = ws_host
        self.ws_port = ws_port
        self._bases: list[dict] = []
        self._load_bases()

    def _load_bases(self):
        geojson_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "bases.geojson",
        )
        if not os.path.exists(geojson_path):
            return
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [0, 0])
            self._bases.append(
                {
                    "id": props.get("base_id", props.get("name", "")),
                    "name": props.get("name", ""),
                    "lat": coords[1] if len(coords) >= 2 else 0,
                    "lon": coords[0] if len(coords) >= 2 else 0,
                    "is_ace_hub": props.get("is_ace_hub", False),
                }
            )

    def generate_html(self, output_path: str = None) -> str:
        """Generate the real-time display HTML file."""
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "pmtec_realtime_display.html")

        bases_js = json.dumps(self._bases, ensure_ascii=False)
        ws_url = f"ws://{self.ws_host}:{self.ws_port}"

        html = _REALTIME_HTML_TEMPLATE
        html = html.replace("__WS_URL__", ws_url)
        html = html.replace("__BASES__", bases_js)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path


_REALTIME_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>PMTEC Real-time Tactical Display - DTC 2026</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0e1a; color: #c0c8d8; font-family: 'Courier New', monospace; overflow: hidden; }
  #header { background: linear-gradient(135deg, #0d1b2a, #1b263b); padding: 8px 16px;
             border-bottom: 2px solid #415977; display: flex; justify-content: space-between; align-items: center; }
  #header h1 { color: #4e9af5; font-size: 16px; }
  #header .status { display: flex; gap: 12px; font-size: 12px; }
  .badge { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }
  .badge-asda { background: #1a4a2a; color: #4e9af5; border: 1px solid #2a6a3a; }
  .badge-time { background: #2a1a1a; color: #f59e4e; border: 1px solid #6a3a1a; }
  .badge-vuln { background: #2a1a1a; color: #f54e4e; border: 1px solid #6a2a2a; }
  .badge-conn { background: #1a2a1a; color: #4ef59e; border: 1px solid #2a6a3a; }
  .badge-learn { background: #2a1a2a; color: #9e4ef5; border: 1px solid #4a2a6a; }
  #toolbar { background: #0d1b2a; padding: 6px 16px; border-bottom: 1px solid #1b263b;
              display: flex; gap: 10px; align-items: center; }
  #toolbar button { background: #1b263b; color: #4e9af5; border: 1px solid #415977;
                      padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
  #toolbar button:hover { background: #2b3650; }
  #toolbar .label { color: #666; font-size: 11px; margin-right: 4px; }
  #view-toggle { margin-left: auto; }
  #main { display: flex; height: calc(100vh - 80px); }
  #map-container { flex: 3; position: relative; }
  #map { width: 100%; height: 100%; }
  #view3d { position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            display: none; background: #0a0e17; z-index: 500; }
  #view3d canvas { display: block; }
  #view3d .hint { position: absolute; bottom: 10px; left: 12px; color: #484f58;
                  font-size: 11px; pointer-events: none; z-index: 5; }
  .hud-title { position: absolute; top: 14px; left: 0; right: 0; text-align: center;
               color: #aefeee; font-size: 15px; font-weight: bold; letter-spacing: 4px;
               pointer-events: none; z-index: 5; text-shadow: 0 0 12px rgba(46,196,182,.6); }
  .hud-title span { font-size: 9px; color: #415977; letter-spacing: 2px; }
  .hud-block { position: absolute; background: rgba(10,14,23,0.55); border: 1px solid #1e3a5f;
               border-radius: 4px; padding: 8px 12px; font-size: 11px; line-height: 1.9;
               pointer-events: none; z-index: 5; }
  .hud-block b { font-size: 12px; }
  .hud-tl { top: 52px; left: 16px; }
  .hud-tr { top: 52px; right: 16px; text-align: right; }
  .hud-corner { position: absolute; width: 26px; height: 26px; z-index: 5; pointer-events: none; }
  .c1 { top: 6px; left: 6px; border-top: 2px solid #2ec4b6; border-left: 2px solid #2ec4b6; }
  .c2 { top: 6px; right: 6px; border-top: 2px solid #2ec4b6; border-right: 2px solid #2ec4b6; }
  .c3 { bottom: 6px; left: 6px; border-bottom: 2px solid #2ec4b6; border-left: 2px solid #2ec4b6; }
  .c4 { bottom: 6px; right: 6px; border-bottom: 2px solid #2ec4b6; border-right: 2px solid #2ec4b6; }
  .hud-scan { position: absolute; inset: 0; pointer-events: none; z-index: 4;
              background: repeating-linear-gradient(0deg, transparent 0 3px,
                          rgba(46,196,182,0.016) 3px 4px); }
  .hud-kill-title { position: absolute; bottom: 46px; left: 16px; color: #415977;
                    font-size: 9px; letter-spacing: 2px; pointer-events: none; z-index: 6; }
  #killchain { position: absolute; bottom: 14px; left: 16px; right: 16px; display: flex;
               gap: 6px; overflow: hidden; pointer-events: none; z-index: 6; }
  .kc-chip { padding: 3px 10px; border-radius: 3px; font-size: 10px; white-space: nowrap;
             background: rgba(10,14,23,0.75); border-left: 3px solid; color: #c0c8d8;
             animation: kcin .4s ease, kcout 1s ease 13s forwards; }
  @keyframes kcin { from { opacity: 0; transform: translateX(-12px); } }
  @keyframes kcout { to { opacity: 0; } }
  #sidebar { flex: 1; background: #0d1b2a; border-left: 2px solid #415977;
              display: flex; flex-direction: column; overflow: hidden; }
  .panel { padding: 8px; border-bottom: 1px solid #1b263b; }
  .panel h3 { color: #4e9af5; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; }
  #event-log { flex: 1; overflow-y: auto; padding: 8px; }
  .event-item { padding: 3px 6px; margin: 2px 0; font-size: 10px;
                border-left: 3px solid #333; background: #111; }
  .event-item.deploy { border-color: #4e9af5; }
  .event-item.damage { border-color: #f54e4e; background: #1a0808; }
  .event-item.detect { border-color: #4ef59e; }
  .event-item.transfer { border-color: #f5e44e; }
  .event-item.missile_launch { border-color: #f54e4e; background: #1a0808; }
  .event-item.intercept_decision { border-color: #9e4ef5; }
  .event-item.recover { border-color: #4ef5d4; }
  .conn-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }
  .dot-on { background: #4ef59e; }
  .dot-off { background: #f54e4e; }
  #legend { position: absolute; bottom: 8px; left: 8px; background: rgba(10,14,26,0.9);
              padding: 6px 10px; border-radius: 4px; font-size: 10px; border: 1px solid #333; }
  .legend-item { display: flex; align-items: center; gap: 6px; margin: 2px 0; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; }
  .dot-friendly { background: #4e9af5; }
  .dot-hostile { background: #f54e4e; }
  .dot-base { background: #4ef59e; border: 2px solid #2a6a3a; }
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div id="header">
  <h1>PMTEC Real-time Battlefield - DTC 2026 P0 Upgrade</h1>
  <div class="status">
    <span class="badge badge-conn"><span class="conn-dot dot-off" id="conn-dot"></span>WS</span>
    <span class="badge badge-time">SIM: <span id="sim-time">--:--:--</span></span>
    <span class="badge badge-asda">ASDA #<span id="asda-cycle">0</span> | <span id="asda-phase">idle</span></span>
    <span class="badge badge-vuln">Vuln: <span id="net-vuln">0%</span></span>
    <span class="badge badge-asda">Ent: <span id="total-ent">0</span> | Trk: <span id="total-trk">0</span></span>
    <span class="badge badge-learn">Learn: <span id="learn-info">--</span></span>
  </div>
</div>
<div id="toolbar">
  <span class="label">Playback:</span>
  <button id="btn-pause" onclick="togglePause()">Pause</button>
  <button id="btn-step-back" onclick="stepBack()">&lt; Step</button>
  <button id="btn-step-fwd" onclick="stepFwd()">Step &gt;</button>
  <span class="label" style="margin-left:10px;">Speed:</span>
  <button onclick="setSpeed(0.5)">0.5x</button>
  <button onclick="setSpeed(1)">1x</button>
  <button onclick="setSpeed(2)">2x</button>
  <button onclick="setSpeed(4)">4x</button>
  <button id="view-toggle" onclick="cycleView()">切换 3D</button>
  <span class="label" style="margin-left:10px;">AI:</span>
  <button id="btn-ai" onclick="toggleAIPanel()">AI 参谋官</button>
  <a href="dt_dashboard.html" target="_blank" style="background:#1b263b;color:#2ec4b6;border:1px solid #2a6a3a;padding:4px 12px;border-radius:4px;font-size:12px;text-decoration:none;">孪生仪表盘</a>
</div>
<!-- P13: AI situational analysis panel -->
<div id="ai-panel" style="display:none; position:fixed; top:64px; right:16px; width:420px; max-height:70vh;
     overflow-y:auto; background:#0d1117; border:1px solid #4e9af5; border-radius:6px; z-index:9999;
     padding:12px; color:#c9d1d9; font-size:12px; line-height:1.6; box-shadow:0 4px 20px rgba(0,0,0,.6);">
  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
    <strong style="color:#4e9af5;">AI 参谋官态势分析</strong>
    <button onclick="toggleAIPanel()" style="padding:1px 6px;">x</button>
  </div>
  <div id="ai-meta" style="color:#8b949e; margin-bottom:6px;"></div>
  <div id="ai-content">点击"生成分析"基于当前仿真态势调用大模型。</div>
  <div style="margin-top:8px;">
    <button id="btn-ai-gen" onclick="generateAIAnalysis()">生成分析</button>
    <a id="btn-ai-docx" href="#" style="display:none;background:#2ec4b6;color:#0a0e17;
       padding:4px 12px;border-radius:4px;font-size:12px;text-decoration:none;
       font-weight:bold;margin-left:6px;" download>⬇ 导出 Word 报告</a>
    <span id="ai-status" style="color:#f5b84e;"></span>
  </div>
</div>
<div id="main">
  <div id="map-container">
    <div id="map"></div>
    <div id="view3d">
      <div class="hud-title">PMTEC 数字孪生作战中心<br><span>DIGITAL TWIN OPERATION CENTER · LVC LIVE FEED</span></div>
      <div class="hud-block hud-tl">
        <div>决策相位 <b id="hud-phase" style="color:#f5b84e;">IDLE</b></div>
        <div>ASDA 循环 <b id="hud-cycle" style="color:#4ef59e;">0</b></div>
        <div>仿真时间 <b id="hud-time" style="color:#4e9af5;">--:--</b></div>
      </div>
      <div class="hud-block hud-tr">
        <div>来袭导弹 <b id="hud-threat" style="color:#f54e4e;">0</b></div>
        <div>网络脆弱度 <b id="hud-vuln" style="color:#f54e4e;">0%</b></div>
        <div>实体 / 航迹 <b id="hud-ent" style="color:#4e9af5;">0 / 0</b></div>
      </div>
      <div class="hud-corner c1"></div><div class="hud-corner c2"></div>
      <div class="hud-corner c3"></div><div class="hud-corner c4"></div>
      <div class="hud-scan"></div>
      <div class="hud-kill-title">KILL CHAIN · 杀伤链实时流</div>
      <div id="killchain"></div>
      <div class="hint">拖拽旋转 · 滚轮缩放 · 绿柱=基地 红球+轨迹=来袭导弹 蓝锥=飞机 红圈=预测落点</div>
    </div>
    <div id="legend">
      <div class="legend-item"><div class="legend-dot dot-friendly"></div> Friendly</div>
      <div class="legend-item"><div class="legend-dot dot-hostile"></div> Hostile</div>
      <div class="legend-item"><div class="legend-dot dot-base"></div> Base</div>
    </div>
  </div>
  <div id="sidebar">
    <div class="panel">
      <h3>DTB Model + ASDA + LVC</h3>
      <div style="font-size:10px;line-height:1.5;">
        <div style="color:#4e9af5;">WarEngine</div><div>Real-time ASDA loop + learning</div>
        <div style="color:#4e9af5;">BattleNetwork</div><div>WebSocket track feed</div>
        <div style="color:#4e9af5;">ApplicationStore</div><div>6 capability apps</div>
        <div style="color:#4e9af5;">PlugAndPlay</div><div>Dynamic component registration</div>
        <div style="color:#9e4ef5;margin-top:4px;">Learning (P0-3)</div>
        <div>UCB1 intercept + Q-learning dispersal + sensor opt</div>
      </div>
    </div>
    <div class="panel">
      <h3 style="color:#2ec4b6;">数字孪生注册表 (DT Registry)</h3>
      <div style="font-size:10px;line-height:1.6;">
        <div>孪生体总数: <span id="twin-total" style="color:#2ec4b6;">0</span>
             | 保真度: <span id="twin-fidelity" style="color:#2ec4b6;">--</span></div>
        <div>基地孪生: <span id="twin-base">0</span>
             | 威胁孪生: <span id="twin-threat">0</span>
             | 场景: <span id="twin-scenario">0</span></div>
        <div>引擎同步次数: <span id="twin-syncs">0</span></div>
        <div id="twin-deviations" style="color:#f5b84e;"></div>
        <div id="twin-model" style="color:#8b949e;"></div>
      </div>
    </div>
    <div class="panel">
      <h3>Event Log (Live)</h3>
    </div>
    <div id="event-log"></div>
  </div>
</div>
<script>
var bases = __BASES__;
/* WS 候选端点轮换：同源 /ws（nginx 反代，公网部署）优先，回退直连 __WS_URL__
   （本地开发 / SSH 隧道场景）。onclose 时切换下一个候选并重连。 */
var WS_CANDIDATES = [];
if (location.protocol === 'http:' || location.protocol === 'https:') {
  WS_CANDIDATES.push((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
}
WS_CANDIDATES.push("__WS_URL__");
var wsIdx = 0;
var ws = null;
var map = L.map('map', {zoomControl: true}).setView([25, 140], 3);
L.tileLayer('tiles/{z}/{x}/{y}.png', {
  attribution: 'PMTEC | DTC 2026 P0 | © OpenStreetMap 离线瓦片', maxZoom: 12, maxNativeZoom: 7
}).addTo(map);

var entityMarkers = {};
var trackMarkers = {};
var paused = false;
var speedMultiplier = 1.0;
var replayHistory = [];
var historyIdx = -1;
var maxHistory = 200;

function nextWsCandidate() {
  wsIdx = (wsIdx + 1) % WS_CANDIDATES.length;
}

function connectWS() {
  var url = WS_CANDIDATES[wsIdx];
  try {
    ws = new WebSocket(url);
  } catch(e) {
    nextWsCandidate();
    setTimeout(connectWS, 3000);
    return;
  }
  ws.onopen = function() {
    document.getElementById('conn-dot').className = 'conn-dot dot-on';
  };
  ws.onclose = function() {
    document.getElementById('conn-dot').className = 'conn-dot dot-off';
    nextWsCandidate();
    setTimeout(connectWS, 2000);
  };
  ws.onerror = function() {};
  ws.onmessage = function(evt) {
    var msg = JSON.parse(evt.data);
    if (msg.type === 'full') handleFull(msg);
    else if (msg.type === 'delta') handleDelta(msg);
  };
}

function handleFull(msg) {
  for (var id in entityMarkers) {
    map.removeLayer(entityMarkers[id]);
    delete entityMarkers[id];
  }
  for (var id in trackMarkers) {
    map.removeLayer(trackMarkers[id]);
    delete trackMarkers[id];
  }
  var entities = Object.values(msg.entities || {});
  entities.forEach(function(e) { addEntity(e); });
  (msg.tracks || []).forEach(function(t) { addTrack(t); });
  (msg.events || []).forEach(function(ev) { addEvent(ev); });
  replayHistory.push(msg);
  if (replayHistory.length > maxHistory) replayHistory.shift();
  historyIdx = replayHistory.length - 1;
  updateStatus(msg);
}

function handleDelta(msg) {
  (msg.changed || []).forEach(function(e) { updateEntity(e); });
  (msg.added || []).forEach(function(e) { addEntity(e); });
  (msg.removed_ids || []).forEach(function(id) { removeEntity(id); });
  (msg.new_tracks || []).forEach(function(t) { addTrack(t); });
  (msg.new_events || []).forEach(function(ev) { addEvent(ev); });
  replayHistory.push(msg);
  if (replayHistory.length > maxHistory) replayHistory.shift();
  historyIdx = replayHistory.length - 1;
  updateStatus(msg);
}

function addEntity(e) {
  var color = e.affiliation === 'hostile' ? '#f54e4e' : '#4e9af5';
  var icon;
  if (e.type === 'missile') {
    icon = L.divIcon({html:'<div style="color:#f54e4e;font-size:14px;">\u26a0</div>',
      iconSize:[20,20], className:''});
  } else if (e.type === 'sensor') {
    icon = L.divIcon({html:'<div style="color:#4ef59e;font-size:12px;">\u25c8</div>',
      iconSize:[16,16], className:''});
  } else {
    icon = L.divIcon({html:'<div style="color:'+color+';font-size:12px;">\u2708</div>',
      iconSize:[20,20], className:''});
  }
  var m = L.marker([e.lat, e.lon], {icon:icon}).addTo(map);
  m.bindPopup('<b>'+e.id+'</b><br>Type: '+e.subtype+'<br>Status: '+e.status+
    '<br>Speed: '+e.speed_kmh+' km/h<br>Base: '+(e.base_id||'N/A'));
  entityMarkers[e.id] = m;
  sync3D(e);
}

function updateEntity(e) {
  var m = entityMarkers[e.id];
  if (m) {
    var latlng = m.getLatLng();
    var newLat = latlng.lat + (e.lat - latlng.lat) * speedMultiplier;
    var newLng = latlng.lng + (e.lon - latlng.lng) * speedMultiplier;
    m.setLatLng([newLat, newLng]);
    m.setPopupContent('<b>'+e.id+'</b><br>Type: '+e.subtype+'<br>Status: '+e.status+
      '<br>Speed: '+e.speed_kmh+' km/h<br>Base: '+(e.base_id||'N/A'));
    sync3D(e);
  } else {
    addEntity(e);
  }
}

function removeEntity(id) {
  if (entityMarkers[id]) {
    map.removeLayer(entityMarkers[id]);
    delete entityMarkers[id];
  }
  remove3D(id);
}

function addTrack(t) {
  var m = L.circleMarker([t.lat, t.lon], {
    radius:4, fillColor:'#f5e44e', fillOpacity:0.3,
    color:'#f5e44e', weight:1, dashArray:'3,3'
  }).addTo(map).bindPopup('Track: '+t.track_id+'<br>Conf: '+
    (t.confidence*100).toFixed(0)+'%<br>Class: '+t.classification);
  trackMarkers[t.track_id] = m;
}

function addEvent(ev) {
  var log = document.getElementById('event-log');
  var div = document.createElement('div');
  div.className = 'event-item ' + (ev.event_type || '');
  var time = new Date((ev.timestamp||0)*1000).toLocaleTimeString();
  div.innerHTML = '<span style="color:#666;">'+time+'</span> '+
    '<b style="color:#4e9af5;">'+(ev.event_type||'')+'</b> '+(ev.description||'');
  log.insertBefore(div, log.firstChild);
  while (log.children.length > 100) log.removeChild(log.lastChild);
  /* P13-3: kill-chain stream (command-center HUD) */
  var KC = {
    missile_launch: '#ff8844', detect: '#4ef59e', intercept_decision: '#f5b84e',
    intercept_success: '#2ec4b6', intercept_fail: '#f54e4e', c2_order: '#5aa7ff',
    c2_feedback: '#9e4ef5', damage: '#ff2222', twin_guided_decision: '#e6a8ff',
    political_access_change: '#ffd166',
  };
  var et = ev.event_type || '';
  if (KC[et]) {
    var kc = document.getElementById('killchain');
    if (kc) {
      var chip = document.createElement('div');
      chip.className = 'kc-chip';
      chip.style.borderLeftColor = KC[et];
      var desc = (ev.description || '').replace(/\s+/g, ' ');
      if (desc.length > 46) desc = desc.slice(0, 45) + '…';
      chip.innerHTML = '<b style="color:' + KC[et] + ';">' + et + '</b> ' + desc;
      kc.insertBefore(chip, kc.firstChild);
      while (kc.children.length > 14) kc.removeChild(kc.lastChild);
      setTimeout(function() { if (chip.parentNode) chip.parentNode.removeChild(chip); }, 14500);
    }
  }
}

function updateStatus(msg) {
  document.getElementById('sim-time').textContent = msg.sim_time || '--:--:--';
  document.getElementById('asda-cycle').textContent = msg.asda_cycle || 0;
  document.getElementById('asda-phase').textContent = msg.asda_phase || 'idle';
  document.getElementById('net-vuln').textContent =
    ((msg.network_vulnerability||0)*100).toFixed(1)+'%';
  document.getElementById('total-ent').textContent = msg.total_entities || 0;
  document.getElementById('total-trk').textContent = msg.total_tracks || 0;
  if (msg.learning) {
    document.getElementById('learn-info').textContent = msg.learning;
  }
  /* P13: command-center HUD */
  var hp = document.getElementById('hud-phase');
  if (hp) {
    hp.textContent = (msg.asda_phase || 'idle').toUpperCase();
    document.getElementById('hud-cycle').textContent = msg.asda_cycle || 0;
    document.getElementById('hud-time').textContent = msg.sim_time || '--:--';
    document.getElementById('hud-vuln').textContent =
      ((msg.network_vulnerability||0)*100).toFixed(1)+'%';
    document.getElementById('hud-ent').textContent =
      (msg.total_entities||0) + ' / ' + (msg.total_tracks||0);
  }
  /* P13: digital twin registry panel */
  var ts = msg.twin_summary;
  if (ts) {
    var threatN = (ts.by_kind && ts.by_kind.threat) || 0;
    var hth = document.getElementById('hud-threat');
    if (hth) hth.textContent = threatN;
    document.getElementById('twin-total').textContent = ts.total_twins || 0;
    document.getElementById('twin-fidelity').textContent =
      ((ts.avg_fidelity||0)*100).toFixed(1)+'%';
    document.getElementById('twin-base').textContent =
      (ts.by_kind && ts.by_kind.base) || 0;
    document.getElementById('twin-threat').textContent =
      (ts.by_kind && ts.by_kind.threat) || 0;
    document.getElementById('twin-scenario').textContent =
      (ts.by_kind && ts.by_kind.scenario) || 0;
    document.getElementById('twin-syncs').textContent = ts.engine_syncs || 0;
    var dv = ts.deviating_twins || [];
    document.getElementById('twin-deviations').textContent =
      dv.length ? ('偏差告警: ' + dv.map(function(d){return d.name+'('+d.deviation+')';}).join(', ')) : '';
    var im = ts.intercept_model || {};
    var parts = Object.keys(im).map(function(k){
      return k + ':P=' + (im[k].p*100).toFixed(0) + '%(n=' + im[k].n + ')';
    });
    document.getElementById('twin-model').textContent =
      parts.length ? ('拦截概率孪生模型: ' + parts.join(' | ')) : '';
  }
}

function togglePause() {
  paused = !paused;
  document.getElementById('btn-pause').textContent = paused ? 'Resume' : 'Pause';
}

/* ---------------- P13: AI situational analysis panel ---------------- */
/* REST 基址运行时解析：http(s) 页面走同源 /api/v1（nginx 反代，含会话 Cookie），
   file:// 本地浏览回退 localhost:8080。 */
var REST_BASE = (location.protocol === 'http:' || location.protocol === 'https:')
  ? location.origin + '/api/v1'
  : 'http://localhost:8080/api/v1';

function toggleAIPanel() {
  var p = document.getElementById('ai-panel');
  p.style.display = (p.style.display === 'none') ? 'block' : 'none';
  if (p.style.display === 'block') { loadAICache(); }
}

function renderAI(md) {
  var el = document.getElementById('ai-content');
  el.innerHTML = md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#f54e4e;">$1</strong>')
    .replace(/^### (.*)$/gm, '<h4 style="color:#4e9af5;margin:8px 0 2px;">$1</h4>')
    .replace(/^## (.*)$/gm, '<h3 style="color:#4e9af5;margin:10px 0 4px;border-bottom:1px solid #1b263b;">$1</h3>')
    .replace(/^# (.*)$/gm, '<h3 style="color:#4e9af5;">$1</h3>')
    .replace(/\n/g, '<br>');
}

function loadAICache() {
  fetch(REST_BASE + '/analysis').then(r => r.json()).then(d => {
    if (d.status === 'generated') {
      document.getElementById('ai-meta').textContent =
        d.model + ' | ' + d.generated_at;
      renderAI(d.markdown);
      if (d.docx_path) {
        var btn = document.getElementById('btn-ai-docx');
        btn.href = REST_BASE + '/analysis/download';
        btn.style.display = 'inline-block';
      }
    } else {
      document.getElementById('ai-content').textContent =
        '尚无分析结果，点击"生成分析"。';
    }
  }).catch(() => {
    document.getElementById('ai-content').textContent =
      'REST 网关不可达 (' + REST_BASE + ')。';
  });
}

function generateAIAnalysis() {
  var btn = document.getElementById('btn-ai-gen');
  var status = document.getElementById('ai-status');
  btn.disabled = true;
  status.textContent = ' 大模型分析中，约 40-60 秒...';
  fetch(REST_BASE + '/analysis', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'
  }).then(r => r.json()).then(d => {
    btn.disabled = false;
    status.textContent = '';
    if (d.status === 'generated') {
      document.getElementById('ai-meta').textContent = d.model + ' | ' + d.generated_at;
      renderAI(d.markdown);
      if (d.docx_path) {
        var docxBtn = document.getElementById('btn-ai-docx');
        docxBtn.href = REST_BASE + '/analysis/download';
        docxBtn.style.display = 'inline-block';
      }
    } else {
      status.textContent = ' 生成失败: ' + (d.error || 'unknown');
    }
  }).catch(e => {
    btn.disabled = false;
    status.textContent = ' 请求失败: ' + e;
  });
}
/* ---------------- end P13 AI panel ---------------- */

function stepBack() {
  if (historyIdx > 0) {
    historyIdx--;
    var snap = replayHistory[historyIdx];
    if (snap.type === 'full') handleFull(snap);
  }
}

function stepFwd() {
  if (historyIdx < replayHistory.length - 1) {
    historyIdx++;
    var snap = replayHistory[historyIdx];
    if (snap.type === 'full') handleFull(snap);
    else if (snap.type === 'delta') handleDelta(snap);
  }
}

function setSpeed(s) { speedMultiplier = s; }

/* ------------- P13-2/3: command-center 3D battlefield (Three.js) ------------- */
var view3dOn = false, renderer3d = null, scene3d = null, camera3d = null;
var objects3d = {}, twinGroup3d = null, missilePulse = {};
var trails3d = {}, targetLines3d = {}, baseLabelY = 0;
var globeMode = false, flatGroup3d = null, globeGroup3d = null;
var GLOBE_R = 170;

function latLonToGlobe(lat, lon, altM) {
  var la = THREE.MathUtils.degToRad(lat);
  var lo = THREE.MathUtils.degToRad(lon - 150);  // Indo-Pacific faces camera
  var r = GLOBE_R + (altM || 0) / 40000;
  return {
    x: r * Math.cos(la) * Math.sin(lo),
    y: r * Math.sin(la),
    z: r * Math.cos(la) * Math.cos(lo),
  };
}

function posOf(lat, lon, altM) {
  return globeMode ? latLonToGlobe(lat, lon, altM) : latLonToXYZ(lat, lon, altM);
}

function makeTextSprite(text, color, opts) {
  opts = opts || {};
  var canvas = document.createElement('canvas');
  canvas.width = 768; canvas.height = 160;
  var ctx = canvas.getContext('2d');
  if (!opts.plain) {
    ctx.fillStyle = 'rgba(10,14,23,0.6)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = color || '#7ffde8';
    ctx.lineWidth = 3;
    ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4);
  }
  ctx.font = 'bold 56px "Microsoft YaHei", sans-serif';
  ctx.fillStyle = color || '#7ffde8';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 384, 80);
  var tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  var mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
  var sp = new THREE.Sprite(mat);
  sp.renderOrder = 10;
  return sp;
}

function latLonToXYZ(lat, lon, altM) {
  return { x: (lon - 140) * 16, z: -(lat - 20) * 16, y: (altM || 0) / 4200 + 1 };
}

function disposeLine(ref, key) {
  var l = ref[key];
  if (l) {
    twinGroup3d.remove(l);
    if (l.geometry) l.geometry.dispose();
    if (l.material) l.material.dispose();
    delete ref[key];
  }
}

function init3D() {
  if (renderer3d) { onResize3D(); return; }
  if (typeof THREE === 'undefined') {
    document.getElementById('view3d').innerHTML =
      '<div style="padding:40px;color:#8b949e;">Three.js CDN 加载失败（需外网）。' +
      '可打开静态 <b>pmtec_3d_display.html</b> 查看 3D 终态。</div>';
    return;
  }
  var holder = document.getElementById('view3d');
  renderer3d = new THREE.WebGLRenderer({ antialias: true });
  renderer3d.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer3d.setSize(holder.clientWidth, holder.clientHeight);
  holder.insertBefore(renderer3d.domElement, holder.firstChild);
  scene3d = new THREE.Scene();
  scene3d.background = new THREE.Color(0x070b12);
  scene3d.fog = new THREE.Fog(0x070b12, 900, 2400);
  camera3d = new THREE.PerspectiveCamera(55, holder.clientWidth / holder.clientHeight, 0.1, 8000);
  camera3d.position.set(0, 300, 430);
  scene3d.add(new THREE.AmbientLight(0x505878, 1.3));
  var dl = new THREE.DirectionalLight(0xffffff, 0.85);
  dl.position.set(200, 500, 200);
  scene3d.add(dl);
  var grid = new THREE.GridHelper(2000, 56, 0x1e3a5f, 0x0f1c2e);
  grid.position.y = -0.5;
  scene3d.add(grid);
  // ---- mode groups: flat battlefield vs digital globe ----
  flatGroup3d = new THREE.Group();
  scene3d.add(flatGroup3d);
  globeGroup3d = new THREE.Group();
  globeGroup3d.visible = false;
  scene3d.add(globeGroup3d);
  // globe: occluder + wireframe + glow ring
  var occluder = new THREE.Mesh(
    new THREE.SphereGeometry(GLOBE_R - 1.2, 48, 32),
    new THREE.MeshBasicMaterial({ color: 0x0a1220 }));
  globeGroup3d.add(occluder);
  var wire = new THREE.Mesh(
    new THREE.SphereGeometry(GLOBE_R, 42, 28),
    new THREE.MeshBasicMaterial(
      { color: 0x1e3a5f, wireframe: true, transparent: true, opacity: 0.3 }));
  globeGroup3d.add(wire);
  var equator = new THREE.Mesh(
    new THREE.TorusGeometry(GLOBE_R + 0.6, 0.5, 8, 96),
    new THREE.MeshBasicMaterial({ color: 0x2ec4b6, transparent: true, opacity: 0.4 }));
  equator.rotation.x = Math.PI / 2;
  globeGroup3d.add(equator);
  // starfield
  var starGeo = new THREE.BufferGeometry();
  var starPos = [];
  for (var i = 0; i < 1200; i++) {
    starPos.push((Math.random()-0.5)*3600, 80+Math.random()*1100, (Math.random()-0.5)*3600);
  }
  starGeo.setAttribute('position', new THREE.Float32BufferAttribute(starPos, 3));
  scene3d.add(new THREE.Points(starGeo, new THREE.PointsMaterial(
    { color: 0x9db4dd, size: 1.8, sizeAttenuation: false, transparent: true, opacity: 0.75 })));
  // bases: pillars + glow ring + name sprites (staggered heights)
  var baseGeo = new THREE.CylinderGeometry(5, 6, 9, 14);
  var baseMat = new THREE.MeshLambertMaterial({ color: 0x2ec4b6, emissive: 0x0d3b38 });
  var edgeGeo = new THREE.EdgesGeometry(baseGeo);
  var edgeMat = new THREE.LineBasicMaterial({ color: 0x9ffff0 });
  var ringGeo = new THREE.RingGeometry(7, 8.2, 32);
  bases.forEach(function(b, idx) {
    var p = latLonToXYZ(b.lat, b.lon, 0);
    var mesh = new THREE.Mesh(baseGeo, baseMat);
    mesh.position.set(p.x, 4.5, p.z);
    flatGroup3d.add(mesh);
    var edges = new THREE.LineSegments(edgeGeo, edgeMat);
    edges.position.copy(mesh.position);
    flatGroup3d.add(edges);
    var ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial(
      { color: 0x2ec4b6, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(p.x, 0.4, p.z);
    flatGroup3d.add(ring);
    var labelY = 18 + (idx % 2) * 9;
    var label = makeTextSprite(b.name || b.id, '#aefeee');
    label.position.set(p.x, labelY, p.z);
    label.scale.set(60, 12.5, 1);
    flatGroup3d.add(label);
    // globe pin: cone oriented outward + label
    var gp = latLonToGlobe(b.lat, b.lon, 0);
    var n = new THREE.Vector3(gp.x, gp.y, gp.z).normalize();
    var pin = new THREE.Mesh(
      new THREE.ConeGeometry(2.6, 8, 10),
      new THREE.MeshBasicMaterial({ color: 0x2ec4b6 }));
    pin.position.copy(n.clone().multiplyScalar(GLOBE_R + 3));
    pin.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), n);
    globeGroup3d.add(pin);
    var glabel = makeTextSprite(b.name || b.id, '#aefeee');
    glabel.position.copy(n.clone().multiplyScalar(GLOBE_R + 16));
    glabel.scale.set(52, 10.8, 1);
    globeGroup3d.add(glabel);
  });
  twinGroup3d = new THREE.Group();
  scene3d.add(twinGroup3d);
  // drag-rotate / wheel-zoom
  var dragging = false, px = 0, py = 0, theta = 0, phi = 0.95, radius = 500;
  holder.onmousedown = function(ev) { dragging = true; px = ev.clientX; py = ev.clientY; };
  window.onmouseup = function() { dragging = false; };
  holder.onmousemove = function(ev) {
    if (!dragging) return;
    theta += (ev.clientX - px) * 0.005;
    phi = Math.max(0.12, Math.min(1.45, phi + (ev.clientY - py) * 0.004));
    px = ev.clientX; py = ev.clientY;
    camera3d.position.set(
      radius * Math.sin(phi) * Math.sin(theta),
      radius * Math.cos(phi),
      radius * Math.sin(phi) * Math.cos(theta));
    camera3d.lookAt(0, 0, 0);
  };
  holder.onwheel = function(ev) {
    radius = Math.max(90, Math.min(1800, radius + ev.deltaY * 0.4));
    camera3d.position.setLength(radius);
  };
  (function loop() {
    requestAnimationFrame(loop);
    if (view3dOn && renderer3d) {
      var t = Date.now() * 0.004;
      for (var id in missilePulse) {
        var s = 1 + 0.4 * Math.sin(t + missilePulse[id]);
        if (objects3d[id]) objects3d[id].scale.set(s, s, s);
      }
      twinGroup3d.children.forEach(function(ch) {
        if (ch.userData.pulse) {
          ch.material.opacity = 0.35 + 0.3 * Math.sin(t * 2);
        }
      });
      renderer3d.render(scene3d, camera3d);
    }
  })();
  onResize3D();
  window.addEventListener('resize', onResize3D);
}

function onResize3D() {
  var holder = document.getElementById('view3d');
  if (renderer3d && holder.clientWidth > 0) {
    renderer3d.setSize(holder.clientWidth, holder.clientHeight);
    camera3d.aspect = holder.clientWidth / holder.clientHeight;
    camera3d.updateProjectionMatrix();
  }
}

var lastEntities = {};

function applyMode() {
  if (flatGroup3d) flatGroup3d.visible = !globeMode;
  if (globeGroup3d) globeGroup3d.visible = globeMode;
  for (var id in lastEntities) sync3D(lastEntities[id]);
}

function sync3D(e) {
  if (!scene3d || !view3dOn) return;
  lastEntities[e.id] = e;
  var isMissile = e.type === 'missile';
  var o = objects3d[e.id];
  if (!o) {
    var mat, geo;
    if (isMissile) {
      geo = new THREE.SphereGeometry(4.6, 12, 12);
      mat = new THREE.MeshBasicMaterial({ color: 0xff4d4d });
    } else if (e.type === 'sensor') {
      geo = new THREE.OctahedronGeometry(4);
      mat = new THREE.MeshLambertMaterial({ color: 0x4ef59e });
    } else {
      geo = new THREE.ConeGeometry(3.6, 10, 8);
      mat = new THREE.MeshLambertMaterial({ color: 0x5aa7ff });
    }
    o = new THREE.Mesh(geo, mat);
    objects3d[e.id] = o;
    twinGroup3d.add(o);
    if (isMissile) {
      missilePulse[e.id] = Math.random() * 6.28;
      // trail line (stores geo coords, re-projected per mode)
      var trailGeo = new THREE.BufferGeometry();
      trailGeo.setAttribute('position',
        new THREE.Float32BufferAttribute(new Float32Array(90), 3));
      var trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial(
        { color: 0xff6b6b, transparent: true, opacity: 0.55 }));
      twinGroup3d.add(trail);
      trails3d[e.id] = { line: trail, pts: [] };
      if (e.target_lat != null) {
        // flat-mode target ring
        var tp0 = latLonToXYZ(e.target_lat, e.target_lon, 0);
        var ring = new THREE.Mesh(
          new THREE.RingGeometry(9, 11, 32),
          new THREE.MeshBasicMaterial(
            { color: 0xff4d4d, transparent: true, opacity: 0.5,
              side: THREE.DoubleSide }));
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(tp0.x, 0.8, tp0.z);
        ring.userData.pulse = true;
        twinGroup3d.add(ring);
        targetLines3d[e.id + '-ring'] = ring;
        // globe-mode target marker
        var tg = latLonToGlobe(e.target_lat, e.target_lon, 0);
        var gm = new THREE.Mesh(
          new THREE.SphereGeometry(4, 10, 10),
          new THREE.MeshBasicMaterial(
            { color: 0xff4d4d, transparent: true, opacity: 0.85 }));
        gm.position.set(tg.x, tg.y, tg.z);
        twinGroup3d.add(gm);
        targetLines3d[e.id + '-gmark'] = gm;
        // target line (arc in globe mode)
        var tlGeo = new THREE.BufferGeometry();
        tlGeo.setAttribute('position',
          new THREE.Float32BufferAttribute(new Float32Array(66), 3));
        var tl = new THREE.Line(tlGeo, new THREE.LineDashedMaterial(
          { color: 0xff8844, dashSize: 6, gapSize: 4,
            transparent: true, opacity: 0.6 }));
        twinGroup3d.add(tl);
        targetLines3d[e.id + '-line'] = tl;
        // threat label
        var lbl = makeTextSprite(
          '⚠ ' + (e.subtype || 'MISSILE'), '#ff9d9d', { plain: true });
        lbl.scale.set(54, 11, 1);
        twinGroup3d.add(lbl);
        targetLines3d[e.id + '-lbl'] = lbl;
      }
    }
  }
  var p = posOf(e.lat, e.lon, e.alt_m);
  o.position.set(p.x, p.y, p.z);
  if (isMissile) {
    // trail: store geo triples, re-project on every sync (mode-safe)
    var tr = trails3d[e.id];
    if (tr) {
      tr.pts.push([e.lat, e.lon, e.alt_m || 0]);
      if (tr.pts.length > 30) tr.pts = tr.pts.slice(-30);
      var flat = [];
      tr.pts.forEach(function(pt) {
        var q = posOf(pt[0], pt[1], pt[2]);
        flat.push(q.x, q.y, q.z);
      });
      tr.line.geometry.setAttribute('position',
        new THREE.Float32BufferAttribute(flat, 3));
    }
    if (e.target_lat != null) {
      var tl = targetLines3d[e.id + '-line'];
      if (tl) {
        var pts = [];
        if (globeMode) {
          // great-circle arc with altitude bump
          var a = new THREE.Vector3(p.x, p.y, p.z);
          var tp = latLonToGlobe(e.target_lat, e.target_lon, 0);
          var b = new THREE.Vector3(tp.x, tp.y, tp.z);
          for (var i = 0; i <= 21; i++) {
            var t = i / 21;
            var v = a.clone().lerp(b, t).normalize().multiplyScalar(
              GLOBE_R + 4 + 26 * Math.sin(Math.PI * t));
            pts.push(v.x, v.y, v.z);
          }
        } else {
          var tp = latLonToXYZ(e.target_lat, e.target_lon, 0);
          pts = [p.x, p.y, p.z, tp.x, 1, tp.z];
        }
        tl.geometry.setAttribute('position',
          new THREE.Float32BufferAttribute(pts, 3));
        tl.computeLineDistances();
      }
      var fring = targetLines3d[e.id + '-ring'];
      if (fring) fring.visible = !globeMode;
      var gmk = targetLines3d[e.id + '-gmark'];
      if (gmk) gmk.visible = globeMode;
      var lbl = targetLines3d[e.id + '-lbl'];
      if (lbl) {
        if (globeMode) {
          var n = new THREE.Vector3(p.x, p.y, p.z).normalize();
          lbl.position.set(p.x + n.x * 12, p.y + n.y * 12, p.z + n.z * 12);
        } else {
          lbl.position.set(p.x, p.y + 14, p.z);
        }
      }
    }
  }
}

function remove3D(id) {
  var o = objects3d[id];
  if (o && twinGroup3d) { twinGroup3d.remove(o); delete objects3d[id]; }
  disposeLine(trails3d, id);
  disposeLine(targetLines3d, id + '-ring');
  disposeLine(targetLines3d, id + '-gmark');
  disposeLine(targetLines3d, id + '-line');
  disposeLine(targetLines3d, id + '-lbl');
  delete missilePulse[id];
  delete lastEntities[id];
}

/* view cycle: 2D map -> 3D flat battlefield -> digital globe -> 2D */
function cycleView() {
  if (!view3dOn) {
    view3dOn = true;
    globeMode = false;
  } else if (!globeMode) {
    globeMode = true;
  } else {
    view3dOn = false;
    globeMode = false;
  }
  document.getElementById('map').style.display = view3dOn ? 'none' : 'block';
  var legend = document.getElementById('legend');
  if (legend) legend.style.display = view3dOn ? 'none' : 'block';
  var v3 = document.getElementById('view3d');
  v3.style.display = view3dOn ? 'block' : 'none';
  document.getElementById('view-toggle').textContent = view3dOn
    ? (globeMode ? '切换 2D' : '切换 地球')
    : '切换 3D';
  if (view3dOn) {
    init3D();
    applyMode();
    onResize3D();
  } else if (typeof map !== 'undefined' && map) {
    setTimeout(function(){ map.invalidateSize(); }, 50);
  }
}

bases.forEach(function(b) {
  var isHub = b.is_ace_hub;
  L.circleMarker([b.lat, b.lon], {
    radius: isHub ? 7 : 4, fillColor: '#4ef59e', fillOpacity: 0.5,
    color: '#2a6a3a', weight: 2
  }).addTo(map).bindPopup('<b>'+b.name+'</b>'+(isHub?'<br><b>ACE Hub</b>':''));
});

connectWS();
</script>
</body>
</html>"""
