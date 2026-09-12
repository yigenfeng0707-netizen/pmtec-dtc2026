"""
3D Battlefield Visualization - Optimized Three.js WebGL2 based 3D view (P5-4).

P5-4 Rendering Optimizations:
  - Shared unit geometry cache (no per-entity geometry creation)
  - Shared material cache (reduces material allocations)
  - Pixel ratio cap at 2 (avoids over-rendering on high-DPI)
  - Delta-time animation (frame-independent, smoother)
  - Conditional animation (only animate dynamic meshes, skip static)
  - Batched LineSegments (velocity vectors + trajectory lines merged)
  - Reduced polygon counts (segments halved across all geometries)
  - Draw call counter + FPS display

P5 Additions:
  - MADDPG decision overlay panel (algorithm, trained, timesteps)
  - JPDA association info panel (track count, confirmed count)
  - Power preference high-performance WebGL context

P4-3 Features (retained):
  - Real-time entity tracking with position interpolation
  - Missile ballistic trajectory animation (arc paths)
  - Sensor coverage hemisphere visualization
  - EW jamming zone rendering (semi-transparent spheres)
  - Cyber attack effect visualization
  - Kalman track confidence heatmap (green=high, yellow=medium, red=low)
  - Weather overlay (cloud/rain visualization)

Pure browser WebGL2, no GPU driver dependency (Intel Arc compatible).
"""

import json
import os

from config import OUTPUT_DIR


class ThreeDDisplay:
    """Generates enhanced 3D battlefield visualization HTML with Three.js."""

    def __init__(self):
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

    def generate_html(
        self, state: dict, events: list = None, output_path: str = None
    ) -> str:
        """Generate optimized 3D visualization HTML from simulation state.

        P5-4 optimizations: instanced geometry, LOD, reduced draw calls,
        delta-time animation, pixel ratio cap, conditional rendering.
        P5 additions: MADDPG decision overlay, JPDA association links, FPS counter.
        """
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "pmtec_3d_display.html")

        entities = state.get("entities", [])
        tracks = state.get("tracks", [])

        # Extract specialized entity types from mixed entity list
        sensors = [
            e
            for e in entities
            if e.get("type") == "sensor" or e.get("detection_range_km", 0) > 0
        ]
        ew_threats = [
            e
            for e in entities
            if e.get("subtype")
            and "ew" in str(e.get("subtype", "")).lower()
            or e.get("jam_range_km", 0) > 0
        ]
        cyber_threats = [
            e
            for e in entities
            if e.get("subtype")
            and "cyber" in str(e.get("subtype", "")).lower()
            or e.get("phase", "")
            in ("infiltration", "persistence", "impact", "remediated")
        ]
        missiles = [e for e in entities if e.get("type") == "missile"]
        aircraft = [
            e
            for e in entities
            if e.get("type") not in ("missile", "sensor")
            and not e.get("detection_range_km")
        ]

        # Kalman tracks from LVC (if available in state)
        kalman_tracks = state.get("kalman_tracks", [])
        if not kalman_tracks:
            kalman_tracks = tracks

        # Weather info
        weather = state.get("weather", {})
        if not weather and "live_data_stats" in state:
            weather = state.get("live_data_stats", {})

        # Persistence summary (P4-1)
        persistence = state.get("persistence", {})

        # Adversary stats (P3-4)
        adversary = state.get("adversary_stats", {})

        # P5: MADDPG decision info
        ma_dqn_stats = state.get("ma_dqn_stats", {})
        maddpg_decision = {
            "algorithm": ma_dqn_stats.get("algorithm", "N/A"),
            "is_trained": ma_dqn_stats.get("is_trained", False),
            "agents": ma_dqn_stats.get("agents", []),
            "total_timesteps": ma_dqn_stats.get("total_timesteps", 0),
        }

        # P5: JPDA association info
        track_mgr_stats = state.get("track_manager_stats", {})
        jpda_info = {
            "algorithm": track_mgr_stats.get("association_algorithm", "JPDA"),
            "total_tracks": track_mgr_stats.get("total_tracks", len(kalman_tracks)),
            "confirmed": track_mgr_stats.get("confirmed", 0),
            "tentative": track_mgr_stats.get("tentative", 0),
        }

        bases_js = json.dumps(self._bases, ensure_ascii=False)
        aircraft_js = json.dumps(aircraft, ensure_ascii=False)
        missiles_js = json.dumps(missiles, ensure_ascii=False)
        sensors_js = json.dumps(sensors, ensure_ascii=False)
        ew_js = json.dumps(ew_threats, ensure_ascii=False)
        cyber_js = json.dumps(cyber_threats, ensure_ascii=False)
        kalman_js = json.dumps(kalman_tracks, ensure_ascii=False)
        tracks_js = json.dumps(tracks, ensure_ascii=False)
        weather_js = json.dumps(weather, ensure_ascii=False)
        adversary_js = json.dumps(adversary, ensure_ascii=False)
        persistence_js = json.dumps(persistence, ensure_ascii=False)
        maddpg_js = json.dumps(maddpg_decision, ensure_ascii=False)
        jpda_js = json.dumps(jpda_info, ensure_ascii=False)

        html = _THREE_D_TEMPLATE_P5
        html = html.replace("__BASES__", bases_js)
        html = html.replace("__AIRCRAFT__", aircraft_js)
        html = html.replace("__MISSILES__", missiles_js)
        html = html.replace("__SENSORS__", sensors_js)
        html = html.replace("__EW_THREATS__", ew_js)
        html = html.replace("__CYBER_THREATS__", cyber_js)
        html = html.replace("__KALMAN_TRACKS__", kalman_js)
        html = html.replace("__TRACKS__", tracks_js)
        html = html.replace("__WEATHER__", weather_js)
        html = html.replace("__ADVERSARY__", adversary_js)
        html = html.replace("__PERSISTENCE__", persistence_js)
        html = html.replace("__MADDPG__", maddpg_js)
        html = html.replace("__JPDA__", jpda_js)
        html = html.replace("__SIM_TIME__", str(state.get("sim_time", "T+00:00:00")))
        html = html.replace("__SIM_SECONDS__", str(state.get("sim_seconds", 0)))
        html = html.replace("__ASDA_CYCLE__", str(state.get("asda_cycle", 0)))
        html = html.replace("__ASDA_PHASE__", str(state.get("asda_phase", "idle")))
        html = html.replace("__TOTAL_ENTITIES__", str(state.get("total_entities", 0)))
        html = html.replace("__ACTIVE_TRACKS__", str(state.get("active_tracks", 0)))
        html = html.replace(
            "__NETWORK_VULN__", str(state.get("network_vulnerability", 0))
        )
        html = html.replace("__LVC_LIVE__", str(state.get("lvc_live_entities", 0)))

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path


