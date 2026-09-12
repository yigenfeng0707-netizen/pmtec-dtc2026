"""
Tactical Display - Real-time HTML/JS visualization for PMTEC battlefield.
DTB Model: BattleNetwork (track display) + ApplicationStore (visualization app).
"""

import json
import os

from config import OUTPUT_DIR


class TacticalDisplay:
    """Generates an interactive HTML tactical display from simulation state."""

    def __init__(self, bases_geojson: str = None):
        self.bases_geojson = bases_geojson or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "bases.geojson",
        )
        self._bases: list[dict] = []
        self._load_bases()

    def _load_bases(self):
        if not os.path.exists(self.bases_geojson):
            return
        with open(self.bases_geojson, "r", encoding="utf-8") as f:
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
                    "region": props.get("region", ""),
                    "is_ace_hub": props.get("is_ace_hub", False),
                    "military_branch": props.get("military_branch", ""),
                }
            )

    def generate_html(
        self, state: dict, events: list = None, output_path: str = None
    ) -> str:
        """Generate the tactical display HTML."""
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "pmtec_tactical_display.html")

        entities = state.get("entities", [])
        tracks = state.get("tracks", [])
        sim_time = state.get("sim_time", "T+00:00:00")
        asda_cycle = state.get("asda_cycle", 0)
        asda_phase = state.get("asda_phase", "idle")
        net_vuln = state.get("network_vulnerability", 0)
        total_entities = state.get("total_entities", 0)
        total_tracks = len(tracks)

        entity_js = json.dumps(entities, ensure_ascii=False)
        track_js = json.dumps(tracks, ensure_ascii=False)
        bases_js = json.dumps(self._bases, ensure_ascii=False)
        events_js = json.dumps(events or [], ensure_ascii=False)

        html = _HTML_TEMPLATE
        html = html.replace("__ENTITIES__", entity_js)
        html = html.replace("__TRACKS__", track_js)
        html = html.replace("__BASES__", bases_js)
        html = html.replace("__EVENTS__", events_js)
        html = html.replace("__SIM_TIME__", str(sim_time))
        html = html.replace("__ASDA_CYCLE__", str(asda_cycle))
        html = html.replace("__ASDA_PHASE__", str(asda_phase))
        html = html.replace("__NET_VULN__", f"{net_vuln:.1%}")
        html = html.replace("__TOTAL_ENTITIES__", str(total_entities))
        html = html.replace("__TOTAL_TRACKS__", str(total_tracks))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path


