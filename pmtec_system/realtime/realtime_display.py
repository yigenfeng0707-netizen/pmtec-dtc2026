"""
Real-time Display HTML Generator - WebSocket client + Leaflet dynamic updates.
Generates a single-file HTML with WebSocket connection, entity position
interpolation, and time-axis pause/replay controls.
"""

import json
import os
from typing import Optional
from config import OUTPUT_DIR


class RealtimeDisplay:
    """Generates real-time tactical display HTML with WebSocket client."""

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
  <button id="view-toggle" onclick="toggleView()">2D / 3D</button>
</div>
<div id="main">
  <div id="map-container">
    <div id="map"></div>
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
      <h3>Event Log (Live)</h3>
    </div>
    <div id="event-log"></div>
  </div>
</div>
<script>
var bases = __BASES__;
var wsUrl = "__WS_URL__";
var ws = null;
var map = L.map('map', {zoomControl: true}).setView([25, 140], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: 'PMTEC | DTC 2026 P0', maxZoom: 12
}).addTo(map);

var entityMarkers = {};
var trackMarkers = {};
var paused = false;
var speedMultiplier = 1.0;
var history = [];
var historyIdx = -1;
var maxHistory = 200;

function connectWS() {
  try {
    ws = new WebSocket(wsUrl);
  } catch(e) {
    setTimeout(connectWS, 3000);
    return;
  }
  ws.onopen = function() {
    document.getElementById('conn-dot').className = 'conn-dot dot-on';
  };
  ws.onclose = function() {
    document.getElementById('conn-dot').className = 'conn-dot dot-off';
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
  history.push(msg);
  if (history.length > maxHistory) history.shift();
  historyIdx = history.length - 1;
  updateStatus(msg);
}

function handleDelta(msg) {
  (msg.changed || []).forEach(function(e) { updateEntity(e); });
  (msg.added || []).forEach(function(e) { addEntity(e); });
  (msg.removed_ids || []).forEach(function(id) { removeEntity(id); });
  (msg.new_tracks || []).forEach(function(t) { addTrack(t); });
  (msg.new_events || []).forEach(function(ev) { addEvent(ev); });
  history.push(msg);
  if (history.length > maxHistory) history.shift();
  historyIdx = history.length - 1;
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
  } else {
    addEntity(e);
  }
}

function removeEntity(id) {
  if (entityMarkers[id]) {
    map.removeLayer(entityMarkers[id]);
    delete entityMarkers[id];
  }
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
}

function togglePause() {
  paused = !paused;
  document.getElementById('btn-pause').textContent = paused ? 'Resume' : 'Pause';
}

function stepBack() {
  if (historyIdx > 0) {
    historyIdx--;
    var snap = history[historyIdx];
    if (snap.type === 'full') handleFull(snap);
  }
}

function stepFwd() {
  if (historyIdx < history.length - 1) {
    historyIdx++;
    var snap = history[historyIdx];
    if (snap.type === 'full') handleFull(snap);
    else if (snap.type === 'delta') handleDelta(snap);
  }
}

function setSpeed(s) { speedMultiplier = s; }

function toggleView() {
  alert('3D view toggle - see three_d_display.html for 3D mode');
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