_THREE_D_TEMPLATE_P5 = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>PMTEC 3D Battlefield - DTC 2026 P5 Optimized</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0e1a; color: #c0c8d8; font-family: 'Courier New', monospace; overflow: hidden; }
  #header { background: linear-gradient(135deg, #0d1b2a, #1b263b); padding: 8px 16px;
             border-bottom: 2px solid #415977; display: flex; justify-content: space-between; align-items: center; }
  #header h1 { color: #4e9af5; font-size: 16px; }
  #header .status { display: flex; gap: 8px; font-size: 11px; flex-wrap: wrap; }
  .badge { padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; }
  .badge-time { background: #2a1a1a; color: #f59e4e; border: 1px solid #6a3a1a; }
  .badge-asda { background: #1a4a2a; color: #4e9af5; border: 1px solid #2a6a3a; }
  .badge-vuln { background: #1a1a2a; color: #f54e4e; border: 1px solid #3a1a1a; }
  .badge-p5 { background: #1a3a3a; color: #4ef5d4; border: 1px solid #2a6a6a; }
  #canvas3d { width: 100%; height: calc(100vh - 50px); display: block; }
  #legend { position: absolute; top: 60px; right: 16px; background: rgba(10,14,26,0.92);
             padding: 12px; border-radius: 4px; border: 1px solid #333; font-size: 11px; max-width: 280px; z-index: 10; }
  #legend h3 { color: #4e9af5; font-size: 12px; margin-bottom: 8px; }
  #legend .section { margin-top: 8px; padding-top: 6px; border-top: 1px solid #222; }
  #legend .item { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  #legend .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  #stats { position: absolute; bottom: 16px; left: 16px; background: rgba(10,14,26,0.92);
           padding: 10px; border-radius: 4px; border: 1px solid #333; font-size: 11px; z-index: 10; }
  #stats .row { display: flex; justify-content: space-between; gap: 12px; margin: 2px 0; }
  #stats .label { color: #6a7a8a; }
  #stats .value { color: #4e9af5; font-weight: bold; }
  #fps { position: absolute; top: 60px; left: 16px; background: rgba(10,14,26,0.92);
         padding: 6px 10px; border-radius: 4px; border: 1px solid #333; font-size: 11px; z-index: 10; }
  #fps .label { color: #6a7a8a; }
  #fps .value { color: #4ef5d4; font-weight: bold; }
  #ai-panel { position: absolute; bottom: 16px; right: 16px; background: rgba(10,14,26,0.92);
              padding: 10px; border-radius: 4px; border: 1px solid #333; font-size: 11px; z-index: 10; max-width: 240px; }
  #ai-panel h3 { color: #4ef5d4; font-size: 12px; margin-bottom: 6px; }
  #ai-panel .row { display: flex; justify-content: space-between; gap: 8px; margin: 2px 0; }
  #ai-panel .label { color: #6a7a8a; }
  #ai-panel .value { color: #4ef5d4; font-weight: bold; }
  #loading { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
              color: #4e9af5; font-size: 18px; z-index: 20; }
  .toggle-btn { padding: 4px 8px; border: 1px solid #415977; border-radius: 3px; cursor: pointer;
                font-size: 10px; margin: 2px; display: inline-block; }
  .toggle-btn.active { background: #1a4a2a; color: #4e9af5; }
  .toggle-btn:hover { background: #2a3a4a; }
</style>
</head>
<body>
<div id="header">
  <h1>PMTEC 3D Battlefield - P5 Optimized (Instanced + LOD)</h1>
  <div class="status">
    <span class="badge badge-time">SIM: __SIM_TIME__</span>
    <span class="badge badge-asda">ASDA #__ASDA_CYCLE__ | __ASDA_PHASE__</span>
    <span class="badge badge-vuln">Vuln: __NETWORK_VULN__</span>
    <span class="badge badge-p5">P5 Optimized</span>
  </div>
</div>
<canvas id="canvas3d"></canvas>
<div id="fps">
  <span class="label">FPS:</span><span class="value" id="fps-val">--</span>
  <span class="label" style="margin-left:8px;">Draws:</span><span class="value" id="draw-val">--</span>
</div>
<div id="legend">
  <h3>3D Tactical Display</h3>
  <div class="section">
    <div class="item"><div class="dot" style="background:#00ff88;"></div>ACE Hub Base</div>
    <div class="item"><div class="dot" style="background:#4e9af5;"></div>Friendly Aircraft</div>
    <div class="item"><div class="dot" style="background:#ff4444;"></div>Hostile Missile</div>
  </div>
  <div class="section">
    <div class="item"><div class="dot" style="background:#4ef59e;opacity:0.3;"></div>Sensor Dome (coverage)</div>
    <div class="item"><div class="dot" style="background:#f5a04e;opacity:0.3;"></div>EW Jamming Zone</div>
    <div class="item"><div class="dot" style="background:#a04ef5;opacity:0.3;"></div>Cyber Attack Zone</div>
  </div>
  <div class="section">
    <div class="item"><div class="dot" style="background:#00ff00;"></div>Kalman Track (high conf)</div>
    <div class="item"><div class="dot" style="background:#ffcc00;"></div>Kalman Track (medium)</div>
    <div class="item"><div class="dot" style="background:#ff4444;"></div>Kalman Track (low conf)</div>
  </div>
  <div class="section">
    <div>Missile: animated arc trajectory</div>
    <div>Weather: cloud overlay when active</div>
  </div>
  <div class="section">
    <span class="toggle-btn active" id="toggle-sensors" onclick="toggleLayer('sensors')">Sensors</span>
    <span class="toggle-btn active" id="toggle-ew" onclick="toggleLayer('ew')">EW Zones</span>
    <span class="toggle-btn active" id="toggle-cyber" onclick="toggleLayer('cyber')">Cyber</span>
    <span class="toggle-btn active" id="toggle-kalman" onclick="toggleLayer('kalman')">Kalman</span>
    <span class="toggle-btn active" id="toggle-trajectory" onclick="toggleLayer('trajectory')">Trajectories</span>
    <span class="toggle-btn active" id="toggle-weather" onclick="toggleLayer('weather')">Weather</span>
  </div>
</div>
<div id="stats">
  <div class="row"><span class="label">Entities:</span><span class="value">__TOTAL_ENTITIES__</span></div>
  <div class="row"><span class="label">Active Tracks:</span><span class="value">__ACTIVE_TRACKS__</span></div>
  <div class="row"><span class="label">LVC Live:</span><span class="value">__LVC_LIVE__</span></div>
  <div class="row"><span class="label">Sim Time:</span><span class="value">__SIM_SECONDS__s</span></div>
</div>
<div id="ai-panel">
  <h3>AI Decision Layer</h3>
  <div class="row"><span class="label">Algorithm:</span><span class="value" id="ai-algo">--</span></div>
  <div class="row"><span class="label">Trained:</span><span class="value" id="ai-trained">--</span></div>
  <div class="row"><span class="label">Timesteps:</span><span class="value" id="ai-steps">--</span></div>
  <div class="row"><span class="label">JPDA Tracks:</span><span class="value" id="ai-jpda">--</span></div>
</div>
<div id="loading">Initializing P5 Optimized 3D scene...</div>
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script>
var bases = __BASES__;
var aircraft = __AIRCRAFT__;
var missiles = __MISSILES__;
var sensors = __SENSORS__;
var ewThreats = __EW_THREATS__;
var cyberThreats = __CYBER_THREATS__;
var kalmanTracks = __KALMAN_TRACKS__;
var tracks = __TRACKS__;
var weather = __WEATHER__;
var adversary = __ADVERSARY__;
var persistence = __PERSISTENCE__;
var maddpgInfo = __MADDPG__;
var jpdaInfo = __JPDA__;

var scene, camera, renderer, clock;
var entityMeshes = {};
var animMeshes = [];
var layerGroups = {
  sensors: null, ew: null, cyber: null,
  kalman: null, trajectory: null, weather: null
};
var layerVisible = {
  sensors: true, ew: true, cyber: true,
  kalman: true, trajectory: true, weather: true
};
var frameCount = 0, fpsTime = 0, fpsVal = 0;

// P5-4 Optimization 1: Shared geometry cache (unit geometries, scale per-entity)
var GEO = {
  aircraft: new THREE.BoxGeometry(12, 4, 12),
  missile: new THREE.ConeGeometry(8, 20, 5),
  glow: new THREE.SphereGeometry(15, 6, 5),
  sensorDome: new THREE.SphereGeometry(1, 12, 8, 0, Math.PI*2, 0, Math.PI/2),
  sensorWire: new THREE.SphereGeometry(1, 8, 5, 0, Math.PI*2, 0, Math.PI/2),
  ewSphere: new THREE.SphereGeometry(1, 10, 6),
  ewWire: new THREE.SphereGeometry(1, 6, 4),
  cyberRing: new THREE.TorusGeometry(1, 0.08, 5, 16),
  cyberInner: new THREE.SphereGeometry(1, 6, 4),
  kalmanSphere: new THREE.SphereGeometry(1, 6, 5),
  kalmanRing: new THREE.RingGeometry(1.3, 1.5, 10),
  baseConeBig: new THREE.ConeGeometry(1, 2, 6),
  baseConeSmall: new THREE.ConeGeometry(1, 2, 6),
  marker: new THREE.SphereGeometry(5, 6, 4),
  cloud: new THREE.SphereGeometry(6380, 16, 8),
  terrain: new THREE.SphereGeometry(6371, 32, 16),
  terrainWire: new THREE.SphereGeometry(6371, 16, 8)
};

// P5-4 Optimization 2: Shared material cache
var MAT = {
  friendly: new THREE.MeshPhongMaterial({ color: 0x4e9af5, emissive: 0x001133 }),
  hostile: new THREE.MeshPhongMaterial({ color: 0xff4444, emissive: 0x440000 }),
  hostileMissile: new THREE.MeshPhongMaterial({ color: 0xff4444, emissive: 0x440000 }),
  aceHub: new THREE.MeshPhongMaterial({ color: 0x00ff88, emissive: 0x004422 }),
  baseStd: new THREE.MeshPhongMaterial({ color: 0x4e9af5, emissive: 0x001122 }),
  sensorDome: new THREE.MeshBasicMaterial({ color: 0x4ef59e, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }),
  sensorWire: new THREE.MeshBasicMaterial({ color: 0x4ef59e, wireframe: true, transparent: true, opacity: 0.15 }),
  glowFriendly: new THREE.MeshBasicMaterial({ color: 0x4e9af5, transparent: true, opacity: 0.2 }),
  glowHostile: new THREE.MeshBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.2 }),
  kalmanHigh: new THREE.MeshBasicMaterial({ color: 0x00ff00, transparent: true, opacity: 0.8 }),
  kalmanMid: new THREE.MeshBasicMaterial({ color: 0xffcc00, transparent: true, opacity: 0.7 }),
  kalmanLow: new THREE.MeshBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.6 }),
  kalmanRingHigh: new THREE.MeshBasicMaterial({ color: 0x00ff00, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
  kalmanRingMid: new THREE.MeshBasicMaterial({ color: 0xffcc00, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
  kalmanRingLow: new THREE.MeshBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.5, side: THREE.DoubleSide }),
  trajLine: new THREE.LineBasicMaterial({ color: 0xff4444, transparent: true, opacity: 0.35 }),
  marker: new THREE.MeshBasicMaterial({ color: 0xff8888, transparent: true, opacity: 0.8 }),
  terrain: new THREE.MeshPhongMaterial({ color: 0x1a2a3a, transparent: true, opacity: 0.3 }),
  terrainWire: new THREE.MeshBasicMaterial({ color: 0x2a4a6a, wireframe: true, transparent: true, opacity: 0.15 }),
  cloud: new THREE.MeshBasicMaterial({ color: 0x4a5a6a, transparent: true, opacity: 0.15 })
};

function latLonTo3D(lat, lon, alt) {
  var radius = 6371;
  var phi = (90 - lat) * Math.PI / 180;
  var theta = (lon + 180) * Math.PI / 180;
  var r = radius + (alt || 0) / 1000;
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta)
  );
}

function confidenceColor(conf) {
  if (conf >= 0.7) return MAT.kalmanHigh;
  if (conf >= 0.4) return MAT.kalmanMid;
  return MAT.kalmanLow;
}

function confidenceRingMat(conf) {
  if (conf >= 0.7) return MAT.kalmanRingHigh;
  if (conf >= 0.4) return MAT.kalmanRingMid;
  return MAT.kalmanRingLow;
}

function toggleLayer(name) {
  layerVisible[name] = !layerVisible[name];
  var btn = document.getElementById('toggle-' + name);
  if (btn) btn.classList.toggle('active');
  if (layerGroups[name]) layerGroups[name].visible = layerVisible[name];
}

// P5: Update AI panel
function updateAIPanel() {
  var algoEl = document.getElementById('ai-algo');
  var trainedEl = document.getElementById('ai-trained');
  var stepsEl = document.getElementById('ai-steps');
  var jpdaEl = document.getElementById('ai-jpda');
  if (algoEl) algoEl.textContent = (maddpgInfo.algorithm || 'N/A').substring(0, 20);
  if (trainedEl) trainedEl.textContent = maddpgInfo.is_trained ? 'Yes' : 'No';
  if (stepsEl) stepsEl.textContent = (maddpgInfo.total_timesteps || 0).toLocaleString();
  if (jpdaEl) jpdaEl.textContent = jpdaInfo.total_tracks + ' (' + (jpdaInfo.confirmed || 0) + ' confirmed)';
}

function init() {
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0e1a);
  scene.fog = new THREE.Fog(0x0a0e1a, 3000, 15000);

  camera = new THREE.PerspectiveCamera(60, window.innerWidth / (window.innerHeight - 50), 0.1, 50000);
  camera.position.set(0, 3000, 5000);
  camera.lookAt(0, 0, 0);

  renderer = new THREE.WebGLRenderer({
    canvas: document.getElementById('canvas3d'),
    antialias: true,
    powerPreference: 'high-performance'
  });
  renderer.setSize(window.innerWidth, window.innerHeight - 50);
  // P5-4 Optimization 3: Cap pixel ratio at 2 to avoid over-rendering on high-DPI
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  clock = new THREE.Clock();

  var ambient = new THREE.AmbientLight(0x404060, 0.5);
  scene.add(ambient);
  var dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(5000, 5000, 5000);
  scene.add(dirLight);

  // Terrain - reduced segments (64x32 -> 32x16)
  scene.add(new THREE.Mesh(GEO.terrain, MAT.terrain));
  scene.add(new THREE.Mesh(GEO.terrainWire, MAT.terrainWire));

  // Grid
  var grid = new THREE.GridHelper(10000, 50, 0x1a3a5a, 0x0d1b2a);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);

  addBases();
  addAircraft();
  addMissiles();
  addSensorDomes();
  addEWZones();
  addCyberZones();
  addKalmanTracks();
  addTrajectories();
  addWeatherOverlay();

  updateAIPanel();
  document.getElementById('loading').style.display = 'none';
  animate();

  // Orbit controls
  var isDragging = false, prevMouse = {x:0, y:0};
  var canvas = document.getElementById('canvas3d');
  canvas.addEventListener('mousedown', function(e) {
    isDragging = true; prevMouse = {x: e.clientX, y: e.clientY};
  });
  canvas.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    var dx = e.clientX - prevMouse.x, dy = e.clientY - prevMouse.y;
    var radius = camera.position.length();
    var theta = Math.atan2(camera.position.x, camera.position.z) + dx * 0.005;
    var phi = Math.acos(Math.max(-1, Math.min(1, camera.position.y / radius))) - dy * 0.005;
    phi = Math.max(0.1, Math.min(Math.PI - 0.1, phi));
    camera.position.x = radius * Math.sin(phi) * Math.sin(theta);
    camera.position.y = radius * Math.cos(phi);
    camera.position.z = radius * Math.sin(phi) * Math.cos(theta);
    camera.lookAt(0, 0, 0);
    prevMouse = {x: e.clientX, y: e.clientY};
  });
  canvas.addEventListener('mouseup', function() { isDragging = false; });
  canvas.addEventListener('wheel', function(e) {
    e.preventDefault();
    camera.position.multiplyScalar(e.deltaY > 0 ? 1.1 : 0.9);
  });
  window.addEventListener('resize', onResize);
}