_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>PMTEC Tactical Display - DTC 2026</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0e1a; color: #c0c8d8; font-family: 'Courier New', monospace; overflow: hidden; }
  #header { background: linear-gradient(135deg, #0d1b2a, #1b263b); padding: 10px 20px;
             border-bottom: 2px solid #415977; display: flex; justify-content: space-between; align-items: center; }
  #header h1 { color: #4e9af5; font-size: 18px; }
  #header .status { display: flex; gap: 20px; font-size: 13px; }
  .badge { padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; }
  .badge-asda { background: #1a4a2a; color: #4e9af5; border: 1px solid #2a6a3a; }
  .badge-time { background: #2a1a1a; color: #f59e4e; border: 1px solid #6a3a1a; }
  .badge-vuln { background: #2a1a1a; color: #f54e4e; border: 1px solid #6a2a2a; }
  #main { display: flex; height: calc(100vh - 50px); }
  #map-container { flex: 3; position: relative; }
  #map { width: 100%; height: 100%; }
  #sidebar { flex: 1; background: #0d1b2a; border-left: 2px solid #415977;
             display: flex; flex-direction: column; overflow: hidden; }
  .panel { padding: 10px; border-bottom: 1px solid #1b263b; }
  .panel h3 { color: #4e9af5; font-size: 13px; margin-bottom: 8px; text-transform: uppercase; }
  #event-log { flex: 1; overflow-y: auto; padding: 10px; }
  .event-item { padding: 4px 8px; margin: 2px 0; font-size: 11px;
                border-left: 3px solid #333; background: #111; }
  .event-item.deploy { border-color: #4e9af5; }
  .event-item.damage { border-color: #f54e4e; }
  .event-item.detect { border-color: #4ef59e; }
  .event-item.transfer { border-color: #f5e44e; }
  .event-item.missile_launch { border-color: #f54e4e; background: #1a0808; }
  .event-item.asda_cycle { border-color: #9e4ef5; }
  .event-item.recover { border-color: #4ef5d4; }
  #legend { position: absolute; bottom: 10px; left: 10px; background: rgba(10,14,26,0.9);
             padding: 8px 12px; border-radius: 4px; font-size: 11px; border: 1px solid #333; }
  .legend-item { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; }
  .dot-friendly { background: #4e9af5; }
  .dot-hostile { background: #f54e4e; }
  .dot-base { background: #4ef59e; border: 2px solid #2a6a3a; }
  .dot-track { background: #f5e44e; border: 1px dashed #999; }
  .leaflet-popup-content-wrapper { background: #0d1b2a; color: #c0c8d8;
             border: 1px solid #415977; }
  .leaflet-popup-tip { background: #0d1b2a; }
</style>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
</head>
<body>
<div id="header">
  <h1>PMTEC Digital Battlefield - DTC 2026 Level 3</h1>
  <div class="status">
    <span class="badge badge-time">SIM: __SIM_TIME__</span>
    <span class="badge badge-asda">ASDA Cycle __ASDA_CYCLE__ | Phase: __ASDA_PHASE__</span>
    <span class="badge badge-vuln">Net Vulnerability: __NET_VULN__</span>
    <span class="badge badge-asda">Entities: __TOTAL_ENTITIES__ | Tracks: __TOTAL_TRACKS__</span>
  </div>
</div>
<div id="main">
  <div id="map-container">
    <div id="map"></div>
    <div id="legend">
      <div class="legend-item"><div class="legend-dot dot-friendly"></div> Friendly Aircraft</div>
      <div class="legend-item"><div class="legend-dot dot-hostile"></div> Hostile Missile</div>
      <div class="legend-item"><div class="legend-dot dot-base"></div> Military Base</div>
      <div class="legend-item"><div class="legend-dot dot-track"></div> Sensor Track</div>
    </div>
  </div>
  <div id="sidebar">
    <div class="panel">
      <h3>DTB Model Services</h3>
      <div style="font-size:11px;line-height:1.6;">
        <div style="color:#4e9af5;">WarEngine</div><div>Simulation control, ASDA loop, SPEAR replay</div>
        <div style="color:#4e9af5;">BattleNetwork</div><div>gRPC track feed, entity status, network state</div>
        <div style="color:#4e9af5;">ApplicationStore</div><div>6 capability apps: strike, IAMD, ISR, ACE, SPEAR, JAD-AI</div>
        <div style="color:#4e9af5;">PlugAndPlay</div><div>4 components registered, service discovery</div>
      </div>
    </div>
    <div class="panel">
      <h3>LVC Architecture</h3>
      <div style="font-size:11px;line-height:1.6;">
        <div>Live: Sensors &amp; real data feeds</div>
        <div>Virtual: CGF aircraft &amp; missiles</div>
        <div>Constructive: ASDA command decisions</div>
      </div>
    </div>
    <div class="panel">
      <h3>Event Log</h3>
    </div>
    <div id="event-log"></div>
  </div>
</div>
<script>
var entities = __ENTITIES__;
var tracks = __TRACKS__;
var bases = __BASES__;
var events = __EVENTS__;

var map = L.map('map', {zoomControl: true}).setView([25, 140], 3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: 'PMTEC | DTC 2026',
  maxZoom: 12,
}).addTo(map);

bases.forEach(function(b) {
  var isHub = b.is_ace_hub;
  var marker = L.circleMarker([b.lat, b.lon], {
    radius: isHub ? 8 : 5,
    fillColor: '#4ef59e',
    fillOpacity: 0.6,
    color: '#2a6a3a',
    weight: 2,
  }).addTo(map);
  marker.bindPopup('<b>' + b.name + '</b><br>Region: ' + (b.region||'') +
    '<br>Branch: ' + (b.military_branch||'') +
    (isHub ? '<br><b style="color:#4e9af5;">ACE Hub</b>' : ''));
});

entities.forEach(function(e) {
  var color = e.affiliation === 'hostile' ? '#f54e4e' : '#4e9af5';
  var icon;
  if (e.type === 'missile') {
    icon = L.divIcon({html: '<div style="color:#f54e4e;font-size:16px;">&#x1F480;</div>',
      iconSize: [20, 20], className: ''});
  } else {
    icon = L.divIcon({html: '<div style="color:' + color + ';font-size:14px;">&#9992;</div>',
      iconSize: [20, 20], className: ''});
  }
  var m = L.marker([e.lat, e.lon], {icon: icon}).addTo(map);
  m.bindPopup('<b>' + e.id + '</b><br>Type: ' + e.subtype +
    '<br>Status: ' + e.status + '<br>Speed: ' + e.speed_kmh + ' km/h' +
    '<br>Base: ' + (e.base_id || 'N/A'));
});

tracks.forEach(function(t) {
  L.circleMarker([t.lat, t.lon], {
    radius: 4,
    fillColor: '#f5e44e',
    fillOpacity: 0.3,
    color: '#f5e44e',
    weight: 1,
    dashArray: '3,3',
  }).addTo(map).bindPopup('Track: ' + t.track_id +
    '<br>Confidence: ' + (t.confidence * 100).toFixed(0) + '%' +
    '<br>Classification: ' + t.classification);
});

var logEl = document.getElementById('event-log');
events.slice(-100).reverse().forEach(function(ev) {
  var div = document.createElement('div');
  div.className = 'event-item ' + (ev.event_type || '');
  var time = new Date(ev.timestamp * 1000).toLocaleTimeString();
  div.innerHTML = '<span style="color:#666;">' + time + '</span> ' +
    '<b style="color:#4e9af5;">' + (ev.event_type || '') + '</b> ' +
    (ev.description || '');
  logEl.appendChild(div);
});
</script>
</body>
</html>"""