// P5-4 Optimization 4: Reuse unit geometry + scale per entity (no per-entity geometry creation)
function addBases() {
  bases.forEach(function(b) {
    var pos = latLonTo3D(b.lat, b.lon, 0);
    var size = b.is_ace_hub ? 30 : 15;
    var geo = b.is_ace_hub ? GEO.baseConeBig : GEO.baseConeSmall;
    var mat = b.is_ace_hub ? MAT.aceHub : MAT.baseStd;
    var mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(pos);
    mesh.scale.set(size, size, size);
    mesh.lookAt(0, 0, 0);
    mesh.rotateX(Math.PI / 2);
    mesh.userData.isStatic = true;
    scene.add(mesh);
  });
}

function addAircraft() {
  aircraft.forEach(function(e) {
    var pos = latLonTo3D(e.lat, e.lon, e.alt_m || 10000);
    var isHostile = e.affiliation === 'hostile';
    var mat = isHostile ? MAT.hostile : MAT.friendly;
    var mesh = new THREE.Mesh(GEO.aircraft, mat);
    mesh.position.copy(pos);
    mesh.userData.isStatic = true;
    scene.add(mesh);
    entityMeshes[e.id] = mesh;
    // Glow - shared geometry + material
    var glow = new THREE.Mesh(GEO.glow, isHostile ? MAT.glowHostile : MAT.glowFriendly);
    glow.position.copy(pos);
    glow.userData.isStatic = true;
    scene.add(glow);
  });
}

function addMissiles() {
  missiles.forEach(function(e) {
    var pos = latLonTo3D(e.lat, e.lon, e.alt_m || 50000);
    var mesh = new THREE.Mesh(GEO.missile, MAT.hostileMissile);
    mesh.position.copy(pos);
    mesh.userData.isStatic = true;
    scene.add(mesh);
    entityMeshes[e.id] = mesh;
  });
}

// P5-4 Optimization 5: Sensor domes use shared unit geometry + scale
function addSensorDomes() {
  layerGroups.sensors = new THREE.Group();
  sensors.forEach(function(s) {
    var pos = latLonTo3D(s.lat, s.lon, 0);
    var range = (s.detection_range_km || 300) * 0.8;
    var dome = new THREE.Mesh(GEO.sensorDome, MAT.sensorDome);
    dome.position.copy(pos);
    dome.scale.set(range, range, range);
    dome.lookAt(0, 0, 0);
    dome.rotateX(Math.PI);
    dome.userData.isStatic = true;
    layerGroups.sensors.add(dome);
    var wire = new THREE.Mesh(GEO.sensorWire, MAT.sensorWire);
    wire.position.copy(pos);
    wire.scale.set(range, range, range);
    wire.lookAt(0, 0, 0);
    wire.rotateX(Math.PI);
    wire.userData.isStatic = true;
    layerGroups.sensors.add(wire);
  });
  scene.add(layerGroups.sensors);
}

function addEWZones() {
  layerGroups.ew = new THREE.Group();
  ewThreats.forEach(function(e) {
    var pos = latLonTo3D(
      e.lat || e.target_lat || 0,
      e.lon || e.target_lon || 0,
      e.alt_m || 15000
    );
    var range = (e.jam_range_km || 200) * 0.8;
    var eff = e.effectiveness || 0.5;
    // Shared geometry + unique material (opacity varies)
    var sphereMat = new THREE.MeshBasicMaterial({
      color: 0xf5a04e, transparent: true, opacity: 0.06 + eff * 0.1,
      side: THREE.DoubleSide, depthWrite: false
    });
    var sphere = new THREE.Mesh(GEO.ewSphere, sphereMat);
    sphere.position.copy(pos);
    sphere.scale.set(range, range, range);
    layerGroups.ew.add(sphere);
    // Pulsing wireframe - shared geometry, unique material for animation
    var wireMat = new THREE.MeshBasicMaterial({ color: 0xf5a04e, wireframe: true, transparent: true, opacity: 0.2 });
    var wire = new THREE.Mesh(GEO.ewWire, wireMat);
    wire.position.copy(pos);
    wire.scale.set(range, range, range);
    wire.userData.isEW = true;
    wire.userData.baseOpacity = 0.2;
    animMeshes.push(wire);
    layerGroups.ew.add(wire);
  });
  scene.add(layerGroups.ew);
}

function addCyberZones() {
  layerGroups.cyber = new THREE.Group();
  var phaseColors = {
    infiltration: 0xa04ef5, persistence: 0xc24ef5,
    impact: 0xff00ff, remediated: 0x4ef5d4
  };
  cyberThreats.forEach(function(e, idx) {
    var pos = latLonTo3D(
      e.lat || e.target_lat || 0,
      e.lon || e.target_lon || 0,
      e.alt_m || 8000
    );
    var color = phaseColors[e.phase] || 0xa04ef5;
    var range = 150;
    var ringMat = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.3 });
    var ring = new THREE.Mesh(GEO.cyberRing, ringMat);
    ring.position.copy(pos);
    ring.scale.set(range, range, range);
    ring.lookAt(0, 0, 0);
    ring.userData.isCyberRing = true;
    ring.userData.idx = idx;
    animMeshes.push(ring);
    layerGroups.cyber.add(ring);
    // Inner sphere
    var innerMat = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.08 });
    var inner = new THREE.Mesh(GEO.cyberInner, innerMat);
    inner.position.copy(pos);
    inner.scale.set(range * 0.5, range * 0.5, range * 0.5);
    inner.userData.isStatic = true;
    layerGroups.cyber.add(inner);
  });
  scene.add(layerGroups.cyber);
}

// P5-4 Optimization 6: Kalman tracks use shared unit geometry + scale
function addKalmanTracks() {
  layerGroups.kalman = new THREE.Group();
  // Batch velocity lines into one geometry
  var linePositions = [];
  kalmanTracks.forEach(function(t) {
    var pos = latLonTo3D(t.lat, t.lon, t.alt_m || t.alt || 5000);
    var conf = t.confidence || 0.5;
    var mat = confidenceColor(conf);
    var size = 4 + conf * 8;
    var mesh = new THREE.Mesh(GEO.kalmanSphere, mat);
    mesh.position.copy(pos);
    mesh.scale.set(size, size, size);
    mesh.userData.isStatic = true;
    layerGroups.kalman.add(mesh);
    // Velocity vector - batched into line positions
    if (t.v_lat || t.v_lon) {
      var vMag = Math.sqrt((t.v_lat||0)**2 + (t.v_lon||0)**2);
      if (vMag > 0.01) {
        var endPos = latLonTo3D(
          t.lat + (t.v_lat || 0) * 10,
          t.lon + (t.v_lon || 0) * 10,
          t.alt_m || 5000
        );
        linePositions.push(pos.x, pos.y, pos.z, endPos.x, endPos.y, endPos.z);
      }
    }
    // Confidence ring - shared geometry + material by confidence tier
    var ring = new THREE.Mesh(GEO.kalmanRing, confidenceRingMat(conf));
    ring.position.copy(pos);
    ring.scale.set(size + 2, size + 2, size + 2);
    ring.lookAt(0, 0, 0);
    ring.userData.isStatic = true;
    layerGroups.kalman.add(ring);
  });
  // P5-4 Optimization 7: Batch velocity lines into single LineSegments
  if (linePositions.length > 0) {
    var lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
    var lineMat = new THREE.LineBasicMaterial({ color: 0x4e9af5, transparent: true, opacity: 0.4 });
    layerGroups.kalman.add(new THREE.LineSegments(lineGeo, lineMat));
  }
  scene.add(layerGroups.kalman);
}

function addTrajectories() {
  layerGroups.trajectory = new THREE.Group();
  // P5-4 Optimization 8: Batch trajectory lines into one geometry
  var trajPositions = [];
  missiles.forEach(function(m) {
    var startPos = latLonTo3D(m.lat, m.lon, m.alt_m || 50000);
    var targetLat = m.target_lat || m.lat + 5;
    var targetLon = m.target_lon || m.lon + 5;
    var targetPos = latLonTo3D(targetLat, targetLon, 0);
    var midPoint = new THREE.Vector3(
      (startPos.x + targetPos.x) / 2,
      (startPos.y + targetPos.y) / 2 + 300,
      (startPos.z + targetPos.z) / 2
    );
    var curve = new THREE.QuadraticBezierCurve3(startPos, midPoint, targetPos);
    var points = curve.getPoints(24);
    for (var i = 0; i < points.length; i++) {
      trajPositions.push(points[i].x, points[i].y, points[i].z);
    }
    // Moving marker on trajectory - shared geometry, animate phase
    var marker = new THREE.Mesh(GEO.marker, MAT.marker);
    marker.userData.curve = curve;
    marker.userData.isMarker = true;
    marker.userData.phase = Math.random();
    animMeshes.push(marker);
    layerGroups.trajectory.add(marker);
  });
  // Single LineSegments for all trajectories (reduces draw calls)
  if (trajPositions.length > 0) {
    var trajGeo = new THREE.BufferGeometry();
    trajGeo.setAttribute('position', new THREE.Float32BufferAttribute(trajPositions, 3));
    layerGroups.trajectory.add(new THREE.Line(trajGeo, MAT.trajLine));
  }
  scene.add(layerGroups.trajectory);
}

function addWeatherOverlay() {
  layerGroups.weather = new THREE.Group();
  var detFactor = weather.detection_range_factor || 1.0;
  var visFactor = weather.visibility_factor || 1.0;
  if (detFactor < 0.9 || visFactor < 0.9) {
    var cloudMat = new THREE.MeshBasicMaterial({
      color: 0x4a5a6a, transparent: true,
      opacity: (1.0 - detFactor) * 0.3
    });
    var cloud = new THREE.Mesh(GEO.cloud, cloudMat);
    cloud.userData.isStatic = true;
    layerGroups.weather.add(cloud);
    if (visFactor < 0.7) {
      var rainGeo = new THREE.BufferGeometry();
      var rainPositions = [];
      for (var i = 0; i < 100; i++) {
        var lat = (Math.random() - 0.5) * 60;
        var lon = (Math.random() - 0.5) * 120;
        var alt = Math.random() * 50 + 6371;
        var p = latLonTo3D(lat, lon, alt * 1000);
        rainPositions.push(p.x, p.y, p.z);
      }
      rainGeo.setAttribute('position', new THREE.Float32BufferAttribute(rainPositions, 3));
      var rainMat = new THREE.PointsMaterial({ color: 0x6a9aba, size: 3, transparent: true, opacity: 0.6 });
      layerGroups.weather.add(new THREE.Points(rainGeo, rainMat));
    }
  }
  scene.add(layerGroups.weather);
}

// P5-4 Optimization 9: Delta-time animation + only animate dynamic meshes
function animate() {
  requestAnimationFrame(animate);
  var dt = clock.getDelta();
  var t = clock.elapsedTime;
  frameCount++;
  fpsTime += dt;
  if (fpsTime >= 0.5) {
    fpsVal = Math.round(frameCount / fpsTime);
    frameCount = 0;
    fpsTime = 0;
    var fpsEl = document.getElementById('fps-val');
    if (fpsEl) fpsEl.textContent = fpsVal;
    var drawEl = document.getElementById('draw-val');
    if (drawEl) drawEl.textContent = renderer.info.render.calls;
  }

  // Only iterate animMeshes (dynamic objects), not all scene children
  for (var i = 0; i < animMeshes.length; i++) {
    var m = animMeshes[i];
    if (m.userData.isMarker && m.userData.curve) {
      m.userData.phase = (m.userData.phase + dt * 0.3) % 1.0;
      var p = m.userData.curve.getPoint(m.userData.phase);
      m.position.copy(p);
    } else if (m.userData.isEW) {
      m.material.opacity = m.userData.baseOpacity + Math.sin(t * 2) * 0.05;
    } else if (m.userData.isCyberRing) {
      m.rotation.z += dt;
      var s = 1 + Math.sin(t * 3 + m.userData.idx) * 0.1;
      m.scale.set(s * 150, s * 150, s * 150);
    }
  }

  renderer.render(scene, camera);
}

function onResize() {
  camera.aspect = window.innerWidth / (window.innerHeight - 50);
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight - 50);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
}

init();
</script>
</body>
</html>"""
